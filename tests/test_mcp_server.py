"""Tests for rein.mcp_server - MCP tool functions."""
import json
import os
import sqlite3
import tempfile

import pytest
import yaml

from rein.mcp_server import (
    list_flows,
    list_specialists,
    list_teams,
    create_task,
    task_status,
    list_tasks,
)


@pytest.fixture
def agents_dir(tmp_path):
    """Create a minimal agents directory structure."""
    flows_dir = tmp_path / "flows"
    specs_dir = tmp_path / "specialists"
    teams_dir = tmp_path / "teams"
    tasks_dir = tmp_path / "tasks"

    flows_dir.mkdir()
    specs_dir.mkdir()
    teams_dir.mkdir()
    tasks_dir.mkdir()

    # Create a flow
    flow_dir = flows_dir / "test-flow"
    flow_dir.mkdir()
    flow_yaml = {
        "name": "test-flow",
        "description": "A test flow",
        "team": "test-team",
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "blocks": [
            {"name": "block1", "specialist": "researcher", "prompt": "Do research", "depends_on": []},
            {"name": "block2", "specialist": "writer", "prompt": "Write", "depends_on": ["block1"]},
        ],
    }
    with open(flow_dir / "test-flow.yaml", "w") as f:
        yaml.dump(flow_yaml, f)

    # Create specialists
    (specs_dir / "researcher.md").write_text(
        "# Researcher\n\nYou are a research analyst.\n\n## Goal\nFind facts.\n"
    )
    (specs_dir / "writer.md").write_text(
        "# Writer\n\nYou are a technical writer.\n\n## Goal\nWrite articles.\n"
    )

    # Create team
    team_yaml = {
        "name": "test-team",
        "description": "Test team",
        "specialists": ["researcher", "writer"],
        "collaboration_tone": "Be factual.",
    }
    with open(teams_dir / "test-team.yaml", "w") as f:
        yaml.dump(team_yaml, f)

    return str(tmp_path)


# ---------------------------------------------------------------------------
# list_flows
# ---------------------------------------------------------------------------

class TestListFlows:
    def test_lists_flows(self, agents_dir):
        result = json.loads(list_flows(agents_dir=agents_dir))
        assert len(result["flows"]) == 1
        flow = result["flows"][0]
        assert flow["name"] == "test-flow"
        assert flow["description"] == "A test flow"
        assert flow["blocks"] == 2
        assert flow["team"] == "test-team"

    def test_empty_dir(self, tmp_path):
        flows_dir = tmp_path / "flows"
        flows_dir.mkdir()
        result = json.loads(list_flows(agents_dir=str(tmp_path)))
        assert result["flows"] == []

    def test_missing_dir(self, tmp_path):
        result = json.loads(list_flows(agents_dir=str(tmp_path / "nope")))
        assert "error" in result

    def test_malformed_yaml(self, tmp_path):
        flows_dir = tmp_path / "flows" / "bad"
        flows_dir.mkdir(parents=True)
        (flows_dir / "bad.yaml").write_text(": invalid: yaml: [")
        result = json.loads(list_flows(agents_dir=str(tmp_path)))
        assert len(result["flows"]) == 1
        assert "error" in result["flows"][0]


# ---------------------------------------------------------------------------
# list_specialists
# ---------------------------------------------------------------------------

class TestListSpecialists:
    def test_lists_specialists(self, agents_dir):
        result = json.loads(list_specialists(agents_dir=agents_dir))
        assert result["count"] == 2
        names = [s["name"] for s in result["specialists"]]
        assert "researcher" in names
        assert "writer" in names

    def test_summary_skips_headers(self, agents_dir):
        result = json.loads(list_specialists(agents_dir=agents_dir))
        for spec in result["specialists"]:
            # First non-header line should be the summary
            assert not spec["summary"].startswith("#")

    def test_empty_dir(self, tmp_path):
        (tmp_path / "specialists").mkdir()
        result = json.loads(list_specialists(agents_dir=str(tmp_path)))
        assert result["count"] == 0

    def test_missing_dir(self, tmp_path):
        result = json.loads(list_specialists(agents_dir=str(tmp_path)))
        assert "error" in result


# ---------------------------------------------------------------------------
# list_teams
# ---------------------------------------------------------------------------

class TestListTeams:
    def test_lists_teams(self, agents_dir):
        result = json.loads(list_teams(agents_dir=agents_dir))
        assert len(result["teams"]) == 1
        team = result["teams"][0]
        assert team["name"] == "test-team"
        assert "researcher" in team["specialists"]
        assert "writer" in team["specialists"]

    def test_missing_dir(self, tmp_path):
        result = json.loads(list_teams(agents_dir=str(tmp_path)))
        assert "error" in result


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------

