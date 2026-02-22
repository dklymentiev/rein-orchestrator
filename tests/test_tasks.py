"""Tests for rein/tasks.py"""
import os
import json
import pytest
import tempfile
import yaml
from unittest.mock import patch, MagicMock

from rein.tasks import update_task_status, save_task_to_memory, load_config, execute_task


class TestUpdateTaskStatus:
    """Tests for update_task_status (deprecated no-op)"""

    def test_noop_with_valid_args(self):
        """Test that update_task_status does nothing with valid arguments"""
        result = update_task_status("/some/path", "completed")
        assert result is None

    def test_noop_with_kwargs(self):
        """Test that update_task_status does nothing even with extra kwargs"""
        result = update_task_status("/some/path", "failed", exit_code=1, message="error")
        assert result is None

    def test_noop_with_none_args(self):
        """Test that update_task_status does nothing with None arguments"""
        result = update_task_status(None, None)
        assert result is None


class TestSaveTaskToMemory:
    """Tests for save_task_to_memory"""

    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_empty_output_dir(self):
        """Test with None output_dir returns early"""
        # Should not raise, just return
        save_task_to_memory(None, {"guid": "test"})

    def test_empty_memory_config(self, temp_output_dir):
        """Test with None memory_config returns early"""
        save_task_to_memory(temp_output_dir, None)

    def test_both_args_none(self):
        """Test with both arguments None returns early"""
        save_task_to_memory(None, None)

    def test_empty_string_output_dir(self):
        """Test with empty string output_dir returns early"""
        save_task_to_memory("", {"guid": "test"})

    def test_empty_dict_memory_config(self, temp_output_dir):
        """Test with empty dict memory_config returns early"""
        save_task_to_memory(temp_output_dir, {})

    def test_no_json_files(self, temp_output_dir):
        """Test with output_dir containing no JSON files"""
        # Create a non-JSON file
        with open(os.path.join(temp_output_dir, "readme.txt"), "w") as f:
            f.write("not json")

        save_task_to_memory(temp_output_dir, {"guid": "test-guid"})

    def test_nonexistent_output_dir(self):
        """Test with nonexistent output_dir does not raise"""
        save_task_to_memory("/nonexistent/path/to/output", {"guid": "test-guid"})

    def test_json_files_no_mem_cli(self, temp_output_dir):
        """Test with JSON files but mem-cli not found"""
        # Create JSON files in output dir
        result_data = {"score": 95, "summary": "Test passed"}
        with open(os.path.join(temp_output_dir, "result.json"), "w") as f:
            json.dump(result_data, f)

        # Set REIN_MEM_CLI to a nonexistent path
        with patch.dict(os.environ, {"REIN_MEM_CLI": "/nonexistent/mem-cli.sh"}):
            save_task_to_memory(temp_output_dir, {"guid": "test-guid"})

    def test_invalid_json_files_skipped(self, temp_output_dir):
        """Test that invalid JSON files are skipped without error"""
        # Create invalid JSON file
        with open(os.path.join(temp_output_dir, "broken.json"), "w") as f:
            f.write("not valid json{{{")

        # Create valid JSON file
        with open(os.path.join(temp_output_dir, "valid.json"), "w") as f:
            json.dump({"key": "value"}, f)

        with patch.dict(os.environ, {"REIN_MEM_CLI": "/nonexistent/mem-cli.sh"}):
            save_task_to_memory(temp_output_dir, {"guid": "test-guid"})

    @patch("subprocess.run")
    def test_mem_cli_called_with_guid(self, mock_run, temp_output_dir):
        """Test that mem-cli is called when guid is provided and CLI exists"""
        # Create JSON file
        with open(os.path.join(temp_output_dir, "output.json"), "w") as f:
            json.dump({"result": "success"}, f)

        # Create a fake mem-cli script
        mem_cli_path = os.path.join(temp_output_dir, "mem-cli.sh")
        with open(mem_cli_path, "w") as f:
            f.write("#!/bin/bash\n")

        memory_config = {
            "guid": "abc123",
            "tags": ["type:artifact", "stage:completed"]
        }

        with patch.dict(os.environ, {"REIN_MEM_CLI": mem_cli_path}):
            save_task_to_memory(temp_output_dir, memory_config)

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0] == mem_cli_path
        assert cmd[1] == "register"
        assert cmd[2] == "abc123"
        # Content should mention the output file
        assert "output.json" in cmd[3]
        # Tags should be joined
        assert cmd[4] == "type:artifact,stage:completed"

    @patch("subprocess.run")
    def test_mem_cli_default_tags(self, mock_run, temp_output_dir):
        """Test default tags when memory_config has no tags"""
        with open(os.path.join(temp_output_dir, "data.json"), "w") as f:
            json.dump({"x": 1}, f)

        mem_cli_path = os.path.join(temp_output_dir, "mem-cli.sh")
        with open(mem_cli_path, "w") as f:
            f.write("#!/bin/bash\n")

        memory_config = {"guid": "def456"}

        with patch.dict(os.environ, {"REIN_MEM_CLI": mem_cli_path}):
            save_task_to_memory(temp_output_dir, memory_config)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[4] == "type:artifact,stage:completed"

    @patch("subprocess.run")
    def test_mem_cli_not_called_without_guid(self, mock_run, temp_output_dir):
        """Test that mem-cli is not called when guid is missing"""
        with open(os.path.join(temp_output_dir, "data.json"), "w") as f:
            json.dump({"x": 1}, f)

        mem_cli_path = os.path.join(temp_output_dir, "mem-cli.sh")
        with open(mem_cli_path, "w") as f:
            f.write("#!/bin/bash\n")

        memory_config = {"tags": ["type:note"]}

        with patch.dict(os.environ, {"REIN_MEM_CLI": mem_cli_path}):
            save_task_to_memory(temp_output_dir, memory_config)

        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_mem_cli_multiple_json_files(self, mock_run, temp_output_dir):
        """Test content includes all JSON files sorted alphabetically"""
        for name in ["charlie.json", "alpha.json", "bravo.json"]:
            with open(os.path.join(temp_output_dir, name), "w") as f:
                json.dump({"file": name}, f)

        mem_cli_path = os.path.join(temp_output_dir, "mem-cli.sh")
        with open(mem_cli_path, "w") as f:
            f.write("#!/bin/bash\n")

        memory_config = {"guid": "multi-test"}

        with patch.dict(os.environ, {"REIN_MEM_CLI": mem_cli_path}):
            save_task_to_memory(temp_output_dir, memory_config)

        mock_run.assert_called_once()
        content = mock_run.call_args[0][0][3]
        # Files should appear sorted
        alpha_pos = content.index("alpha.json")
        bravo_pos = content.index("bravo.json")
        charlie_pos = content.index("charlie.json")
        assert alpha_pos < bravo_pos < charlie_pos

    @patch("subprocess.run", side_effect=Exception("subprocess error"))
    def test_mem_cli_exception_handled(self, mock_run, temp_output_dir):
        """Test that subprocess exceptions are handled gracefully"""
        with open(os.path.join(temp_output_dir, "data.json"), "w") as f:
            json.dump({"x": 1}, f)

        mem_cli_path = os.path.join(temp_output_dir, "mem-cli.sh")
        with open(mem_cli_path, "w") as f:
            f.write("#!/bin/bash\n")

        memory_config = {"guid": "error-test"}

        with patch.dict(os.environ, {"REIN_MEM_CLI": mem_cli_path}):
            # Should not raise
            save_task_to_memory(temp_output_dir, memory_config)


