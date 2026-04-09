"""
Comprehensive tests for --step mode: functional, integration, infrastructure, e2e.

Test levels:
  1. Functional    - run_step() logic with mocked LLM, real state machine
  2. Integration   - CLI -> ProcessManager -> SQLite roundtrip
  3. Infrastructure - file system state, task dirs, DB persistence across invocations
  4. E2E           - subprocess calls to `rein --step`, exit codes, real file outputs
"""

import fcntl
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest
import yaml

from rein.models import Process
from rein.orchestrator import ProcessManager
from rein.providers.base import UsageStats
from rein.state import ReinState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agents_dir(tmpdir):
    """Create minimal agents directory structure."""
    agents_dir = os.path.join(tmpdir, "agents")
    os.makedirs(os.path.join(agents_dir, "tasks"), exist_ok=True)
    os.makedirs(os.path.join(agents_dir, "specialists"), exist_ok=True)
    os.makedirs(os.path.join(agents_dir, "teams"), exist_ok=True)
    os.makedirs(os.path.join(agents_dir, "flows"), exist_ok=True)
    return agents_dir


def _make_flow(agents_dir, flow_name, blocks, team_name="team-test"):
    """Create flow YAML + team YAML + specialist files."""
    flow_dir = os.path.join(agents_dir, "flows", flow_name)
    os.makedirs(flow_dir, exist_ok=True)

    # Flow YAML
    flow_config = {
        "schema_version": "2.6.0",
        "name": flow_name,
        "team": team_name,
        "default_max_runs": 2,
        "blocks": blocks,
    }
    flow_path = os.path.join(flow_dir, f"{flow_name}.yaml")
    with open(flow_path, "w") as f:
        yaml.dump(flow_config, f)

    # Team YAML
    specialists = list({b.get("specialist", "default-spec") for b in blocks})
    team_path = os.path.join(agents_dir, "teams", f"{team_name}.yaml")
    with open(team_path, "w") as f:
        yaml.dump({"name": team_name, "specialists": specialists, "collaboration_tone": "Be concise."}, f)

    # Specialist files
    for spec in specialists:
        spec_path = os.path.join(agents_dir, "specialists", f"{spec}.md")
        if not os.path.exists(spec_path):
            with open(spec_path, "w") as f:
                f.write(f"# {spec}\nYou are a test specialist.\n")

    return flow_path


def _mock_provider():
    """Create a mock LLM provider that returns canned responses."""
    provider = MagicMock()
    provider.call.return_value = ('{"result": "ok"}', UsageStats())
    provider.last_usage = UsageStats()
    return provider


def _make_manager(tmpdir, blocks, task_input=None):
    """Create a ProcessManager with mocked provider, ready for run_step()."""
    agents_dir = _make_agents_dir(tmpdir)
    flow_path = _make_flow(agents_dir, "test-flow", blocks)

    from rein.tasks import load_config

    config = load_config(flow_path)

    manager = ProcessManager(
        max_parallel=3,
        flow_name="test-flow",
        task_input=task_input or {},
        agents_dir=agents_dir,
    )

    # Use the auto-created task dir
    task_id = manager.create_task("test-flow", task_input or {})
    manager.task_id = task_id
    manager.task_dir = os.path.join(manager.tasks_root, task_id)
    manager.run_dir = manager.task_dir
    manager.log_dir = os.path.join(manager.task_dir, "state")
    manager.rein_log_file = os.path.join(manager.task_dir, "state", "rein.log")
    manager.db_path = os.path.join(manager.task_dir, "state", "rein.db")
    os.makedirs(manager.log_dir, exist_ok=True)
    manager.state = ReinState(manager.db_path, resume=False)

    # Mock provider, validation, and team loading BEFORE load_config
    manager._provider = _mock_provider()
    with patch.object(manager, "_init_provider"), patch.object(manager, "_run_preflight_validation"):
        manager.load_config(config, workflow_file=flow_path)

    # Patch load_team to return a valid tone (needed for _execute_block to use Claude path)
    manager.load_team = lambda name: "Be concise and helpful."

    return manager


# ===========================================================================
# 1. FUNCTIONAL TESTS - run_step() logic with mocked LLM
# ===========================================================================


