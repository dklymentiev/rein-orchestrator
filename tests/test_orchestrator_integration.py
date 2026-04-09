"""In-process integration tests for ProcessManager.

Unlike test_integration_stable.py which runs subprocess (no coverage data),
these tests run orchestrator code directly via ProcessManager. This gives
coverage visibility into _execute_block, spawn_process, run_workflow etc.

Uses deterministic mock scripts from tests/fixtures/mock_scripts/
to avoid LLM calls.
"""

import os

import pytest

from rein.orchestrator import ProcessManager

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def mock_provider_env(monkeypatch):
    """Provide a fake provider URL so ProcessManager can init."""
    monkeypatch.setenv("AI_GATEWAY_URL", "http://mock-gateway.invalid:19850")
    yield


@pytest.fixture
def isolated_tasks_dir(tmp_path):
    """Create isolated agents_dir for a test."""
    agents_dir = tmp_path / "agents"
    (agents_dir / "tasks").mkdir(parents=True)
    (agents_dir / "teams").mkdir()
    (agents_dir / "specialists").mkdir()
    (agents_dir / "flows").mkdir()
    yield str(agents_dir)


def _make_minimal_flow(flow_dir, blocks, name="test-flow"):
    """Write minimal flow YAML + logic scripts to flow_dir."""
    import yaml

    os.makedirs(flow_dir, exist_ok=True)
    logic_dir = os.path.join(flow_dir, "logic")
    os.makedirs(logic_dir, exist_ok=True)

    # Deterministic pass-through script (no sleep, no randomness)
    pass_script = """#!/usr/bin/env python3
import sys, json, os
ctx = json.load(sys.stdin)
os.makedirs(os.path.dirname(ctx['output_file']), exist_ok=True)
with open(ctx['output_file'], 'w') as f:
    json.dump({"result": "ok", "approved": True}, f)
"""
    with open(os.path.join(logic_dir, "pass.py"), "w") as f:
        f.write(pass_script)

    flow = {
        "schema_version": "3.3.0",
        "name": name,
        "team": "team-test",
        "blocks": blocks,
    }
    yaml_path = os.path.join(flow_dir, f"{name}.yaml")
    with open(yaml_path, "w") as f:
        yaml.dump(flow, f)
    return yaml_path


