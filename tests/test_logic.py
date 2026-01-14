"""Tests for rein/logic.py"""
import os
import json
import pytest
import tempfile

from rein.logic import LogicRunner


class TestLogicRunner:
    """Tests for LogicRunner"""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary task and workflow directories"""
        with tempfile.TemporaryDirectory() as task_dir:
            with tempfile.TemporaryDirectory() as workflow_dir:
                yield task_dir, workflow_dir

    @pytest.fixture
    def sample_script(self, temp_dirs):
        """Create sample Python script for testing"""
        task_dir, workflow_dir = temp_dirs

        script_content = '''#!/usr/bin/env python3
import sys
import json

context = json.loads(sys.stdin.read())
output_file = context.get("output_file")

result = {
    "status": "success",
    "task_id": context.get("task_id"),
    "block_name": context.get("block_config", {}).get("name", "unknown")
}

with open(output_file, "w") as f:
    json.dump({"result": json.dumps(result)}, f)

print("Script executed successfully")
'''
        script_path = os.path.join(workflow_dir, "test_script.py")
        with open(script_path, "w") as f:
            f.write(script_content)

        return script_path, "test_script.py"

    @pytest.fixture
    def failing_script(self, temp_dirs):
        """Create a script that fails"""
        task_dir, workflow_dir = temp_dirs

        script_content = '''#!/usr/bin/env python3
import sys
sys.exit(1)
'''
        script_path = os.path.join(workflow_dir, "failing_script.py")
        with open(script_path, "w") as f:
            f.write(script_content)

        return script_path, "failing_script.py"

    def test_init(self, temp_dirs):
        """Test LogicRunner initialization"""
        task_dir, workflow_dir = temp_dirs
        logs = []

        runner = LogicRunner(
            task_dir=task_dir,
            workflow_dir=workflow_dir,
            task_id="test-001",
            task_input={"key": "value"},
            logger=lambda x: logs.append(x),
            timeout=60
        )

        assert runner.task_dir == task_dir
        assert runner.workflow_dir == workflow_dir
        assert runner.task_id == "test-001"
        assert runner.task_input == {"key": "value"}
        assert runner.timeout == 60

    def test_run_python_script(self, temp_dirs, sample_script):
        """Test running Python script"""
        task_dir, workflow_dir = temp_dirs
        full_path, rel_path = sample_script
        logs = []

        runner = LogicRunner(
            task_dir=task_dir,
            workflow_dir=workflow_dir,
            task_id="test-002",
            logger=lambda x: logs.append(x)
        )

        output_file = os.path.join(task_dir, "output.json")

        result = runner.run(
            script_path=rel_path,
            output_file=output_file,
            block_name="test-block",
            block_config={"name": "test-block"}
        )

        assert result is True
        assert os.path.exists(output_file)

        with open(output_file) as f:
            data = json.load(f)
        assert "result" in data

    def test_run_script_not_found(self, temp_dirs):
        """Test running non-existent script"""
        task_dir, workflow_dir = temp_dirs
        logs = []

        runner = LogicRunner(
            task_dir=task_dir,
            workflow_dir=workflow_dir,
            logger=lambda x: logs.append(x)
        )

        result = runner.run(
            script_path="nonexistent.py",
            output_file="/tmp/out.json"
        )

        assert result is False
        assert any("not found" in log for log in logs)

    def test_run_failing_script(self, temp_dirs, failing_script):
        """Test running script that fails"""
        task_dir, workflow_dir = temp_dirs
        full_path, rel_path = failing_script
        logs = []

        runner = LogicRunner(
            task_dir=task_dir,
            workflow_dir=workflow_dir,
            logger=lambda x: logs.append(x)
        )

        result = runner.run(
            script_path=rel_path,
            output_file="/tmp/out.json"
        )

        assert result is False

    def test_run_unknown_script_type(self, temp_dirs):
        """Test running unknown script type"""
        task_dir, workflow_dir = temp_dirs
        logs = []

        # Create a file with unknown extension
        script_path = os.path.join(workflow_dir, "script.xyz")
        with open(script_path, "w") as f:
            f.write("content")

        runner = LogicRunner(
            task_dir=task_dir,
            workflow_dir=workflow_dir,
            logger=lambda x: logs.append(x)
        )

        result = runner.run(
            script_path="script.xyz",
            output_file="/tmp/out.json"
        )

        assert result is False
        assert any("unknown script type" in log for log in logs)

    def test_prepare_input_dir(self, temp_dirs):
        """Test preparing input directory"""
        task_dir, workflow_dir = temp_dirs
        logs = []

        # Create dependency output
        dep_dir = os.path.join(task_dir, "dep-block", "outputs")
        os.makedirs(dep_dir)
        with open(os.path.join(dep_dir, "result.json"), "w") as f:
            json.dump({"result": "dep output"}, f)

        runner = LogicRunner(
            task_dir=task_dir,
            workflow_dir=workflow_dir,
            logger=lambda x: logs.append(x)
        )

        input_dir = runner.prepare_input_dir("my-block", ["dep-block"])

        assert os.path.exists(input_dir)
        assert "my-block" in input_dir
        assert any("INPUT DEP" in log for log in logs)

    def test_prepare_input_dir_missing_dep(self, temp_dirs):
        """Test preparing input dir with missing dependency"""
        task_dir, workflow_dir = temp_dirs
        logs = []

        runner = LogicRunner(
            task_dir=task_dir,
            workflow_dir=workflow_dir,
            logger=lambda x: logs.append(x)
        )

        input_dir = runner.prepare_input_dir("my-block", ["missing-dep"])

        assert os.path.exists(input_dir)
        assert any("INPUT WARN" in log for log in logs)

    def test_context_passed_to_script(self, temp_dirs):
        """Test that context is passed correctly to script"""
        task_dir, workflow_dir = temp_dirs

        # Create script that writes context to output
        script_content = '''#!/usr/bin/env python3
import sys
import json

context = json.loads(sys.stdin.read())
output_file = context.get("output_file")

with open(output_file, "w") as f:
    json.dump(context, f)
'''
        script_path = os.path.join(workflow_dir, "context_test.py")
        with open(script_path, "w") as f:
            f.write(script_content)

        runner = LogicRunner(
            task_dir=task_dir,
            workflow_dir=workflow_dir,
            task_id="ctx-test",
            task_input={"topic": "test topic"}
        )

        output_file = os.path.join(task_dir, "context_output.json")
        runner.run(
            script_path="context_test.py",
            output_file=output_file,
            block_name="ctx-block",
            block_config={"name": "ctx-block", "specialist": "test"}
        )

        with open(output_file) as f:
            ctx = json.load(f)

        assert ctx["task_id"] == "ctx-test"
        assert ctx["task_input"]["topic"] == "test topic"
        assert ctx["block_config"]["name"] == "ctx-block"
