"""Tests for rein/orchestrator.py - ProcessManager pure logic methods"""
import os
import time
import pytest
import tempfile

from rein.models import Process
from rein.orchestrator import ProcessManager


class TestProcessManagerFixture:
    """Shared fixture for ProcessManager instantiation"""

    @pytest.fixture
    def manager(self):
        """Create ProcessManager with temp directory for isolated testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = os.path.join(tmpdir, "agents")
            os.makedirs(os.path.join(agents_dir, "tasks"), exist_ok=True)
            mgr = ProcessManager(max_parallel=3, agents_dir=agents_dir)
            yield mgr


class TestCalculatePhase(TestProcessManagerFixture):
    """Tests for _calculate_phase method"""

    def test_no_dependencies_returns_phase_1(self, manager):
        """Block with no dependencies should be phase 1"""
        phase = manager._calculate_phase([], {})
        assert phase == 1

    def test_single_dependency(self, manager):
        """Block depending on phase-1 block should be phase 2"""
        block_phases = {"step-1": 1}
        phase = manager._calculate_phase(["step-1"], block_phases)
        assert phase == 2

    def test_multiple_dependencies_same_phase(self, manager):
        """Block depending on multiple phase-1 blocks should be phase 2"""
        block_phases = {"step-a": 1, "step-b": 1, "step-c": 1}
        phase = manager._calculate_phase(["step-a", "step-b", "step-c"], block_phases)
        assert phase == 2

    def test_multiple_dependencies_different_phases(self, manager):
        """Block should be max(dep phases) + 1"""
        block_phases = {"step-1": 1, "step-2": 2, "step-3": 3}
        phase = manager._calculate_phase(["step-1", "step-2", "step-3"], block_phases)
        assert phase == 4

    def test_chained_dependencies(self, manager):
        """Simulate chained deps: A(1) -> B(2) -> C(3)"""
        block_phases = {}

        # Phase 1: no deps
        block_phases["A"] = manager._calculate_phase([], block_phases)
        assert block_phases["A"] == 1

        # Phase 2: depends on A
        block_phases["B"] = manager._calculate_phase(["A"], block_phases)
        assert block_phases["B"] == 2

        # Phase 3: depends on B
        block_phases["C"] = manager._calculate_phase(["B"], block_phases)
        assert block_phases["C"] == 3

    def test_diamond_dependencies(self, manager):
        """Diamond pattern: A -> B, A -> C, B+C -> D"""
        block_phases = {}

        block_phases["A"] = manager._calculate_phase([], block_phases)
        assert block_phases["A"] == 1

        block_phases["B"] = manager._calculate_phase(["A"], block_phases)
        assert block_phases["B"] == 2

        block_phases["C"] = manager._calculate_phase(["A"], block_phases)
        assert block_phases["C"] == 2

        block_phases["D"] = manager._calculate_phase(["B", "C"], block_phases)
        assert block_phases["D"] == 3

    def test_unknown_dependency_treated_as_phase_0(self, manager):
        """Dependency not in block_phases dict defaults to phase 0"""
        phase = manager._calculate_phase(["unknown-block"], {})
        assert phase == 1  # max(0) + 1 = 1


class TestShouldExecuteBlock(TestProcessManagerFixture):
    """Tests for _should_execute_block method"""

    def test_no_failures_no_skip_flag(self, manager):
        """Block without skip flag and no failures should execute"""
        block = {"name": "step-1"}
        assert manager._should_execute_block(block, []) is True

    def test_no_failures_with_skip_flag(self, manager):
        """Block with skip flag but no failures should execute"""
        block = {"name": "step-1", "skip_if_previous_failed": True}
        assert manager._should_execute_block(block, []) is True

    def test_failures_without_skip_flag(self, manager):
        """Block without skip flag should execute even with failures (default behavior)"""
        block = {"name": "step-2"}
        assert manager._should_execute_block(block, ["step-1"]) is True

    def test_failures_with_skip_flag_false(self, manager):
        """Block with skip_if_previous_failed=False should execute with failures"""
        block = {"name": "step-2", "skip_if_previous_failed": False}
        assert manager._should_execute_block(block, ["step-1"]) is True

    def test_failures_with_skip_flag_true(self, manager):
        """Block with skip_if_previous_failed=True should NOT execute when failures exist"""
        block = {"name": "step-2", "skip_if_previous_failed": True}
        assert manager._should_execute_block(block, ["step-1"]) is False

    def test_multiple_failures_with_skip_flag(self, manager):
        """Block should skip when multiple previous blocks failed"""
        block = {"name": "step-3", "skip_if_previous_failed": True}
        assert manager._should_execute_block(block, ["step-1", "step-2"]) is False


class TestShouldContinueAfterFailure(TestProcessManagerFixture):
    """Tests for _should_continue_after_failure method"""

    def test_no_failure_continues(self, manager):
        """No failure means always continue"""
        block = {"name": "step-1"}
        assert manager._should_continue_after_failure(block, block_failed=False) is True

    def test_no_failure_continues_even_with_flag_false(self, manager):
        """No failure means continue regardless of continue_if_failed setting"""
        block = {"name": "step-1", "continue_if_failed": False}
        assert manager._should_continue_after_failure(block, block_failed=False) is True

    def test_failure_with_default_continues(self, manager):
        """Default continue_if_failed=True means workflow continues on failure"""
        block = {"name": "step-1"}
        assert manager._should_continue_after_failure(block, block_failed=True) is True

    def test_failure_with_continue_true(self, manager):
        """Explicit continue_if_failed=True means workflow continues on failure"""
        block = {"name": "step-1", "continue_if_failed": True}
        assert manager._should_continue_after_failure(block, block_failed=True) is True

    def test_failure_with_continue_false_stops(self, manager):
        """continue_if_failed=False means workflow stops on failure"""
        block = {"name": "step-1", "continue_if_failed": False}
        assert manager._should_continue_after_failure(block, block_failed=True) is False


class TestResolvePath(TestProcessManagerFixture):
    """Tests for _resolve_path method"""

    def test_simple_key(self, manager):
        """Resolve single-level key"""
        data = {"approved": True}
        assert manager._resolve_path("approved", data) is True

    def test_nested_path(self, manager):
        """Resolve dot-separated nested path"""
        data = {"result": {"status": "done"}}
        assert manager._resolve_path("result.status", data) == "done"

    def test_deeply_nested_path(self, manager):
        """Resolve deeply nested path"""
        data = {"a": {"b": {"c": {"d": 42}}}}
        assert manager._resolve_path("a.b.c.d", data) == 42

    def test_missing_key_returns_none(self, manager):
        """Missing key in path returns None"""
        data = {"result": {"status": "done"}}
        assert manager._resolve_path("result.missing", data) is None

    def test_missing_intermediate_key(self, manager):
        """Missing intermediate key returns None"""
        data = {"result": {"status": "done"}}
        assert manager._resolve_path("nonexistent.status", data) is None

    def test_empty_data(self, manager):
        """Empty data dict returns None"""
        assert manager._resolve_path("anything", {}) is None

    def test_numeric_value(self, manager):
        """Resolve path to numeric value"""
        data = {"result": {"score": 0.95}}
        assert manager._resolve_path("result.score", data) == 0.95

    def test_list_value(self, manager):
        """Resolve path to list value"""
        data = {"result": {"items": [1, 2, 3]}}
        assert manager._resolve_path("result.items", data) == [1, 2, 3]

    def test_non_dict_intermediate(self, manager):
        """Non-dict intermediate value returns None"""
        data = {"result": "just a string"}
        assert manager._resolve_path("result.field", data) is None


class TestEvaluateCondition(TestProcessManagerFixture):
    """Tests for _evaluate_condition method"""

    # Truthy / falsy checks

    def test_truthy_boolean(self, manager):
        """True boolean value is truthy"""
        assert manager._evaluate_condition("{{ result.approved }}", {"result": {"approved": True}}) is True

    def test_falsy_boolean(self, manager):
        """False boolean value is falsy"""
        assert manager._evaluate_condition("{{ result.approved }}", {"result": {"approved": False}}) is False

    def test_truthy_string(self, manager):
        """Non-empty string is truthy"""
        assert manager._evaluate_condition("{{ result.name }}", {"result": {"name": "test"}}) is True

    def test_falsy_empty_string(self, manager):
        """Empty string is falsy"""
        assert manager._evaluate_condition("{{ result.name }}", {"result": {"name": ""}}) is False

    def test_truthy_number(self, manager):
        """Non-zero number is truthy"""
        assert manager._evaluate_condition("{{ result.count }}", {"result": {"count": 5}}) is True

    def test_falsy_zero(self, manager):
        """Zero is falsy"""
        assert manager._evaluate_condition("{{ result.count }}", {"result": {"count": 0}}) is False

    def test_falsy_none(self, manager):
        """None (missing path) is falsy"""
        assert manager._evaluate_condition("{{ result.missing }}", {"result": {}}) is False

    # Equality comparisons

    def test_string_equality(self, manager):
        """String equality with == operator"""
        data = {"result": {"status": "approved"}}
        assert manager._evaluate_condition("{{ result.status == 'approved' }}", data) is True

    def test_string_equality_double_quotes(self, manager):
        """String equality with double quotes"""
        data = {"result": {"status": "approved"}}
        assert manager._evaluate_condition('{{ result.status == "approved" }}', data) is True

    def test_string_inequality_match(self, manager):
        """String inequality when values differ"""
        data = {"result": {"status": "rejected"}}
        assert manager._evaluate_condition("{{ result.status != 'approved' }}", data) is True

    def test_string_inequality_no_match(self, manager):
        """String inequality when values are same"""
        data = {"result": {"status": "approved"}}
        assert manager._evaluate_condition("{{ result.status != 'approved' }}", data) is False

    def test_string_equality_no_match(self, manager):
        """String equality fails when values differ"""
        data = {"result": {"status": "rejected"}}
        assert manager._evaluate_condition("{{ result.status == 'approved' }}", data) is False

    # Numeric comparisons

    def test_greater_than_true(self, manager):
        """Greater than comparison succeeds"""
        data = {"result": {"score": 0.9}}
        assert manager._evaluate_condition("{{ result.score > 0.8 }}", data) is True

    def test_greater_than_false(self, manager):
        """Greater than comparison fails"""
        data = {"result": {"score": 0.5}}
        assert manager._evaluate_condition("{{ result.score > 0.8 }}", data) is False

    def test_less_than_true(self, manager):
        """Less than comparison succeeds"""
        data = {"result": {"score": 0.3}}
        assert manager._evaluate_condition("{{ result.score < 0.5 }}", data) is True

    def test_less_than_false(self, manager):
        """Less than comparison fails"""
        data = {"result": {"score": 0.9}}
        assert manager._evaluate_condition("{{ result.score < 0.5 }}", data) is False

    def test_greater_equal_true_gt(self, manager):
        """Greater or equal when greater"""
        data = {"result": {"score": 0.9}}
        assert manager._evaluate_condition("{{ result.score >= 0.8 }}", data) is True

    def test_greater_equal_true_eq(self, manager):
        """Greater or equal when equal"""
        data = {"result": {"score": 0.8}}
        assert manager._evaluate_condition("{{ result.score >= 0.8 }}", data) is True

    def test_greater_equal_false(self, manager):
        """Greater or equal fails"""
        data = {"result": {"score": 0.7}}
        assert manager._evaluate_condition("{{ result.score >= 0.8 }}", data) is False

    def test_less_equal_true_lt(self, manager):
        """Less or equal when less"""
        data = {"result": {"score": 0.3}}
        assert manager._evaluate_condition("{{ result.score <= 0.5 }}", data) is True

    def test_less_equal_true_eq(self, manager):
        """Less or equal when equal"""
        data = {"result": {"score": 0.5}}
        assert manager._evaluate_condition("{{ result.score <= 0.5 }}", data) is True

    def test_less_equal_false(self, manager):
        """Less or equal fails"""
        data = {"result": {"score": 0.9}}
        assert manager._evaluate_condition("{{ result.score <= 0.5 }}", data) is False

    def test_integer_comparison(self, manager):
        """Comparison with integer values"""
        data = {"result": {"count": 10}}
        assert manager._evaluate_condition("{{ result.count > 5 }}", data) is True

    def test_numeric_equality(self, manager):
        """Numeric equality check"""
        data = {"result": {"count": 3}}
        assert manager._evaluate_condition("{{ result.count == 3 }}", data) is True

    # Invalid expressions

    def test_no_braces_returns_false(self, manager):
        """Expression without {{ }} returns False"""
        assert manager._evaluate_condition("result.approved", {"result": {"approved": True}}) is False

    def test_empty_expression_returns_false(self, manager):
        """Empty expression returns False"""
        assert manager._evaluate_condition("", {}) is False

    def test_extra_whitespace(self, manager):
        """Extra whitespace inside braces is handled"""
        data = {"result": {"approved": True}}
        assert manager._evaluate_condition("{{   result.approved   }}", data) is True


class TestEvaluateNextBlock(TestProcessManagerFixture):
    """Tests for _evaluate_next_block method"""

    def test_no_next_spec(self, manager):
        """Block without next spec returns None"""
        block = {"name": "step-1"}
        assert manager._evaluate_next_block(block, {}) is None

    def test_simple_string_next(self, manager):
        """Simple string next returns the block name"""
        block = {"name": "step-1", "next": "step-2"}
        assert manager._evaluate_next_block(block, {}) == "step-2"

    def test_conditional_if_true(self, manager):
        """Conditional next with matching if condition"""
        block = {
            "name": "review",
            "next": [
                {"if": "{{ result.approved }}", "goto": "publish"},
                {"else": True, "goto": "revision"}
            ]
        }
        result_data = {"result": {"approved": True}}
        assert manager._evaluate_next_block(block, result_data) == "publish"

    def test_conditional_if_false_falls_to_else(self, manager):
        """Conditional next falls through to else when if is false"""
        block = {
            "name": "review",
            "next": [
                {"if": "{{ result.approved }}", "goto": "publish"},
                {"else": True, "goto": "revision"}
            ]
        }
        result_data = {"result": {"approved": False}}
        # First condition is False, should fall to else
        assert manager._evaluate_next_block(block, result_data) == "revision"

    def test_conditional_with_comparison(self, manager):
        """Conditional with comparison operator"""
        block = {
            "name": "scoring",
            "next": [
                {"if": "{{ result.score > 0.8 }}", "goto": "accept"},
                {"else": True, "goto": "reject"}
            ]
        }
        result_data = {"result": {"score": 0.9}}
        assert manager._evaluate_next_block(block, result_data) == "accept"

    def test_conditional_comparison_falls_to_else(self, manager):
        """Conditional comparison fails, falls to else"""
        block = {
            "name": "scoring",
            "next": [
                {"if": "{{ result.score > 0.8 }}", "goto": "accept"},
                {"else": True, "goto": "reject"}
            ]
        }
        result_data = {"result": {"score": 0.5}}
        assert manager._evaluate_next_block(block, result_data) == "reject"

    def test_conditional_multiple_ifs(self, manager):
        """Multiple if conditions - first match wins"""
        block = {
            "name": "router",
            "next": [
                {"if": "{{ result.status == 'urgent' }}", "goto": "fast-track"},
                {"if": "{{ result.status == 'normal' }}", "goto": "standard"},
                {"else": True, "goto": "default"}
            ]
        }
        result_data = {"result": {"status": "normal"}}
        assert manager._evaluate_next_block(block, result_data) == "standard"

    def test_else_as_goto_value(self, manager):
        """Else clause where else value is the goto target"""
        block = {
            "name": "review",
            "next": [
                {"if": "{{ result.ok }}", "goto": "done"},
                {"else": "fallback"}
            ]
        }
        result_data = {"result": {"ok": False}}
        # When "else" key holds the goto value (no separate "goto" key)
        assert manager._evaluate_next_block(block, result_data) == "fallback"

    def test_empty_next_list(self, manager):
        """Empty next list returns None"""
        block = {"name": "step-1", "next": []}
        assert manager._evaluate_next_block(block, {}) is None

    def test_next_none(self, manager):
        """Explicit next: None returns None"""
        block = {"name": "step-1", "next": None}
        assert manager._evaluate_next_block(block, {}) is None

    def test_stage_key_fallback(self, manager):
        """Block using 'stage' key instead of 'name' still works"""
        block = {"stage": "analysis", "next": "synthesis"}
        assert manager._evaluate_next_block(block, {}) == "synthesis"


class TestPauseResumeWorkflow(TestProcessManagerFixture):
    """Tests for pause_workflow and resume_workflow methods"""

    def test_pause_workflow(self, manager):
        """Pausing workflow returns True and sets paused state"""
        assert manager.workflow_paused is False
        result = manager.pause_workflow()
        assert result is True
        assert manager.workflow_paused is True
        assert manager.workflow_paused_at is not None

    def test_pause_already_paused(self, manager):
        """Pausing already paused workflow returns False"""
        manager.pause_workflow()
        result = manager.pause_workflow()
        assert result is False

    def test_resume_workflow(self, manager):
        """Resuming paused workflow returns True and clears paused state"""
        manager.pause_workflow()
        result = manager.resume_workflow()
        assert result is True
        assert manager.workflow_paused is False
        assert manager.workflow_paused_at is None

    def test_resume_not_paused(self, manager):
        """Resuming when not paused returns False"""
        result = manager.resume_workflow()
        assert result is False

    def test_pause_resume_cycle(self, manager):
        """Multiple pause/resume cycles work correctly"""
        assert manager.pause_workflow() is True
        assert manager.resume_workflow() is True
        assert manager.pause_workflow() is True
        assert manager.resume_workflow() is True
        assert manager.workflow_paused is False

    def test_pause_sets_timestamp(self, manager):
        """Pausing records the timestamp"""
        before = time.time()
        manager.pause_workflow()
        after = time.time()
        assert before <= manager.workflow_paused_at <= after


class TestAllCompleted(TestProcessManagerFixture):
    """Tests for all_completed method"""

    def test_empty_processes(self, manager):
        """No processes means all completed (vacuous truth)"""
        assert manager.all_completed() is True

    def test_all_done(self, manager):
        """All processes done returns True"""
        manager.processes["uid1"] = Process(
            pid=None, name="step-1", status="done",
            start_time=0, command=""
        )
        manager.processes["uid2"] = Process(
            pid=None, name="step-2", status="done",
            start_time=0, command=""
        )
        assert manager.all_completed() is True

    def test_all_failed(self, manager):
        """All processes failed also counts as completed"""
        manager.processes["uid1"] = Process(
            pid=None, name="step-1", status="failed",
            start_time=0, command=""
        )
        assert manager.all_completed() is True

    def test_mixed_done_and_failed(self, manager):
        """Mix of done and failed is still all completed"""
        manager.processes["uid1"] = Process(
            pid=None, name="step-1", status="done",
            start_time=0, command=""
        )
        manager.processes["uid2"] = Process(
            pid=None, name="step-2", status="failed",
            start_time=0, command=""
        )
        assert manager.all_completed() is True

    def test_one_running(self, manager):
        """One running process means not all completed"""
        manager.processes["uid1"] = Process(
            pid=None, name="step-1", status="done",
            start_time=0, command=""
        )
        manager.processes["uid2"] = Process(
            pid=None, name="step-2", status="running",
            start_time=0, command=""
        )
        assert manager.all_completed() is False

    def test_one_waiting(self, manager):
        """One waiting process means not all completed"""
        manager.processes["uid1"] = Process(
            pid=None, name="step-1", status="done",
            start_time=0, command=""
        )
        manager.processes["uid2"] = Process(
            pid=None, name="step-2", status="waiting",
            start_time=0, command=""
        )
        assert manager.all_completed() is False

    def test_one_paused(self, manager):
        """One paused process means not all completed"""
        manager.processes["uid1"] = Process(
            pid=None, name="step-1", status="paused",
            start_time=0, command=""
        )
        assert manager.all_completed() is False


class TestHasWork(TestProcessManagerFixture):
    """Tests for has_work method"""

    def test_no_processes(self, manager):
        """No processes - has_work still returns True (keeps UI running)"""
        # Based on the implementation: always returns True to keep UI running
        assert manager.has_work() is True

    def test_running_process(self, manager):
        """Running process means has work"""
        manager.processes["uid1"] = Process(
            pid=None, name="step-1", status="running",
            start_time=0, command=""
        )
        assert manager.has_work() is True

    def test_waiting_process(self, manager):
        """Waiting process means has work (processes dict is non-empty)"""
        manager.processes["uid1"] = Process(
            pid=None, name="step-1", status="waiting",
            start_time=0, command=""
        )
        assert manager.has_work() is True

    def test_all_done(self, manager):
        """All done processes - has_work True because processes dict is non-empty"""
        manager.processes["uid1"] = Process(
            pid=None, name="step-1", status="done",
            start_time=0, command=""
        )
        assert manager.has_work() is True


class TestManagerInitialization(TestProcessManagerFixture):
    """Tests for ProcessManager initialization and basic state"""

    def test_initial_state(self, manager):
        """Test ProcessManager starts with correct initial state"""
        assert manager.max_parallel == 3
        assert manager.running is True
        assert manager.workflow_paused is False
        assert manager.workflow_paused_at is None
        assert manager.stop_workflow is False
        assert manager.stop_reason is None
        assert len(manager.processes) == 0
        assert len(manager.completed) == 0
        assert len(manager.next_queue) == 0
        assert len(manager.run_counts) == 0
        assert len(manager.block_configs) == 0

    def test_run_dir_created(self, manager):
        """Test that run directory is created on init"""
        assert os.path.exists(manager.run_dir)
        assert os.path.exists(manager.log_dir)
        assert os.path.exists(os.path.join(manager.task_dir, "state"))

    def test_custom_agents_dir(self):
        """Test custom agents_dir is used"""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = os.path.join(tmpdir, "custom-agents")
            os.makedirs(os.path.join(agents_dir, "tasks"), exist_ok=True)
            mgr = ProcessManager(max_parallel=5, agents_dir=agents_dir)
            assert mgr.agents_dir == agents_dir
            assert mgr.max_parallel == 5


class TestFindProcessByName(TestProcessManagerFixture):
    """Tests for _find_process_by_name method"""

    def test_find_existing(self, manager):
        """Find existing process by name"""
        proc = Process(
            pid=None, name="my-block", status="waiting",
            start_time=0, command=""
        )
        manager.processes["uid-123"] = proc
        result = manager._find_process_by_name("my-block")
        assert result is not None
        uid, found_proc = result
        assert uid == "uid-123"
        assert found_proc.name == "my-block"

    def test_find_nonexistent(self, manager):
        """Return None for non-existent process name"""
        result = manager._find_process_by_name("nonexistent")
        assert result is None

    def test_find_among_multiple(self, manager):
        """Find correct process among multiple"""
        manager.processes["uid-1"] = Process(
            pid=None, name="alpha", status="waiting",
            start_time=0, command=""
        )
        manager.processes["uid-2"] = Process(
            pid=None, name="beta", status="running",
            start_time=0, command=""
        )
        manager.processes["uid-3"] = Process(
            pid=None, name="gamma", status="done",
            start_time=0, command=""
        )

        result = manager._find_process_by_name("beta")
        assert result is not None
        uid, proc = result
        assert uid == "uid-2"
        assert proc.status == "running"


class TestGetPreviousBlocksStatus(TestProcessManagerFixture):
    """Tests for _get_previous_blocks_status method"""

    def test_no_failed_blocks(self, manager):
        """No failed blocks returns empty list"""
        manager.processes["uid-1"] = Process(
            pid=None, name="step-1", status="done",
            start_time=0, command=""
        )
        manager.processes["uid-2"] = Process(
            pid=None, name="step-2", status="running",
            start_time=0, command=""
        )
        block = {"name": "step-3"}
        failed = manager._get_previous_blocks_status(block)
        assert failed == []

    def test_one_failed_block(self, manager):
        """One failed block is returned"""
        manager.processes["uid-1"] = Process(
            pid=None, name="step-1", status="failed",
            start_time=0, command=""
        )
        manager.processes["uid-2"] = Process(
            pid=None, name="step-2", status="done",
            start_time=0, command=""
        )
        block = {"name": "step-3"}
        failed = manager._get_previous_blocks_status(block)
        assert failed == ["step-1"]

    def test_multiple_failed_blocks(self, manager):
        """Multiple failed blocks returned"""
        manager.processes["uid-1"] = Process(
            pid=None, name="a", status="failed",
            start_time=0, command=""
        )
        manager.processes["uid-2"] = Process(
            pid=None, name="b", status="failed",
            start_time=0, command=""
        )
        manager.processes["uid-3"] = Process(
            pid=None, name="c", status="done",
            start_time=0, command=""
        )
        block = {"name": "d"}
        failed = manager._get_previous_blocks_status(block)
        assert set(failed) == {"a", "b"}
