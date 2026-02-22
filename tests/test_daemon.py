"""Tests for rein/daemon.py"""
import os
import sqlite3
import pytest
import tempfile
import time
from unittest.mock import patch

from rein.daemon import get_tasks_root, get_task_state_snapshot, get_running_tasks


# ---------------------------------------------------------------------------
# Helper: create a rein.db with the processes table and optional rows
# ---------------------------------------------------------------------------

CREATE_PROCESSES_TABLE = """
CREATE TABLE IF NOT EXISTS processes (
    name TEXT PRIMARY KEY,
    status TEXT DEFAULT 'waiting',
    phase INTEGER DEFAULT 0,
    progress INTEGER DEFAULT 0,
    start_time REAL,
    updated_at REAL,
    exit_code INTEGER,
    pid INTEGER,
    command TEXT DEFAULT '',
    uid TEXT DEFAULT '',
    depends_on TEXT DEFAULT '',
    cpu_percent REAL DEFAULT 0,
    memory_mb REAL DEFAULT 0,
    blocking_pause INTEGER DEFAULT 0,
    agent TEXT DEFAULT '',
    next_spec TEXT DEFAULT '',
    max_runs INTEGER DEFAULT 1,
    run_count INTEGER DEFAULT 0
)
"""


def _create_rein_db(task_dir, rows=None):
    """Create state/rein.db inside *task_dir* with optional process rows.

    Each row in *rows* is a dict whose keys map to columns in the processes
    table.  Only ``name`` is required; the rest fall back to schema defaults.

    Returns the path to the created rein.db file.
    """
    state_dir = os.path.join(task_dir, "state")
    os.makedirs(state_dir, exist_ok=True)
    db_path = os.path.join(state_dir, "rein.db")

    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_PROCESSES_TABLE)

    if rows:
        columns = [
            "name", "status", "phase", "progress", "start_time",
            "updated_at", "exit_code", "pid", "command", "uid",
            "depends_on", "cpu_percent", "memory_mb", "blocking_pause",
            "agent", "next_spec", "max_runs", "run_count",
        ]
        for row in rows:
            cols = [c for c in columns if c in row]
            placeholders = ", ".join("?" for _ in cols)
            col_names = ", ".join(cols)
            values = [row[c] for c in cols]
            conn.execute(
                f"INSERT INTO processes ({col_names}) VALUES ({placeholders})",
                values,
            )

    conn.commit()
    conn.close()
    return db_path


# ===========================================================================
# Tests for get_tasks_root
# ===========================================================================

class TestGetTasksRoot:
    """Tests for get_tasks_root()"""

    def test_with_explicit_agents_dir(self):
        """Explicit agents_dir is joined with 'tasks'"""
        result = get_tasks_root(agents_dir="/some/agents")
        assert result == os.path.join("/some/agents", "tasks")

    def test_env_var_overrides_agents_dir(self):
        """REIN_TASKS_ROOT env var takes precedence over agents_dir"""
        with patch.dict(os.environ, {"REIN_TASKS_ROOT": "/override/tasks"}):
            result = get_tasks_root(agents_dir="/some/agents")
            assert result == "/override/tasks"

    def test_env_var_overrides_default(self):
        """REIN_TASKS_ROOT env var takes precedence over default agents dir"""
        with patch.dict(os.environ, {"REIN_TASKS_ROOT": "/env/tasks"}):
            result = get_tasks_root()
            assert result == "/env/tasks"

    def test_default_agents_dir_used_when_no_args(self):
        """When no agents_dir given and no env var, DEFAULT_AGENTS_DIR is used"""
        env = os.environ.copy()
        env.pop("REIN_TASKS_ROOT", None)
        with patch.dict(os.environ, env, clear=True):
            from rein.config import DEFAULT_AGENTS_DIR
            result = get_tasks_root()
            assert result == os.path.join(DEFAULT_AGENTS_DIR, "tasks")

    def test_empty_string_agents_dir_falls_back_to_default(self):
        """Passing empty string as agents_dir behaves like no argument"""
        env = os.environ.copy()
        env.pop("REIN_TASKS_ROOT", None)
        with patch.dict(os.environ, env, clear=True):
            from rein.config import DEFAULT_AGENTS_DIR
            result = get_tasks_root(agents_dir="")
            assert result == os.path.join(DEFAULT_AGENTS_DIR, "tasks")


