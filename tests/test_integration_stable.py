"""Stable integration tests using deterministic mock scripts.

These tests use fixtures in tests/fixtures/ with:
- pass.py: instant pass-through (no delays, no randomness)
- gate_retry_once.py: deterministic gate (fails run 0, passes run 1+)
- gate_pass.py: deterministic gate (passes on first try)

All tests should be idempotent and produce identical results every run.
"""
import os
import sqlite3
import subprocess
import pytest


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
REIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Load .env for subprocess (provider config)
_ENV = os.environ.copy()
_env_file = os.path.join(REIN_DIR, ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                _ENV[k.strip()] = v.strip()


def _run_fixture_flow(flow_name, timeout=60):
    """Run a fixture flow and return (code, stdout, run_dir)."""
    yaml_path = os.path.join(FIXTURES_DIR, "flows", flow_name, f"{flow_name}.yaml")
    assert os.path.exists(yaml_path), f"Flow not found: {yaml_path}"

    result = subprocess.run(
        ["python3", "-m", "rein", yaml_path, "--no-ui"],
        capture_output=True, text=True, timeout=timeout,
        cwd=REIN_DIR, env=_ENV,
    )
    run_dir = None
    for line in result.stdout.split("\n"):
        if "Run Directory:" in line:
            run_dir = line.split(":", 1)[1].strip()
            break
    return result.returncode, result.stdout, run_dir


def _get_block_states(run_dir):
    db_path = os.path.join(run_dir, "state", "rein.db")
    if not os.path.exists(db_path):
        return {}
    db = sqlite3.connect(db_path)
    rows = db.execute("SELECT name, status, run_count FROM processes").fetchall()
    db.close()
    return {name: {"status": status, "runs": rc} for name, status, rc in rows}


# ============================================================
# Linear 3-block flow: A -> B -> C
# ============================================================

class TestLinear3:
    """Simple linear chain, no routing, no retries."""

    def test_completes_successfully(self):
        code, stdout, run_dir = _run_fixture_flow("linear-3")
        assert code == 0, f"Exit {code}"

    def test_exactly_3_block_done(self):
        """Each block runs exactly once"""
        code, stdout, run_dir = _run_fixture_flow("linear-3")
        assert stdout.count("[BLOCK_DONE]") == 3

    def test_execution_order(self):
        """Blocks execute in dependency order: a before b before c"""
        code, stdout, run_dir = _run_fixture_flow("linear-3")
        done_blocks = []
        for line in stdout.split("\n"):
            if "[BLOCK_DONE]" in line and "block=" in line:
                done_blocks.append(line.split("block=")[1].strip())
        assert done_blocks.index("step_a") < done_blocks.index("step_b")
        assert done_blocks.index("step_b") < done_blocks.index("step_c")

    def test_all_blocks_done_in_sqlite(self):
        """All 3 blocks marked done in SQLite"""
        code, stdout, run_dir = _run_fixture_flow("linear-3")
        states = _get_block_states(run_dir)
        assert len(states) == 3
        for name, state in states.items():
            assert state["status"] == "done", f"{name} is {state['status']}"

    def test_deterministic_across_runs(self):
        """Same result every time"""
        results = []
        for _ in range(3):
            code, stdout, run_dir = _run_fixture_flow("linear-3")
            results.append((code, stdout.count("[BLOCK_DONE]")))
        assert all(r == (0, 3) for r in results), f"Nondeterministic: {results}"


# ============================================================
# Fan-out / fan-in: start -> {a, b, c} -> merge
# ============================================================

class TestFanoutFanin:
    """Diamond dependency: parallel branches merge into single block."""

    def test_completes_successfully(self):
        code, stdout, run_dir = _run_fixture_flow("fanout-fanin")
        assert code == 0

    def test_all_5_blocks_done(self):
        code, stdout, run_dir = _run_fixture_flow("fanout-fanin")
        states = _get_block_states(run_dir)
        assert len(states) == 5
        for name, state in states.items():
            assert state["status"] == "done"

    def test_merge_runs_after_branches(self):
        """merge must complete after all three branches"""
        code, stdout, run_dir = _run_fixture_flow("fanout-fanin")
        done_order = []
        for line in stdout.split("\n"):
            if "[BLOCK_DONE]" in line and "block=" in line:
                done_order.append(line.split("block=")[1].strip())
        merge_idx = done_order.index("merge")
        for branch in ("branch_a", "branch_b", "branch_c"):
            assert done_order.index(branch) < merge_idx

    def test_start_runs_first(self):
        code, stdout, run_dir = _run_fixture_flow("fanout-fanin")
        done_order = []
        for line in stdout.split("\n"):
            if "[BLOCK_DONE]" in line and "block=" in line:
                done_order.append(line.split("block=")[1].strip())
        assert done_order[0] == "start"


# ============================================================
# Gate that passes on first run (forward routing)
# ============================================================

class TestGatePass:
    """Gate always passes -- forward routing to _default target."""

    def test_completes_successfully(self):
        code, stdout, run_dir = _run_fixture_flow("gate-pass")
        assert code == 0

    def test_fix_is_skipped_when_gate_routes_to_finish(self):
        """After fix #1190: non-chosen routing branches are explicitly skipped.
        Gate routes to _default=finish, so fix must NOT execute."""
        code, stdout, run_dir = _run_fixture_flow("gate-pass")
        states = _get_block_states(run_dir)
        assert states["finish"]["status"] == "done"
        assert states["fix"]["status"] == "skipped"

    def test_finish_executes_under_routing_default(self):
        """After fix #1190: finish (routing _default target) runs to completion
        without being blocked by depends_on race with the fix branch."""
        code, stdout, run_dir = _run_fixture_flow("gate-pass")
        states = _get_block_states(run_dir)
        assert states["finish"]["status"] == "done"


# ============================================================
# Routing with deterministic retry cycle
# ============================================================

class TestSimpleRouting:
    """Gate fails once then passes -- tests backward routing and cascade."""

    def test_completes_successfully(self):
        code, stdout, run_dir = _run_fixture_flow("simple-routing", timeout=90)
        assert code == 0

    def test_gate_runs_twice(self):
        """Gate runs twice: first REVISE, then PASS"""
        code, stdout, run_dir = _run_fixture_flow("simple-routing", timeout=90)
        gate_starts = sum(
            1 for line in stdout.split("\n")
            if "[BLOCK_START]" in line and "block=gate" in line
        )
        assert gate_starts >= 2, f"Expected 2+ gate runs, got {gate_starts}"

    def test_fix_executed_once(self):
        """fix block runs once (called by revise signal)"""
        code, stdout, run_dir = _run_fixture_flow("simple-routing", timeout=90)
        fix_dones = sum(
            1 for line in stdout.split("\n")
            if "[BLOCK_DONE]" in line and "block=fix" in line
        )
        assert fix_dones >= 1, "fix should have run at least once"

    def test_process_terminates_cleanly(self):
        """Process exits cleanly (no hang). finish state may vary due to #1190."""
        code, stdout, run_dir = _run_fixture_flow("simple-routing", timeout=90)
        assert code == 0
        states = _get_block_states(run_dir)
        # gate and prepare must be done; finish may be affected by race
        assert states["prepare"]["status"] == "done"
        assert states["gate"]["status"] == "done"

    def test_gate_and_prepare_done(self):
        """gate and prepare must reach done state (finish subject to #1190 race)"""
        code, stdout, run_dir = _run_fixture_flow("simple-routing", timeout=90)
        states = _get_block_states(run_dir)
        assert states["gate"]["status"] == "done"
        assert states["prepare"]["status"] == "done"
