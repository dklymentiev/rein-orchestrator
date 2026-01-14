"""Tests for rein/output.py"""
import os
import json
import pytest
import tempfile

from rein.output import (
    get_block_dir,
    get_output_dir,
    format_json_as_md,
    save_readable_output
)


class TestGetBlockDir:
    """Tests for get_block_dir function"""

    def test_with_task_dir(self):
        """Test getting block dir with task_dir set"""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = os.path.join(tmpdir, "task")
            os.makedirs(task_dir)

            block_dir = get_block_dir(task_dir, tmpdir, "my-block")

            assert block_dir == os.path.join(task_dir, "my-block")
            assert os.path.exists(os.path.join(block_dir, "inputs"))
            assert os.path.exists(os.path.join(block_dir, "outputs"))
            assert os.path.exists(os.path.join(block_dir, "logs"))

    def test_without_task_dir(self):
        """Test getting block dir without task_dir"""
        with tempfile.TemporaryDirectory() as workflow_dir:
            block_dir = get_block_dir(None, workflow_dir, "my-block")

            assert block_dir == os.path.join(workflow_dir, "my-block")
            assert os.path.exists(os.path.join(block_dir, "inputs"))


class TestGetOutputDir:
    """Tests for get_output_dir function"""

    def test_with_block_name_and_task_dir(self):
        """Test getting output dir with block name and task_dir"""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = os.path.join(tmpdir, "task")
            os.makedirs(task_dir)

            output_dir = get_output_dir(task_dir, tmpdir, "my-block")

            assert output_dir.endswith("outputs")
            assert "my-block" in output_dir

    def test_with_task_dir_no_block(self):
        """Test getting output dir with task_dir but no block name"""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = os.path.join(tmpdir, "task")
            os.makedirs(task_dir)

            output_dir = get_output_dir(task_dir, tmpdir, None)

            assert output_dir == os.path.join(task_dir, "outputs")
            assert os.path.exists(output_dir)

    def test_without_task_dir(self):
        """Test getting output dir without task_dir"""
        with tempfile.TemporaryDirectory() as workflow_dir:
            output_dir = get_output_dir(None, workflow_dir, "block")

            assert output_dir == workflow_dir


class TestFormatJsonAsMd:
    """Tests for format_json_as_md function"""

    def test_simple_dict(self):
        """Test formatting simple dictionary"""
        data = {"name": "Test", "value": 42}
        lines = format_json_as_md(data)

        assert "## Name" in lines
        assert "## Value" in lines
        assert "42" in lines

    def test_nested_dict(self):
        """Test formatting nested dictionary"""
        data = {
            "outer": {
                "inner": "value"
            }
        }
        lines = format_json_as_md(data)

        assert "## Outer" in lines
        assert "### Inner" in lines

    def test_list_values(self):
        """Test formatting list values"""
        data = {"items": ["one", "two", "three"]}
        lines = format_json_as_md(data)

        assert "- one" in lines
        assert "- two" in lines
        assert "- three" in lines

    def test_list_of_dicts(self):
        """Test formatting list of dictionaries"""
        data = {
            "people": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25}
            ]
        }
        lines = format_json_as_md(data)

        assert "### Alice" in lines
        assert "### Bob" in lines

    def test_non_dict_input(self):
        """Test handling non-dict input"""
        lines = format_json_as_md("just a string")
        assert "just a string" in lines

    def test_empty_dict(self):
        """Test handling empty dictionary"""
        lines = format_json_as_md({})
        assert lines == []


class TestSaveReadableOutput:
    """Tests for save_readable_output function"""

    def test_save_json_content(self):
        """Test saving JSON content as markdown"""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "result.json")
            logs = []

            result = save_readable_output(
                json_file,
                "test-block",
                '{"key": "value"}',
                logger=lambda x: logs.append(x)
            )

            assert result is True
            md_file = os.path.join(tmpdir, "result.md")
            assert os.path.exists(md_file)

            with open(md_file) as f:
                content = f.read()
            assert "# test-block" in content
            assert "Key" in content

    def test_save_plain_text(self):
        """Test saving plain text content"""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "result.json")

            result = save_readable_output(
                json_file,
                "text-block",
                "This is plain text content"
            )

            assert result is True
            md_file = os.path.join(tmpdir, "result.md")

            with open(md_file) as f:
                content = f.read()
            assert "plain text content" in content

    def test_save_with_json_code_block(self):
        """Test saving content with JSON code block"""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "result.json")

            result_with_block = '''Here is the analysis:
```json
{"findings": ["item1", "item2"]}
```
That's all.'''

            result = save_readable_output(
                json_file,
                "analysis-block",
                result_with_block
            )

            assert result is True

    def test_logger_called(self):
        """Test that logger is called on success"""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "result.json")
            logs = []

            save_readable_output(
                json_file,
                "logged-block",
                "content",
                logger=lambda x: logs.append(x)
            )

            assert len(logs) == 1
            assert "READABLE OUTPUT" in logs[0]
            assert "logged-block" in logs[0]