class TestFunctionalStepMode:
    """Test run_step() behavior: budget, deps, state transitions, next routing."""

    def test_single_block_completes_in_one_step(self):
        """Single block workflow: --step 1 should complete and return True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "only-block", "specialist": "spec-a", "prompt": "Do thing", "depends_on": []},
            ]
            manager = _make_manager(tmpdir, blocks)
            result = manager.run_step(1)
            assert result is True
            assert "only-block" in manager.completed

    def test_step_budget_limits_execution(self):
        """3 sequential blocks, --step 1: only first block runs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "step a", "depends_on": []},
                {"name": "b", "specialist": "spec-a", "prompt": "step b", "depends_on": ["a"]},
                {"name": "c", "specialist": "spec-a", "prompt": "step c", "depends_on": ["b"]},
            ]
            manager = _make_manager(tmpdir, blocks)
            result = manager.run_step(1)

            assert result is False  # more steps remain
            assert "a" in manager.completed
            assert "b" not in manager.completed
            assert "c" not in manager.completed

    def test_step_two_runs_two_sequential(self):
        """3 sequential blocks, --step 2: first two blocks run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "step a", "depends_on": []},
                {"name": "b", "specialist": "spec-a", "prompt": "step b", "depends_on": ["a"]},
                {"name": "c", "specialist": "spec-a", "prompt": "step c", "depends_on": ["b"]},
            ]
            manager = _make_manager(tmpdir, blocks)
            result = manager.run_step(2)

            assert result is False
            assert "a" in manager.completed
            assert "b" in manager.completed
            assert "c" not in manager.completed

    def test_step_zero_runs_all(self):
        """--step 0 (unlimited): runs entire workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "step a", "depends_on": []},
                {"name": "b", "specialist": "spec-a", "prompt": "step b", "depends_on": ["a"]},
            ]
            manager = _make_manager(tmpdir, blocks)
            result = manager.run_step(0)

            assert result is True
            assert "a" in manager.completed
            assert "b" in manager.completed

    def test_parallel_blocks_count_separately(self):
        """3 independent blocks + --step 2: only 2 spawned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
                {"name": "b", "specialist": "spec-a", "prompt": "b", "depends_on": []},
                {"name": "c", "specialist": "spec-a", "prompt": "c", "depends_on": []},
            ]
            manager = _make_manager(tmpdir, blocks)
            result = manager.run_step(2)

            assert result is False
            completed_count = len(manager.completed)
            assert completed_count == 2  # exactly 2 of the 3

    def test_respects_dependencies(self):
        """Cannot run block B until A is done, even with budget."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
                {"name": "b", "specialist": "spec-a", "prompt": "b", "depends_on": ["a"]},
            ]
            manager = _make_manager(tmpdir, blocks)

            # Step 1: only A can run (B depends on A)
            result = manager.run_step(1)
            assert "a" in manager.completed
            assert "b" not in manager.completed
            assert result is False

    def test_diamond_dependency_pattern(self):
        """Diamond: A -> B, A -> C, B+C -> D. Step 1 runs A, step 2 runs B+C, step 1 runs D."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
                {"name": "b", "specialist": "spec-a", "prompt": "b", "depends_on": ["a"]},
                {"name": "c", "specialist": "spec-a", "prompt": "c", "depends_on": ["a"]},
                {"name": "d", "specialist": "spec-a", "prompt": "d", "depends_on": ["b", "c"]},
            ]
            manager = _make_manager(tmpdir, blocks)

            # Step 1: A runs
            r1 = manager.run_step(1)
            assert r1 is False
            assert manager.completed == {"a"}

            # Step 2: B and C run in parallel
            r2 = manager.run_step(2)
            assert r2 is False
            assert "b" in manager.completed
            assert "c" in manager.completed

            # Step 1: D runs, workflow complete
            r3 = manager.run_step(1)
            assert r3 is True
            assert "d" in manager.completed

    def test_already_complete_noop(self):
        """If workflow already done, run_step returns True immediately."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
            ]
            manager = _make_manager(tmpdir, blocks)

            # Complete it
            manager.run_step(1)
            assert manager.completed == {"a"}

            # Call again -- should be noop
            result = manager.run_step(1)
            assert result is True

    def test_failed_block_counts_as_completed(self):
        """A failed block should still allow dependent blocks to see it in completed set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
            ]
            manager = _make_manager(tmpdir, blocks)

            # Make provider raise to simulate failure
            manager._provider.call.side_effect = Exception("LLM error")

            result = manager.run_step(1)
            # Block should be in completed (even though failed)
            assert "a" in manager.completed
            # Workflow is "done" (all blocks processed)
            assert result is True


# ===========================================================================
# 2. INTEGRATION TESTS - CLI + ProcessManager + SQLite roundtrip
# ===========================================================================


class TestIntegrationStepMode:
    """Test the full path: CLI args -> ProcessManager -> SQLite -> resume."""

    def test_step_resume_reads_state_from_db(self):
        """Second invocation resumes from SQLite: completed blocks are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
                {"name": "b", "specialist": "spec-a", "prompt": "b", "depends_on": ["a"]},
                {"name": "c", "specialist": "spec-a", "prompt": "c", "depends_on": ["b"]},
            ]

            # First invocation: run 1 block
            m1 = _make_manager(tmpdir, blocks)
            r1 = m1.run_step(1)
            assert r1 is False
            assert "a" in m1.completed
            task_dir = m1.task_dir
            db_path = m1.db_path

            # Second invocation: new manager, same task dir, resume
            agents_dir = _make_agents_dir(tmpdir)
            _make_flow(agents_dir, "test-flow", blocks)

            from rein.tasks import load_config

            flow_path = os.path.join(agents_dir, "flows", "test-flow", "test-flow.yaml")
            config = load_config(flow_path)

            m2 = ProcessManager(
                max_parallel=3,
                flow_name="test-flow",
                task_input={},
                agents_dir=agents_dir,
            )
            m2.task_id = os.path.basename(task_dir)
            m2.task_dir = task_dir
            m2.run_dir = task_dir
            m2.log_dir = os.path.join(task_dir, "state")
            m2.rein_log_file = os.path.join(task_dir, "state", "rein.log")
            m2.db_path = db_path
            os.makedirs(m2.log_dir, exist_ok=True)
            m2.state = ReinState(db_path, resume=True)

            m2._provider = _mock_provider()
            with patch.object(m2, "_init_provider"), patch.object(m2, "_run_preflight_validation"):
                m2.load_config(config, workflow_file=flow_path)

            # Block A should be skipped (already done)
            assert "a" in m2.completed

            # Run step 1: should execute B (not A)
            r2 = m2.run_step(1)
            assert r2 is False
            assert "b" in m2.completed

            # Third invocation: same pattern
            m3 = ProcessManager(
                max_parallel=3,
                flow_name="test-flow",
                task_input={},
                agents_dir=agents_dir,
            )
            m3.task_id = os.path.basename(task_dir)
            m3.task_dir = task_dir
            m3.run_dir = task_dir
            m3.log_dir = os.path.join(task_dir, "state")
            m3.rein_log_file = os.path.join(task_dir, "state", "rein.log")
            m3.db_path = db_path
            m3.state = ReinState(db_path, resume=True)

            m3._provider = _mock_provider()
            with patch.object(m3, "_init_provider"), patch.object(m3, "_run_preflight_validation"):
                m3.load_config(config, workflow_file=flow_path)

            assert "a" in m3.completed
            assert "b" in m3.completed

            r3 = m3.run_step(1)
            assert r3 is True  # C was the last block
            assert "c" in m3.completed

    def test_provider_called_once_per_step(self):
        """--step 1 results in exactly 1 LLM call."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "do thing", "depends_on": []},
                {"name": "b", "specialist": "spec-a", "prompt": "next thing", "depends_on": ["a"]},
            ]
            manager = _make_manager(tmpdir, blocks)
            manager.run_step(1)

            assert manager._provider.call.call_count == 1


# ===========================================================================
# 3. INFRASTRUCTURE TESTS - file system, SQLite, task dirs
# ===========================================================================


class TestInfrastructureStepMode:
    """Test file system artifacts: task dirs, SQLite DB, status files, logs."""

    def test_sqlite_state_persisted(self):
        """After run_step, SQLite DB contains correct block statuses."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
                {"name": "b", "specialist": "spec-a", "prompt": "b", "depends_on": ["a"]},
            ]
            manager = _make_manager(tmpdir, blocks)
            manager.run_step(1)

            # Read SQLite directly
            conn = sqlite3.connect(manager.db_path)
            rows = conn.execute("SELECT name, status FROM processes ORDER BY name").fetchall()
            conn.close()

            status_map = {name: status for name, status in rows}
            assert status_map["a"] == "done"
            assert status_map["b"] == "waiting"

    def test_rein_log_written(self):
        """run_step writes to state/rein.log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
            ]
            manager = _make_manager(tmpdir, blocks)
            manager.run_step(1)

            log_path = os.path.join(manager.task_dir, "state", "rein.log")
            assert os.path.exists(log_path)

            with open(log_path) as f:
                log_content = f.read()

            assert "STEP MODE" in log_content
            assert "budget=1" in log_content

    def test_step_log_contains_yielding_on_partial(self):
        """Partial execution logs STEP YIELDING."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
                {"name": "b", "specialist": "spec-a", "prompt": "b", "depends_on": ["a"]},
            ]
            manager = _make_manager(tmpdir, blocks)
            manager.run_step(1)

            with open(manager.rein_log_file) as f:
                log = f.read()

            assert "STEP YIELDING" in log
            assert "remaining=1" in log

    def test_step_log_contains_complete_on_done(self):
        """Full completion logs STEP COMPLETE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
            ]
            manager = _make_manager(tmpdir, blocks)
            manager.run_step(1)

            with open(manager.rein_log_file) as f:
                log = f.read()

            assert "STEP COMPLETE" in log

    def test_task_dir_structure_preserved(self):
        """Step mode preserves standard task dir layout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
            ]
            manager = _make_manager(tmpdir, blocks)
            manager.run_step(1)

            task_dir = manager.task_dir
            assert os.path.isdir(os.path.join(task_dir, "input"))
            assert os.path.isdir(os.path.join(task_dir, "state"))
            assert os.path.exists(os.path.join(task_dir, "state", "rein.db"))
            assert os.path.exists(os.path.join(task_dir, "input", "task.json"))

    def test_result_json_created_for_completed_block(self):
        """Completed block should have result.json in outputs dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "first-block", "specialist": "spec-a", "prompt": "do thing", "depends_on": []},
            ]
            manager = _make_manager(tmpdir, blocks)
            manager.run_step(1)

            # Check for result.json in block output dir
            # Block outputs go to task_dir/first-block/outputs/result.json
            result_path = os.path.join(manager.task_dir, "first-block", "outputs", "result.json")
            assert os.path.exists(result_path), f"Expected result.json at {result_path}"

    def test_finalize_creates_summary_on_completion(self):
        """When workflow completes, summary.json is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
            ]
            manager = _make_manager(tmpdir, blocks)
            result = manager.run_step(1)
            assert result is True

            summary_path = os.path.join(manager.task_dir, "summary.json")
            assert os.path.exists(summary_path)
            with open(summary_path) as f:
                summary = json.load(f)
            assert summary["completed"] >= 1

    def test_no_summary_on_partial(self):
        """Partial execution should NOT create summary.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
                {"name": "b", "specialist": "spec-a", "prompt": "b", "depends_on": ["a"]},
            ]
            manager = _make_manager(tmpdir, blocks)
            result = manager.run_step(1)
            assert result is False

            summary_path = os.path.join(manager.task_dir, "summary.json")
            assert not os.path.exists(summary_path)

    def test_db_survives_multiple_invocations(self):
        """SQLite DB accumulates state across 3 separate invocations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
                {"name": "b", "specialist": "spec-a", "prompt": "b", "depends_on": ["a"]},
                {"name": "c", "specialist": "spec-a", "prompt": "c", "depends_on": ["b"]},
            ]
            manager = _make_manager(tmpdir, blocks)
            db_path = manager.db_path
            task_dir = manager.task_dir
            agents_dir = os.path.join(tmpdir, "agents")

            # Invocation 1
            manager.run_step(1)

            conn = sqlite3.connect(db_path)
            done_count = conn.execute("SELECT COUNT(*) FROM processes WHERE status='done'").fetchone()[0]
            conn.close()
            assert done_count == 1

            # Invocation 2: new manager, same DB
            from rein.tasks import load_config

            flow_path = os.path.join(agents_dir, "flows", "test-flow", "test-flow.yaml")
            config = load_config(flow_path)

            m2 = ProcessManager(
                max_parallel=3,
                flow_name="test-flow",
                task_input={},
                agents_dir=agents_dir,
            )
            m2.task_id = os.path.basename(task_dir)
            m2.task_dir = task_dir
            m2.run_dir = task_dir
            m2.log_dir = os.path.join(task_dir, "state")
            m2.rein_log_file = os.path.join(task_dir, "state", "rein.log")
            m2.db_path = db_path
            m2.state = ReinState(db_path, resume=True)

            m2._provider = _mock_provider()
            m2.load_team = lambda name: "Be concise and helpful."
            with patch.object(m2, "_init_provider"), patch.object(m2, "_run_preflight_validation"):
                m2.load_config(config, workflow_file=flow_path)

            m2.run_step(1)

            conn = sqlite3.connect(db_path)
            done_count = conn.execute("SELECT COUNT(*) FROM processes WHERE status='done'").fetchone()[0]
            conn.close()
            assert done_count == 2


