"""
Rein State Manager - SQLite-based state persistence for workflow execution
"""
import sqlite3
import time
from typing import List

from .models import Process


class ReinState:
    """State management with SQLite"""

    def __init__(self, db_path: str = "/tmp/rein.db", resume: bool = False):
        self.db_path = db_path
        self.resume = resume
        self._init_db()

    def _init_db(self):
        """Initialize database schema and clean old data"""
        conn = sqlite3.connect(self.db_path)

        # If resuming, don't drop the table - preserve existing data
        if not self.resume:
            # Drop old table if exists (fresh run)
            conn.execute("DROP TABLE IF EXISTS processes")

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
                updated_at REAL
            )
        """)
        conn.commit()
        conn.close()


    def save_process(self, proc: Process):
        """Save process state"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            REPLACE INTO processes
            (name, pid, status, start_time, command, exit_code, cpu_percent, memory_mb, progress, phase, blocking_pause, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (proc.name, proc.pid, proc.status, proc.start_time, proc.command,
              proc.exit_code, proc.cpu_percent, proc.memory_mb, proc.progress, proc.phase, int(proc.blocking_pause), time.time()))
        conn.commit()
        conn.close()

    def get_all_processes(self) -> List[Process]:
        """Get all tracked processes"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT name, pid, status, start_time, command, exit_code, cpu_percent, memory_mb, progress, phase, blocking_pause FROM processes ORDER BY phase, name"
        ).fetchall()
        conn.close()

        processes = []
        for row in rows:
            proc = Process(
                name=row[0], pid=row[1], status=row[2],
                start_time=row[3], command=row[4],
                exit_code=row[5], cpu_percent=row[6],
                memory_mb=row[7], progress=row[8],
                phase=row[9], blocking_pause=bool(row[10])
            )
            processes.append(proc)
        return processes

    def get_process(self, name: str) -> Process:
        """Get single process by name"""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT name, pid, status, start_time, command, exit_code, cpu_percent, memory_mb, progress, phase, blocking_pause FROM processes WHERE name = ?",
            (name,)
        ).fetchone()
        conn.close()

        if row:
            return Process(
                name=row[0], pid=row[1], status=row[2],
                start_time=row[3], command=row[4],
                exit_code=row[5], cpu_percent=row[6],
                memory_mb=row[7], progress=row[8],
                phase=row[9], blocking_pause=bool(row[10])
            )
        return None

    def update_status(self, name: str, status: str, exit_code: int = None):
        """Update process status"""
        conn = sqlite3.connect(self.db_path)
        if exit_code is not None:
            conn.execute(
                "UPDATE processes SET status = ?, exit_code = ?, updated_at = ? WHERE name = ?",
                (status, exit_code, time.time(), name)
            )
        else:
            conn.execute(
                "UPDATE processes SET status = ?, updated_at = ? WHERE name = ?",
                (status, time.time(), name)
            )
        conn.commit()
        conn.close()

    def clear(self):
        """Clear all process data"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM processes")
        conn.commit()
        conn.close()
