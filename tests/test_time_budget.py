"""Tests for time budgets: a block or a run that takes too long is failed.

The clock is stopped in these tests and moved by hand, so "thirty minutes
later" costs nothing and means exactly that. The model of the case the
feature exists for is a block that keeps answering "still waiting" and routes
back to itself: something was handed off and the answer never comes.
"""

import fcntl
import json
import os
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
import yaml

from rein import time_budget as tb
from rein.orchestrator import ProcessManager
from rein.providers.base import UsageStats
from rein.state import ReinState
from rein.sweep import check_task, sweep
from rein.tasks import load_config

FLOW = "budget-flow"
T0 = 1_000_000.0

ON_ERROR_SCRIPT = """import json, os, sys
context = json.load(sys.stdin)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "errors.log"), "a") as f:
    f.write(json.dumps({"block": context["block_name"], "error": context["error"]}) + "\\n")
"""


class Clock:
    def __init__(self, now=T0):
        self.now = now

    def __call__(self):
        return self.now


class Stand:
    """One flow and one task of it, driven the way `rein --step` drives a task."""

    def __init__(self, tmp_path, blocks, **flow_extra):
        self.agents_dir = str(tmp_path / "agents")
        for sub in ("tasks", "specialists", "teams", "flows"):
            os.makedirs(os.path.join(self.agents_dir, sub))
        self.flow_dir = os.path.join(self.agents_dir, "flows", FLOW)
        os.makedirs(self.flow_dir)
        self.flow_path = os.path.join(self.flow_dir, f"{FLOW}.yaml")
        config = {"schema_version": "3.3.0", "name": FLOW, "team": "team-test", "on_error": "on_error.py"}
        config.update(flow_extra)
        config["blocks"] = blocks
        with open(self.flow_path, "w") as f:
            yaml.dump(config, f, sort_keys=False)
        with open(os.path.join(self.flow_dir, "on_error.py"), "w") as f:
            f.write(ON_ERROR_SCRIPT)
        with open(os.path.join(self.agents_dir, "teams", "team-test.yaml"), "w") as f:
            yaml.dump({"name": "team-test", "specialists": ["spec-a"], "collaboration_tone": "Be concise."}, f)
        with open(os.path.join(self.agents_dir, "specialists", "spec-a.md"), "w") as f:
            f.write("# spec-a\nYou are a test specialist.\n")

        self.task_dir = os.path.join(self.agents_dir, "tasks", "task-one")
        os.makedirs(os.path.join(self.task_dir, "input"))
        os.makedirs(os.path.join(self.task_dir, "state"))
        with open(os.path.join(self.task_dir, "input", "task.json"), "w") as f:
            json.dump({"id": "task-one", "flow": FLOW, "input": {}}, f)

        self.db_path = os.path.join(self.task_dir, "state", "rein.db")
        self.clock = Clock()
        self.answers = {}  # marker found in a block's prompt -> what the block answers
        self.calls = []  # prompts of the blocks that actually ran, in order
        self._fresh = True

    def _answer(self, *args, **kwargs):
        prompt = " ".join(str(a) for a in args) + " ".join(str(v) for v in kwargs.values())
        for marker, text in self.answers.items():
            if marker in prompt:
                self.calls.append(marker)
                return text, UsageStats()
        self.calls.append("?")
        return "ok", UsageStats()

    def manager(self):
        """A new engine instance on the task, as every `rein --step` call makes one."""
        m = ProcessManager(max_parallel=3, flow_name=FLOW, task_input={}, agents_dir=self.agents_dir)
        m.task_id = "task-one"
        m.task_dir = m.run_dir = self.task_dir
        m.log_dir = os.path.join(self.task_dir, "state")
        m.rein_log_file = os.path.join(self.task_dir, "state", "rein.log")
        m.db_path = self.db_path
        m.state = ReinState(self.db_path, resume=not self._fresh)
        self._fresh = False
        m._now = self.clock
        m._provider = MagicMock()
        m._provider.call.side_effect = self._answer
        m._provider.last_usage = UsageStats()
        with patch.object(m, "_init_provider"), patch.object(m, "_run_preflight_validation"):
            m.load_config(load_config(self.flow_path), workflow_file=self.flow_path)
        m.load_team = lambda name: "Be concise."
        return m

    def step(self, n=1):
        return self.manager().run_step(n)

    def rows(self):
        return ReinState(self.db_path, resume=True).budget_rows()

    def status(self, block):
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT status FROM processes WHERE name = ?", (block,)).fetchone()
        conn.close()
        return row[0] if row else None

    def errors(self):
        path = os.path.join(self.flow_dir, "errors.log")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]

    def events(self):
        path = os.path.join(self.task_dir, "state", "time_budget.json")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return json.load(f)

    def log(self):
        with open(os.path.join(self.task_dir, "state", "rein.log")) as f:
            return f.read()