class TestLoadConfig:
    """Tests for load_config"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for config files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_load_valid_yaml(self, temp_dir):
        """Test loading a valid YAML config file"""
        config_data = {
            "name": "test-flow",
            "team": "test-team",
            "semaphore": 3,
            "blocks": [
                {"name": "step1", "specialist": "analyzer", "prompt": "Analyze"}
            ]
        }
        config_path = os.path.join(temp_dir, "flow.yaml")
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        result = load_config(config_path)
        assert result["name"] == "test-flow"
        assert result["team"] == "test-team"
        assert result["semaphore"] == 3
        assert len(result["blocks"]) == 1
        assert result["blocks"][0]["name"] == "step1"

    def test_load_missing_file(self):
        """Test loading a missing file raises FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_load_empty_yaml(self, temp_dir):
        """Test loading an empty YAML file returns None"""
        config_path = os.path.join(temp_dir, "empty.yaml")
        with open(config_path, "w") as f:
            f.write("")

        result = load_config(config_path)
        assert result is None

    def test_load_yaml_with_comments_only(self, temp_dir):
        """Test loading YAML with only comments returns None"""
        config_path = os.path.join(temp_dir, "comments.yaml")
        with open(config_path, "w") as f:
            f.write("# This is a comment\n# Another comment\n")

        result = load_config(config_path)
        assert result is None

    def test_load_complex_yaml(self, temp_dir):
        """Test loading a complex YAML structure"""
        config_path = os.path.join(temp_dir, "complex.yaml")
        content = """
name: deliberation
team: design-team
semaphore: 5
blocks:
  - name: research
    specialist: researcher
    prompt: "Investigate the topic"
    depends_on: []
  - name: analysis
    specialist: analyst
    prompt: "Analyze findings"
    depends_on: [research]
  - name: synthesis
    specialist: writer
    prompt: "Write final report"
    depends_on: [research, analysis]
memory:
  guid: test-guid
  tags:
    - type:artifact
    - stage:completed
"""
        with open(config_path, "w") as f:
            f.write(content)

        result = load_config(config_path)
        assert result["name"] == "deliberation"
        assert result["semaphore"] == 5
        assert len(result["blocks"]) == 3
        assert result["blocks"][1]["depends_on"] == ["research"]
        assert result["memory"]["guid"] == "test-guid"


