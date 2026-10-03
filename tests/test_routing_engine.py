"""Tests for rein.routing_engine.

These tests cover signal extraction and routing rule matching, including
the determinism guarantee: when a block emits two signals that both
appear in the routing dict, the first declared routing key wins, not
whichever the set iterator happens to visit first.
"""

from rein.routing_engine import extract_verdict_signals, match_routing_rule

# ---------------------------------------------------------------------------
# extract_verdict_signals
# ---------------------------------------------------------------------------


def test_extract_single_verdict():
    signals = extract_verdict_signals("VERDICT: DONE\nSome text")
    assert "done" in signals


def test_extract_legacy_pass():
    signals = extract_verdict_signals("VERDICT: PASS")
    assert "needs-review" in signals
    assert "pass" in signals


def test_extract_legacy_approved():
    signals = extract_verdict_signals("VERDICT: APPROVED")
    assert "needs-review" in signals


def test_extract_legacy_revise():
    signals = extract_verdict_signals("VERDICT: REVISE")
    assert "revise" in signals


def test_extract_custom_verdict():
    signals = extract_verdict_signals("VERDICT: bounced")
    assert "bounced" in signals


def test_extract_no_verdict():
    assert extract_verdict_signals("no verdict here") == set()


def test_extract_empty_string():
    assert extract_verdict_signals("") == set()


def test_extract_multiple_verdicts():
    text = "VERDICT: DONE\nVERDICT: PASS"
    signals = extract_verdict_signals(text)
    assert "done" in signals
    assert "needs-review" in signals


# ---------------------------------------------------------------------------
# match_routing_rule -- basic cases
# ---------------------------------------------------------------------------


def test_match_explicit_signal():
    routing = {"revise": "block_a", "_default": "block_b"}
    next_block, signal = match_routing_rule(routing, {"revise"})
    assert next_block == "block_a"
    assert signal == "revise"


def test_match_default_when_no_signal_matches():
    routing = {"revise": "block_a", "_default": "block_b"}
    next_block, signal = match_routing_rule(routing, {"approve"})
    assert next_block == "block_b"
    assert signal == "_default"


def test_match_default_when_signals_empty():
    routing = {"_default": "block_b"}
    next_block, signal = match_routing_rule(routing, set())
    assert next_block == "block_b"
    assert signal == "_default"


def test_match_no_default_no_signal():
    routing = {"revise": "block_a"}
    next_block, signal = match_routing_rule(routing, set())
    assert next_block is None
    assert signal == "_default"


# ---------------------------------------------------------------------------
# match_routing_rule -- DECLARATION ORDER determinism
#
# When a block emits two signals that both appear as routing keys, the engine
# must pick the key that appears FIRST in the routing dict, not whichever the
# Python set iterator visits first. This test exercises that contract.
#
# With the buggy code (iterating the signals set) this test is flaky: it
# passes under some PYTHONHASHSEED values and fails under others. After the
# fix (iterating routing keys in declaration order) it always passes.
# ---------------------------------------------------------------------------


def test_declaration_order_first_key_wins():
    """First declared routing key wins when both signals are present."""
    routing = {"revise": "block_a", "approve": "block_b", "_default": "block_c"}
    signals = {"revise", "approve"}
    next_block, matched = match_routing_rule(routing, signals)
    assert matched == "revise", (
        f"Expected first declared key 'revise' but got {matched!r}. "
        "The routing engine must iterate routing keys in declaration order, "
        "not signal set order."
    )
    assert next_block == "block_a"


def test_declaration_order_second_key_wins_when_first_absent():
    """Second declared key wins when first is absent from signals."""
    routing = {"revise": "block_a", "approve": "block_b", "_default": "block_c"}
    signals = {"approve"}
    next_block, matched = match_routing_rule(routing, signals)
    assert matched == "approve"
    assert next_block == "block_b"


def test_declaration_order_three_keys_first_declared_wins():
    """With three declared keys and all three signals present, first wins."""
    routing = {"alpha": "A", "beta": "B", "gamma": "C", "_default": "D"}
    signals = {"gamma", "alpha", "beta"}
    next_block, matched = match_routing_rule(routing, signals)
    assert matched == "alpha", f"Expected 'alpha' (first declared) but got {matched!r}"
    assert next_block == "A"


def test_declaration_order_consistent_across_many_calls():
    """match_routing_rule must return the same result on every call.

    Runs the function 500 times with the same inputs. With a hash-randomised
    set this would produce different results across calls; after the fix it
    must always return the same answer.
    """
    routing = {"revise": "block_a", "approve": "block_b", "_default": "block_c"}
    signals = {"revise", "approve"}
    results = {match_routing_rule(routing, signals)[1] for _ in range(500)}
    assert results == {"revise"}, (
        f"Got multiple distinct results: {results}. "
        "Routing must be deterministic regardless of signal set iteration order."
    )