def handoff_block(**extra):
    """A block that hands work off and answers 'waiting' until it is done."""
    block = {
        "name": "handoff",
        "specialist": "spec-a",
        "prompt": "HANDOFF",
        "depends_on": [],
        "max_runs": 9,
        "time_budget": "30m",
        "routing": {"waiting": "handoff"},
    }
    block.update(extra)
    return block


@pytest.fixture
def waiting(tmp_path):
    """A task whose only block has been handed off and keeps waiting."""
    stand = Stand(tmp_path, [handoff_block()])
    stand.answers["HANDOFF"] = "VERDICT: waiting"
    assert stand.step() is False
    return stand


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------


class TestParse:
    @pytest.mark.parametrize(
        "value, seconds",
        [(30, 30), ("45", 45), ("90s", 90), ("30m", 1800), ("2h", 7200), ("1d", 86400), (" 5 m ", 300), (None, None)],
    )
    def test_accepts(self, value, seconds):
        assert tb.parse_time_budget(value) == seconds

    @pytest.mark.parametrize("value", ["3x", "soon", "", "-5", -5, 0, "0m", True, 1.5, ["30m"], "31d", "1h30m"])
    def test_rejects(self, value):
        with pytest.raises(ValueError, match="time_budget"):
            tb.parse_time_budget(value)

    def test_error_names_the_block(self):
        with pytest.raises(ValueError, match=r"blocks\.draft\.time_budget"):
            tb.block_budgets([{"name": "draft", "time_budget": "3x"}])

    def test_run_has_no_budget_unless_it_asks_for_one(self):
        assert tb.run_budget({"schema_version": "3.3.0", "blocks": []}) is None
        assert tb.run_budget({"blocks": []}) is None

    def test_run_of_the_new_schema_version_gets_the_default(self):
        assert tb.run_budget({"schema_version": "3.4.0", "blocks": []}) == tb.DEFAULT_RUN_SECONDS
        assert tb.run_budget({"schema_version": "3.4.0", "time_budget": "2h", "blocks": []}) == 7200

    def test_a_flow_with_a_bad_value_does_not_load(self, tmp_path):
        stand = Stand(tmp_path, [handoff_block(time_budget="3x")])
        with pytest.raises(ValueError, match=r"blocks\.handoff\.time_budget"):
            stand.manager()


# ---------------------------------------------------------------------------
# When the clock of a block starts and stops
# ---------------------------------------------------------------------------