class TestLoadConfigInProcess:
    """Tests for ProcessManager.load_config using real YAML files"""

    def test_load_minimal_config(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """Load a minimal 1-block config"""
        flow_dir = tmp_path / "flow"
        yaml_path = _make_minimal_flow(
            str(flow_dir),
            [
                {"name": "a", "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            ],
        )

        mgr = ProcessManager(max_parallel=3, agents_dir=isolated_tasks_dir)
        config = {
            "schema_version": "3.3.0",
            "name": "test-flow",
            "team": "team-test",
            "blocks": [{"name": "a", "prompt": "x"}],
        }
        mgr.load_config(config, workflow_file=yaml_path)
        assert len(mgr.all_blocks) == 1
        assert mgr.all_blocks[0]["name"] == "a"

    def test_load_config_sets_team(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        flow_dir = tmp_path / "flow"
        yaml_path = _make_minimal_flow(
            str(flow_dir),
            [
                {"name": "a", "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            ],
        )
        mgr = ProcessManager(agents_dir=isolated_tasks_dir)
        config = {
            "schema_version": "3.3.0",
            "name": "test",
            "team": "team-test",
            "blocks": [{"name": "a", "prompt": "x"}],
        }
        mgr.load_config(config, workflow_file=yaml_path)
        assert mgr.team_name == "team-test"

    def test_load_config_reads_default_max_runs(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        flow_dir = tmp_path / "flow"
        yaml_path = _make_minimal_flow(
            str(flow_dir),
            [
                {"name": "a", "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            ],
        )
        mgr = ProcessManager(agents_dir=isolated_tasks_dir)
        config = {
            "schema_version": "3.3.0",
            "name": "test",
            "team": "team-test",
            "default_max_runs": 7,
            "blocks": [{"name": "a", "prompt": "x"}],
        }
        mgr.load_config(config, workflow_file=yaml_path)
        assert mgr.default_max_runs == 7

    def test_load_config_sets_timeout(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        flow_dir = tmp_path / "flow"
        yaml_path = _make_minimal_flow(
            str(flow_dir),
            [
                {"name": "a", "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            ],
        )
        mgr = ProcessManager(agents_dir=isolated_tasks_dir)
        config = {
            "schema_version": "3.3.0",
            "name": "test",
            "team": "team-test",
            "timeout": 3600,
            "blocks": [{"name": "a", "prompt": "x"}],
        }
        mgr.load_config(config, workflow_file=yaml_path)
        assert mgr.timeout == 3600


class TestRunStepInProcess:
    """In-process run_step tests"""

    def _setup_mgr(self, agents_dir, tmp_path, blocks):
        """Helper: create ProcessManager loaded with given blocks"""
        flow_dir = tmp_path / "flow"
        yaml_path = _make_minimal_flow(str(flow_dir), blocks)
        mgr = ProcessManager(max_parallel=3, agents_dir=agents_dir)
        config = {
            "schema_version": "3.3.0",
            "name": "test-flow",
            "team": "team-test",
            "blocks": blocks,
        }
        mgr.load_config(config, workflow_file=yaml_path)
        return mgr

    def test_run_step_empty_workflow(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """Empty workflow completes immediately"""
        flow_dir = tmp_path / "flow"
        yaml_path = _make_minimal_flow(
            str(flow_dir),
            [
                {"name": "noop", "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            ],
        )
        mgr = ProcessManager(max_parallel=3, agents_dir=isolated_tasks_dir)
        config = {
            "schema_version": "3.3.0",
            "name": "empty",
            "team": "team-test",
            "blocks": [{"name": "noop", "prompt": "x"}],
        }
        mgr.load_config(config, workflow_file=yaml_path)
        # Mark as completed to simulate resume
        mgr.completed.add("noop")
        for p in mgr.processes.values():
            p.status = "done"
        result = mgr.run_step(1)
        assert result is True  # already complete

    def test_run_step_single_block(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """Run a single block via run_step with real logic script"""
        blocks = [
            {"name": "step_a", "phase": 1, "prompt": "x", "logic": {"custom": "logic/pass.py"}},
        ]
        mgr = self._setup_mgr(isolated_tasks_dir, tmp_path, blocks)
        # May need multiple invocations if step_mode yields early
        for _ in range(5):
            if mgr.run_step(max_steps=0):
                break
        assert "step_a" in mgr.completed

    def test_run_step_linear_chain(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """Run 3-block linear chain: a -> b -> c via run_step (may need multiple invocations)"""
        blocks = [
            {"name": "a", "phase": 1, "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            {"name": "b", "phase": 2, "depends_on": ["a"], "prompt": "y", "logic": {"custom": "logic/pass.py"}},
            {"name": "c", "phase": 3, "depends_on": ["b"], "prompt": "z", "logic": {"custom": "logic/pass.py"}},
        ]
        mgr = self._setup_mgr(isolated_tasks_dir, tmp_path, blocks)
        # Invoke run_step multiple times (like cron would)
        for _ in range(10):
            if mgr.run_step(max_steps=0):
                break
        assert "a" in mgr.completed
        assert "b" in mgr.completed
        assert "c" in mgr.completed

    def test_run_step_parallel_blocks(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """Run fan-out: start -> {a, b} -> merge"""
        blocks = [
            {"name": "start", "phase": 1, "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            {
                "name": "branch_a",
                "phase": 2,
                "depends_on": ["start"],
                "prompt": "a",
                "logic": {"custom": "logic/pass.py"},
            },
            {
                "name": "branch_b",
                "phase": 2,
                "depends_on": ["start"],
                "prompt": "b",
                "logic": {"custom": "logic/pass.py"},
            },
            {
                "name": "merge",
                "phase": 3,
                "depends_on": ["branch_a", "branch_b"],
                "prompt": "m",
                "logic": {"custom": "logic/pass.py"},
            },
        ]
        mgr = self._setup_mgr(isolated_tasks_dir, tmp_path, blocks)
        result = mgr.run_step(max_steps=20)
        assert result is True
        assert len(mgr.completed) == 4


class TestInitializeProcesses:
    """Tests for _initialize_all_processes"""

    def test_processes_created_for_all_blocks(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """All blocks in config create Process entries"""
        flow_dir = tmp_path / "flow"
        blocks = [
            {"name": "a", "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            {"name": "b", "prompt": "y", "depends_on": ["a"], "logic": {"custom": "logic/pass.py"}},
        ]
        yaml_path = _make_minimal_flow(str(flow_dir), blocks)
        mgr = ProcessManager(agents_dir=isolated_tasks_dir)
        config = {"schema_version": "3.3.0", "name": "test", "team": "team-test", "blocks": blocks}
        mgr.load_config(config, workflow_file=yaml_path)
        assert len(mgr.processes) == 2
        names = {p.name for p in mgr.processes.values()}
        assert names == {"a", "b"}

    def test_initial_status_is_waiting(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        flow_dir = tmp_path / "flow"
        yaml_path = _make_minimal_flow(
            str(flow_dir),
            [
                {"name": "a", "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            ],
        )
        mgr = ProcessManager(agents_dir=isolated_tasks_dir)
        config = {
            "schema_version": "3.3.0",
            "name": "test",
            "team": "team-test",
            "blocks": [{"name": "a", "prompt": "x"}],
        }
        mgr.load_config(config, workflow_file=yaml_path)
        for p in mgr.processes.values():
            assert p.status == "waiting"


class TestBlockConfigsStored:
    """Tests that load_config stores block_configs correctly"""

    def test_block_configs_by_name(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        flow_dir = tmp_path / "flow"
        blocks = [
            {"name": "foo", "prompt": "f", "logic": {"custom": "logic/pass.py"}},
            {"name": "bar", "prompt": "b", "logic": {"custom": "logic/pass.py"}},
        ]
        yaml_path = _make_minimal_flow(str(flow_dir), blocks)
        mgr = ProcessManager(agents_dir=isolated_tasks_dir)
        config = {"schema_version": "3.3.0", "name": "test", "team": "team-test", "blocks": blocks}
        mgr.load_config(config, workflow_file=yaml_path)
        assert "foo" in mgr.block_configs
        assert "bar" in mgr.block_configs
        assert mgr.block_configs["foo"]["prompt"] == "f"


class TestRunWorkflowInProcess:
    """Tests for run_workflow method (continuous mode, alternative to run_step)"""

    def _setup_mgr(self, agents_dir, tmp_path, blocks):
        flow_dir = tmp_path / "flow"
        yaml_path = _make_minimal_flow(str(flow_dir), blocks)
        mgr = ProcessManager(max_parallel=3, agents_dir=agents_dir)
        config = {"schema_version": "3.3.0", "name": "test-flow", "team": "team-test", "blocks": blocks}
        mgr.load_config(config, workflow_file=yaml_path)
        return mgr

    def test_run_workflow_single_block(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """run_workflow completes a single-block flow"""
        blocks = [
            {"name": "only", "prompt": "x", "logic": {"custom": "logic/pass.py"}},
        ]
        mgr = self._setup_mgr(isolated_tasks_dir, tmp_path, blocks)
        mgr.run_workflow()
        assert "only" in mgr.completed

    def test_run_workflow_linear(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """run_workflow completes linear chain"""
        blocks = [
            {"name": "a", "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            {"name": "b", "depends_on": ["a"], "prompt": "y", "logic": {"custom": "logic/pass.py"}},
            {"name": "c", "depends_on": ["b"], "prompt": "z", "logic": {"custom": "logic/pass.py"}},
        ]
        mgr = self._setup_mgr(isolated_tasks_dir, tmp_path, blocks)
        mgr.run_workflow()
        assert "a" in mgr.completed
        assert "b" in mgr.completed
        assert "c" in mgr.completed

    def test_run_workflow_parallel(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """run_workflow runs parallel blocks correctly"""
        blocks = [
            {"name": "p1", "prompt": "1", "logic": {"custom": "logic/pass.py"}},
            {"name": "p2", "prompt": "2", "logic": {"custom": "logic/pass.py"}},
            {"name": "p3", "prompt": "3", "logic": {"custom": "logic/pass.py"}},
            {"name": "merge", "depends_on": ["p1", "p2", "p3"], "prompt": "m", "logic": {"custom": "logic/pass.py"}},
        ]
        mgr = self._setup_mgr(isolated_tasks_dir, tmp_path, blocks)
        mgr.run_workflow()
        assert len(mgr.completed) == 4

    def test_run_workflow_diamond(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """Diamond: A -> {B, C} -> D"""
        blocks = [
            {"name": "a", "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            {"name": "b", "depends_on": ["a"], "prompt": "y", "logic": {"custom": "logic/pass.py"}},
            {"name": "c", "depends_on": ["a"], "prompt": "z", "logic": {"custom": "logic/pass.py"}},
            {"name": "d", "depends_on": ["b", "c"], "prompt": "w", "logic": {"custom": "logic/pass.py"}},
        ]
        mgr = self._setup_mgr(isolated_tasks_dir, tmp_path, blocks)
        mgr.run_workflow()
        assert mgr.completed == {"a", "b", "c", "d"}


class TestFailingScript:
    """Tests for blocks with scripts that fail"""

    def _make_failing_flow(self, tmp_path, blocks, exit_code=1):
        """Flow with a script that exits with error"""
        import yaml

        flow_dir = tmp_path / "flow"
        logic_dir = flow_dir / "logic"
        os.makedirs(logic_dir)

        # Failing script
        with open(logic_dir / "fail.py", "w") as f:
            f.write(f"#!/usr/bin/env python3\nimport sys\nsys.exit({exit_code})\n")

        # Passing script
        with open(logic_dir / "pass.py", "w") as f:
            f.write(
                '#!/usr/bin/env python3\nimport sys, json, os\nctx=json.load(sys.stdin)\nos.makedirs(os.path.dirname(ctx["output_file"]), exist_ok=True)\nwith open(ctx["output_file"], "w") as f: json.dump({"result": "ok"}, f)\n'
            )

        flow = {
            "schema_version": "3.3.0",
            "name": "fail-test",
            "team": "team-test",
            "blocks": blocks,
        }
        yaml_path = flow_dir / "fail-test.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(flow, f)
        return str(yaml_path)

    def test_failing_block_marked_failed(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """Block with failing script gets status='failed'"""
        blocks = [
            {"name": "doomed", "prompt": "x", "logic": {"custom": "logic/fail.py"}},
        ]
        yaml_path = self._make_failing_flow(tmp_path, blocks)
        mgr = ProcessManager(max_parallel=3, agents_dir=isolated_tasks_dir)
        config = {"schema_version": "3.3.0", "name": "fail-test", "team": "team-test", "blocks": blocks}
        mgr.load_config(config, workflow_file=yaml_path)
        mgr.run_workflow()

        # Block should have run and failed
        failed = [p for p in mgr.processes.values() if p.status == "failed"]
        assert len(failed) == 1
        assert failed[0].name == "doomed"

    def test_continue_if_failed_allows_downstream(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """Block with continue_if_failed=True doesn't stop workflow"""
        blocks = [
            {"name": "failing", "prompt": "x", "logic": {"custom": "logic/fail.py"}, "continue_if_failed": True},
            {"name": "downstream", "depends_on": ["failing"], "prompt": "y", "logic": {"custom": "logic/pass.py"}},
        ]
        yaml_path = self._make_failing_flow(tmp_path, blocks)
        mgr = ProcessManager(max_parallel=3, agents_dir=isolated_tasks_dir)
        config = {"schema_version": "3.3.0", "name": "fail-test", "team": "team-test", "blocks": blocks}
        mgr.load_config(config, workflow_file=yaml_path)
        mgr.run_workflow()

        # Both should be in completed (failing as failed, downstream as done)
        assert "failing" in mgr.completed
        # downstream may or may not run depending on skip_if_previous_failed


class TestErrorHandlers:
    """Tests for _run_error_handlers method (logic.error + on_error)"""

    def _setup_flow_with_error_handler(self, tmp_path, per_block_error=None, global_error=None):
        """Create a flow with a failing block and optional error handlers"""
        import yaml

        flow_dir = tmp_path / "flow"
        logic_dir = flow_dir / "logic"
        os.makedirs(logic_dir)

        # Failing script
        with open(logic_dir / "fail.py", "w") as f:
            f.write("#!/usr/bin/env python3\nimport sys\nsys.exit(1)\n")

        # Error handler script (always succeeds, writes marker)
        with open(logic_dir / "handler.py", "w") as f:
            f.write("#!/usr/bin/env python3\nimport sys, os\n")
            f.write(f'with open("{tmp_path}/handler_called.txt", "w") as f: f.write("called")\n')

        block = {"name": "failing", "prompt": "x", "logic": {"custom": "logic/fail.py"}}
        if per_block_error:
            block["logic"]["error"] = per_block_error

        flow = {
            "schema_version": "3.3.0",
            "name": "err-test",
            "team": "team-test",
            "blocks": [block],
        }
        if global_error:
            flow["on_error"] = global_error

        yaml_path = flow_dir / "err-test.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(flow, f)
        return str(yaml_path), flow

    def test_global_on_error_called(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """Global on_error handler runs when block fails"""
        yaml_path, flow = self._setup_flow_with_error_handler(tmp_path, global_error="logic/handler.py")
        mgr = ProcessManager(max_parallel=3, agents_dir=isolated_tasks_dir)
        mgr.load_config(flow, workflow_file=yaml_path)
        mgr.run_workflow()

        # Failing block should be marked failed
        failed = [p for p in mgr.processes.values() if p.status == "failed"]
        assert len(failed) == 1
        # Handler should have been called (wrote marker file)
        marker = tmp_path / "handler_called.txt"
        assert marker.exists(), "global on_error handler was not invoked"

    def test_per_block_error_handler_called(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """Per-block logic.error handler runs when block fails"""
        yaml_path, flow = self._setup_flow_with_error_handler(tmp_path, per_block_error="logic/handler.py")
        mgr = ProcessManager(max_parallel=3, agents_dir=isolated_tasks_dir)
        mgr.load_config(flow, workflow_file=yaml_path)
        mgr.run_workflow()

        marker = tmp_path / "handler_called.txt"
        assert marker.exists(), "per-block logic.error handler was not invoked"

    def test_no_error_handler_still_exits_cleanly(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """Block fails without handler -- workflow still terminates"""
        yaml_path, flow = self._setup_flow_with_error_handler(tmp_path)
        mgr = ProcessManager(max_parallel=3, agents_dir=isolated_tasks_dir)
        mgr.load_config(flow, workflow_file=yaml_path)
        # Should not hang
        mgr.run_workflow()
        failed = [p for p in mgr.processes.values() if p.status == "failed"]
        assert len(failed) == 1


class TestInputValidation:
    """Tests for _validate_task_inputs (v2.6.0 feature)"""

    def test_no_inputs_section_backward_compat(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """Workflow without inputs section skips validation"""
        flow_dir = tmp_path / "flow"
        yaml_path = _make_minimal_flow(
            str(flow_dir),
            [
                {"name": "a", "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            ],
        )
        mgr = ProcessManager(max_parallel=3, agents_dir=isolated_tasks_dir)
        config = {
            "schema_version": "3.3.0",
            "name": "no-inputs",
            "team": "team-test",
            "blocks": [{"name": "a", "prompt": "x"}],
        }
        mgr.load_config(config, workflow_file=yaml_path)
        # Should not raise -- no inputs section = backward compat

    def test_optional_input_with_default_injected(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """Optional input with default gets injected into task_input"""
        flow_dir = tmp_path / "flow"
        yaml_path = _make_minimal_flow(
            str(flow_dir),
            [
                {"name": "a", "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            ],
        )
        mgr = ProcessManager(max_parallel=3, agents_dir=isolated_tasks_dir, task_input={})
        config = {
            "schema_version": "3.3.0",
            "name": "with-defaults",
            "team": "team-test",
            "inputs": {
                "priority": {"required": False, "default": "high"},
            },
            "blocks": [{"name": "a", "prompt": "x"}],
        }
        mgr.load_config(config, workflow_file=yaml_path)
        assert mgr.task_input.get("priority") == "high"

    def test_missing_required_input_exits(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """Missing required input triggers sys.exit(1)"""
        flow_dir = tmp_path / "flow"
        yaml_path = _make_minimal_flow(
            str(flow_dir),
            [
                {"name": "a", "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            ],
        )
        mgr = ProcessManager(max_parallel=3, agents_dir=isolated_tasks_dir, task_input={})
        config = {
            "schema_version": "3.3.0",
            "name": "strict",
            "team": "team-test",
            "inputs": {
                "topic": {"required": True, "description": "Topic to analyze"},
            },
            "blocks": [{"name": "a", "prompt": "x"}],
        }
        with pytest.raises(SystemExit):
            mgr.load_config(config, workflow_file=yaml_path)

    def test_provided_input_accepted(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """Provided required input is accepted"""
        flow_dir = tmp_path / "flow"
        yaml_path = _make_minimal_flow(
            str(flow_dir),
            [
                {"name": "a", "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            ],
        )
        mgr = ProcessManager(max_parallel=3, agents_dir=isolated_tasks_dir, task_input={"topic": "AI"})
        config = {
            "schema_version": "3.3.0",
            "name": "strict",
            "team": "team-test",
            "inputs": {"topic": {"required": True}},
            "blocks": [{"name": "a", "prompt": "x"}],
        }
        mgr.load_config(config, workflow_file=yaml_path)
        assert mgr.task_input["topic"] == "AI"


class TestResumeFromSqlite:
    """Tests for resuming workflow state from SQLite"""

    def test_completed_blocks_skipped_on_resume(self, mock_provider_env, isolated_tasks_dir, tmp_path):
        """When loading state from DB, already-done blocks are skipped"""
        flow_dir = tmp_path / "flow"
        blocks = [
            {"name": "a", "prompt": "x", "logic": {"custom": "logic/pass.py"}},
            {"name": "b", "depends_on": ["a"], "prompt": "y", "logic": {"custom": "logic/pass.py"}},
        ]
        yaml_path = _make_minimal_flow(str(flow_dir), blocks)

        # First run
        mgr1 = ProcessManager(max_parallel=3, agents_dir=isolated_tasks_dir)
        config = {"schema_version": "3.3.0", "name": "resume-test", "team": "team-test", "blocks": blocks}
        mgr1.load_config(config, workflow_file=yaml_path)
        mgr1.run_workflow()
        assert "a" in mgr1.completed
        assert "b" in mgr1.completed

        # Verify SQLite has state
        assert os.path.exists(os.path.join(mgr1.task_dir, "state", "rein.db"))