class TestExecuteTask:
    """Tests for execute_task"""

    @pytest.fixture
    def temp_agents_dir(self):
        """Create temporary agents directory structure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "tasks"))
            os.makedirs(os.path.join(tmpdir, "flows"))
            yield tmpdir

    def _create_flow(self, agents_dir, flow_name, config=None):
        """Helper to create a flow config file"""
        flow_dir = os.path.join(agents_dir, "flows", flow_name)
        os.makedirs(flow_dir, exist_ok=True)
        flow_config = config or {
            "name": flow_name,
            "team": "test-team",
            "semaphore": 2,
            "blocks": [
                {"name": "step1", "specialist": "tester", "prompt": "Test"}
            ]
        }
        flow_path = os.path.join(flow_dir, f"{flow_name}.yaml")
        with open(flow_path, "w") as f:
            yaml.dump(flow_config, f)
        return flow_path

    def _create_task(self, agents_dir, task_id, flow_name):
        """Helper to create a task directory with task.yaml"""
        task_dir = os.path.join(agents_dir, "tasks", task_id)
        os.makedirs(task_dir, exist_ok=True)
        task_yaml = os.path.join(task_dir, "task.yaml")
        with open(task_yaml, "w") as f:
            yaml.dump({"id": task_id, "flow": flow_name}, f)
        return task_dir

    def test_missing_task_yaml(self, temp_agents_dir):
        """Test execute_task returns 1 when task.yaml is missing"""
        task_id = "task-missing"
        task_dir = os.path.join(temp_agents_dir, "tasks", task_id)
        os.makedirs(task_dir, exist_ok=True)
        # No task.yaml created

        result = execute_task(task_id, temp_agents_dir)
        assert result == 1

    def test_empty_task_yaml(self, temp_agents_dir):
        """Test execute_task returns 1 when task.yaml has no flow"""
        task_id = "task-empty"
        task_dir = os.path.join(temp_agents_dir, "tasks", task_id)
        os.makedirs(task_dir, exist_ok=True)

        # Create empty task.yaml
        task_yaml = os.path.join(task_dir, "task.yaml")
        with open(task_yaml, "w") as f:
            f.write("")

        result = execute_task(task_id, temp_agents_dir)
        assert result == 1

    def test_task_yaml_no_flow_key(self, temp_agents_dir):
        """Test execute_task returns 1 when task.yaml has no flow key"""
        task_id = "task-noflow"
        task_dir = os.path.join(temp_agents_dir, "tasks", task_id)
        os.makedirs(task_dir, exist_ok=True)

        task_yaml = os.path.join(task_dir, "task.yaml")
        with open(task_yaml, "w") as f:
            yaml.dump({"id": task_id, "created_at": "2026-01-01"}, f)

        result = execute_task(task_id, temp_agents_dir)
        assert result == 1

    def test_task_yaml_empty_flow(self, temp_agents_dir):
        """Test execute_task returns 1 when flow is empty string"""
        task_id = "task-emptyflow"
        task_dir = os.path.join(temp_agents_dir, "tasks", task_id)
        os.makedirs(task_dir, exist_ok=True)

        task_yaml = os.path.join(task_dir, "task.yaml")
        with open(task_yaml, "w") as f:
            yaml.dump({"id": task_id, "flow": ""}, f)

        result = execute_task(task_id, temp_agents_dir)
        assert result == 1

    def test_missing_flow_config(self, temp_agents_dir):
        """Test execute_task returns 1 when flow YAML does not exist"""
        task_id = "task-noflowfile"
        self._create_task(temp_agents_dir, task_id, "nonexistent-flow")

        result = execute_task(task_id, temp_agents_dir)
        assert result == 1

    def test_early_return_no_exit_code_file(self, temp_agents_dir):
        """Test that early returns (no flow, missing flow) do not write exit_code file"""
        task_id = "task-early"
        self._create_task(temp_agents_dir, task_id, "missing-flow")

        execute_task(task_id, temp_agents_dir)

        # Early returns happen before the try/except block that writes exit_code
        exit_code_path = os.path.join(
            temp_agents_dir, "tasks", task_id, "state", "exit_code"
        )
        assert not os.path.exists(exit_code_path)

    def test_invalid_task_yaml(self, temp_agents_dir):
        """Test execute_task returns 1 when task.yaml is malformed"""
        task_id = "task-badyaml"
        task_dir = os.path.join(temp_agents_dir, "tasks", task_id)
        os.makedirs(task_dir, exist_ok=True)

        task_yaml = os.path.join(task_dir, "task.yaml")
        with open(task_yaml, "w") as f:
            f.write(": : : invalid yaml {{{\n")

        result = execute_task(task_id, temp_agents_dir)
        assert result == 1

    @patch("rein.orchestrator.ProcessManager")
    @patch("rein.tasks.ReinState")
    def test_successful_execution(self, mock_state_cls, mock_pm_cls, temp_agents_dir):
        """Test successful task execution with mocked ProcessManager"""
        task_id = "task-success"
        flow_name = "test-flow"

        self._create_task(temp_agents_dir, task_id, flow_name)
        self._create_flow(temp_agents_dir, flow_name)

        # Setup mocks
        mock_manager = MagicMock()
        mock_pm_cls.return_value = mock_manager
        mock_state_cls.return_value = MagicMock()

        result = execute_task(task_id, temp_agents_dir)

        assert result == 0
        mock_pm_cls.assert_called_once_with(
            max_parallel=2,
            flow_name=flow_name,
            task_input={},
            agents_dir=temp_agents_dir
        )
        mock_manager.load_config.assert_called_once()
        mock_manager.run_workflow.assert_called_once()

        # Verify exit code file is written with 0
        task_dir = os.path.join(temp_agents_dir, "tasks", task_id)
        exit_code_path = os.path.join(task_dir, "state", "exit_code")
        assert os.path.exists(exit_code_path)
        with open(exit_code_path) as f:
            assert f.read().strip() == "0"

    @patch("rein.orchestrator.ProcessManager")
    @patch("rein.tasks.ReinState")
    def test_exit_code_file_written_on_failure(self, mock_state_cls, mock_pm_cls, temp_agents_dir):
        """Test that exit_code file is written with 1 when workflow fails"""
        task_id = "task-exitcode"
        flow_name = "exitcode-flow"

        self._create_task(temp_agents_dir, task_id, flow_name)
        self._create_flow(temp_agents_dir, flow_name)

        mock_manager = MagicMock()
        mock_manager.run_workflow.side_effect = RuntimeError("Workflow failed")
        mock_pm_cls.return_value = mock_manager
        mock_state_cls.return_value = MagicMock()

        execute_task(task_id, temp_agents_dir)

        task_dir = os.path.join(temp_agents_dir, "tasks", task_id)
        exit_code_path = os.path.join(task_dir, "state", "exit_code")
        assert os.path.exists(exit_code_path)
        with open(exit_code_path) as f:
            assert f.read().strip() == "1"

    @patch("rein.orchestrator.ProcessManager")
    @patch("rein.tasks.ReinState")
    def test_execution_with_question_txt(self, mock_state_cls, mock_pm_cls, temp_agents_dir):
        """Test task execution reads input from question.txt"""
        task_id = "task-question"
        flow_name = "qa-flow"

        task_dir = self._create_task(temp_agents_dir, task_id, flow_name)
        self._create_flow(temp_agents_dir, flow_name, {
            "name": flow_name, "semaphore": 1, "blocks": []
        })

        # Create question.txt
        os.makedirs(os.path.join(task_dir, "input"), exist_ok=True)
        question = "What is the meaning of life?"
        with open(os.path.join(task_dir, "input", "question.txt"), "w") as f:
            f.write(question)

        mock_manager = MagicMock()
        mock_pm_cls.return_value = mock_manager
        mock_state_cls.return_value = MagicMock()

        execute_task(task_id, temp_agents_dir)

        # Verify task_input was read from question.txt
        call_kwargs = mock_pm_cls.call_args[1]
        assert call_kwargs["task_input"]["topic"] == question
        assert call_kwargs["task_input"]["task"] == question

    @patch("rein.orchestrator.ProcessManager")
    @patch("rein.tasks.ReinState")
    def test_execution_with_task_input_json(self, mock_state_cls, mock_pm_cls, temp_agents_dir):
        """Test task execution reads input from task.input.json (highest priority)"""
        task_id = "task-inputjson"
        flow_name = "input-flow"

        task_dir = self._create_task(temp_agents_dir, task_id, flow_name)
        self._create_flow(temp_agents_dir, flow_name, {
            "name": flow_name, "semaphore": 1, "blocks": []
        })

        # Create task.input.json (takes priority over input/question.txt)
        input_data = {"topic": "Testing", "context": "Unit tests", "depth": 3}
        with open(os.path.join(task_dir, "task.input.json"), "w") as f:
            json.dump(input_data, f)

        # Also create question.txt to verify priority
        os.makedirs(os.path.join(task_dir, "input"), exist_ok=True)
        with open(os.path.join(task_dir, "input", "question.txt"), "w") as f:
            f.write("This should be ignored")

        mock_manager = MagicMock()
        mock_pm_cls.return_value = mock_manager
        mock_state_cls.return_value = MagicMock()

        execute_task(task_id, temp_agents_dir)

        call_kwargs = mock_pm_cls.call_args[1]
        assert call_kwargs["task_input"] == input_data

    @patch("rein.orchestrator.ProcessManager")
    @patch("rein.tasks.ReinState")
    def test_execution_with_input_task_json(self, mock_state_cls, mock_pm_cls, temp_agents_dir):
        """Test task execution reads input from input/task.json"""
        task_id = "task-taskjson"
        flow_name = "json-flow"

        task_dir = self._create_task(temp_agents_dir, task_id, flow_name)
        self._create_flow(temp_agents_dir, flow_name, {
            "name": flow_name, "semaphore": 1, "blocks": []
        })

        # Create input/task.json
        os.makedirs(os.path.join(task_dir, "input"), exist_ok=True)
        input_data = {"task": "Analyze code", "files": ["a.py", "b.py"]}
        with open(os.path.join(task_dir, "input", "task.json"), "w") as f:
            json.dump(input_data, f)

        mock_manager = MagicMock()
        mock_pm_cls.return_value = mock_manager
        mock_state_cls.return_value = MagicMock()

        execute_task(task_id, temp_agents_dir)

        call_kwargs = mock_pm_cls.call_args[1]
        assert call_kwargs["task_input"] == input_data

    @patch("rein.orchestrator.ProcessManager")
    @patch("rein.tasks.ReinState")
    def test_execution_no_input_files(self, mock_state_cls, mock_pm_cls, temp_agents_dir):
        """Test task execution with no input files passes empty dict"""
        task_id = "task-noinput"
        flow_name = "noinput-flow"

        self._create_task(temp_agents_dir, task_id, flow_name)
        self._create_flow(temp_agents_dir, flow_name, {
            "name": flow_name, "semaphore": 1, "blocks": []
        })

        mock_manager = MagicMock()
        mock_pm_cls.return_value = mock_manager
        mock_state_cls.return_value = MagicMock()

        execute_task(task_id, temp_agents_dir)

        call_kwargs = mock_pm_cls.call_args[1]
        assert call_kwargs["task_input"] == {}

    @patch("rein.orchestrator.ProcessManager")
    @patch("rein.tasks.ReinState")
    def test_workflow_exception_returns_1(self, mock_state_cls, mock_pm_cls, temp_agents_dir):
        """Test that exception during workflow returns exit code 1"""
        task_id = "task-exception"
        flow_name = "fail-flow"

        self._create_task(temp_agents_dir, task_id, flow_name)
        self._create_flow(temp_agents_dir, flow_name, {
            "name": flow_name, "semaphore": 1, "blocks": []
        })

        mock_manager = MagicMock()
        mock_manager.run_workflow.side_effect = RuntimeError("LLM API failed")
        mock_pm_cls.return_value = mock_manager
        mock_state_cls.return_value = MagicMock()

        result = execute_task(task_id, temp_agents_dir)
        assert result == 1

        # Verify exit code file
        task_dir = os.path.join(temp_agents_dir, "tasks", task_id)
        exit_code_path = os.path.join(task_dir, "state", "exit_code")
        assert os.path.exists(exit_code_path)
        with open(exit_code_path) as f:
            assert f.read().strip() == "1"

    @patch("rein.orchestrator.ProcessManager")
    @patch("rein.tasks.ReinState")
    def test_state_dir_created(self, mock_state_cls, mock_pm_cls, temp_agents_dir):
        """Test that state directory is created during execution"""
        task_id = "task-statedir"
        flow_name = "state-flow"

        self._create_task(temp_agents_dir, task_id, flow_name)
        self._create_flow(temp_agents_dir, flow_name, {
            "name": flow_name, "semaphore": 1, "blocks": []
        })

        mock_pm_cls.return_value = MagicMock()
        mock_state_cls.return_value = MagicMock()

        execute_task(task_id, temp_agents_dir)

        task_dir = os.path.join(temp_agents_dir, "tasks", task_id)
        state_dir = os.path.join(task_dir, "state")
        assert os.path.isdir(state_dir)

    @patch("rein.orchestrator.ProcessManager")
    @patch("rein.tasks.ReinState")
    def test_manager_attributes_set(self, mock_state_cls, mock_pm_cls, temp_agents_dir):
        """Test that ProcessManager attributes are correctly set"""
        task_id = "task-attrs"
        flow_name = "attrs-flow"

        task_dir = self._create_task(temp_agents_dir, task_id, flow_name)
        self._create_flow(temp_agents_dir, flow_name, {
            "name": flow_name, "semaphore": 4, "blocks": []
        })

        mock_manager = MagicMock()
        mock_pm_cls.return_value = mock_manager
        mock_state_cls.return_value = MagicMock()

        execute_task(task_id, temp_agents_dir)

        assert mock_manager.task_id == task_id
        assert mock_manager.task_dir == task_dir
        assert mock_manager.run_dir == task_dir
        assert mock_manager.log_dir == os.path.join(task_dir, "state")
        assert mock_manager.rein_log_file == os.path.join(task_dir, "state", "rein.log")
        assert mock_manager.db_path == os.path.join(task_dir, "state", "rein.db")

    @patch("rein.orchestrator.ProcessManager")
    @patch("rein.tasks.ReinState")
    def test_semaphore_from_config(self, mock_state_cls, mock_pm_cls, temp_agents_dir):
        """Test that semaphore value from flow config is passed to ProcessManager"""
        task_id = "task-sem"
        flow_name = "sem-flow"

        self._create_task(temp_agents_dir, task_id, flow_name)
        self._create_flow(temp_agents_dir, flow_name, {
            "name": flow_name, "semaphore": 7, "blocks": []
        })

        mock_manager = MagicMock()
        mock_pm_cls.return_value = mock_manager
        mock_state_cls.return_value = MagicMock()

        execute_task(task_id, temp_agents_dir)

        call_kwargs = mock_pm_cls.call_args[1]
        assert call_kwargs["max_parallel"] == 7

    @patch("rein.orchestrator.ProcessManager")
    @patch("rein.tasks.ReinState")
    def test_reinstate_called_with_correct_db_path(self, mock_state_cls, mock_pm_cls, temp_agents_dir):
        """Test that ReinState is initialized with correct db_path and resume=False"""
        task_id = "task-dbpath"
        flow_name = "db-flow"

        task_dir = self._create_task(temp_agents_dir, task_id, flow_name)
        self._create_flow(temp_agents_dir, flow_name, {
            "name": flow_name, "semaphore": 1, "blocks": []
        })

        mock_manager = MagicMock()
        mock_pm_cls.return_value = mock_manager
        mock_state_cls.return_value = MagicMock()

        execute_task(task_id, temp_agents_dir)

        expected_db_path = os.path.join(task_dir, "state", "rein.db")
        mock_state_cls.assert_called_once_with(expected_db_path, resume=False)