class TestAttempt:
    def test_clock_starts_when_the_block_first_runs(self, waiting):
        assert waiting.rows()["handoff"] == (T0, None)

    def test_routing_back_to_itself_does_not_restart_the_clock(self, waiting):
        waiting.clock.now = T0 + 600
        assert waiting.step() is False
        waiting.clock.now = T0 + 1200
        assert waiting.step() is False

        assert waiting.calls == ["HANDOFF", "HANDOFF", "HANDOFF"]
        assert waiting.rows()["handoff"] == (T0, None)

    def test_clock_is_gone_once_the_block_answers(self, waiting):
        waiting.answers["HANDOFF"] = "VERDICT: done"
        waiting.clock.now = T0 + 600
        assert waiting.step() is True

        assert "handoff" not in waiting.rows()
        waiting.clock.now = T0 + 99_999
        assert waiting.manager().enforce_time_budgets() is False
        assert waiting.events() == []

    def test_coming_back_from_another_block_starts_a_new_attempt(self, tmp_path):
        stand = Stand(
            tmp_path,
            [
                handoff_block(),
                {
                    "name": "review",
                    "specialist": "spec-a",
                    "prompt": "REVIEW",
                    "depends_on": ["handoff"],
                    "max_runs": 9,
                    "routing": {"revise": "handoff"},
                },
            ],
        )
        stand.answers["HANDOFF"] = "VERDICT: waiting"
        stand.step()  # handed off at T0
        stand.clock.now = T0 + 1500
        stand.answers["HANDOFF"] = "VERDICT: done"
        stand.step()  # answered after 25 minutes of a 30 minute budget
        stand.answers["REVIEW"] = "VERDICT: revise"
        stand.step()  # review sends it back
        stand.answers["HANDOFF"] = "VERDICT: waiting"
        stand.step()  # second attempt handed off

        assert stand.calls == ["HANDOFF", "HANDOFF", "REVIEW", "HANDOFF"]
        assert stand.rows()["handoff"] == (T0 + 1500, None)

        # 25 minutes into the second attempt, 50 minutes after the first hand-off:
        # still within the budget of this attempt.
        stand.clock.now = T0 + 3000
        assert stand.manager().enforce_time_budgets() is False
        assert stand.events() == []


# ---------------------------------------------------------------------------
# A block runs out of time
# ---------------------------------------------------------------------------


class TestBlockBudget:
    def test_nothing_happens_before_the_budget_is_used_up(self, waiting):
        waiting.clock.now = T0 + 1800
        assert waiting.manager().check_time_budgets() == "ok"
        assert waiting.events() == []
        assert waiting.errors() == []

    def test_block_fails_once_the_budget_is_exceeded(self, waiting):
        waiting.clock.now = T0 + 1801
        assert waiting.manager().check_time_budgets() == "expired"

        assert waiting.status("handoff") == "failed"
        assert [(e["scope"], e["block"], e["budget_seconds"]) for e in waiting.events()] == [("block", "handoff", 1800)]
        assert "TIME BUDGET EXCEEDED | block=handoff" in waiting.log()

    def test_error_handler_runs_exactly_once(self, waiting):
        waiting.clock.now = T0 + 1801
        waiting.manager().check_time_budgets()
        for later in (1900, 5000, 90_000):
            waiting.clock.now = T0 + later
            assert waiting.manager().check_time_budgets() == "ok"

        errors = waiting.errors()
        assert len(errors) == 1
        assert errors[0]["block"] == "handoff"
        assert "time budget exceeded" in errors[0]["error"]
        assert len(waiting.events()) == 1

    def test_a_step_checks_the_budget_before_it_runs_anything(self, waiting):
        waiting.clock.now = T0 + 1801
        waiting.manager()  # loading alone must not act
        assert waiting.errors() == []

        waiting.step()

        assert len(waiting.errors()) == 1
        assert len(waiting.events()) == 1

    def test_timeout_route_is_taken_and_the_block_is_not_run_again(self, tmp_path):
        stand = Stand(
            tmp_path,
            [
                handoff_block(routing={"waiting": "handoff", "timeout": "stopped", "_default": "finish"}),
                {"name": "finish", "specialist": "spec-a", "prompt": "FINISH", "depends_on": ["handoff"]},
                {"name": "stopped", "specialist": "spec-a", "prompt": "STOPPED", "depends_on": ["handoff"]},
            ],
        )
        stand.answers.update({"HANDOFF": "VERDICT: waiting", "STOPPED": "ok", "FINISH": "ok"})
        stand.step()
        stand.clock.now = T0 + 1801

        stand.step(0)

        assert stand.calls == ["HANDOFF", "STOPPED"]
        assert stand.status("handoff") == "done"
        assert stand.status("stopped") == "done"
        assert stand.status("finish") == "skipped"
        assert len(stand.errors()) == 1

    def test_fail_route_is_used_when_there_is_no_timeout_route(self, tmp_path):
        stand = Stand(
            tmp_path,
            [
                handoff_block(routing={"waiting": "handoff", "fail": "stopped", "_default": "finish"}),
                {"name": "finish", "specialist": "spec-a", "prompt": "FINISH", "depends_on": ["handoff"]},
                {"name": "stopped", "specialist": "spec-a", "prompt": "STOPPED", "depends_on": ["handoff"]},
            ],
        )
        stand.answers.update({"HANDOFF": "VERDICT: waiting", "STOPPED": "ok", "FINISH": "ok"})
        stand.step()
        stand.clock.now = T0 + 1801

        stand.step(0)

        assert stand.calls == ["HANDOFF", "STOPPED"]

    def test_result_that_arrives_after_the_budget_ran_out_is_ignored(self, tmp_path):
        stand = Stand(
            tmp_path,
            [
                handoff_block(routing={"timeout": "stopped", "_default": "finish"}),
                {"name": "finish", "specialist": "spec-a", "prompt": "FINISH", "depends_on": ["handoff"]},
                {"name": "stopped", "specialist": "spec-a", "prompt": "STOPPED", "depends_on": ["handoff"]},
            ],
        )
        engine = stand.manager()

        def slow_answer(*args, **kwargs):
            prompt = " ".join(str(a) for a in args) + " ".join(str(v) for v in kwargs.values())
            if "HANDOFF" in prompt:
                # The budget runs out while the block is still working.
                stand.clock.now = T0 + 1801
                engine.enforce_time_budgets()
                stand.calls.append("HANDOFF")
                return "VERDICT: done", UsageStats()
            stand.calls.append("STOPPED" if "STOPPED" in prompt else "FINISH")
            return "ok", UsageStats()

        engine._provider.call.side_effect = slow_answer
        engine.run_step(0)

        assert "LATE RESULT IGNORED | handoff" in stand.log()
        assert stand.calls == ["HANDOFF", "STOPPED"]
        assert stand.status("finish") == "skipped"


