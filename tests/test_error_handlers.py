"""Tests for on_error and logic.error handlers (T#1146)."""
import os
import json
import tempfile

import pytest
import yaml

from unittest.mock import patch, MagicMock

from rein.orchestrator import ProcessManager
from rein.state import ReinState
from rein.providers.base import UsageStats


def _mock_provider_failing():
    """Provider that always fails."""
    provider = MagicMock()
    provider.call.side_effect = Exception("LLM API error")
    provider.last_usage = UsageStats()
    return provider


def _mock_provider_ok():
    """Provider that succeeds."""
    provider = MagicMock()
    provider.call.return_value = ('{"result": "ok"}', UsageStats())
    provider.last_usage = UsageStats()
    return provider


def _make_flow_with_error_handler(tmpdir, blocks, on_error=None):
    """Create a flow with optional on_error and blocks with optional logic.error."""
    agents_dir = os.path.join(tmpdir, "agents")
    os.makedirs(os.path.join(agents_dir, "tasks"), exist_ok=True)
    os.makedirs(os.path.join(agents_dir, "specialists"), exist_ok=True)
    os.makedirs(os.path.join(agents_dir, "teams"), exist_ok=True)

    flow_dir = os.path.join(agents_dir, "flows", "test-flow")
    os.makedirs(flow_dir, exist_ok=True)

    flow_config = {
        "name": "test-flow",
        "team": "team-test",
        "blocks": blocks,
    }
    if on_error:
        flow_config["on_error"] = on_error

    flow_path = os.path.join(flow_dir, "test-flow.yaml")
    with open(flow_path, "w") as f:
        yaml.dump(flow_config, f)

    # Create specialist
    spec_path = os.path.join(agents_dir, "specialists", "spec-a.md")
    with open(spec_path, "w") as f:
        f.write("# spec-a\nTest specialist.\n")

    # Create team
    team_path = os.path.join(agents_dir, "teams", "team-test.yaml")
    with open(team_path, "w") as f:
        yaml.dump({"name": "team-test", "specialists": ["spec-a"],
                    "collaboration_tone": "Be concise."}, f)

    return agents_dir, flow_path, flow_dir


def _make_manager_with_flow(tmpdir, blocks, on_error=None, provider=None):
    """Create a ProcessManager with a flow that has error handling."""
    agents_dir, flow_path, flow_dir = _make_flow_with_error_handler(
        tmpdir, blocks, on_error
    )

    from rein.tasks import load_config
    config = load_config(flow_path)

    manager = ProcessManager(
        max_parallel=3,
        flow_name="test-flow",
        task_input={},
        agents_dir=agents_dir,
    )

    task_id = manager.create_task("test-flow", {})
    manager.task_id = task_id
    manager.task_dir = os.path.join(manager.tasks_root, task_id)
    manager.run_dir = manager.task_dir
    manager.log_dir = os.path.join(manager.task_dir, "state")
    manager.rein_log_file = os.path.join(manager.task_dir, "state", "rein.log")
    manager.db_path = os.path.join(manager.task_dir, "state", "rein.db")
    os.makedirs(manager.log_dir, exist_ok=True)
    manager.state = ReinState(manager.db_path, resume=False)

    manager._provider = provider or _mock_provider_failing()
    manager.load_team = lambda name: "Be concise."
    with patch.object(manager, '_init_provider'), \
         patch.object(manager, '_run_preflight_validation'):
        manager.load_config(config, workflow_file=flow_path)

    return manager, flow_dir


