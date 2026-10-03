"""A branch skipped by routing must stay skipped when a --step run resumes.

Each step runs in a fresh ProcessManager over the same task dir and SQLite
state, the way an external runner drives `rein --step 1 --task-dir DIR`.
Before the fix, resume restored only `done` blocks, so a branch that routing
had marked `skipped` was spawned on the next step through `depends_on`.
"""

import os
from unittest.mock import MagicMock, patch

from rein.orchestrator import ProcessManager
from rein.providers.base import UsageStats
from rein.state import ReinState
from rein.tasks import load_config
from tests.test_step_mode import _make_manager


def _provider(calls, verdicts):
    """Mock provider: records every prompt, answers the decision block with
    the next verdict from `verdicts` and every other block with a plain result."""

    def call(prompt, *args, **kwargs):
        calls.append(prompt)
        if "PROMPT-decision" in prompt:
            return (next(verdicts), UsageStats())
        return ('{"result": "ok"}', UsageStats())

    provider = MagicMock()
    provider.call.side_effect = call
    provider.last_usage = UsageStats()
    return provider


def _resume(agents_dir, task_dir, db_path, provider):
    """A new ProcessManager over an existing task dir, as a fresh `rein --step` process."""
    flow_path = os.path.join(agents_dir, "flows", "test-flow", "test-flow.yaml")
    config = load_config(flow_path)
    m = ProcessManager(max_parallel=3, flow_name="test-flow", task_input={}, agents_dir=agents_dir)
    m.task_id = os.path.basename(task_dir)
    m.task_dir = task_dir
    m.run_dir = task_dir
    m.log_dir = os.path.join(task_dir, "state")
    m.rein_log_file = os.path.join(task_dir, "state", "rein.log")
    m.db_path = db_path
    m.state = ReinState(db_path, resume=True)
    m._provider = provider
    with patch.object(m, "_init_provider"), patch.object(m, "_run_preflight_validation"):
        m.load_config(config, workflow_file=flow_path)
    m.load_team = lambda name: "Be concise and helpful."
    return m


def _run_one_step_per_process(tmpdir, blocks, verdicts, max_steps):
    """Drive a flow with --step 1 semantics. Returns (finished, prompts, db_path)."""
    calls = []
    provider = _provider(calls, iter(verdicts))
    m = _make_manager(tmpdir, blocks)
    m._provider = provider
    agents_dir = os.path.join(tmpdir, "agents")
    task_dir, db_path = m.task_dir, m.db_path

    finished = m.run_step(1)
    for _ in range(max_steps):
        if finished:
            break
        m = _resume(agents_dir, task_dir, db_path, provider)
        finished = m.run_step(1)
    return finished, calls, db_path


def _ran(calls, names):
    """Block names in the order their prompts reached the provider."""
    return [n for c in calls for n in names if f"PROMPT-{n}" in c]


def test_skipped_branch_stays_skipped_across_step_resumes(tmp_path):
    blocks = [
        {
            "name": "decision",
            "specialist": "spec",
            "prompt": "PROMPT-decision",
            "depends_on": [],
            "routing": {"a": "block_a", "b": "block_b"},
        },
        {"name": "block_a", "specialist": "spec", "prompt": "PROMPT-block_a", "depends_on": ["decision"]},
        {"name": "block_b", "specialist": "spec", "prompt": "PROMPT-block_b", "depends_on": ["decision"]},
    ]
    finished, calls, db_path = _run_one_step_per_process(str(tmp_path), blocks, ["VERDICT: a"], max_steps=6)

    order = _ran(calls, ("decision", "block_a", "block_b"))
    assert finished, order
    assert order == ["decision", "block_a"], order
    statuses = {p.name: p.status for p in ReinState(db_path, resume=True).get_all_processes()}
    assert statuses["block_b"] == "skipped", statuses


def test_branch_skipped_on_first_pass_runs_when_chosen_after_revise(tmp_path):
    """A branch skipped on the first pass must still run when a later pass chooses it,
    and the branch not chosen on the last pass must not run."""
    blocks = [
        {"name": "draft", "specialist": "spec", "prompt": "PROMPT-draft", "depends_on": [], "max_runs": 3},
        {
            "name": "decision",
            "specialist": "spec",
            "prompt": "PROMPT-decision",
            "depends_on": ["draft"],
            "max_runs": 3,
            "routing": {"revise": "draft", "approve": "deliver", "cancel": "cancelled"},
        },
        {"name": "deliver", "specialist": "spec", "prompt": "PROMPT-deliver", "depends_on": ["decision"]},
        {"name": "cancelled", "specialist": "spec", "prompt": "PROMPT-cancelled", "depends_on": ["decision"]},
    ]
    finished, calls, _ = _run_one_step_per_process(
        str(tmp_path), blocks, ["VERDICT: revise", "VERDICT: approve"], max_steps=10
    )

    order = _ran(calls, ("draft", "decision", "deliver", "cancelled"))
    assert finished, order
    assert order == ["draft", "decision", "draft", "decision", "deliver"], order
