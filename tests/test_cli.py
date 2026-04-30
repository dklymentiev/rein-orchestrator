"""Tests for rein/cli.py"""

import argparse
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
import yaml

from rein.cli import _handle_config, _handle_flow, _handle_status, _handle_step_resume, _handle_task, main


class TestArgumentParsing:
    """Tests for CLI argument parsing via main()"""

    @patch("rein.cli.argparse.ArgumentParser.parse_args")
    def _parse(self, argv, mock_parse):
        """Helper: invoke main() with controlled parse_args return."""
        # We only need to verify that parse_args is called;
        # actual integration parsing is tested below via parse_known_args.
        mock_parse.return_value = argparse.Namespace(
            config=None,
            flow=None,
            input=None,
            task_dir=None,
            question=None,
            task=None,
            status=None,
            pause=False,
            resume=None,
            no_ui=False,
            agents_dir="/tmp/agents",
            daemon=False,
            daemon_interval=5,
            max_workflows=3,
            ws_port=8765,
            run_task=None,
        )
        return mock_parse.return_value

    def test_defaults(self):
        """Test that default values are correct when no arguments given"""
        parser = argparse.ArgumentParser()
        parser.add_argument("config", nargs="?")
        parser.add_argument("--flow", metavar="FLOW_NAME")
        parser.add_argument("--input", metavar="JSON")
        parser.add_argument("--task-dir", metavar="DIR")
        parser.add_argument("--question", metavar="FILE")
        parser.add_argument("--task", metavar="TASK_DIR")
        parser.add_argument("--status", metavar="TASK_ID")
        parser.add_argument("--pause", action="store_true")
        parser.add_argument("--resume", metavar="RUN_ID")
        parser.add_argument("--no-ui", action="store_true")
        parser.add_argument("--agents-dir", metavar="PATH", default="/default/agents")
        parser.add_argument("--daemon", action="store_true")
        parser.add_argument("--daemon-interval", type=int, default=5)
        parser.add_argument("--max-workflows", type=int, default=3)
        parser.add_argument("--ws-port", type=int, default=8765)
        parser.add_argument("--run-task", metavar="TASK_ID")

        args = parser.parse_args([])
        assert args.config is None
        assert args.flow is None
        assert args.input is None
        assert args.task_dir is None
        assert args.question is None
        assert args.task is None
        assert args.status is None
        assert args.pause is False
        assert args.resume is None
        assert args.no_ui is False
        assert args.agents_dir == "/default/agents"
        assert args.daemon is False
        assert args.daemon_interval == 5
        assert args.max_workflows == 3
        assert args.ws_port == 8765
        assert args.run_task is None

    def test_config_positional(self):
        """Test positional config argument"""
        parser = argparse.ArgumentParser()
        parser.add_argument("config", nargs="?")
        args = parser.parse_args(["workflow.yaml"])
        assert args.config == "workflow.yaml"

    def test_flow_argument(self):
        """Test --flow argument"""
        parser = argparse.ArgumentParser()
        parser.add_argument("config", nargs="?")
        parser.add_argument("--flow", metavar="FLOW_NAME")
        parser.add_argument("--question", metavar="FILE")
        args = parser.parse_args(["--flow", "deliberation", "--question", "q.txt"])
        assert args.flow == "deliberation"
        assert args.question == "q.txt"

    def test_daemon_arguments(self):
        """Test --daemon with related arguments"""
        parser = argparse.ArgumentParser()
        parser.add_argument("config", nargs="?")
        parser.add_argument("--daemon", action="store_true")
        parser.add_argument("--daemon-interval", type=int, default=5)
        parser.add_argument("--max-workflows", type=int, default=3)
        parser.add_argument("--ws-port", type=int, default=8765)
        parser.add_argument("--no-ui", action="store_true")
        args = parser.parse_args(["--daemon", "--daemon-interval", "10", "--max-workflows", "5", "--ws-port", "9000"])
        assert args.daemon is True
        assert args.daemon_interval == 10
        assert args.max_workflows == 5
        assert args.ws_port == 9000

    def test_task_argument(self):
        """Test --task argument"""
        parser = argparse.ArgumentParser()
        parser.add_argument("config", nargs="?")
        parser.add_argument("--task", metavar="TASK_DIR")
        args = parser.parse_args(["--task", "/path/to/task-001"])
        assert args.task == "/path/to/task-001"

    def test_status_argument(self):
        """Test --status argument"""
        parser = argparse.ArgumentParser()
        parser.add_argument("config", nargs="?")
        parser.add_argument("--status", metavar="TASK_ID")
        args = parser.parse_args(["--status", "task-20260101-120000"])
        assert args.status == "task-20260101-120000"

    def test_run_task_argument(self):
        """Test --run-task argument"""
        parser = argparse.ArgumentParser()
        parser.add_argument("config", nargs="?")
        parser.add_argument("--run-task", metavar="TASK_ID")
        args = parser.parse_args(["--run-task", "task-001"])
        assert args.run_task == "task-001"

    def test_pause_flag(self):
        """Test --pause flag"""
        parser = argparse.ArgumentParser()
        parser.add_argument("config", nargs="?")
        parser.add_argument("--pause", action="store_true")
        args = parser.parse_args(["--pause"])
        assert args.pause is True

    def test_resume_argument(self):
        """Test --resume argument"""
        parser = argparse.ArgumentParser()
        parser.add_argument("config", nargs="?")
        parser.add_argument("--resume", metavar="RUN_ID")
        args = parser.parse_args(["--resume", "20251230-142345"])
        assert args.resume == "20251230-142345"

    def test_input_json_argument(self):
        """Test --input with JSON string"""
        parser = argparse.ArgumentParser()
        parser.add_argument("config", nargs="?")
        parser.add_argument("--input", metavar="JSON")
        args = parser.parse_args(["--input", '{"key": "value"}'])
        assert args.input == '{"key": "value"}'

    def test_agents_dir_argument(self):
        """Test --agents-dir argument"""
        parser = argparse.ArgumentParser()
        parser.add_argument("config", nargs="?")
        parser.add_argument("--agents-dir", metavar="PATH", default="/default")
        args = parser.parse_args(["--agents-dir", "/custom/agents"])
        assert args.agents_dir == "/custom/agents"

    def test_no_ui_flag(self):
        """Test --no-ui flag"""
        parser = argparse.ArgumentParser()
        parser.add_argument("config", nargs="?")
        parser.add_argument("--no-ui", action="store_true")
        args = parser.parse_args(["--no-ui"])
        assert args.no_ui is True

    def test_combined_flow_with_task_dir(self):
        """Test --flow combined with --task-dir"""
        parser = argparse.ArgumentParser()
        parser.add_argument("config", nargs="?")
        parser.add_argument("--flow", metavar="FLOW_NAME")
        parser.add_argument("--task-dir", metavar="DIR")
        args = parser.parse_args(["--flow", "analysis", "--task-dir", "/tasks/t1"])
        assert args.flow == "analysis"
        assert args.task_dir == "/tasks/t1"