# ===========================================================================
# Tests for get_task_state_snapshot
# ===========================================================================

class TestGetTaskStateSnapshot:
    """Tests for get_task_state_snapshot()"""

    @pytest.fixture
    def tasks_root(self):
        """Create a temporary tasks root directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    # ---- No database / missing state -----------------------------------

    def test_no_rein_db_returns_unknown(self, tasks_root):
        """When no rein.db exists, status should be 'unknown'"""
        task_id = "task-no-db"
        task_dir = os.path.join(tasks_root, task_id)
        os.makedirs(task_dir, exist_ok=True)

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)

        assert result["type"] == "state"
        assert result["task_id"] == task_id
        assert result["status"] == "unknown"
        assert result["total"] == 0
        assert result["done"] == 0
        assert result["failed"] == 0
        assert result["running"] == 0
        assert result["blocks"] == []

    def test_nonexistent_task_dir_returns_unknown(self, tasks_root):
        """When even the task directory does not exist, status is 'unknown'"""
        result = get_task_state_snapshot("does-not-exist", tasks_root=tasks_root)

        assert result["status"] == "unknown"
        assert result["blocks"] == []

    # ---- Empty database (no rows) --------------------------------------

    def test_empty_db_returns_pending(self, tasks_root):
        """Database with processes table but no rows -> status 'pending'"""
        task_id = "task-empty-db"
        task_dir = os.path.join(tasks_root, task_id)
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[])

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)

        assert result["status"] == "pending"
        assert result["total"] == 0
        assert result["blocks"] == []

    # ---- All processes pending (waiting) --------------------------------

    def test_all_waiting_returns_pending(self, tasks_root):
        """All processes in 'waiting' status -> task is 'pending'"""
        task_id = "task-all-waiting"
        task_dir = os.path.join(tasks_root, task_id)
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[
            {"name": "block-a", "status": "waiting", "phase": 1, "progress": 0},
            {"name": "block-b", "status": "waiting", "phase": 2, "progress": 0},
        ])

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)

        assert result["status"] == "pending"
        assert result["total"] == 2
        assert result["done"] == 0
        assert result["running"] == 0

    # ---- Running processes ---------------------------------------------

    def test_some_running_returns_running(self, tasks_root):
        """Mix of running and waiting -> task is 'running'"""
        task_id = "task-running"
        task_dir = os.path.join(tasks_root, task_id)
        os.makedirs(task_dir, exist_ok=True)
        now = time.time()
        _create_rein_db(task_dir, rows=[
            {"name": "block-a", "status": "running", "phase": 1, "progress": 50,
             "start_time": now - 10, "updated_at": now},
            {"name": "block-b", "status": "waiting", "phase": 2, "progress": 0},
        ])

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)

        assert result["status"] == "running"
        assert result["total"] == 2
        assert result["running"] == 1
        assert result["done"] == 0

    def test_some_done_some_waiting_returns_running(self, tasks_root):
        """Some done, some waiting (no running) -> task is 'running'"""
        task_id = "task-partial-done"
        task_dir = os.path.join(tasks_root, task_id)
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[
            {"name": "block-a", "status": "done", "phase": 1, "progress": 100},
            {"name": "block-b", "status": "waiting", "phase": 2, "progress": 0},
        ])

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)

        assert result["status"] == "running"
        assert result["done"] == 1

    # ---- All completed --------------------------------------------------

    def test_all_done_returns_completed(self, tasks_root):
        """All processes done -> task is 'completed'"""
        task_id = "task-completed"
        task_dir = os.path.join(tasks_root, task_id)
        os.makedirs(task_dir, exist_ok=True)
        now = time.time()
        _create_rein_db(task_dir, rows=[
            {"name": "block-a", "status": "done", "phase": 1, "progress": 100,
             "start_time": now - 20, "updated_at": now - 10, "exit_code": 0},
            {"name": "block-b", "status": "done", "phase": 2, "progress": 100,
             "start_time": now - 10, "updated_at": now, "exit_code": 0},
        ])

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)

        assert result["status"] == "completed"
        assert result["total"] == 2
        assert result["done"] == 2
        assert result["failed"] == 0

    # ---- Failed processes -----------------------------------------------

    def test_any_failed_returns_failed(self, tasks_root):
        """Even one failed process -> task is 'failed'"""
        task_id = "task-failed"
        task_dir = os.path.join(tasks_root, task_id)
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[
            {"name": "block-a", "status": "done", "phase": 1, "progress": 100},
            {"name": "block-b", "status": "failed", "phase": 2, "progress": 30,
             "exit_code": 1},
        ])

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)

        assert result["status"] == "failed"
        assert result["failed"] == 1
        assert result["done"] == 1

    def test_multiple_failed_returns_failed(self, tasks_root):
        """Multiple failures still yield 'failed'"""
        task_id = "task-multi-fail"
        task_dir = os.path.join(tasks_root, task_id)
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[
            {"name": "block-a", "status": "failed", "phase": 1, "progress": 0,
             "exit_code": 2},
            {"name": "block-b", "status": "failed", "phase": 1, "progress": 0,
             "exit_code": 1},
            {"name": "block-c", "status": "waiting", "phase": 2, "progress": 0},
        ])

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)

        assert result["status"] == "failed"
        assert result["failed"] == 2
        assert result["total"] == 3

    # ---- Block detail fields -------------------------------------------

    def test_block_detail_fields(self, tasks_root):
        """Verify each block dict has the expected keys"""
        task_id = "task-details"
        task_dir = os.path.join(tasks_root, task_id)
        os.makedirs(task_dir, exist_ok=True)
        now = time.time()
        _create_rein_db(task_dir, rows=[
            {"name": "my-block", "status": "running", "phase": 1, "progress": 42,
             "start_time": now - 5.0, "updated_at": now},
        ])

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)
        blocks = result["blocks"]

        assert len(blocks) == 1
        b = blocks[0]
        assert b["name"] == "my-block"
        assert b["status"] == "running"
        assert b["phase"] == 1
        assert b["progress"] == 42
        assert "started" in b
        assert "updated" in b
        assert "duration" in b
        assert b["duration"] == pytest.approx(5.0, abs=0.2)

    def test_block_without_times(self, tasks_root):
        """Block with no start_time / updated_at omits those keys"""
        task_id = "task-no-times"
        task_dir = os.path.join(tasks_root, task_id)
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[
            {"name": "bare-block", "status": "waiting", "phase": 0, "progress": 0},
        ])

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)
        b = result["blocks"][0]

        assert "started" not in b
        assert "updated" not in b
        assert "duration" not in b

    def test_block_with_updated_at_but_no_start_time(self, tasks_root):
        """updated_at present but no start_time -> no duration key"""
        task_id = "task-only-updated"
        task_dir = os.path.join(tasks_root, task_id)
        os.makedirs(task_dir, exist_ok=True)
        now = time.time()
        _create_rein_db(task_dir, rows=[
            {"name": "block-x", "status": "running", "phase": 1, "progress": 10,
             "updated_at": now},
        ])

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)
        b = result["blocks"][0]

        assert "updated" in b
        assert "started" not in b
        assert "duration" not in b

    # ---- Output size detection -----------------------------------------

    def test_output_size_json(self, tasks_root):
        """Block with result.json -> output_size populated"""
        task_id = "task-output-json"
        task_dir = os.path.join(tasks_root, task_id)
        block_output_dir = os.path.join(task_dir, "block-a", "outputs")
        os.makedirs(block_output_dir, exist_ok=True)

        payload = '{"result": "some data"}'
        with open(os.path.join(block_output_dir, "result.json"), "w") as f:
            f.write(payload)

        _create_rein_db(task_dir, rows=[
            {"name": "block-a", "status": "done", "phase": 1, "progress": 100},
        ])

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)
        b = result["blocks"][0]

        assert "output_size" in b
        assert b["output_size"] == len(payload)

    def test_output_size_md(self, tasks_root):
        """Block with result.md (no result.json) -> output_size from .md"""
        task_id = "task-output-md"
        task_dir = os.path.join(tasks_root, task_id)
        block_output_dir = os.path.join(task_dir, "block-a", "outputs")
        os.makedirs(block_output_dir, exist_ok=True)

        md_content = "# Result\n\nAll good."
        with open(os.path.join(block_output_dir, "result.md"), "w") as f:
            f.write(md_content)

        _create_rein_db(task_dir, rows=[
            {"name": "block-a", "status": "done", "phase": 1, "progress": 100},
        ])

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)
        b = result["blocks"][0]

        assert "output_size" in b
        assert b["output_size"] == len(md_content)

    def test_no_output_files(self, tasks_root):
        """Block without any output files -> no output_size key"""
        task_id = "task-no-output"
        task_dir = os.path.join(tasks_root, task_id)
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[
            {"name": "block-a", "status": "waiting", "phase": 1, "progress": 0},
        ])

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)
        b = result["blocks"][0]

        assert "output_size" not in b

    def test_json_preferred_over_md(self, tasks_root):
        """When both result.json and result.md exist, json takes precedence"""
        task_id = "task-both-outputs"
        task_dir = os.path.join(tasks_root, task_id)
        block_output_dir = os.path.join(task_dir, "block-a", "outputs")
        os.makedirs(block_output_dir, exist_ok=True)

        json_payload = '{"data": "json"}'
        md_payload = "# Markdown result"
        with open(os.path.join(block_output_dir, "result.json"), "w") as f:
            f.write(json_payload)
        with open(os.path.join(block_output_dir, "result.md"), "w") as f:
            f.write(md_payload)

        _create_rein_db(task_dir, rows=[
            {"name": "block-a", "status": "done", "phase": 1, "progress": 100},
        ])

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)
        b = result["blocks"][0]

        assert b["output_size"] == len(json_payload)

    # ---- Return structure invariants ------------------------------------

    def test_return_structure_keys(self, tasks_root):
        """Verify all expected top-level keys are present"""
        task_id = "task-struct"
        task_dir = os.path.join(tasks_root, task_id)
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[
            {"name": "b", "status": "done", "phase": 1, "progress": 100},
        ])

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)

        expected_keys = {"type", "task_id", "status", "total", "done", "failed", "running", "blocks"}
        assert set(result.keys()) == expected_keys

    # ---- Corrupt / invalid database ------------------------------------

    def test_corrupt_db_returns_unknown(self, tasks_root):
        """A corrupt (non-SQLite) rein.db should return status 'unknown'"""
        task_id = "task-corrupt"
        task_dir = os.path.join(tasks_root, task_id)
        state_dir = os.path.join(task_dir, "state")
        os.makedirs(state_dir, exist_ok=True)

        with open(os.path.join(state_dir, "rein.db"), "w") as f:
            f.write("this is not a sqlite database")

        result = get_task_state_snapshot(task_id, tasks_root=tasks_root)

        assert result["status"] == "unknown"
        assert result["blocks"] == []

    # ---- Uses get_tasks_root when no tasks_root given -------------------

    def test_uses_get_tasks_root_default(self, tasks_root):
        """When tasks_root is not provided, get_tasks_root() is called"""
        with patch.dict(os.environ, {"REIN_TASKS_ROOT": tasks_root}):
            task_id = "task-default-root"
            task_dir = os.path.join(tasks_root, task_id)
            os.makedirs(task_dir, exist_ok=True)
            _create_rein_db(task_dir, rows=[
                {"name": "x", "status": "done", "phase": 1, "progress": 100},
            ])

            result = get_task_state_snapshot(task_id)

            assert result["status"] == "completed"
            assert result["total"] == 1


# ===========================================================================
# Tests for get_running_tasks
# ===========================================================================

class TestGetRunningTasks:
    """Tests for get_running_tasks()"""

    @pytest.fixture
    def tasks_root(self):
        """Create a temporary tasks root directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    # ---- Empty / non-existent directory ---------------------------------

    def test_empty_directory(self, tasks_root):
        """No task subdirectories -> empty list"""
        result = get_running_tasks(tasks_root=tasks_root)
        assert result == []

    def test_nonexistent_directory(self):
        """Non-existent tasks_root -> empty list"""
        result = get_running_tasks(tasks_root="/tmp/nonexistent-rein-test-dir")
        assert result == []

    # ---- Completed tasks ------------------------------------------------

    def test_completed_task_not_returned(self, tasks_root):
        """Task where all processes are done is NOT running"""
        task_dir = os.path.join(tasks_root, "task-done")
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[
            {"name": "block-a", "status": "done", "phase": 1, "progress": 100},
            {"name": "block-b", "status": "done", "phase": 2, "progress": 100},
        ])

        result = get_running_tasks(tasks_root=tasks_root)
        assert result == []

    # ---- Failed tasks ---------------------------------------------------

    def test_failed_task_not_returned(self, tasks_root):
        """Task with any failed processes is NOT considered running"""
        task_dir = os.path.join(tasks_root, "task-fail")
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[
            {"name": "block-a", "status": "done", "phase": 1, "progress": 100},
            {"name": "block-b", "status": "failed", "phase": 2, "progress": 10,
             "exit_code": 1},
        ])

        result = get_running_tasks(tasks_root=tasks_root)
        assert result == []

    # ---- Running tasks --------------------------------------------------

    def test_running_task_returned(self, tasks_root):
        """Task with processes still in progress IS returned"""
        task_dir = os.path.join(tasks_root, "task-active")
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[
            {"name": "block-a", "status": "done", "phase": 1, "progress": 100},
            {"name": "block-b", "status": "running", "phase": 2, "progress": 50},
        ])

        result = get_running_tasks(tasks_root=tasks_root)
        assert result == ["task-active"]

    def test_waiting_task_returned(self, tasks_root):
        """Task with waiting processes (total > done, no failures) IS returned"""
        task_dir = os.path.join(tasks_root, "task-waiting")
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[
            {"name": "block-a", "status": "waiting", "phase": 1, "progress": 0},
            {"name": "block-b", "status": "waiting", "phase": 2, "progress": 0},
        ])

        result = get_running_tasks(tasks_root=tasks_root)
        assert result == ["task-waiting"]

    # ---- Multiple tasks -------------------------------------------------

    def test_multiple_tasks_mixed(self, tasks_root):
        """Mix of running, completed, and failed tasks"""
        # Running task
        running_dir = os.path.join(tasks_root, "task-running")
        os.makedirs(running_dir, exist_ok=True)
        _create_rein_db(running_dir, rows=[
            {"name": "block-a", "status": "running", "phase": 1, "progress": 50},
        ])

        # Completed task
        done_dir = os.path.join(tasks_root, "task-done")
        os.makedirs(done_dir, exist_ok=True)
        _create_rein_db(done_dir, rows=[
            {"name": "block-a", "status": "done", "phase": 1, "progress": 100},
        ])

        # Failed task
        fail_dir = os.path.join(tasks_root, "task-fail")
        os.makedirs(fail_dir, exist_ok=True)
        _create_rein_db(fail_dir, rows=[
            {"name": "block-a", "status": "failed", "phase": 1, "progress": 0},
        ])

        # Another running task
        running2_dir = os.path.join(tasks_root, "task-running2")
        os.makedirs(running2_dir, exist_ok=True)
        _create_rein_db(running2_dir, rows=[
            {"name": "block-a", "status": "done", "phase": 1, "progress": 100},
            {"name": "block-b", "status": "waiting", "phase": 2, "progress": 0},
        ])

        result = get_running_tasks(tasks_root=tasks_root)
        assert sorted(result) == ["task-running", "task-running2"]

    # ---- No rein.db present ---------------------------------------------

    def test_task_without_db_not_returned(self, tasks_root):
        """Task directory without rein.db is skipped"""
        task_dir = os.path.join(tasks_root, "task-no-db")
        os.makedirs(task_dir, exist_ok=True)

        result = get_running_tasks(tasks_root=tasks_root)
        assert result == []

    # ---- Non-directory entries ------------------------------------------

    def test_files_in_tasks_root_ignored(self, tasks_root):
        """Regular files in tasks_root are handled gracefully"""
        # Create a plain file (not a directory)
        with open(os.path.join(tasks_root, "not-a-task.txt"), "w") as f:
            f.write("just a file")

        # Create a valid running task alongside
        task_dir = os.path.join(tasks_root, "task-valid")
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[
            {"name": "block-a", "status": "running", "phase": 1, "progress": 25},
        ])

        result = get_running_tasks(tasks_root=tasks_root)
        assert result == ["task-valid"]

    # ---- Corrupt database -----------------------------------------------

    def test_corrupt_db_skipped(self, tasks_root):
        """Task with corrupt rein.db is silently skipped"""
        task_dir = os.path.join(tasks_root, "task-corrupt")
        state_dir = os.path.join(task_dir, "state")
        os.makedirs(state_dir, exist_ok=True)
        with open(os.path.join(state_dir, "rein.db"), "w") as f:
            f.write("garbage data that is not sqlite")

        result = get_running_tasks(tasks_root=tasks_root)
        assert result == []

    # ---- Empty processes table ------------------------------------------

    def test_empty_processes_table_not_running(self, tasks_root):
        """Task with empty processes table (total=0) is NOT running"""
        task_dir = os.path.join(tasks_root, "task-empty-procs")
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[])

        result = get_running_tasks(tasks_root=tasks_root)
        assert result == []

    # ---- Uses get_tasks_root when no tasks_root given -------------------

    def test_uses_get_tasks_root_default(self, tasks_root):
        """When tasks_root is not provided, get_tasks_root() is called"""
        with patch.dict(os.environ, {"REIN_TASKS_ROOT": tasks_root}):
            task_dir = os.path.join(tasks_root, "task-env")
            os.makedirs(task_dir, exist_ok=True)
            _create_rein_db(task_dir, rows=[
                {"name": "b", "status": "running", "phase": 1, "progress": 10},
            ])

            result = get_running_tasks()
            assert result == ["task-env"]

    # ---- Single process task --------------------------------------------

    def test_single_done_process_not_running(self, tasks_root):
        """Single-block task fully done is NOT running"""
        task_dir = os.path.join(tasks_root, "task-single-done")
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[
            {"name": "only-block", "status": "done", "phase": 1, "progress": 100},
        ])

        result = get_running_tasks(tasks_root=tasks_root)
        assert result == []

    def test_single_running_process_is_running(self, tasks_root):
        """Single-block task still running IS returned"""
        task_dir = os.path.join(tasks_root, "task-single-run")
        os.makedirs(task_dir, exist_ok=True)
        _create_rein_db(task_dir, rows=[
            {"name": "only-block", "status": "running", "phase": 1, "progress": 50},
        ])

        result = get_running_tasks(tasks_root=tasks_root)
        assert result == ["task-single-run"]