# ---------------------------------------------------------------------------
# The run as a whole runs out of time
# ---------------------------------------------------------------------------


class TestRunBudget:
    def test_run_clock_starts_once_and_is_never_restarted(self, tmp_path):
        stand = Stand(tmp_path, [handoff_block(time_budget=None)], time_budget="2h")
        stand.answers["HANDOFF"] = "VERDICT: waiting"
        stand.step()
        for later in (600, 1200, 1800):
            stand.clock.now = T0 + later
            stand.step()

        assert stand.rows()[tb.RUN_KEY] == (T0, None)

    def test_run_is_stopped_when_its_budget_is_exceeded(self, tmp_path):
        stand = Stand(tmp_path, [handoff_block(time_budget=None)], time_budget="2h")
        stand.answers["HANDOFF"] = "VERDICT: waiting"
        stand.step()
        stand.clock.now = T0 + 7201

        assert stand.step() is True

        assert stand.calls == ["HANDOFF"]  # nothing ran in the second step
        assert stand.status("handoff") == "failed"
        assert [(e["scope"], e["budget_seconds"]) for e in stand.events()] == [("run", 7200)]
        with open(os.path.join(stand.task_dir, "state", "status")) as f:
            assert f.read().strip() == "failed"
        assert [e["block"] for e in stand.errors()] == [""]

    def test_a_stopped_run_stays_stopped(self, tmp_path):
        stand = Stand(tmp_path, [handoff_block(time_budget=None)], time_budget="2h")
        stand.answers["HANDOFF"] = "VERDICT: waiting"
        stand.step()
        stand.clock.now = T0 + 7201
        stand.step()

        for later in (7300, 9000, 99_000):
            stand.clock.now = T0 + later
            assert stand.step() is True
            assert stand.manager().check_time_budgets() == "ok"

        assert stand.calls == ["HANDOFF"]
        assert stand.status("handoff") == "failed"
        assert len(stand.errors()) == 1
        assert len(stand.events()) == 1

    def test_block_budgets_reset_by_revision_loops_do_not_extend_the_run(self, tmp_path):
        stand = Stand(
            tmp_path,
            [
                handoff_block(),
                {
                    "name": "review",
                    "specialist": "spec-a",
                    "prompt": "REVIEW",
                    "depends_on": ["handoff"],
                    "max_runs": 9,
                    "routing": {"revise": "handoff"},
                },
            ],
            time_budget="1h",
        )
        stand.answers.update({"HANDOFF": "VERDICT: done", "REVIEW": "VERDICT: revise"})
        # Every attempt of the block takes 20 minutes, within its 30 minute
        # budget, and review keeps sending it back.
        for round_no in range(3):
            stand.clock.now = T0 + round_no * 1200
            stand.step()  # handoff
            stand.step()  # review -> back to handoff
        assert stand.events() == []

        stand.clock.now = T0 + 3601
        assert stand.step() is True
        assert [e["scope"] for e in stand.events()] == ["run"]