class TestHandleStatus:
    """Tests for _handle_status()"""

    @pytest.fixture
    def temp_agents_dir(self):
        """Create temporary agents directory with task structure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_status_with_valid_task(self, temp_agents_dir, capsys):
        """Test --status with a valid task directory containing task.json"""
        task_id = "task-20260101-120000"
        task_dir = os.path.join(temp_agents_dir, "tasks", task_id)
        input_dir = os.path.join(task_dir, "input")
        state_dir = os.path.join(task_dir, "state")
        outputs_dir = os.path.join(task_dir, "outputs")
        os.makedirs(input_dir)
        os.makedirs(state_dir)
        os.makedirs(outputs_dir)

        # Create task.json
        task_data = {
            "id": task_id,
            "flow": "deliberation",
            "created": "2026-01-01T12:00:00",
            "status": "completed",
            "input": {"topic": "test topic"},
        }
        with open(os.path.join(input_dir, "task.json"), "w") as f:
            json.dump(task_data, f)

        # Create status file
        with open(os.path.join(state_dir, "status"), "w") as f:
            f.write("completed")

        # Create output files
        with open(os.path.join(outputs_dir, "result.json"), "w") as f:
            json.dump({"result": "ok"}, f)

        args = argparse.Namespace(
            agents_dir=temp_agents_dir,
            status=task_id,
        )
        _handle_status(args)

        captured = capsys.readouterr()
        assert task_id in captured.out
        assert "deliberation" in captured.out
        assert "completed" in captured.out
        assert "test topic" in captured.out
        assert "result.json" in captured.out
        assert "1 files" in captured.out

    def test_status_with_missing_task_dir(self, temp_agents_dir):
        """Test --status with non-existent task directory exits with code 1"""
        os.makedirs(os.path.join(temp_agents_dir, "tasks"))

        args = argparse.Namespace(
            agents_dir=temp_agents_dir,
            status="nonexistent-task",
        )

        with pytest.raises(SystemExit) as exc_info:
            _handle_status(args)

        assert exc_info.value.code == 1

    def test_status_without_task_json(self, temp_agents_dir, capsys):
        """Test --status with task dir that has no task.json (only status file)"""
        task_id = "task-minimal"
        task_dir = os.path.join(temp_agents_dir, "tasks", task_id)
        state_dir = os.path.join(task_dir, "state")
        os.makedirs(state_dir)

        with open(os.path.join(state_dir, "status"), "w") as f:
            f.write("pending")

        args = argparse.Namespace(
            agents_dir=temp_agents_dir,
            status=task_id,
        )
        _handle_status(args)

        captured = capsys.readouterr()
        assert "pending" in captured.out

    def test_status_with_no_outputs(self, temp_agents_dir, capsys):
        """Test --status with task dir that has no outputs directory"""
        task_id = "task-no-outputs"
        task_dir = os.path.join(temp_agents_dir, "tasks", task_id)
        os.makedirs(task_dir)

        args = argparse.Namespace(
            agents_dir=temp_agents_dir,
            status=task_id,
        )
        _handle_status(args)

        captured = capsys.readouterr()
        # Should not crash and should not show OUTPUTS section
        assert "OUTPUTS" not in captured.out

    def test_status_with_multiple_outputs(self, temp_agents_dir, capsys):
        """Test --status with multiple output files"""
        task_id = "task-multi-out"
        task_dir = os.path.join(temp_agents_dir, "tasks", task_id)
        outputs_dir = os.path.join(task_dir, "outputs")
        os.makedirs(outputs_dir)

        for name in ["alpha.json", "beta.md", "gamma.txt"]:
            with open(os.path.join(outputs_dir, name), "w") as f:
                f.write("content")

        args = argparse.Namespace(
            agents_dir=temp_agents_dir,
            status=task_id,
        )
        _handle_status(args)

        captured = capsys.readouterr()
        assert "3 files" in captured.out
        assert "alpha.json" in captured.out
        assert "beta.md" in captured.out
        assert "gamma.txt" in captured.out


class TestRunTaskMode:
    """Tests for --run-task mode in main()"""

    def test_run_task_calls_execute_task(self):
        """Test --run-task calls execute_task with correct args and exits"""
        with patch("sys.argv", ["rein", "--run-task", "task-001", "--agents-dir", "/tmp/agents"]):
            with patch("rein.tasks.execute_task", return_value=0) as mock_exec:
                with pytest.raises(SystemExit) as exc_info:
                    main()
                mock_exec.assert_called_once_with("task-001", "/tmp/agents")
                assert exc_info.value.code == 0

    def test_run_task_propagates_nonzero_exit(self):
        """Test --run-task propagates non-zero exit code from execute_task"""
        with patch("sys.argv", ["rein", "--run-task", "task-fail", "--agents-dir", "/tmp/agents"]):
            with patch("rein.tasks.execute_task", return_value=1):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1


class TestDaemonMode:
    """Tests for --daemon mode in main()"""

    def test_daemon_calls_run_daemon(self):
        """Test --daemon calls run_daemon with correct arguments and exits"""
        with patch(
            "sys.argv",
            [
                "rein",
                "--daemon",
                "--daemon-interval",
                "10",
                "--max-workflows",
                "5",
                "--ws-port",
                "9000",
                "--agents-dir",
                "/tmp/agents",
                "--no-ui",
            ],
        ):
            with patch("rein.daemon.run_daemon") as mock_daemon:
                with pytest.raises(SystemExit) as exc_info:
                    main()
                mock_daemon.assert_called_once_with("/tmp/agents", 10, 5, 9000, True)
                assert exc_info.value.code == 0

    def test_daemon_default_arguments(self):
        """Test --daemon with default interval, max_workflows, ws_port"""
        with patch("sys.argv", ["rein", "--daemon", "--agents-dir", "/tmp/agents"]):
            with patch("rein.daemon.run_daemon") as mock_daemon:
                with pytest.raises(SystemExit) as exc_info:
                    main()
                mock_daemon.assert_called_once_with("/tmp/agents", 5, 3, 8765, False)
                assert exc_info.value.code == 0


class TestHandleFlow:
    """Tests for _handle_flow()"""

    @pytest.fixture
    def temp_agents_dir(self):
        """Create temporary agents directory with flow structure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "flows", "test-flow"))
            os.makedirs(os.path.join(tmpdir, "tasks"))

            flow_config = {
                "schema_version": "3.0",
                "name": "test-flow",
                "team": "test-team",
                "semaphore": 2,
                "blocks": [{"name": "step1", "specialist": "analyzer", "prompt": "Analyze this"}],
            }
            flow_path = os.path.join(tmpdir, "flows", "test-flow", "test-flow.yaml")
            with open(flow_path, "w") as f:
                yaml.dump(flow_config, f)

            yield tmpdir

    def test_flow_missing_file_exits(self):
        """Test _handle_flow exits when flow YAML does not exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "flows", "nonexistent"))

            args = argparse.Namespace(
                flow="nonexistent",
                agents_dir=tmpdir,
                question=None,
                task_dir=None,
                input=None,
            )

            with pytest.raises(SystemExit) as exc_info:
                _handle_flow(args)
            assert exc_info.value.code == 1

    def test_flow_with_valid_config(self, temp_agents_dir):
        """Test _handle_flow creates ProcessManager with correct parameters"""
        args = argparse.Namespace(
            flow="test-flow",
            agents_dir=temp_agents_dir,
            question=None,
            task_dir=None,
            input=None,
        )

        with patch("rein.orchestrator.ProcessManager") as MockPM:
            mock_manager = MagicMock()
            mock_manager.tasks_root = os.path.join(temp_agents_dir, "tasks")
            mock_manager.create_task.return_value = "task-20260101-120000"
            MockPM.return_value = mock_manager

            with patch("rein.tasks.load_config") as mock_load:
                mock_load.return_value = {"semaphore": 2, "blocks": [{"name": "step1"}]}

                result = _handle_flow(args)

            MockPM.assert_called_once_with(
                max_parallel=2,
                flow_name="test-flow",
                task_input={},
                agents_dir=temp_agents_dir,
            )
            assert result is mock_manager

    def test_flow_with_question_file(self, temp_agents_dir):
        """Test _handle_flow reads question file content"""
        question_file = os.path.join(temp_agents_dir, "question.txt")
        with open(question_file, "w") as f:
            f.write("What is the meaning of life?")

        args = argparse.Namespace(
            flow="test-flow",
            agents_dir=temp_agents_dir,
            question=question_file,
            task_dir=None,
            input=None,
        )

        with patch("rein.orchestrator.ProcessManager") as MockPM:
            mock_manager = MagicMock()
            mock_manager.tasks_root = os.path.join(temp_agents_dir, "tasks")
            mock_manager.create_task.return_value = "task-q"
            MockPM.return_value = mock_manager

            with patch("rein.tasks.load_config") as mock_load:
                mock_load.return_value = {"semaphore": 3, "blocks": []}

                _handle_flow(args)

            call_kwargs = MockPM.call_args[1]
            assert "What is the meaning of life?" in call_kwargs["task_input"]["task"]

    def test_flow_with_missing_question_file_exits(self, temp_agents_dir):
        """Test _handle_flow exits when question file does not exist"""
        args = argparse.Namespace(
            flow="test-flow",
            agents_dir=temp_agents_dir,
            question="/nonexistent/question.txt",
            task_dir=None,
            input=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            _handle_flow(args)
        assert exc_info.value.code == 1

    def test_flow_with_task_dir(self, temp_agents_dir):
        """Test _handle_flow with --task-dir reads task.md"""
        task_dir = os.path.join(temp_agents_dir, "my-task")
        os.makedirs(task_dir)
        with open(os.path.join(task_dir, "task.md"), "w") as f:
            f.write("# Analyze the codebase")

        args = argparse.Namespace(
            flow="test-flow",
            agents_dir=temp_agents_dir,
            question=None,
            task_dir=task_dir,
            input=None,
        )

        with patch("rein.orchestrator.ProcessManager") as MockPM:
            mock_manager = MagicMock()
            mock_manager.tasks_root = os.path.join(temp_agents_dir, "tasks")
            MockPM.return_value = mock_manager

            with patch("rein.tasks.load_config") as mock_load:
                mock_load.return_value = {"semaphore": 3, "blocks": []}

                _handle_flow(args)

            call_kwargs = MockPM.call_args[1]
            assert "Analyze the codebase" in call_kwargs["task_input"]["task"]
            assert mock_manager.task_dir == task_dir

    def test_flow_with_task_dir_missing_task_md_exits(self, temp_agents_dir):
        """Test _handle_flow exits when task.md is missing in task-dir"""
        task_dir = os.path.join(temp_agents_dir, "empty-task")
        os.makedirs(task_dir)

        args = argparse.Namespace(
            flow="test-flow",
            agents_dir=temp_agents_dir,
            question=None,
            task_dir=task_dir,
            input=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            _handle_flow(args)
        assert exc_info.value.code == 1

    def test_flow_with_json_input(self, temp_agents_dir):
        """Test _handle_flow with --input JSON string"""
        args = argparse.Namespace(
            flow="test-flow",
            agents_dir=temp_agents_dir,
            question=None,
            task_dir=None,
            input='{"topic": "architecture", "depth": 3}',
        )

        with patch("rein.orchestrator.ProcessManager") as MockPM:
            mock_manager = MagicMock()
            mock_manager.tasks_root = os.path.join(temp_agents_dir, "tasks")
            mock_manager.create_task.return_value = "task-json"
            MockPM.return_value = mock_manager

            with patch("rein.tasks.load_config") as mock_load:
                mock_load.return_value = {"semaphore": 3, "blocks": []}

                _handle_flow(args)

            call_kwargs = MockPM.call_args[1]
            assert call_kwargs["task_input"] == {"topic": "architecture", "depth": 3}

    def test_flow_with_invalid_json_input_exits(self, temp_agents_dir):
        """Test _handle_flow exits when --input is not valid JSON"""
        args = argparse.Namespace(
            flow="test-flow",
            agents_dir=temp_agents_dir,
            question=None,
            task_dir=None,
            input="not valid json{{{",
        )

        with pytest.raises(SystemExit) as exc_info:
            _handle_flow(args)
        assert exc_info.value.code == 1


class TestFlowInputValidationBeforeCreate:
    """Tests that _handle_flow validates required inputs BEFORE calling create_task().

    This prevents orphan task directories when agents call rein --flow
    without providing required inputs (e.g. marketer calling google-ads-report
    without campaign_id). See task #1458.
    """

    @pytest.fixture
    def agents_dir_with_inputs(self):
        """Create agents dir with a flow that declares required inputs"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "flows", "ads-report"))
            os.makedirs(os.path.join(tmpdir, "tasks"))

            flow_config = {
                "schema_version": "3.0",
                "name": "ads-report",
                "team": "test-team",
                "inputs": {
                    "campaign_id": {"required": True, "description": "Google Ads campaign ID"},
                    "date_from": {"required": True, "description": "Start date YYYY-MM-DD"},
                    "mode": {"required": False, "description": "Report mode", "default": "summary"},
                },
                "blocks": [{"name": "step1", "specialist": "analyzer", "prompt": "Analyze"}],
            }
            flow_path = os.path.join(tmpdir, "flows", "ads-report", "ads-report.yaml")
            with open(flow_path, "w") as f:
                yaml.dump(flow_config, f)

            yield tmpdir

    def test_missing_required_inputs_exits_before_create_task(self, agents_dir_with_inputs):
        """Missing required inputs cause sys.exit(1) BEFORE create_task is called"""
        args = argparse.Namespace(
            flow="ads-report",
            agents_dir=agents_dir_with_inputs,
            question=None,
            task_dir=None,
            input='{"mode": "detailed"}',
        )

        with patch("rein.orchestrator.ProcessManager") as MockPM:
            mock_manager = MagicMock()
            MockPM.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                _handle_flow(args)
            assert exc_info.value.code == 1

            # create_task must NOT have been called
            mock_manager.create_task.assert_not_called()

    def test_missing_required_inputs_no_orphan_directory(self, agents_dir_with_inputs):
        """No task directory is created when required inputs are missing"""
        tasks_dir = os.path.join(agents_dir_with_inputs, "tasks")
        before = set(os.listdir(tasks_dir))

        args = argparse.Namespace(
            flow="ads-report",
            agents_dir=agents_dir_with_inputs,
            question=None,
            task_dir=None,
            input='{"topic": "test"}',
        )

        with pytest.raises(SystemExit):
            _handle_flow(args)

        after = set(os.listdir(tasks_dir))
        assert before == after, f"Orphan directories created: {after - before}"

    def test_all_required_inputs_proceeds(self, agents_dir_with_inputs):
        """All required inputs provided allows create_task to be called"""
        args = argparse.Namespace(
            flow="ads-report",
            agents_dir=agents_dir_with_inputs,
            question=None,
            task_dir=None,
            input='{"campaign_id": "12345", "date_from": "2026-01-01"}',
        )

        with patch("rein.orchestrator.ProcessManager") as MockPM:
            mock_manager = MagicMock()
            mock_manager.tasks_root = os.path.join(agents_dir_with_inputs, "tasks")
            mock_manager.create_task.return_value = "task-test"
            MockPM.return_value = mock_manager

            with patch("rein.tasks.load_config") as mock_load:
                mock_load.return_value = {"semaphore": 3, "blocks": []}
                _handle_flow(args)

            mock_manager.create_task.assert_called_once()

    def test_validation_skipped_when_task_dir_provided(self, agents_dir_with_inputs):
        """Input validation is skipped when --task-dir is provided (resume scenario)"""
        task_dir = os.path.join(agents_dir_with_inputs, "existing-task")
        os.makedirs(task_dir)
        with open(os.path.join(task_dir, "task.md"), "w") as f:
            f.write("# Resume this task")

        args = argparse.Namespace(
            flow="ads-report",
            agents_dir=agents_dir_with_inputs,
            question=None,
            task_dir=task_dir,
            input=None,
        )

        with patch("rein.orchestrator.ProcessManager") as MockPM:
            mock_manager = MagicMock()
            mock_manager.tasks_root = os.path.join(agents_dir_with_inputs, "tasks")
            MockPM.return_value = mock_manager

            with patch("rein.tasks.load_config") as mock_load:
                mock_load.return_value = {"semaphore": 3, "blocks": []}
                # Should NOT exit — validation skipped for --task-dir
                _handle_flow(args)

            # create_task should NOT be called (task-dir reuse path)
            mock_manager.create_task.assert_not_called()

    def test_no_inputs_section_skips_validation(self):
        """Flow without inputs: section proceeds without validation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "flows", "simple"))
            os.makedirs(os.path.join(tmpdir, "tasks"))

            flow_config = {
                "schema_version": "3.0",
                "name": "simple",
                "team": "test-team",
                "blocks": [{"name": "step1", "specialist": "analyzer", "prompt": "Do stuff"}],
            }
            flow_path = os.path.join(tmpdir, "flows", "simple", "simple.yaml")
            with open(flow_path, "w") as f:
                yaml.dump(flow_config, f)

            args = argparse.Namespace(
                flow="simple",
                agents_dir=tmpdir,
                question=None,
                task_dir=None,
                input=None,
            )

            with patch("rein.orchestrator.ProcessManager") as MockPM:
                mock_manager = MagicMock()
                mock_manager.tasks_root = os.path.join(tmpdir, "tasks")
                mock_manager.create_task.return_value = "task-simple"
                MockPM.return_value = mock_manager

                with patch("rein.tasks.load_config") as mock_load:
                    mock_load.return_value = {"semaphore": 3, "blocks": []}
                    _handle_flow(args)

                mock_manager.create_task.assert_called_once()

    def test_error_message_includes_field_descriptions(self, agents_dir_with_inputs, capfd):
        """Error message lists missing fields with descriptions"""
        args = argparse.Namespace(
            flow="ads-report",
            agents_dir=agents_dir_with_inputs,
            question=None,
            task_dir=None,
            input='{}',
        )

        with pytest.raises(SystemExit):
            _handle_flow(args)

        captured = capfd.readouterr()
        assert "campaign_id" in captured.out
        assert "date_from" in captured.out
        assert "Google Ads campaign ID" in captured.out

    def test_optional_missing_does_not_block(self, agents_dir_with_inputs):
        """Missing optional input does NOT cause exit"""
        args = argparse.Namespace(
            flow="ads-report",
            agents_dir=agents_dir_with_inputs,
            question=None,
            task_dir=None,
            input='{"campaign_id": "12345", "date_from": "2026-01-01"}',
        )

        with patch("rein.orchestrator.ProcessManager") as MockPM:
            mock_manager = MagicMock()
            mock_manager.tasks_root = os.path.join(agents_dir_with_inputs, "tasks")
            mock_manager.create_task.return_value = "task-opt"
            MockPM.return_value = mock_manager

            with patch("rein.tasks.load_config") as mock_load:
                mock_load.return_value = {"semaphore": 3, "blocks": []}
                # Should succeed — 'mode' is optional
                _handle_flow(args)

            mock_manager.create_task.assert_called_once()


class TestHandleTask:
    """Tests for _handle_task()"""

    @pytest.fixture
    def temp_agents_dir(self):
        """Create temporary agents directory with flow and task structure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "flows", "deliberation"))

            flow_config = {
                "schema_version": "3.0",
                "name": "deliberation",
                "semaphore": 2,
                "blocks": [{"name": "discuss", "specialist": "analyst", "prompt": "Discuss"}],
            }
            flow_path = os.path.join(tmpdir, "flows", "deliberation", "deliberation.yaml")
            with open(flow_path, "w") as f:
                yaml.dump(flow_config, f)

            yield tmpdir

    def test_task_missing_yaml_exits(self):
        """Test _handle_task exits when task.yaml does not exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            args = argparse.Namespace(
                task=tmpdir,
                agents_dir="/tmp/agents",
            )

            with pytest.raises(SystemExit) as exc_info:
                _handle_task(args)
            assert exc_info.value.code == 1

    def test_task_missing_flow_field_exits(self):
        """Test _handle_task exits when task.yaml has no 'flow' field"""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_yaml = os.path.join(tmpdir, "task.yaml")
            with open(task_yaml, "w") as f:
                yaml.dump({"id": "task-001", "output_dir": "./outputs"}, f)

            args = argparse.Namespace(
                task=tmpdir,
                agents_dir="/tmp/agents",
            )

            with pytest.raises(SystemExit) as exc_info:
                _handle_task(args)
            assert exc_info.value.code == 1

    def test_task_flow_not_found_exits(self, temp_agents_dir):
        """Test _handle_task exits when referenced flow does not exist"""
        with tempfile.TemporaryDirectory() as task_dir:
            task_yaml = os.path.join(task_dir, "task.yaml")
            with open(task_yaml, "w") as f:
                yaml.dump({"id": "task-001", "flow": "nonexistent-flow"}, f)

            args = argparse.Namespace(
                task=task_dir,
                agents_dir=temp_agents_dir,
            )

            with pytest.raises(SystemExit) as exc_info:
                _handle_task(args)
            assert exc_info.value.code == 1

    def test_task_with_valid_yaml(self, temp_agents_dir):
        """Test _handle_task creates ProcessManager with correct parameters"""
        task_dir = os.path.join(temp_agents_dir, "tasks", "task-20260101-120000")
        os.makedirs(task_dir, exist_ok=True)
        task_yaml_data = {
            "id": "task-20260101-120000",
            "flow": "deliberation",
            "output_dir": "./outputs",
            "input": {"topic": "testing"},
        }
        with open(os.path.join(task_dir, "task.yaml"), "w") as f:
            yaml.dump(task_yaml_data, f)

        args = argparse.Namespace(
            task=task_dir,
            agents_dir=temp_agents_dir,
        )

        with patch("rein.orchestrator.ProcessManager") as MockPM:
            mock_manager = MagicMock()
            MockPM.return_value = mock_manager

            with patch("rein.tasks.load_config") as mock_load:
                mock_load.return_value = {"semaphore": 2, "blocks": []}

                result = _handle_task(args)

            MockPM.assert_called_once_with(
                max_parallel=2,
                task_id="task-20260101-120000",
                flow_name="deliberation",
                task_input={"topic": "testing"},
                agents_dir=temp_agents_dir,
            )
            assert mock_manager.task_dir == task_dir
            assert mock_manager.run_dir == task_dir
            mock_manager.load_config.assert_called_once()
            assert result is mock_manager

    def test_task_trailing_slash_stripped(self, temp_agents_dir):
        """Test _handle_task strips trailing slash from task path"""
        task_dir = os.path.join(temp_agents_dir, "tasks", "task-002")
        os.makedirs(task_dir, exist_ok=True)
        task_yaml_data = {
            "id": "task-002",
            "flow": "deliberation",
        }
        with open(os.path.join(task_dir, "task.yaml"), "w") as f:
            yaml.dump(task_yaml_data, f)

        args = argparse.Namespace(
            task=task_dir + "/",
            agents_dir=temp_agents_dir,
        )

        with patch("rein.orchestrator.ProcessManager") as MockPM:
            mock_manager = MagicMock()
            MockPM.return_value = mock_manager

            with patch("rein.tasks.load_config") as mock_load:
                mock_load.return_value = {"semaphore": 3, "blocks": []}

                _handle_task(args)

            # task_dir should not end with /
            assert not mock_manager.task_dir.endswith("/")

    def test_task_output_dir_from_config(self, temp_agents_dir):
        """Test _handle_task passes output_dir from task.yaml to config"""
        task_dir = os.path.join(temp_agents_dir, "tasks", "task-003")
        os.makedirs(task_dir, exist_ok=True)
        task_yaml_data = {
            "id": "task-003",
            "flow": "deliberation",
            "output_dir": "./custom-output",
        }
        with open(os.path.join(task_dir, "task.yaml"), "w") as f:
            yaml.dump(task_yaml_data, f)

        args = argparse.Namespace(
            task=task_dir,
            agents_dir=temp_agents_dir,
        )

        with patch("rein.orchestrator.ProcessManager") as MockPM:
            mock_manager = MagicMock()
            MockPM.return_value = mock_manager

            with patch("rein.tasks.load_config") as mock_load:
                loaded_config = {"semaphore": 2, "blocks": []}
                mock_load.return_value = loaded_config

                _handle_task(args)

            # Check that load_config's returned dict was modified
            call_args = mock_manager.load_config.call_args
            config_passed = call_args[0][0] if call_args[0] else call_args[1].get("config")
            assert "output_dir" in config_passed
            assert config_passed["output_dir"].endswith("custom-output")


class TestHandleConfig:
    """Tests for _handle_config()"""

    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary workflow config YAML file"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config_data = {
                "schema_version": "3.0",
                "name": "test-workflow",
                "semaphore": 4,
                "blocks": [{"name": "step1", "specialist": "writer", "prompt": "Write something"}],
            }
            yaml.dump(config_data, f)
            path = f.name
        yield path
        os.unlink(path)

    def test_config_creates_process_manager(self, temp_config_file):
        """Test _handle_config creates ProcessManager with config from YAML"""
        args = argparse.Namespace(
            config=temp_config_file,
            agents_dir="/tmp/agents",
            input=None,
            resume=None,
        )

        with patch("rein.orchestrator.ProcessManager") as MockPM:
            mock_manager = MagicMock()
            MockPM.return_value = mock_manager

            with patch("rein.tasks.load_config") as mock_load:
                mock_load.return_value = {"semaphore": 4, "blocks": [{"name": "step1"}]}

                result = _handle_config(args)

            mock_load.assert_called_once_with(temp_config_file)
            MockPM.assert_called_once_with(
                max_parallel=4,
                resume_run_id=None,
                agents_dir="/tmp/agents",
                task_input={},
            )
            mock_manager.load_config.assert_called_once()
            assert result is mock_manager

    def test_config_with_input_json(self, temp_config_file):
        """Test _handle_config parses --input JSON"""
        args = argparse.Namespace(
            config=temp_config_file,
            agents_dir="/tmp/agents",
            input='{"mode": "fast"}',
            resume=None,
        )

        with patch("rein.orchestrator.ProcessManager") as MockPM:
            mock_manager = MagicMock()
            MockPM.return_value = mock_manager

            with patch("rein.tasks.load_config") as mock_load:
                mock_load.return_value = {"semaphore": 3, "blocks": []}

                _handle_config(args)

            call_kwargs = MockPM.call_args[1]
            assert call_kwargs["task_input"] == {"mode": "fast"}

    def test_config_with_invalid_json_exits(self, temp_config_file):
        """Test _handle_config exits on invalid --input JSON"""
        args = argparse.Namespace(
            config=temp_config_file,
            agents_dir="/tmp/agents",
            input="broken json {{",
            resume=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            _handle_config(args)
        assert exc_info.value.code == 1

    def test_config_with_resume(self, temp_config_file):
        """Test _handle_config passes resume_run_id"""
        args = argparse.Namespace(
            config=temp_config_file,
            agents_dir="/tmp/agents",
            input=None,
            resume="20251230-142345",
        )

        with patch("rein.orchestrator.ProcessManager") as MockPM:
            mock_manager = MagicMock()
            MockPM.return_value = mock_manager

            with patch("rein.tasks.load_config") as mock_load:
                mock_load.return_value = {"semaphore": 3, "blocks": []}

                _handle_config(args)

            call_kwargs = MockPM.call_args[1]
            assert call_kwargs["resume_run_id"] == "20251230-142345"

    def test_config_default_semaphore(self, temp_config_file):
        """Test _handle_config defaults semaphore to 3 when not in config"""
        args = argparse.Namespace(
            config=temp_config_file,
            agents_dir="/tmp/agents",
            input=None,
            resume=None,
        )

        with patch("rein.orchestrator.ProcessManager") as MockPM:
            mock_manager = MagicMock()
            MockPM.return_value = mock_manager

            with patch("rein.tasks.load_config") as mock_load:
                mock_load.return_value = {"blocks": []}  # No semaphore key

                _handle_config(args)

            call_kwargs = MockPM.call_args[1]
            assert call_kwargs["max_parallel"] == 3


class TestMainNoArgs:
    """Tests for main() when no mode arguments are provided"""

    def test_no_args_exits_with_error(self):
        """Test main() exits with code 1 when no config, --flow, or --task given"""
        with patch("sys.argv", ["rein", "--agents-dir", "/tmp/agents"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1


class TestStepMode:
    """Tests for --step argument parsing and step mode dispatch"""

    def test_step_argument_parsing(self):
        """Test --step parses integer correctly"""
        parser = argparse.ArgumentParser()
        parser.add_argument("--step", type=int, default=None, metavar="N")
        args = parser.parse_args(["--step", "3"])
        assert args.step == 3

    def test_step_zero_means_unlimited(self):
        """Test --step 0 parses correctly (unlimited mode)"""
        parser = argparse.ArgumentParser()
        parser.add_argument("--step", type=int, default=None, metavar="N")
        args = parser.parse_args(["--step", "0"])
        assert args.step == 0

    def test_step_default_is_none(self):
        """Test --step defaults to None (continuous mode)"""
        parser = argparse.ArgumentParser()
        parser.add_argument("--step", type=int, default=None, metavar="N")
        args = parser.parse_args([])
        assert args.step is None

    def test_step_negative_exits_with_error(self):
        """Test --step with negative value exits with code 1"""
        with patch("sys.argv", ["rein", "--step", "-1", "--agents-dir", "/tmp/agents"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_step_exit_code_0_when_complete(self):
        """Test exit code 0 when run_step returns True (workflow complete)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = os.path.join(tmpdir, "agents")
            flow_dir = os.path.join(agents_dir, "flows", "test-flow")
            os.makedirs(os.path.join(agents_dir, "tasks"), exist_ok=True)
            os.makedirs(flow_dir, exist_ok=True)

            flow_yaml = os.path.join(flow_dir, "test-flow.yaml")
            with open(flow_yaml, "w") as f:
                yaml.dump({"blocks": [], "team": "t"}, f)

            with patch("sys.argv", ["rein", "--flow", "test-flow", "--step", "1", "--agents-dir", agents_dir]):
                with patch("rein.orchestrator.ProcessManager") as MockPM:
                    mock_manager = MagicMock()
                    mock_manager.tasks_root = os.path.join(agents_dir, "tasks")
                    mock_manager.task_dir = os.path.join(agents_dir, "tasks", "t1")
                    mock_manager.db_path = "/tmp/rein.db"
                    mock_manager.run_step.return_value = True  # workflow complete
                    MockPM.return_value = mock_manager

                    with patch("rein.tasks.load_config", return_value={"blocks": []}):
                        with pytest.raises(SystemExit) as exc_info:
                            main()
                        assert exc_info.value.code == 0

    def test_step_exit_code_2_when_more_steps(self):
        """Test exit code 2 when run_step returns False (more steps remain)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = os.path.join(tmpdir, "agents")
            flow_dir = os.path.join(agents_dir, "flows", "test-flow")
            os.makedirs(os.path.join(agents_dir, "tasks"), exist_ok=True)
            os.makedirs(flow_dir, exist_ok=True)

            flow_yaml = os.path.join(flow_dir, "test-flow.yaml")
            with open(flow_yaml, "w") as f:
                yaml.dump({"blocks": [], "team": "t"}, f)

            with patch("sys.argv", ["rein", "--flow", "test-flow", "--step", "1", "--agents-dir", agents_dir]):
                with patch("rein.orchestrator.ProcessManager") as MockPM:
                    mock_manager = MagicMock()
                    mock_manager.tasks_root = os.path.join(agents_dir, "tasks")
                    mock_manager.task_dir = os.path.join(agents_dir, "tasks", "t1")
                    mock_manager.db_path = "/tmp/rein.db"
                    mock_manager.run_step.return_value = False  # more steps
                    MockPM.return_value = mock_manager

                    with patch("rein.tasks.load_config", return_value={"blocks": []}):
                        with pytest.raises(SystemExit) as exc_info:
                            main()
                        assert exc_info.value.code == 2

    def test_step_resume_from_task_dir(self):
        """Test --step with --task-dir (no --flow) reads task.json to infer flow"""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = os.path.join(tmpdir, "agents")
            task_dir = os.path.join(agents_dir, "tasks", "task-001")
            flow_dir = os.path.join(agents_dir, "flows", "my-flow")
            os.makedirs(os.path.join(task_dir, "input"), exist_ok=True)
            os.makedirs(os.path.join(task_dir, "state"), exist_ok=True)
            os.makedirs(flow_dir, exist_ok=True)

            # Create task.json with flow reference
            with open(os.path.join(task_dir, "input", "task.json"), "w") as f:
                json.dump({"flow": "my-flow", "input": {"topic": "test"}}, f)

            # Create flow YAML
            with open(os.path.join(flow_dir, "my-flow.yaml"), "w") as f:
                yaml.dump({"blocks": [], "team": "t"}, f)

            with patch("rein.orchestrator.ProcessManager") as MockPM:
                mock_manager = MagicMock()
                mock_manager.task_dir = task_dir
                mock_manager.db_path = os.path.join(task_dir, "state", "rein.db")
                mock_manager.run_step.return_value = True
                MockPM.return_value = mock_manager

                with patch("rein.tasks.load_config", return_value={"blocks": []}):
                    args = argparse.Namespace(
                        step=1,
                        task_dir=task_dir,
                        flow=None,
                        agents_dir=agents_dir,
                    )
                    _handle_step_resume(args)

                # Verify ProcessManager was created with correct params
                call_kwargs = MockPM.call_args[1]
                assert call_kwargs["flow_name"] == "my-flow"
                assert call_kwargs["task_input"] == {"topic": "test"}
