"""Tests for block-level save_as field (fix #1185).

Covers two pieces:
1. resolve_file_placeholder falls back to scanning block output dirs
   so that {{ custom_name.json }} resolves when produced via save_as.
2. Alias copy is created next to result.json when save_as is set
   (smoke-tested via shutil.copy2 behavior, since the orchestrator path
   runs through subprocess).
"""
import json
import os
import shutil
import tempfile

from rein.prompt_assembler import resolve_file_placeholder


def test_resolve_file_placeholder_finds_save_as_alias():
    """{{ summary.json }} must resolve when a block saved an alias under that name."""
    with tempfile.TemporaryDirectory() as task_dir:
        block_dir = os.path.join(task_dir, "reviewer", "outputs")
        os.makedirs(block_dir)
        with open(os.path.join(block_dir, "result.json"), "w") as f:
            json.dump({"result": "text"}, f)
        alias_path = os.path.join(block_dir, "summary.json")
        with open(alias_path, "w") as f:
            json.dump({"result": "text"}, f)

        resolved = resolve_file_placeholder("summary.json", task_dir, None)
        assert resolved == alias_path


def test_resolve_file_placeholder_prefers_block_name_over_alias():
    """If filename matches a block name directly, prefer its result.json."""
    with tempfile.TemporaryDirectory() as task_dir:
        # Block named "report" writes a result.json
        report_dir = os.path.join(task_dir, "report", "outputs")
        os.makedirs(report_dir)
        report_result = os.path.join(report_dir, "result.json")
        with open(report_result, "w") as f:
            json.dump({"result": "from report block"}, f)

        # Another block writes an alias called report.json
        other_dir = os.path.join(task_dir, "other", "outputs")
        os.makedirs(other_dir)
        with open(os.path.join(other_dir, "report.json"), "w") as f:
            json.dump({"result": "from other block"}, f)

        resolved = resolve_file_placeholder("report.json", task_dir, None)
        assert resolved == report_result


def test_resolve_file_placeholder_returns_none_when_missing():
    with tempfile.TemporaryDirectory() as task_dir:
        assert resolve_file_placeholder("nothing.json", task_dir, None) is None


def test_save_as_alias_copy_is_identical():
    """shutil.copy2 must produce a byte-identical alias (smoke test of the
    mechanism used by orchestrator to implement save_as)."""
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "result.json")
        payload = {"stage": "reviewer", "result": "body"}
        with open(src, "w") as f:
            json.dump(payload, f)

        dst = os.path.join(d, "summary.json")
        shutil.copy2(src, dst)

        with open(dst) as f:
            assert json.load(f) == payload
