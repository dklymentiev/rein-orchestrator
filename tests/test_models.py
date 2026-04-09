"""Tests for rein/models.py"""

from dataclasses import asdict

import pytest

from rein.models import BlockConfig, Process


class TestProcess:
    """Tests for Process dataclass"""

    def test_create_minimal(self):
        """Test creating Process with minimal required fields"""
        proc = Process(pid=None, name="test-block", status="waiting", start_time=0.0, command="")
        assert proc.name == "test-block"
        assert proc.status == "waiting"
        assert proc.pid is None

    def test_create_with_all_fields(self):
        """Test creating Process with all fields"""
        proc = Process(
            pid=12345,
            name="full-block",
            status="running",
            start_time=1000.0,
            command="python script.py",
            uid="abc123",
            exit_code=0,
            cpu_percent=50.5,
            memory_mb=128.0,
            progress=75,
            phase=2,
            blocking_pause=True,
            run_count=3,
        )
        assert proc.pid == 12345
        assert proc.cpu_percent == 50.5
        assert proc.blocking_pause is True
        assert proc.run_count == 3

    def test_default_values(self):
        """Test default values are set correctly"""
        proc = Process(pid=None, name="test", status="waiting", start_time=0.0, command="")
        assert proc.uid == ""
        assert proc.exit_code is None
        assert proc.cpu_percent == 0.0
        assert proc.memory_mb == 0.0
        assert proc.progress == 0
        assert proc.phase == 0
        assert proc.blocking_pause is True
        assert proc.run_count == 0

    def test_to_dict(self):
        """Test conversion to dictionary"""
        proc = Process(pid=100, name="dict-test", status="done", start_time=500.0, command="test")
        d = asdict(proc)
        assert d["name"] == "dict-test"
        assert d["status"] == "done"
        assert isinstance(d, dict)

    def test_status_values(self):
        """Test various status values"""
        for status in ["waiting", "running", "done", "failed", "paused"]:
            proc = Process(pid=None, name="test", status=status, start_time=0.0, command="")
            assert proc.status == status


class TestBlockConfig:
    """Tests for BlockConfig dataclass"""

    def test_create_minimal(self):
        """Test creating BlockConfig with minimal fields"""
        block = BlockConfig(name="step1", specialist="analyzer", prompt="Analyze this")
        assert block.name == "step1"
        assert block.specialist == "analyzer"
        assert block.prompt == "Analyze this"

    def test_create_with_dependencies(self):
        """Test creating BlockConfig with dependencies"""
        block = BlockConfig(
            name="step2", specialist="writer", prompt="Write based on analysis", depends_on=["step1", "step0"]
        )
        assert block.depends_on == ["step1", "step0"]
        assert len(block.depends_on) == 2

    def test_create_with_logic(self):
        """Test creating BlockConfig with logic scripts"""
        block = BlockConfig(
            name="logic-block",
            specialist="processor",
            prompt="Process data",
            logic={"pre": "scripts/pre.py", "post": "scripts/post.py", "custom": "scripts/main.py"},
        )
        assert block.logic["pre"] == "scripts/pre.py"
        assert block.logic["custom"] == "scripts/main.py"

    def test_default_values(self):
        """Test default values"""
        block = BlockConfig(name="test", specialist="test", prompt="test")
        assert block.depends_on == []
        assert block.logic is None
        assert block.parallel is False
        assert block.max_runs == 1
        assert block.continue_if_failed is True

    def test_parallel_block(self):
        """Test parallel execution flag"""
        block = BlockConfig(name="parallel-block", specialist="fast", prompt="Run fast", parallel=True)
        assert block.parallel is True

    def test_max_runs(self):
        """Test max_runs for loops"""
        block = BlockConfig(name="loop-block", specialist="repeater", prompt="Repeat", max_runs=5)
        assert block.max_runs == 5


class TestPydanticBlockConfig:
    """Tests for Pydantic BlockConfig (models.workflow) -- schema validation"""

    def test_phase_accepts_large_values(self):
        """Phase should accept values up to 1000 (not limited to 10)"""
        from models.workflow import BlockConfig as PydanticBlock

        block = PydanticBlock(name="late_phase", prompt="test", phase=50)
        assert block.phase == 50

    def test_routing_field(self):
        """Block with routing dict"""
        from models.workflow import BlockConfig as PydanticBlock

        block = PydanticBlock(name="gate", prompt="evaluate", routing={"revise": "fix_block", "_default": "next_block"})
        assert block.routing["revise"] == "fix_block"
        assert block.routing["_default"] == "next_block"

    def test_logic_error_handler(self):
        """Block with per-block error handler"""
        from models.workflow import BlockConfig as PydanticBlock
        from models.workflow import LogicConfig

        block = PydanticBlock(
            name="risky", prompt="deploy", logic=LogicConfig(pre="logic/pre.py", error="logic/rollback.py")
        )
        assert block.logic.error == "logic/rollback.py"

    def test_logic_custom_string(self):
        """logic.custom as script path string"""
        from models.workflow import BlockConfig as PydanticBlock
        from models.workflow import LogicConfig

        block = PydanticBlock(name="custom_block", prompt="x", logic=LogicConfig(custom="logic/my-script.py"))
        assert block.logic.custom == "logic/my-script.py"

    def test_agent_field(self):
        """Block with agent identity for step mode"""
        from models.workflow import BlockConfig as PydanticBlock

        block = PydanticBlock(name="draft", prompt="write", agent="writer")
        assert block.agent == "writer"


class TestWorkflowConfig:
    """Tests for WorkflowConfig Pydantic model"""

    def _minimal_workflow(self, **overrides):
        base = {
            "schema_version": "3.3.0",
            "name": "test-flow",
            "team": "team-test",
            "blocks": [{"name": "step_one", "prompt": "test"}],
        }
        base.update(overrides)
        return base

    def test_default_max_runs_accepted(self):
        """default_max_runs should be accepted at workflow level"""
        from models.workflow import WorkflowConfig

        data = self._minimal_workflow(default_max_runs=5)
        w = WorkflowConfig(**data)
        assert w.default_max_runs == 5

    def test_extra_fields_ignored(self):
        """Unknown workflow-level fields should be ignored (not rejected)"""
        from models.workflow import WorkflowConfig

        data = self._minimal_workflow(some_future_field="test", another_field=42)
        w = WorkflowConfig(**data)  # should not raise
        assert w.name == "test-flow"

    def test_block_extra_fields_rejected(self):
        """Unknown block-level fields should still be rejected"""
        from models.workflow import WorkflowConfig

        data = self._minimal_workflow()
        data["blocks"][0]["unknown_field"] = "oops"
        with pytest.raises(Exception):
            WorkflowConfig(**data)

    def test_on_error_field(self):
        """on_error global error handler accepted"""
        from models.workflow import WorkflowConfig

        data = self._minimal_workflow(on_error="logic/notify.py")
        w = WorkflowConfig(**data)
        assert w.on_error == "logic/notify.py"

    def test_readable_outputs(self):
        """readable_outputs field"""
        from models.workflow import WorkflowConfig

        data = self._minimal_workflow(readable_outputs=True)
        w = WorkflowConfig(**data)
        assert w.readable_outputs is True

    def test_backward_compat_old_schema(self):
        """Old schema_version 2.5.3 workflows still validate"""
        from models.workflow import WorkflowConfig

        data = {
            "schema_version": "2.5.3",
            "name": "old-flow",
            "team": "team-legacy",
            "blocks": [{"name": "step", "prompt": "do"}],
        }
        w = WorkflowConfig(**data)
        assert w.schema_version == "2.5.3"