class TestOnErrorGlobal:
    """Tests for global on_error handler in flow YAML."""

    def test_on_error_loaded_from_config(self):
        """on_error field is read from flow config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [{"name": "a", "specialist": "spec-a",
                       "prompt": "test", "depends_on": []}]
            manager, _ = _make_manager_with_flow(tmpdir, blocks, on_error="scripts/notify.sh")
            assert manager.on_error == "scripts/notify.sh"

    def test_on_error_none_by_default(self):
        """No on_error in config -> None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [{"name": "a", "specialist": "spec-a",
                       "prompt": "test", "depends_on": []}]
            manager, _ = _make_manager_with_flow(tmpdir, blocks)
            assert manager.on_error is None

    def test_on_error_called_on_block_failure(self):
        """Global on_error script runs when a block fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [{"name": "failing-block", "specialist": "spec-a",
                       "prompt": "test", "depends_on": []}]

            manager, flow_dir = _make_manager_with_flow(
                tmpdir, blocks, on_error="scripts/on-error.sh"
            )

            # Create the error handler script
            scripts_dir = os.path.join(flow_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            marker = os.path.join(tmpdir, "error-called.json")
            with open(os.path.join(scripts_dir, "on-error.sh"), "w") as f:
                f.write(f'#!/bin/bash\ncat > {marker}\n')
            os.chmod(os.path.join(scripts_dir, "on-error.sh"), 0o755)

            manager.run_step(1)

            # Verify handler was called with correct context
            assert os.path.exists(marker), "on_error handler was not called"
            with open(marker) as f:
                ctx = json.load(f)
            assert ctx["block_name"] == "failing-block"
            assert "LLM API error" in ctx["error"]
            assert ctx["flow_name"] == "test-flow"

    def test_on_error_not_called_on_success(self):
        """Global on_error does NOT run when block succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [{"name": "ok-block", "specialist": "spec-a",
                       "prompt": "test", "depends_on": []}]

            manager, flow_dir = _make_manager_with_flow(
                tmpdir, blocks, on_error="scripts/on-error.sh",
                provider=_mock_provider_ok()
            )

            scripts_dir = os.path.join(flow_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            marker = os.path.join(tmpdir, "should-not-exist.json")
            with open(os.path.join(scripts_dir, "on-error.sh"), "w") as f:
                f.write(f'#!/bin/bash\ncat > {marker}\n')
            os.chmod(os.path.join(scripts_dir, "on-error.sh"), 0o755)

            manager.run_step(1)

            assert not os.path.exists(marker), "on_error should not be called on success"


class TestLogicError:
    """Tests for per-block logic.error handler."""

    def test_logic_error_called_on_failure(self):
        """Per-block logic.error runs when block fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [{
                "name": "failing-block",
                "specialist": "spec-a",
                "prompt": "test",
                "depends_on": [],
                "logic": {"error": "scripts/block-error.sh"},
            }]

            manager, flow_dir = _make_manager_with_flow(tmpdir, blocks)

            scripts_dir = os.path.join(flow_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            marker = os.path.join(tmpdir, "block-error-called.json")
            with open(os.path.join(scripts_dir, "block-error.sh"), "w") as f:
                f.write(f'#!/bin/bash\ncat > {marker}\n')
            os.chmod(os.path.join(scripts_dir, "block-error.sh"), 0o755)

            manager.run_step(1)

            assert os.path.exists(marker), "logic.error handler was not called"
            with open(marker) as f:
                ctx = json.load(f)
            assert ctx["block_name"] == "failing-block"

    def test_logic_error_prevents_on_error(self):
        """If logic.error handles it, on_error is NOT called."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [{
                "name": "failing-block",
                "specialist": "spec-a",
                "prompt": "test",
                "depends_on": [],
                "logic": {"error": "scripts/block-error.sh"},
            }]

            manager, flow_dir = _make_manager_with_flow(
                tmpdir, blocks, on_error="scripts/global-error.sh"
            )

            scripts_dir = os.path.join(flow_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)

            block_marker = os.path.join(tmpdir, "block-error.json")
            global_marker = os.path.join(tmpdir, "global-error.json")

            with open(os.path.join(scripts_dir, "block-error.sh"), "w") as f:
                f.write(f'#!/bin/bash\ncat > {block_marker}\n')
            os.chmod(os.path.join(scripts_dir, "block-error.sh"), 0o755)

            with open(os.path.join(scripts_dir, "global-error.sh"), "w") as f:
                f.write(f'#!/bin/bash\ncat > {global_marker}\n')
            os.chmod(os.path.join(scripts_dir, "global-error.sh"), 0o755)

            manager.run_step(1)

            assert os.path.exists(block_marker), "logic.error should be called"
            assert not os.path.exists(global_marker), "on_error should NOT be called when logic.error handled it"

    def test_on_error_fallback_when_logic_error_fails(self):
        """If logic.error script fails (non-zero), on_error runs as fallback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [{
                "name": "failing-block",
                "specialist": "spec-a",
                "prompt": "test",
                "depends_on": [],
                "logic": {"error": "scripts/bad-handler.sh"},
            }]

            manager, flow_dir = _make_manager_with_flow(
                tmpdir, blocks, on_error="scripts/global-error.sh"
            )

            scripts_dir = os.path.join(flow_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)

            global_marker = os.path.join(tmpdir, "global-error.json")

            # logic.error script that fails
            with open(os.path.join(scripts_dir, "bad-handler.sh"), "w") as f:
                f.write('#!/bin/bash\nexit 1\n')
            os.chmod(os.path.join(scripts_dir, "bad-handler.sh"), 0o755)

            # on_error script that succeeds
            with open(os.path.join(scripts_dir, "global-error.sh"), "w") as f:
                f.write(f'#!/bin/bash\ncat > {global_marker}\n')
            os.chmod(os.path.join(scripts_dir, "global-error.sh"), 0o755)

            manager.run_step(1)

            assert os.path.exists(global_marker), "on_error should run as fallback"


class TestErrorHandlerLogging:
    """Tests for error handler log entries."""

    def test_error_handler_logged(self):
        """Error handler execution is logged in rein.log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [{"name": "a", "specialist": "spec-a",
                       "prompt": "test", "depends_on": []}]

            manager, flow_dir = _make_manager_with_flow(
                tmpdir, blocks, on_error="scripts/handler.sh"
            )

            scripts_dir = os.path.join(flow_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "handler.sh"), "w") as f:
                f.write('#!/bin/bash\ncat > /dev/null\n')
            os.chmod(os.path.join(scripts_dir, "handler.sh"), 0o755)

            manager.run_step(1)

            with open(manager.rein_log_file) as f:
                log = f.read()

            assert "ERROR HANDLER" in log
            assert "on_error" in log