# ===========================================================================
# 4. E2E TESTS - subprocess calls, exit codes, real CLI
# ===========================================================================


class TestE2EStepMode:
    """End-to-end tests using subprocess to call `rein --step`."""

    @pytest.fixture
    def e2e_env(self):
        """Set up a complete environment for e2e testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = _make_agents_dir(tmpdir)

            blocks = [
                {"name": "block-1", "specialist": "spec-a", "prompt": "Say hello", "depends_on": []},
                {"name": "block-2", "specialist": "spec-a", "prompt": "Say goodbye", "depends_on": ["block-1"]},
            ]
            _make_flow(agents_dir, "e2e-flow", blocks)

            yield {
                "tmpdir": tmpdir,
                "agents_dir": agents_dir,
            }

    def _run_rein(self, args, agents_dir, env_extra=None):
        """Run rein as subprocess, return (exit_code, stdout, stderr)."""
        cmd = (
            [sys.executable, "-m", "rein"]
            + args
            + [
                "--agents-dir",
                agents_dir,
            ]
        )
        env = os.environ.copy()
        # Ensure no real API key is used; provider will fail but we mock at a different level
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("OPENAI_API_KEY", None)
        if env_extra:
            env.update(env_extra)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.path.dirname(os.path.dirname(__file__)),  # rein project root
            env=env,
        )
        return result.returncode, result.stdout, result.stderr

    def test_step_negative_exits_1(self, e2e_env):
        """--step -1 exits with code 1."""
        code, stdout, _ = self._run_rein(
            ["--step", "-1"],
            e2e_env["agents_dir"],
        )
        assert code == 1
        assert "must be >= 0" in stdout

    def test_step_without_flow_or_task_dir_exits_1(self, e2e_env):
        """--step 1 alone (no --flow, no --task-dir) exits with error."""
        code, stdout, _ = self._run_rein(
            ["--step", "1"],
            e2e_env["agents_dir"],
        )
        assert code == 1

    def test_step_resume_missing_task_dir_exits_1(self, e2e_env):
        """--step 1 --task-dir /nonexistent exits with error."""
        code, stdout, _ = self._run_rein(
            ["--step", "1", "--task-dir", "/tmp/nonexistent-task-xyz"],
            e2e_env["agents_dir"],
        )
        assert code == 1
        assert "task.json" in stdout.lower() or "not found" in stdout.lower() or "error" in stdout.lower()

    def test_help_includes_step(self, e2e_env):
        """--help output mentions --step."""
        code, stdout, stderr = self._run_rein(
            ["--help"],
            e2e_env["agents_dir"],
        )
        # argparse may use stdout or stderr depending on version
        combined = stdout + stderr
        assert "--step" in combined


# ===========================================================================
# 5. RUN_COUNT PERSISTENCE + FILE LOCK TESTS
# ===========================================================================


class TestRunCountPersistence:
    """Tests for run_count persistence in SQLite across step invocations."""

    def test_run_count_saved_to_db(self):
        """run_count from Process is persisted to SQLite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            state = ReinState(db_path, resume=False)

            proc = Process(pid=1, name="loop-block", status="waiting", start_time=0, command="", run_count=3)
            state.save_process(proc)

            restored = state.get_process("loop-block")
            assert restored.run_count == 3

    def test_run_count_default_zero(self):
        """New process without explicit run_count defaults to 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            state = ReinState(db_path, resume=False)

            proc = Process(pid=1, name="block", status="waiting", start_time=0, command="")
            state.save_process(proc)

            restored = state.get_process("block")
            assert restored.run_count == 0

    def test_run_count_survives_resume(self):
        """run_count preserved when opening DB with resume=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # First session: save with run_count=2
            s1 = ReinState(db_path, resume=False)
            proc = Process(pid=1, name="block", status="done", start_time=0, command="", run_count=2)
            s1.save_process(proc)

            # Second session: resume
            s2 = ReinState(db_path, resume=True)
            restored = s2.get_process("block")
            assert restored.run_count == 2

    def test_schema_migration_adds_run_count(self):
        """Existing DB without run_count column gets it via ALTER TABLE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "old.db")

            # Create old-schema DB manually (no run_count)
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE processes (
                    name TEXT PRIMARY KEY,
                    pid INTEGER,
                    status TEXT,
                    start_time REAL,
                    command TEXT,
                    exit_code INTEGER,
                    cpu_percent REAL,
                    memory_mb REAL,
                    progress INTEGER,
                    phase INTEGER,
                    blocking_pause INTEGER,
                    updated_at REAL
                )
            """)
            conn.execute(
                "INSERT INTO processes (name, status, start_time, command) VALUES (?, ?, ?, ?)",
                ("old-block", "done", 0, ""),
            )
            conn.commit()
            conn.close()

            # Open with resume -- should migrate
            state = ReinState(db_path, resume=True)
            proc = state.get_process("old-block")
            assert proc is not None
            assert proc.run_count == 0  # default after migration

            # New writes should include run_count
            new_proc = Process(pid=1, name="new-block", status="waiting", start_time=0, command="", run_count=5)
            state.save_process(new_proc)
            restored = state.get_process("new-block")
            assert restored.run_count == 5

    def test_run_counts_restored_in_manager(self):
        """ProcessManager.run_counts dict is populated from SQLite on resume."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
            ]
            manager = _make_manager(tmpdir, blocks)
            db_path = manager.db_path
            task_dir = manager.task_dir

            # Manually set run_count in DB
            conn = sqlite3.connect(db_path)
            conn.execute("UPDATE processes SET run_count = 3 WHERE name = 'a'")
            conn.commit()
            conn.close()

            # Create new manager with resume
            agents_dir = os.path.join(tmpdir, "agents")
            from rein.tasks import load_config

            flow_path = os.path.join(agents_dir, "flows", "test-flow", "test-flow.yaml")
            config = load_config(flow_path)

            m2 = ProcessManager(
                max_parallel=3,
                flow_name="test-flow",
                task_input={},
                agents_dir=agents_dir,
            )
            m2.task_id = os.path.basename(task_dir)
            m2.task_dir = task_dir
            m2.run_dir = task_dir
            m2.log_dir = os.path.join(task_dir, "state")
            m2.rein_log_file = os.path.join(task_dir, "state", "rein.log")
            m2.db_path = db_path
            m2.state = ReinState(db_path, resume=True)

            m2._provider = _mock_provider()
            m2.load_team = lambda name: "Be concise."
            with patch.object(m2, "_init_provider"), patch.object(m2, "_run_preflight_validation"):
                m2.load_config(config, workflow_file=flow_path)

            assert m2.run_counts.get("a") == 3


class TestFileLock:
    """Tests for file lock preventing concurrent step invocations."""

    def test_lock_prevents_concurrent_execution(self):
        """Second run_step on same task_dir returns False (locked)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
            ]
            manager = _make_manager(tmpdir, blocks)

            # Manually acquire the lock
            lock_path = os.path.join(manager.task_dir, "state", "rein.lock")
            os.makedirs(os.path.dirname(lock_path), exist_ok=True)
            lock_fd = open(lock_path, "w")
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            try:
                # run_step should fail to acquire lock and return False
                result = manager.run_step(1)
                assert result is False
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()

    def test_lock_released_after_step(self):
        """After run_step completes, lock is released."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "a", "specialist": "spec-a", "prompt": "a", "depends_on": []},
            ]
            manager = _make_manager(tmpdir, blocks)
            manager.run_step(1)

            # Lock should be released -- can acquire again
            lock_path = os.path.join(manager.task_dir, "state", "rein.lock")
            lock_fd = open(lock_path, "w")
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except (BlockingIOError, OSError):
                acquired = False
            finally:
                if acquired:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()

            assert acquired is True


# ===========================================================================
# 6. AGENT ROUTING TESTS
# ===========================================================================


class TestAgentRouting:
    """Tests for --agent-id based block filtering in step mode."""

    def test_agent_filter_runs_matching_blocks(self):
        """--agent-id smm only runs blocks with agent: smm."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "draft", "specialist": "spec-a", "prompt": "write", "depends_on": [], "agent": "smm"},
                {
                    "name": "review",
                    "specialist": "spec-a",
                    "prompt": "review",
                    "depends_on": ["draft"],
                    "agent": "editor",
                },
                {
                    "name": "approve",
                    "specialist": "spec-a",
                    "prompt": "approve",
                    "depends_on": ["review"],
                    "agent": "marketer",
                },
            ]
            manager = _make_manager(tmpdir, blocks)

            result = manager.run_step(1, agent_id="smm")
            assert "draft" in manager.completed
            assert "review" not in manager.completed
            assert result is False

    def test_agent_filter_skips_other_agents(self):
        """--agent-id editor skips smm blocks even if they are ready."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "draft", "specialist": "spec-a", "prompt": "write", "depends_on": [], "agent": "smm"},
                {"name": "review", "specialist": "spec-a", "prompt": "review", "depends_on": [], "agent": "editor"},
            ]
            manager = _make_manager(tmpdir, blocks)

            # Editor should only run "review", not "draft"
            manager.run_step(10, agent_id="editor")
            assert "review" in manager.completed
            assert "draft" not in manager.completed

    def test_no_agent_id_runs_all(self):
        """Without --agent-id, all ready blocks are executed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "draft", "specialist": "spec-a", "prompt": "write", "depends_on": [], "agent": "smm"},
                {"name": "review", "specialist": "spec-a", "prompt": "review", "depends_on": [], "agent": "editor"},
            ]
            manager = _make_manager(tmpdir, blocks)

            manager.run_step(10, agent_id=None)
            assert "draft" in manager.completed
            assert "review" in manager.completed

    def test_empty_agent_field_runs_for_anyone(self):
        """Blocks without agent: field are executed by any agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "setup", "specialist": "spec-a", "prompt": "setup", "depends_on": []},  # no agent
                {"name": "draft", "specialist": "spec-a", "prompt": "write", "depends_on": ["setup"], "agent": "smm"},
            ]
            manager = _make_manager(tmpdir, blocks)

            # SMM agent can run "setup" (no agent) and "draft" (agent: smm)
            result = manager.run_step(10, agent_id="smm")
            assert "setup" in manager.completed
            assert "draft" in manager.completed
            assert result is True

    def test_agent_with_no_matching_blocks_does_nothing(self):
        """Agent with no matching blocks: nothing executed, returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "draft", "specialist": "spec-a", "prompt": "write", "depends_on": [], "agent": "smm"},
            ]
            manager = _make_manager(tmpdir, blocks)

            result = manager.run_step(10, agent_id="marketer")
            assert "draft" not in manager.completed
            assert result is False

    def test_multi_agent_sequential_handoff(self):
        """Full pipeline: smm -> editor -> marketer, each with --step 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "draft", "specialist": "spec-a", "prompt": "write", "depends_on": [], "agent": "smm"},
                {
                    "name": "review",
                    "specialist": "spec-a",
                    "prompt": "review",
                    "depends_on": ["draft"],
                    "agent": "editor",
                },
                {
                    "name": "approve",
                    "specialist": "spec-a",
                    "prompt": "approve",
                    "depends_on": ["review"],
                    "agent": "marketer",
                },
            ]
            manager = _make_manager(tmpdir, blocks)

            # SMM runs draft
            r1 = manager.run_step(1, agent_id="smm")
            assert r1 is False
            assert manager.completed == {"draft"}

            # Editor runs review
            r2 = manager.run_step(1, agent_id="editor")
            assert r2 is False
            assert "review" in manager.completed

            # Marketer runs approve
            r3 = manager.run_step(1, agent_id="marketer")
            assert r3 is True
            assert "approve" in manager.completed


# ===========================================================================
# 7. REVISION LOOP + GATE TESTS
# ===========================================================================


class TestRevisionLoops:
    """Tests for next: routing, gate deferred completion, and max_runs loops."""

    def test_simple_loop_with_max_runs(self):
        """Revision loop terminates when max_runs is reached."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {
                    "name": "gate",
                    "specialist": "spec-a",
                    "prompt": "check",
                    "depends_on": [],
                    "next": [
                        {"if": "{{ result.impossible }}", "goto": "downstream"},
                        {"else": "revision"},
                    ],
                    "max_runs": 2,
                },
                {
                    "name": "revision",
                    "specialist": "spec-a",
                    "prompt": "fix",
                    "depends_on": ["gate"],
                    "next": "gate",
                    "max_runs": 1,
                },
                {"name": "downstream", "specialist": "spec-a", "prompt": "go", "depends_on": ["gate"]},
            ]
            manager = _make_manager(tmpdir, blocks)

            result = manager.run_step(0)

            assert result is True
            assert "gate" in manager.completed
            assert "downstream" in manager.completed

    def test_gate_first_run_completes_forward(self):
        """First routing (current_runs=0) is forward -- gate completes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "gate", "specialist": "spec-a", "prompt": "check", "depends_on": [], "next": "revision"},
                {"name": "revision", "specialist": "spec-a", "prompt": "fix", "depends_on": ["gate"], "max_runs": 1},
                {"name": "downstream", "specialist": "spec-a", "prompt": "go", "depends_on": ["gate"]},
            ]
            manager = _make_manager(tmpdir, blocks)

            # Step 1: gate runs, routes to revision (forward, first time)
            manager.run_step(1)

            # Gate IS completed (forward routing on first run)
            assert "gate" in manager.completed

    def test_max_runs_exhausted_unblocks_downstream(self):
        """When loop exhausts max_runs, gate completes and downstream proceeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "gate", "specialist": "spec-a", "prompt": "check", "depends_on": [], "next": "revision"},
                {
                    "name": "revision",
                    "specialist": "spec-a",
                    "prompt": "fix",
                    "depends_on": ["gate"],
                    "next": "gate",
                    "max_runs": 1,
                },
                {"name": "downstream", "specialist": "spec-a", "prompt": "go", "depends_on": ["gate"]},
            ]
            manager = _make_manager(tmpdir, blocks)

            # Run to completion
            result = manager.run_step(0)

            assert result is True
            # All should be completed
            assert "gate" in manager.completed
            assert "revision" in manager.completed
            assert "downstream" in manager.completed

    def test_loop_does_not_run_forever(self):
        """Revision loop terminates and run_counts stay within limits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {
                    "name": "gate",
                    "specialist": "spec-a",
                    "prompt": "check",
                    "depends_on": [],
                    "next": [
                        {"if": "{{ result.impossible }}", "goto": "done"},
                        {"else": "revision"},
                    ],
                    "max_runs": 2,
                },
                {
                    "name": "revision",
                    "specialist": "spec-a",
                    "prompt": "fix",
                    "depends_on": ["gate"],
                    "next": "gate",
                    "max_runs": 1,
                },
            ]
            manager = _make_manager(tmpdir, blocks)

            result = manager.run_step(0)

            assert result is True
            # Check run counts -- should not exceed max_runs
            gate_runs = manager.run_counts.get("gate", 0)
            revision_runs = manager.run_counts.get("revision", 0)
            assert gate_runs <= 2
            assert revision_runs <= 3

    def test_conditional_next_else_routes_to_revision(self):
        """Gate with if/else: when condition not met, else branch triggers revision."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {
                    "name": "gate",
                    "specialist": "spec-a",
                    "prompt": "check",
                    "depends_on": [],
                    "next": [
                        {"if": "{{ result.impossible_field }}", "goto": "downstream"},
                        {"else": "revision"},
                    ],
                },
                {"name": "revision", "specialist": "spec-a", "prompt": "fix", "depends_on": ["gate"], "max_runs": 1},
                {"name": "downstream", "specialist": "spec-a", "prompt": "go", "depends_on": ["gate"]},
            ]
            manager = _make_manager(tmpdir, blocks)

            # Step 1: gate runs, condition fails, else -> revision
            # This is first run (current_runs=0) so it's forward -- gate completes
            manager.run_step(1)

            assert "gate" in manager.completed  # forward routing on first run

    def test_from_next_queue_bypasses_depends_on(self):
        """Blocks spawned via next_queue skip depends_on check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "gate", "specialist": "spec-a", "prompt": "check", "depends_on": [], "next": "target"},
                {"name": "target", "specialist": "spec-a", "prompt": "fix", "depends_on": ["gate"]},
            ]
            manager = _make_manager(tmpdir, blocks)

            # Run gate (step 1) -- should route to target
            # Gate deferred (routing backward), but target spawns via next_queue
            manager.run_step(2)

            # Target should have run even though gate is not in completed
            assert "target" in manager.completed


class TestForwardRouting:
    """Tests for forward routing via next:/routing -- gate should complete."""

    def test_forward_next_gate_completes(self):
        """Gate with next: forward_target (first run) should complete normally."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {
                    "name": "review",
                    "specialist": "spec-a",
                    "prompt": "review",
                    "depends_on": [],
                    "next": "generate",
                },  # forward: generate hasn't run yet
                {"name": "generate", "specialist": "spec-a", "prompt": "generate", "depends_on": ["review"]},
                {"name": "publish", "specialist": "spec-a", "prompt": "publish", "depends_on": ["review"]},
            ]
            manager = _make_manager(tmpdir, blocks)

            # Step 1: review runs, routes to generate (forward)
            manager.run_step(1)

            # Review should be completed (forward routing, not backward)
            assert "review" in manager.completed

    def test_forward_routing_allows_downstream_in_step_mode(self):
        """After forward routing, other dependents of gate can start in next step."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "review", "specialist": "spec-a", "prompt": "review", "depends_on": [], "next": "generate"},
                {"name": "generate", "specialist": "spec-a", "prompt": "generate", "depends_on": ["review"]},
                {"name": "publish", "specialist": "spec-a", "prompt": "publish", "depends_on": ["review"]},
            ]
            manager = _make_manager(tmpdir, blocks)

            # Step 1: review runs + generate via next_queue
            manager.run_step(2)
            assert "review" in manager.completed
            assert "generate" in manager.completed

            # Step 2: publish should start (review is completed)
            manager.run_step(1)
            assert "publish" in manager.completed

    def test_forward_vs_backward_distinction(self):
        """Forward routing (current_runs=0) completes gate, backward (>0) defers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"name": "gate", "specialist": "spec-a", "prompt": "check", "depends_on": [], "next": "target"},
                {"name": "target", "specialist": "spec-a", "prompt": "do", "depends_on": ["gate"]},
                {"name": "other", "specialist": "spec-a", "prompt": "go", "depends_on": ["gate"]},
            ]
            manager = _make_manager(tmpdir, blocks)

            # Step 1: gate routes to target (forward, first run)
            # Gate should be completed, other should be able to proceed
            manager.run_step(1)

            assert "gate" in manager.completed  # forward: gate completes
            # Other can now see gate as completed in next step
            manager.run_step(2)
            assert "target" in manager.completed
            assert "other" in manager.completed