# ---------------------------------------------------------------------------
# State database
# ---------------------------------------------------------------------------


class TestState:
    def test_database_from_an_earlier_version_gains_the_table(self, tmp_path):
        db_path = str(tmp_path / "rein.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE processes (name TEXT PRIMARY KEY, status TEXT)")
        conn.commit()
        conn.close()

        state = ReinState(db_path, resume=True)

        assert state.budget_rows() == {}
        state.budget_start("a", 5.0)
        assert state.budget_rows() == {"a": (5.0, None)}

    def test_first_start_wins(self, tmp_path):
        state = ReinState(str(tmp_path / "rein.db"))
        state.budget_start("a", 5.0)
        state.budget_start("a", 9.0)
        assert state.budget_rows() == {"a": (5.0, None)}

    def test_expiry_is_claimed_by_one_caller_only(self, tmp_path):
        state = ReinState(str(tmp_path / "rein.db"))
        state.budget_start("a", 5.0)
        assert state.budget_claim_expiry("a", 50.0) is True
        assert state.budget_claim_expiry("a", 60.0) is False
        assert state.budget_rows() == {"a": (5.0, 50.0)}
        assert state.budget_claim_expiry("missing", 60.0) is False

    def test_a_fresh_run_starts_with_no_clocks(self, tmp_path):
        db_path = str(tmp_path / "rein.db")
        ReinState(db_path).budget_start("a", 5.0)
        assert ReinState(db_path, resume=False).budget_rows() == {}


# ---------------------------------------------------------------------------
# Sweep: tasks that no process is running
# ---------------------------------------------------------------------------


@pytest.fixture
def swept(waiting, monkeypatch):
    """The waiting task, with the engine's real flow loading allowed to run."""
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(ProcessManager, "_run_preflight_validation", lambda self, workflow_file: None)
    return waiting


class TestSweep:
    def test_task_within_budget_is_left_alone(self, swept):
        before = swept.log()
        assert check_task(swept.task_dir, swept.agents_dir, now=T0 + 1800) == "ok"
        assert swept.log() == before
        assert swept.status("handoff") == "waiting"

    def test_task_over_budget_is_failed_with_no_engine_running(self, swept):
        result = sweep(swept.agents_dir, log=lambda line: None, now=T0 + 1801)

        assert result["expired"] == ["task-one"]
        assert result["errors"] == []
        assert swept.status("handoff") == "failed"
        assert len(swept.errors()) == 1
        assert swept.calls == ["HANDOFF"]  # the sweep ran no block

    def test_second_sweep_changes_nothing(self, swept):
        sweep(swept.agents_dir, log=lambda line: None, now=T0 + 1801)
        result = sweep(swept.agents_dir, log=lambda line: None, now=T0 + 5000)

        assert result["expired"] == []
        assert result["ok"] == ["task-one"]
        assert len(swept.errors()) == 1
        assert len(swept.events()) == 1

    def test_task_held_by_a_running_engine_is_skipped(self, swept):
        lock_path = os.path.join(swept.task_dir, "state", "rein.lock")
        with open(lock_path, "w") as holder:
            fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = sweep(swept.agents_dir, log=lambda line: None, now=T0 + 1801)
            fcntl.flock(holder, fcntl.LOCK_UN)

        assert result["busy"] == ["task-one"]
        assert swept.status("handoff") == "waiting"
        assert swept.errors() == []

    def test_broken_task_is_reported_and_the_rest_are_still_checked(self, swept):
        tasks_root = os.path.join(swept.agents_dir, "tasks")
        for name in ("task-a-broken", "task-z-broken"):
            os.makedirs(os.path.join(tasks_root, name, "state"))
            os.makedirs(os.path.join(tasks_root, name, "input"))
            with open(os.path.join(tasks_root, name, "state", "rein.db"), "w") as f:
                f.write("this is not a database")
            with open(os.path.join(tasks_root, name, "input", "task.json"), "w") as f:
                json.dump({"flow": FLOW}, f)
        lines = []

        result = sweep(swept.agents_dir, log=lines.append, now=T0 + 1801)

        assert result["errors"] == ["task-a-broken", "task-z-broken"]
        assert result["expired"] == ["task-one"]
        assert any("task-a-broken" in line and "error" in line for line in lines)

    def test_task_from_before_time_budgets_is_not_touched(self, swept):
        conn = sqlite3.connect(swept.db_path)
        conn.execute("DROP TABLE time_budget")
        conn.commit()
        conn.close()

        assert check_task(swept.task_dir, swept.agents_dir, now=T0 + 99_999) == "ok"

        conn = sqlite3.connect(swept.db_path)
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        conn.close()
        assert "time_budget" not in tables

    def test_directory_that_is_not_a_started_task_is_skipped(self, swept):
        os.makedirs(os.path.join(swept.agents_dir, "tasks", "task-empty"))
        result = sweep(swept.agents_dir, log=lambda line: None, now=T0)
        assert result["skipped"] == ["task-empty"]


