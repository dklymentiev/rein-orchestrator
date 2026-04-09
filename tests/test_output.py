"""Tests for rein/output.py"""

import os
import tempfile

from rein.output import format_json_as_md, get_block_dir, get_output_dir, save_readable_output


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
        data = {"outer": {"inner": "value"}}
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
        data = {"people": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]}
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

            result = save_readable_output(json_file, "test-block", '{"key": "value"}', logger=lambda x: logs.append(x))

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

            result = save_readable_output(json_file, "text-block", "This is plain text content")

            assert result is True
            md_file = os.path.join(tmpdir, "result.md")

            with open(md_file) as f:
                content = f.read()
            assert "plain text content" in content

    def test_save_with_json_code_block(self):
        """Test saving content with JSON code block"""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "result.json")

            result_with_block = """Here is the analysis:
```json
{"findings": ["item1", "item2"]}
```
That's all."""

            result = save_readable_output(json_file, "analysis-block", result_with_block)

            assert result is True

    def test_logger_called(self):
        """Test that logger is called on success"""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "result.json")
            logs = []

            save_readable_output(json_file, "logged-block", "content", logger=lambda x: logs.append(x))

            assert len(logs) == 1
            assert "READABLE OUTPUT" in logs[0]
            assert "logged-block" in logs[0]


# ============================================================
# TASK #1176: readable_outputs and metadata
# ============================================================


class TestReadableOutputIntegration:
    """Tests for readable_outputs feature integration"""

    def test_md_file_created_next_to_json(self):
        """save_readable_output creates .md file next to .json"""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "block1", "outputs", "result.json")
            os.makedirs(os.path.dirname(json_file))

            save_readable_output(json_file, "block1", "Some text result")

            md_file = os.path.join(tmpdir, "block1", "outputs", "result.md")
            assert os.path.exists(md_file)

    def test_md_contains_block_name_as_header(self):
        """Generated .md should have block name as H1 header"""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "result.json")
            save_readable_output(json_file, "my_analyzer", "Analysis complete")

            md_file = os.path.join(tmpdir, "result.md")
            with open(md_file) as f:
                content = f.read()
            assert content.startswith("# my_analyzer")

    def test_md_contains_timestamp(self):
        """Generated .md should contain a timestamp"""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "result.json")
            save_readable_output(json_file, "block", "text")

            md_file = os.path.join(tmpdir, "result.md")
            with open(md_file) as f:
                content = f.read()
            # Timestamp format: YYYY-MM-DD HH:MM:SS wrapped in *
            import re

            assert re.search(r"\*\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\*", content)

    def test_md_handles_embedded_json_block(self):
        """Markdown with ```json code blocks should be parsed and formatted"""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "result.json")
            content = 'Summary text\n\n```json\n{"key": "value"}\n```\n\nAfter text'
            save_readable_output(json_file, "block", content)

            md_file = os.path.join(tmpdir, "result.md")
            with open(md_file) as f:
                md = f.read()
            assert "Summary text" in md
            assert "After text" in md

    def test_md_handles_plain_json_string(self):
        """Pure JSON string should be formatted as markdown"""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "result.json")
            save_readable_output(json_file, "block", '{"status": "ok", "count": 42}')

            md_file = os.path.join(tmpdir, "result.md")
            with open(md_file) as f:
                md = f.read()
            # Keys become H2 headers (capitalized)
            assert "Status" in md or "status" in md
            assert "42" in md


class TestMetadata:
    """Tests for workflow metadata handling"""

    def test_metadata_in_pydantic_config(self):
        """Workflow metadata field should be accepted"""
        from models.workflow import WorkflowConfig

        data = {
            "schema_version": "3.3.0",
            "name": "test-flow",
            "team": "team-test",
            "metadata": {"version": "1.0.0", "author": "tester", "created": "2026-01-15T10:00:00Z"},
            "blocks": [{"name": "step", "prompt": "do"}],
        }
        w = WorkflowConfig(**data)
        assert w.metadata is not None
        assert w.metadata["version"] == "1.0.0"
        assert w.metadata["author"] == "tester"

    def test_metadata_optional(self):
        """Metadata should be optional (absent = None)"""
        from models.workflow import WorkflowConfig

        data = {
            "schema_version": "3.3.0",
            "name": "no-meta",
            "team": "team-test",
            "blocks": [{"name": "step", "prompt": "do"}],
        }
        w = WorkflowConfig(**data)
        assert w.metadata is None

    def test_metadata_arbitrary_fields(self):
        """Metadata should accept arbitrary extra fields"""
        from models.workflow import WorkflowConfig

        data = {
            "schema_version": "3.3.0",
            "name": "test",
            "team": "team-x",
            "metadata": {"custom_field_1": "value", "arbitrary": 123},
            "blocks": [{"name": "s", "prompt": "x"}],
        }
        w = WorkflowConfig(**data)
        assert w.metadata["custom_field_1"] == "value"
        assert w.metadata["arbitrary"] == 123
