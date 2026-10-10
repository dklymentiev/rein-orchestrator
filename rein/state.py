"""
Rein State Manager - SQLite-based state persistence for workflow execution
"""

import functools
import sqlite3
import threading
import time
from typing import List

from .models import Process


def _serialized(method):
    """Run a ReinState method under the instance lock.

    Every method opens its own connection. Blocks finish on their own threads
    while the main loop reads, and two connections of one process working on
    the same file at the same moment have been seen to fail with "disk I/O
    error". One at a time is plenty for a state store this small.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class ReinState:
    """State management with SQLite"""

    def __init__(self, db_path: str = "/tmp/rein.db", resume: bool = False):
        self.db_path = db_path
        self.resume = resume
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self):
        """Initialize database schema and clean old data"""
        conn = sqlite3.connect(self.db_path)

        # If resuming, don't drop the table - preserve existing data
        if not self.resume:
            # Drop old table if exists (fresh run)
            conn.execute("DROP TABLE IF EXISTS processes")
            conn.execute("DROP TABLE IF EXISTS time_budget")

        # Create table if it doesn't exist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processes (
                name TEXT PRIMARY KEY,
                pid INTEGER,
                status TEXT,
                start_time REAL,
                command TEXT,
                exit_code INTEGER,
                cpu_percent REAL,
                memory_mb REAL,
                progress INTEGER,
                phase INTEGER,
                blocking_pause INTEGER,
                updated_at REAL,
                run_count INTEGER DEFAULT 0,
                completed_runs INTEGER DEFAULT 0
            )
        """)

        # Time budgets: when the run and each block attempt started, and when a
        # budget was found exceeded. Created on first touch, so a database made
        # by an earlier version gains it without a migration step.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS time_budget (
                name TEXT PRIMARY KEY,
                started_at REAL NOT NULL,
                expired_at REAL
            )
        """)

        # Schema migration: add columns to existing DBs
        if self.resume:
            try:
                cols = [row[1] for row in conn.execute("PRAGMA table_info(processes)").fetchall()]
                if "run_count" not in cols:
                    conn.execute("ALTER TABLE processes ADD COLUMN run_count INTEGER DEFAULT 0")
                if "completed_runs" not in cols:
                    conn.execute("ALTER TABLE processes ADD COLUMN completed_runs INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass

        conn.commit()
        conn.close()

    @_serialized
    def save_process(self, proc: Process):
        """Save process state"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            REPLACE INTO processes
            (name, pid, status, start_time, command, exit_code, cpu_percent, memory_mb, progress, phase, blocking_pause, updated_at, run_count, completed_runs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                proc.name,
                proc.pid,
                proc.status,
                proc.start_time,
                proc.command,
                proc.exit_code,
                proc.cpu_percent,
                proc.memory_mb,
                proc.progress,
                proc.phase,
                int(proc.blocking_pause),
                time.time(),
                proc.run_count,
                proc.completed_runs,
            ),
        )
        conn.commit()
        conn.close()

    @_serialized
    def get_all_processes(self) -> List[Process]:
        """Get all tracked processes"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT name, pid, status, start_time, command, exit_code, cpu_percent, memory_mb, progress, phase, blocking_pause, run_count, completed_runs FROM processes ORDER BY phase, name"
        ).fetchall()
        conn.close()

        processes = []
        for row in rows:
            proc = Process(
                name=row[0],
                pid=row[1],
                status=row[2],
                start_time=row[3],
                command=row[4],
                exit_code=row[5],
                cpu_percent=row[6],
                memory_mb=row[7],
                progress=row[8],
                phase=row[9],
                blocking_pause=bool(row[10]),
                run_count=row[11] or 0,
                completed_runs=row[12] or 0,
            )
            processes.append(proc)
        return processes

    @_serialized
    def get_process(self, name: str) -> Process:
        """Get single process by name"""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT name, pid, status, start_time, command, exit_code, cpu_percent, memory_mb, progress, phase, blocking_pause, run_count, completed_runs FROM processes WHERE name = ?",
            (name,),
        ).fetchone()
        conn.close()

        if row:
            return Process(
                name=row[0],
                pid=row[1],
                status=row[2],
                start_time=row[3],
                command=row[4],
                exit_code=row[5],
                cpu_percent=row[6],
                memory_mb=row[7],
                progress=row[8],
                phase=row[9],
                blocking_pause=bool(row[10]),
                run_count=row[11] or 0,
                completed_runs=row[12] or 0,
            )
        return None

    @_serialized
    def update_status(self, name: str, status: str, exit_code: int = None):
        """Update process status"""
        conn = sqlite3.connect(self.db_path)
        if exit_code is not None:
            conn.execute(
                "UPDATE processes SET status = ?, exit_code = ?, updated_at = ? WHERE name = ?",
                (status, exit_code, time.time(), name),
            )
        else:
            conn.execute("UPDATE processes SET status = ?, updated_at = ? WHERE name = ?", (status, time.time(), name))
        conn.commit()
        conn.close()

    @_serialized
    def budget_start(self, name: str, now: float) -> None:
        """Record when an attempt started, unless one is already recorded.

        Keeping the first value is the point: a block that runs again within
        the same attempt must not get a fresh start time.
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT OR IGNORE INTO time_budget (name, started_at) VALUES (?, ?)", (name, now))
        conn.commit()
        conn.close()

    @_serialized
    def budget_clear(self, name: str) -> None:
        """Forget an attempt: the block finished, or a new attempt begins."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM time_budget WHERE name = ?", (name,))
        conn.commit()
        conn.close()

    @_serialized
    def budget_rows(self) -> dict:
        """Return {name: (started_at, expired_at)} for every recorded attempt."""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT name, started_at, expired_at FROM time_budget").fetchall()
        conn.close()
        return {name: (started_at, expired_at) for name, started_at, expired_at in rows}

    @_serialized
    def budget_claim_expiry(self, name: str, now: float) -> bool:
        """Mark an attempt as over budget. True only for the caller that marked it.

        The update is conditional, so however many processes notice the same
        expiry, exactly one of them gets True and acts on it.
        """
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "UPDATE time_budget SET expired_at = ? WHERE name = ? AND expired_at IS NULL",
            (now, name),
        )
        conn.commit()
        claimed = cur.rowcount == 1
        conn.close()
        return claimed

    @_serialized
    def clear(self):
        """Clear all process data"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM processes")
        conn.commit()
        conn.close()