class TestCreateTask:
    def test_creates_task_structure(self, agents_dir):
        result = json.loads(create_task(
            flow="test-flow",
            question="What is WebSocket?",
            agents_dir=agents_dir,
        ))
        assert result["status"] == "pending"
        assert result["flow"] == "test-flow"
        task_id = result["task_id"]
        assert task_id.startswith("task-")

        # Verify filesystem
        task_dir = result["task_dir"]
        assert os.path.isdir(task_dir)
        assert os.path.isfile(os.path.join(task_dir, "task.yaml"))
        assert os.path.isfile(os.path.join(task_dir, "input", "question.txt"))
        assert os.path.isfile(os.path.join(task_dir, "state", "status"))

        # Verify task.yaml content
        with open(os.path.join(task_dir, "task.yaml")) as f:
            cfg = yaml.safe_load(f)
        assert cfg["flow"] == "test-flow"
        assert cfg["id"] == task_id

        # Verify question
        with open(os.path.join(task_dir, "input", "question.txt")) as f:
            assert f.read() == "What is WebSocket?"

        # Verify status marker
        with open(os.path.join(task_dir, "state", "status")) as f:
            assert f.read() == "pending"

    def test_invalid_flow(self, agents_dir):
        result = json.loads(create_task(
            flow="nonexistent",
            question="test",
            agents_dir=agents_dir,
        ))
        assert "error" in result


# ---------------------------------------------------------------------------
# task_status
# ---------------------------------------------------------------------------

class TestTaskStatus:
    def _make_task_with_db(self, agents_dir, task_id, blocks):
        """Helper: create a task dir with rein.db containing given blocks."""
        tasks_root = os.path.join(agents_dir, "tasks")
        task_dir = os.path.join(tasks_root, task_id)
        state_dir = os.path.join(task_dir, "state")
        os.makedirs(state_dir, exist_ok=True)

        # task.yaml
        with open(os.path.join(task_dir, "task.yaml"), "w") as f:
            yaml.dump({"id": task_id, "flow": "test-flow"}, f)

        # rein.db
        db_path = os.path.join(state_dir, "rein.db")
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE processes (
                name TEXT PRIMARY KEY,
                status TEXT DEFAULT 'pending',
                phase TEXT DEFAULT '',
                progress TEXT DEFAULT '',
                start_time REAL,
                updated_at REAL,
                exit_code INTEGER
            )
        """)
        for block in blocks:
            conn.execute(
                "INSERT INTO processes (name, status, phase, progress) VALUES (?, ?, ?, ?)",
                (block["name"], block["status"], block.get("phase", ""), block.get("progress", "")),
            )
        conn.commit()
        conn.close()
        return task_dir

    def test_completed_task(self, agents_dir):
        self._make_task_with_db(agents_dir, "task-001", [
            {"name": "block1", "status": "done"},
            {"name": "block2", "status": "done"},
        ])
        result = json.loads(task_status("task-001", agents_dir=agents_dir))
        assert result["status"] == "completed"
        assert result["total"] == 2
        assert result["done"] == 2

    def test_running_task(self, agents_dir):
        self._make_task_with_db(agents_dir, "task-002", [
            {"name": "block1", "status": "done"},
            {"name": "block2", "status": "running"},
        ])
        result = json.loads(task_status("task-002", agents_dir=agents_dir))
        assert result["status"] == "running"
        assert result["running"] == 1

    def test_failed_task(self, agents_dir):
        self._make_task_with_db(agents_dir, "task-003", [
            {"name": "block1", "status": "done"},
            {"name": "block2", "status": "failed"},
        ])
        result = json.loads(task_status("task-003", agents_dir=agents_dir))
        assert result["status"] == "failed"
        assert result["failed"] == 1

    def test_pending_no_db(self, agents_dir):
        task_dir = os.path.join(agents_dir, "tasks", "task-004")
        state_dir = os.path.join(task_dir, "state")
        os.makedirs(state_dir, exist_ok=True)
        with open(os.path.join(state_dir, "status"), "w") as f:
            f.write("pending")
        with open(os.path.join(task_dir, "task.yaml"), "w") as f:
            yaml.dump({"id": "task-004", "flow": "test-flow"}, f)
        result = json.loads(task_status("task-004", agents_dir=agents_dir))
        assert result["status"] == "pending"

    def test_not_found(self, agents_dir):
        result = json.loads(task_status("nonexistent", agents_dir=agents_dir))
        assert "error" in result


# ---------------------------------------------------------------------------
# list_tasks
# ---------------------------------------------------------------------------

class TestListTasks:
    def _make_task(self, agents_dir, task_id, flow="test-flow"):
        """Helper: create a minimal task directory."""
        task_dir = os.path.join(agents_dir, "tasks", task_id)
        os.makedirs(os.path.join(task_dir, "state"), exist_ok=True)
        with open(os.path.join(task_dir, "task.yaml"), "w") as f:
            yaml.dump({"id": task_id, "flow": flow, "created_at": "2026-01-01T00:00:00"}, f)
        with open(os.path.join(task_dir, "state", "status"), "w") as f:
            f.write("pending")

    def test_lists_tasks(self, agents_dir):
        self._make_task(agents_dir, "task-001")
        self._make_task(agents_dir, "task-002")

        result = json.loads(list_tasks(agents_dir=agents_dir))
        assert result["count"] == 2
        for task in result["tasks"]:
            assert task["flow"] == "test-flow"

    def test_empty_tasks(self, tmp_path):
        (tmp_path / "tasks").mkdir()
        result = json.loads(list_tasks(agents_dir=str(tmp_path)))
        assert result["count"] == 0
        assert result["tasks"] == []

    def test_limit(self, agents_dir):
        for i in range(5):
            self._make_task(agents_dir, f"task-{i:03d}")
        result = json.loads(list_tasks(agents_dir=agents_dir, limit=3))
        assert result["count"] == 3

    def test_no_tasks_dir(self, tmp_path):
        result = json.loads(list_tasks(agents_dir=str(tmp_path)))
        assert result["tasks"] == []
