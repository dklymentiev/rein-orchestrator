"""Tests for routing branch skip (fix #1190).

When a gate block uses `routing:` to select one of several targets, the
non-chosen branches must be marked skipped so the main loop does not also
spawn them via depends_on scheduling.
"""
from rein import state_machine


def _dm(blocks):
    return state_machine.get_dependents_map(blocks)


def test_simple_two_branch_routing():
    """Gate routes to `merge`; `fix` branch must be skipped."""
    blocks = [
        {"name": "gate", "depends_on": []},
        {"name": "merge", "depends_on": ["gate"]},
        {"name": "fix", "depends_on": ["gate"]},
    ]
    routing = {"needs-review": "fix", "_default": "merge"}
    skip = state_machine.compute_routing_skip_set(routing, "merge", "gate", _dm(blocks))
    assert skip == {"fix"}


def test_skip_cascades_to_branch_descendants():
    """Skipped branch `fix` has its own child `fix_verify`; it must also be skipped."""
    blocks = [
        {"name": "gate", "depends_on": []},
        {"name": "merge", "depends_on": ["gate"]},
        {"name": "fix", "depends_on": ["gate"]},
        {"name": "fix_verify", "depends_on": ["fix"]},
    ]
    routing = {"needs-review": "fix", "_default": "merge"}
    skip = state_machine.compute_routing_skip_set(routing, "merge", "gate", _dm(blocks))
    assert skip == {"fix", "fix_verify"}


def test_reconverging_block_is_not_skipped():
    """A block that depends on BOTH chosen and non-chosen branches must not be
    skipped -- the winning path will unblock it."""
    blocks = [
        {"name": "gate", "depends_on": []},
        {"name": "merge", "depends_on": ["gate"]},
        {"name": "fix", "depends_on": ["gate"]},
        {"name": "final", "depends_on": ["merge", "fix"]},  # reconverges
    ]
    routing = {"needs-review": "fix", "_default": "merge"}
    skip = state_machine.compute_routing_skip_set(routing, "merge", "gate", _dm(blocks))
    # fix is skipped, but final is reachable from merge (the winner) so it lives
    assert "fix" in skip
    assert "final" not in skip


def test_three_way_routing_skips_two_branches():
    blocks = [
        {"name": "triage", "depends_on": []},
        {"name": "bug", "depends_on": ["triage"]},
        {"name": "feature", "depends_on": ["triage"]},
        {"name": "docs", "depends_on": ["triage"]},
    ]
    routing = {"is-bug": "bug", "is-feature": "feature", "_default": "docs"}
    skip = state_machine.compute_routing_skip_set(routing, "bug", "triage", _dm(blocks))
    assert skip == {"feature", "docs"}


def test_gate_never_skipped():
    """The gate itself must never appear in the skip set even if routing loops back."""
    blocks = [
        {"name": "gate", "depends_on": []},
        {"name": "a", "depends_on": ["gate"]},
        {"name": "b", "depends_on": ["gate"]},
    ]
    # Pathological: routing target is the gate itself (backward routing)
    routing = {"retry": "gate", "_default": "a"}
    skip = state_machine.compute_routing_skip_set(routing, "a", "gate", _dm(blocks))
    assert "gate" not in skip


def test_chosen_never_skipped():
    blocks = [
        {"name": "gate", "depends_on": []},
        {"name": "a", "depends_on": ["gate"]},
        {"name": "b", "depends_on": ["gate"]},
    ]
    routing = {"sig": "a", "_default": "b"}
    skip = state_machine.compute_routing_skip_set(routing, "a", "gate", _dm(blocks))
    assert "a" not in skip
    assert skip == {"b"}


def test_stop_marker_ignored():
    """`_stop` is a control marker, not a real block -- should not appear in skip set."""
    blocks = [
        {"name": "gate", "depends_on": []},
        {"name": "proceed", "depends_on": ["gate"]},
    ]
    routing = {"halt": "_stop", "_default": "proceed"}
    skip = state_machine.compute_routing_skip_set(routing, "proceed", "gate", _dm(blocks))
    assert skip == set()


def test_empty_routing():
    blocks = [{"name": "gate", "depends_on": []}]
    skip = state_machine.compute_routing_skip_set({}, "gate", "gate", _dm(blocks))
    assert skip == set()
