"""Tests for rein/models.py"""
import pytest
from dataclasses import asdict

from rein.models import Process, BlockConfig


class TestProcess:
    """Tests for Process dataclass"""

    def test_create_minimal(self):
        """Test creating Process with minimal required fields"""
        proc = Process(
            pid=None,
            name="test-block",
            status="waiting",
            start_time=0.0,
            command=""
        )
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
            run_count=3
        )
        assert proc.pid == 12345
        assert proc.cpu_percent == 50.5
        assert proc.blocking_pause is True
        assert proc.run_count == 3

    def test_default_values(self):
        """Test default values are set correctly"""
        proc = Process(
            pid=None,
            name="test",
            status="waiting",
            start_time=0.0,
            command=""
        )
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
        proc = Process(
            pid=100,
            name="dict-test",
            status="done",
            start_time=500.0,
            command="test"
        )
        d = asdict(proc)
        assert d["name"] == "dict-test"
        assert d["status"] == "done"
        assert isinstance(d, dict)

    def test_status_values(self):
        """Test various status values"""
        for status in ["waiting", "running", "done", "failed", "paused"]:
            proc = Process(
                pid=None,
                name="test",
                status=status,
                start_time=0.0,
                command=""
            )
            assert proc.status == status


class TestBlockConfig:
    """Tests for BlockConfig dataclass"""

    def test_create_minimal(self):
        """Test creating BlockConfig with minimal fields"""
        block = BlockConfig(
            name="step1",
            specialist="analyzer",
            prompt="Analyze this"
        )
        assert block.name == "step1"
        assert block.specialist == "analyzer"
        assert block.prompt == "Analyze this"

    def test_create_with_dependencies(self):
        """Test creating BlockConfig with dependencies"""
        block = BlockConfig(
            name="step2",
            specialist="writer",
            prompt="Write based on analysis",
            depends_on=["step1", "step0"]
        )
        assert block.depends_on == ["step1", "step0"]
        assert len(block.depends_on) == 2

    def test_create_with_logic(self):
        """Test creating BlockConfig with logic scripts"""
        block = BlockConfig(
            name="logic-block",
            specialist="processor",
            prompt="Process data",
            logic={
                "pre": "scripts/pre.py",
                "post": "scripts/post.py",
                "custom": "scripts/main.py"
            }
        )
        assert block.logic["pre"] == "scripts/pre.py"
        assert block.logic["custom"] == "scripts/main.py"

    def test_default_values(self):
        """Test default values"""
        block = BlockConfig(
            name="test",
            specialist="test",
            prompt="test"
        )
        assert block.depends_on == []
        assert block.logic is None
        assert block.parallel is False
        assert block.max_runs == 1
        assert block.continue_if_failed is True

    def test_parallel_block(self):
        """Test parallel execution flag"""
        block = BlockConfig(
            name="parallel-block",
            specialist="fast",
            prompt="Run fast",
            parallel=True
        )
        assert block.parallel is True

    def test_max_runs(self):
        """Test max_runs for loops"""
        block = BlockConfig(
            name="loop-block",
            specialist="repeater",
            prompt="Repeat",
            max_runs=5
        )
        assert block.max_runs == 5