# ---------------------------------------------------------------------------
# Schema 3.4.0 through the real validator
# ---------------------------------------------------------------------------


def _write_flow(tmp_path, **overrides):
    config = {
        "schema_version": "3.4.0",
        "name": "budget-flow",
        "team": "team-test",
        "time_budget": "1d",
        "blocks": [{"name": "draft", "prompt": "write", "time_budget": "30m"}],
    }
    config.update(overrides)
    config = {key: value for key, value in config.items() if value is not None}
    path = tmp_path / "budget-flow.yaml"
    with open(path, "w") as f:
        yaml.dump(config, f, sort_keys=False)
    return path


class TestSchema:
    def test_validator_accepts_a_3_4_0_flow_with_time_budgets(self, tmp_path):
        from models.validator import ValidationEngine

        result = ValidationEngine().validate_workflow(_write_flow(tmp_path), cross_reference_check=False)

        assert result.is_valid, result.errors
        assert not [w for w in result.warnings if "Unknown schema version" in str(w)]

    def test_validator_accepts_seconds_as_a_number(self, tmp_path):
        from models.validator import ValidationEngine

        path = _write_flow(tmp_path, time_budget=3600, blocks=[{"name": "draft", "prompt": "write", "time_budget": 90}])
        assert ValidationEngine().validate_workflow(path, cross_reference_check=False).is_valid

    def test_validator_still_accepts_a_3_3_0_flow(self, tmp_path):
        from models.validator import ValidationEngine

        path = _write_flow(
            tmp_path, schema_version="3.3.0", time_budget=None, blocks=[{"name": "draft", "prompt": "w"}]
        )
        assert ValidationEngine().validate_workflow(path, cross_reference_check=False).is_valid

    @pytest.mark.parametrize("bad", [["30m"], {"minutes": 30}, 1.5])
    def test_validator_rejects_a_time_budget_of_the_wrong_type(self, tmp_path, bad):
        from models.validator import ValidationEngine

        path = _write_flow(tmp_path, blocks=[{"name": "draft", "prompt": "write", "time_budget": bad}])
        assert not ValidationEngine().validate_workflow(path, cross_reference_check=False).is_valid

    def test_registry_names_3_4_0_as_the_current_schema(self):
        from models.validator import ValidationEngine

        engine = ValidationEngine()
        assert engine.registry["current_version"] == "3.4.0"
        assert "3.4.0" in engine.registry["versions"]
        assert engine.check_version_compatibility("3.3.0")[0] is True

    def test_the_3_3_0_schema_file_is_left_as_it_was(self):
        schemas = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schemas")
        with open(os.path.join(schemas, "workflow-v3.3.0.json")) as f:
            old = json.load(f)
        with open(os.path.join(schemas, "workflow-v3.4.0.json")) as f:
            new = json.load(f)
        assert "time_budget" not in old["properties"]
        assert "time_budget" in new["properties"]
        assert "time_budget" in new["definitions"]["block"]["properties"]
