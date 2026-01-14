"""Tests for rein/state.py"""
import os
import pytest
import tempfile
import time

from rein.state import ReinState
from rein.models import Process


class TestReinState:
    """Tests for ReinState SQLite persistence"""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database file"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.fixture
    def sample_process(self):
        """Create sample process for testing"""
        return Process(
            pid=12345,
            name="test-block",
            status="running",
            start_time=time.time(),
            command="python test.py",
            progress=50,
            phase=1
        )

    def test_init_creates_db(self, temp_db):
        """Test initialization creates database"""
        state = ReinState(db_path=temp_db)
        assert os.path.exists(temp_db)

    def test_init_fresh_run(self, temp_db):
        """Test fresh run drops existing table"""
        # Create initial state
        state1 = ReinState(db_path=temp_db, resume=False)
        proc = Process(
            pid=1, name="old", status="done",
            start_time=0.0, command=""
        )
        state1.save_process(proc)

        # Fresh run should clear data
        state2 = ReinState(db_path=temp_db, resume=False)
        processes = state2.get_all_processes()
        assert len(processes) == 0

    def test_init_resume(self, temp_db):
        """Test resume preserves existing data"""
        # Create initial state
        state1 = ReinState(db_path=temp_db, resume=False)
        proc = Process(
            pid=1, name="preserved", status="done",
            start_time=0.0, command=""
        )
        state1.save_process(proc)

        # Resume should preserve data
        state2 = ReinState(db_path=temp_db, resume=True)
        processes = state2.get_all_processes()
        assert len(processes) == 1
        assert processes[0].name == "preserved"

    def test_save_process(self, temp_db, sample_process):
        """Test saving process to database"""
        state = ReinState(db_path=temp_db)
        state.save_process(sample_process)

        processes = state.get_all_processes()
        assert len(processes) == 1
        assert processes[0].name == "test-block"
        assert processes[0].status == "running"

    def test_save_process_update(self, temp_db, sample_process):
        """Test updating existing process"""
        state = ReinState(db_path=temp_db)

        # Save initial
        state.save_process(sample_process)

        # Update
        sample_process.status = "done"
        sample_process.progress = 100
        sample_process.exit_code = 0
        state.save_process(sample_process)

        processes = state.get_all_processes()
        assert len(processes) == 1
        assert processes[0].status == "done"
        assert processes[0].progress == 100
        assert processes[0].exit_code == 0

    def test_get_all_processes_ordering(self, temp_db):
        """Test processes are ordered by phase and name"""
        state = ReinState(db_path=temp_db)

        # Add processes in random order
        procs = [
            Process(pid=1, name="c-block", status="waiting", start_time=0, command="", phase=2),
            Process(pid=2, name="a-block", status="waiting", start_time=0, command="", phase=1),
            Process(pid=3, name="b-block", status="waiting", start_time=0, command="", phase=1),
        ]
        for p in procs:
            state.save_process(p)

        result = state.get_all_processes()
        assert result[0].name == "a-block"  # phase 1, alphabetically first
        assert result[1].name == "b-block"  # phase 1, alphabetically second
        assert result[2].name == "c-block"  # phase 2

    def test_get_process(self, temp_db, sample_process):
        """Test getting single process by name"""
        state = ReinState(db_path=temp_db)
        state.save_process(sample_process)

        proc = state.get_process("test-block")
        assert proc is not None
        assert proc.name == "test-block"
        assert proc.status == "running"

    def test_get_process_not_found(self, temp_db):
        """Test getting non-existent process returns None"""
        state = ReinState(db_path=temp_db)
        proc = state.get_process("nonexistent")
        assert proc is None

    def test_update_status(self, temp_db, sample_process):
        """Test updating process status"""
        state = ReinState(db_path=temp_db)
        state.save_process(sample_process)

        state.update_status("test-block", "done", exit_code=0)

        proc = state.get_process("test-block")
        assert proc.status == "done"
        assert proc.exit_code == 0

    def test_update_status_without_exit_code(self, temp_db, sample_process):
        """Test updating status without exit code"""
        state = ReinState(db_path=temp_db)
        state.save_process(sample_process)

        state.update_status("test-block", "paused")

        proc = state.get_process("test-block")
        assert proc.status == "paused"

    def test_clear(self, temp_db):
        """Test clearing all process data"""
        state = ReinState(db_path=temp_db)

        # Add multiple processes
        for i in range(5):
            proc = Process(
                pid=i, name=f"block-{i}", status="done",
                start_time=0, command=""
            )
            state.save_process(proc)

        assert len(state.get_all_processes()) == 5

        state.clear()
        assert len(state.get_all_processes()) == 0

    def test_blocking_pause_stored(self, temp_db):
        """Test blocking_pause flag is stored correctly"""
        state = ReinState(db_path=temp_db)

        proc = Process(
            pid=1, name="paused-block", status="paused",
            start_time=0, command="", blocking_pause=True
        )
        state.save_process(proc)

        retrieved = state.get_process("paused-block")
        assert retrieved.blocking_pause is True

    def test_multiple_processes(self, temp_db):
        """Test handling multiple processes"""
        state = ReinState(db_path=temp_db)

        names = ["alpha", "beta", "gamma", "delta"]
        for i, name in enumerate(names):
            proc = Process(
                pid=100 + i, name=name, status="waiting",
                start_time=float(i), command=f"cmd-{i}",
                phase=i % 2 + 1
            )
            state.save_process(proc)

        processes = state.get_all_processes()
        assert len(processes) == 4
