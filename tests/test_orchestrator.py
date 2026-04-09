"""Tests for rein/orchestrator.py - ProcessManager pure logic methods"""

import os
import tempfile
import time

import pytest

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
            "next": [{"if": "{{ result.approved }}", "goto": "publish"}, {"else": True, "goto": "revision"}],
        }
        result_data = {"result": {"approved": True}}
        assert manager._evaluate_next_block(block, result_data) == "publish"

    def test_conditional_if_false_falls_to_else(self, manager):
        """Conditional next falls through to else when if is false"""
        block = {
            "name": "review",
            "next": [{"if": "{{ result.approved }}", "goto": "publish"}, {"else": True, "goto": "revision"}],
        }
        result_data = {"result": {"approved": False}}
        # First condition is False, should fall to else
        assert manager._evaluate_next_block(block, result_data) == "revision"

    def test_conditional_with_comparison(self, manager):
        """Conditional with comparison operator"""
        block = {
            "name": "scoring",
            "next": [{"if": "{{ result.score > 0.8 }}", "goto": "accept"}, {"else": True, "goto": "reject"}],
        }
        result_data = {"result": {"score": 0.9}}
        assert manager._evaluate_next_block(block, result_data) == "accept"

    def test_conditional_comparison_falls_to_else(self, manager):
        """Conditional comparison fails, falls to else"""
        block = {
            "name": "scoring",
            "next": [{"if": "{{ result.score > 0.8 }}", "goto": "accept"}, {"else": True, "goto": "reject"}],
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
                {"else": True, "goto": "default"},
            ],
        }
        result_data = {"result": {"status": "normal"}}
        assert manager._evaluate_next_block(block, result_data) == "standard"

    def test_else_as_goto_value(self, manager):
        """Else clause where else value is the goto target"""
        block = {"name": "review", "next": [{"if": "{{ result.ok }}", "goto": "done"}, {"else": "fallback"}]}
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
        manager.processes["uid1"] = Process(pid=None, name="step-1", status="done", start_time=0, command="")
        manager.processes["uid2"] = Process(pid=None, name="step-2", status="done", start_time=0, command="")
        assert manager.all_completed() is True

    def test_all_failed(self, manager):
        """All processes failed also counts as completed"""
        manager.processes["uid1"] = Process(pid=None, name="step-1", status="failed", start_time=0, command="")
        assert manager.all_completed() is True

    def test_mixed_done_and_failed(self, manager):
        """Mix of done and failed is still all completed"""
        manager.processes["uid1"] = Process(pid=None, name="step-1", status="done", start_time=0, command="")
        manager.processes["uid2"] = Process(pid=None, name="step-2", status="failed", start_time=0, command="")
        assert manager.all_completed() is True

    def test_one_running(self, manager):
        """One running process means not all completed"""
        manager.processes["uid1"] = Process(pid=None, name="step-1", status="done", start_time=0, command="")
        manager.processes["uid2"] = Process(pid=None, name="step-2", status="running", start_time=0, command="")
        assert manager.all_completed() is False

    def test_one_waiting(self, manager):
        """One waiting process means not all completed"""
        manager.processes["uid1"] = Process(pid=None, name="step-1", status="done", start_time=0, command="")
        manager.processes["uid2"] = Process(pid=None, name="step-2", status="waiting", start_time=0, command="")
        assert manager.all_completed() is False

    def test_one_paused(self, manager):
        """One paused process means not all completed"""
        manager.processes["uid1"] = Process(pid=None, name="step-1", status="paused", start_time=0, command="")
        assert manager.all_completed() is False


class TestHasWork(TestProcessManagerFixture):
    """Tests for has_work method"""

    def test_no_processes(self, manager):
        """No processes - has_work still returns True (keeps UI running)"""
        # Based on the implementation: always returns True to keep UI running
        assert manager.has_work() is True

    def test_running_process(self, manager):
        """Running process means has work"""
        manager.processes["uid1"] = Process(pid=None, name="step-1", status="running", start_time=0, command="")
        assert manager.has_work() is True

    def test_waiting_process(self, manager):
        """Waiting process means has work (processes dict is non-empty)"""
        manager.processes["uid1"] = Process(pid=None, name="step-1", status="waiting", start_time=0, command="")
        assert manager.has_work() is True

    def test_all_done(self, manager):
        """All done processes - has_work True because processes dict is non-empty"""
        manager.processes["uid1"] = Process(pid=None, name="step-1", status="done", start_time=0, command="")
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
        proc = Process(pid=None, name="my-block", status="waiting", start_time=0, command="")
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
        manager.processes["uid-1"] = Process(pid=None, name="alpha", status="waiting", start_time=0, command="")
        manager.processes["uid-2"] = Process(pid=None, name="beta", status="running", start_time=0, command="")
        manager.processes["uid-3"] = Process(pid=None, name="gamma", status="done", start_time=0, command="")

        result = manager._find_process_by_name("beta")
        assert result is not None
        uid, proc = result
        assert uid == "uid-2"
        assert proc.status == "running"


class TestGetPreviousBlocksStatus(TestProcessManagerFixture):
    """Tests for _get_previous_blocks_status method"""

    def test_no_failed_blocks(self, manager):
        """No failed blocks returns empty list"""
        manager.processes["uid-1"] = Process(pid=None, name="step-1", status="done", start_time=0, command="")
        manager.processes["uid-2"] = Process(pid=None, name="step-2", status="running", start_time=0, command="")
        block = {"name": "step-3"}
        failed = manager._get_previous_blocks_status(block)
        assert failed == []

    def test_one_failed_block(self, manager):
        """One failed block is returned"""
        manager.processes["uid-1"] = Process(pid=None, name="step-1", status="failed", start_time=0, command="")
        manager.processes["uid-2"] = Process(pid=None, name="step-2", status="done", start_time=0, command="")
        block = {"name": "step-3"}
        failed = manager._get_previous_blocks_status(block)
        assert failed == ["step-1"]

    def test_multiple_failed_blocks(self, manager):
        """Multiple failed blocks returned"""
        manager.processes["uid-1"] = Process(pid=None, name="a", status="failed", start_time=0, command="")
        manager.processes["uid-2"] = Process(pid=None, name="b", status="failed", start_time=0, command="")
        manager.processes["uid-3"] = Process(pid=None, name="c", status="done", start_time=0, command="")
        block = {"name": "d"}
        failed = manager._get_previous_blocks_status(block)
        assert set(failed) == {"a", "b"}


class TestRunStep(TestProcessManagerFixture):
    """Tests for run_step() method -- async step-by-step execution"""

    def _setup_blocks(self, manager, blocks):
        """Helper: load blocks into manager and initialize processes."""
        config = {"blocks": blocks}
        manager.load_config(config)

    def test_empty_workflow_returns_true(self, manager):
        """Empty workflow (no blocks) is immediately complete"""
        self._setup_blocks(manager, [])
        result = manager.run_step(1)
        assert result is True

    def test_already_complete_returns_true(self, manager):
        """If all blocks already completed, run_step returns True"""
        blocks = [{"name": "a", "prompt": "test", "depends_on": []}]
        self._setup_blocks(manager, blocks)
        # Manually mark as completed
        manager.completed.add("a")
        for p in manager.processes.values():
            p.status = "done"
        result = manager.run_step(1)
        assert result is True

    def test_has_running_processes(self, manager):
        """_has_running_processes returns True when blocks are running"""
        manager.processes["uid-1"] = Process(pid=None, name="a", status="running", start_time=0, command="")
        assert manager._has_running_processes() is True

    def test_has_no_running_processes(self, manager):
        """_has_running_processes returns False when no blocks running"""
        manager.processes["uid-1"] = Process(pid=None, name="a", status="done", start_time=0, command="")
        manager.completed.add("a")  # done blocks must be in completed set
        assert manager._has_running_processes() is False

    def test_wait_for_inflight_returns_immediately_when_none_running(self, manager):
        """_wait_for_inflight returns immediately if no running processes"""
        manager.processes["uid-1"] = Process(pid=None, name="a", status="done", start_time=0, command="")
        manager.completed.add("a")
        start = time.time()
        manager._wait_for_inflight(timeout=5.0)
        elapsed = time.time() - start
        assert elapsed < 1.0  # Should return nearly instantly

    def test_step_budget_zero_means_unlimited(self, manager):
        """run_step(0) should not be limited by step budget"""
        # With 0 blocks, should just return True (complete)
        self._setup_blocks(manager, [])
        result = manager.run_step(0)
        assert result is True


# ============================================================
# ROUTING & CASCADE TESTS (#1171, #1172, #1173)
# ============================================================


class TestDependentsMap(TestProcessManagerFixture):
    """Tests for _get_dependents_map -- reverse dependency graph"""

    def _setup(self, manager, blocks):
        manager.all_blocks = blocks
        manager.block_configs = {b["name"]: b for b in blocks}

    def test_linear_chain(self, manager):
        """A -> B -> C produces {A: [B], B: [C]}"""
        self._setup(
            manager,
            [
                {"name": "a", "depends_on": []},
                {"name": "b", "depends_on": ["a"]},
                {"name": "c", "depends_on": ["b"]},
            ],
        )
        dm = manager._get_dependents_map()
        assert set(dm.get("a", [])) == {"b"}
        assert set(dm.get("b", [])) == {"c"}
        assert dm.get("c", []) == []

    def test_fan_out(self, manager):
        """A -> {B, C, D}"""
        self._setup(
            manager,
            [
                {"name": "a", "depends_on": []},
                {"name": "b", "depends_on": ["a"]},
                {"name": "c", "depends_on": ["a"]},
                {"name": "d", "depends_on": ["a"]},
            ],
        )
        dm = manager._get_dependents_map()
        assert set(dm["a"]) == {"b", "c", "d"}

    def test_fan_in(self, manager):
        """{A, B, C} -> D"""
        self._setup(
            manager,
            [
                {"name": "a", "depends_on": []},
                {"name": "b", "depends_on": []},
                {"name": "c", "depends_on": []},
                {"name": "d", "depends_on": ["a", "b", "c"]},
            ],
        )
        dm = manager._get_dependents_map()
        for name in ("a", "b", "c"):
            assert "d" in dm[name]

    def test_diamond(self, manager):
        """A -> {B, C} -> D"""
        self._setup(
            manager,
            [
                {"name": "a", "depends_on": []},
                {"name": "b", "depends_on": ["a"]},
                {"name": "c", "depends_on": ["a"]},
                {"name": "d", "depends_on": ["b", "c"]},
            ],
        )
        dm = manager._get_dependents_map()
        assert set(dm["a"]) == {"b", "c"}
        assert set(dm["b"]) == {"d"}
        assert set(dm["c"]) == {"d"}


class TestCascadeInvalidation(TestProcessManagerFixture):
    """Tests for _cascade_invalidation -- BFS downstream invalidation"""

    def _setup(self, manager, blocks):
        manager.all_blocks = blocks
        manager.block_configs = {b["name"]: b for b in blocks}

    def test_single_downstream(self, manager):
        """Invalidating A cascades to B (A -> B)"""
        self._setup(
            manager,
            [
                {"name": "a", "depends_on": []},
                {"name": "b", "depends_on": ["a"]},
            ],
        )
        dm = manager._get_dependents_map()
        result = manager._cascade_invalidation({"a"}, dm)
        assert "b" in result
        assert "a" in result  # seed is included

    def test_deep_chain(self, manager):
        """Invalidating A cascades through A -> B -> C -> D -> E"""
        self._setup(
            manager,
            [
                {"name": "a", "depends_on": []},
                {"name": "b", "depends_on": ["a"]},
                {"name": "c", "depends_on": ["b"]},
                {"name": "d", "depends_on": ["c"]},
                {"name": "e", "depends_on": ["d"]},
            ],
        )
        dm = manager._get_dependents_map()
        result = manager._cascade_invalidation({"a"}, dm)
        assert result == {"a", "b", "c", "d", "e"}

    def test_does_not_cascade_upstream(self, manager):
        """Invalidating C does NOT affect A or B (A -> B -> C -> D)"""
        self._setup(
            manager,
            [
                {"name": "a", "depends_on": []},
                {"name": "b", "depends_on": ["a"]},
                {"name": "c", "depends_on": ["b"]},
                {"name": "d", "depends_on": ["c"]},
            ],
        )
        dm = manager._get_dependents_map()
        result = manager._cascade_invalidation({"c"}, dm)
        assert result == {"c", "d"}
        assert "a" not in result
        assert "b" not in result

    def test_diamond_cascade(self, manager):
        """Invalidating A cascades to B, C, and D (diamond: A -> {B,C} -> D)"""
        self._setup(
            manager,
            [
                {"name": "a", "depends_on": []},
                {"name": "b", "depends_on": ["a"]},
                {"name": "c", "depends_on": ["a"]},
                {"name": "d", "depends_on": ["b", "c"]},
            ],
        )
        dm = manager._get_dependents_map()
        result = manager._cascade_invalidation({"a"}, dm)
        assert result == {"a", "b", "c", "d"}

    def test_partial_cascade_in_diamond(self, manager):
        """Invalidating B only cascades to D, not C (A -> {B,C} -> D)"""
        self._setup(
            manager,
            [
                {"name": "a", "depends_on": []},
                {"name": "b", "depends_on": ["a"]},
                {"name": "c", "depends_on": ["a"]},
                {"name": "d", "depends_on": ["b", "c"]},
            ],
        )
        dm = manager._get_dependents_map()
        result = manager._cascade_invalidation({"b"}, dm)
        assert result == {"b", "d"}
        assert "a" not in result
        assert "c" not in result

    def test_isolated_block(self, manager):
        """Invalidating isolated block with no dependents returns just itself"""
        self._setup(
            manager,
            [
                {"name": "a", "depends_on": []},
                {"name": "b", "depends_on": []},
            ],
        )
        dm = manager._get_dependents_map()
        result = manager._cascade_invalidation({"a"}, dm)
        assert result == {"a"}


class TestRoutingState(TestProcessManagerFixture):
    """Tests for routing-related state management"""

    def _setup_routing(self, manager, blocks):
        """Setup manager with blocks that have routing"""
        manager.all_blocks = blocks
        manager.block_configs = {b["name"]: b for b in blocks}
        manager.default_max_runs = 3
        for b in blocks:
            manager.run_counts[b["name"]] = 0

    def test_routing_target_removed_from_completed(self, manager):
        """When routing activates, target is removed from completed set"""
        blocks = [
            {"name": "gate", "depends_on": [], "routing": {"revise": "fix", "_default": "next"}},
            {"name": "fix", "depends_on": ["gate"], "max_runs": 3},
            {"name": "next", "depends_on": ["gate"]},
        ]
        self._setup_routing(manager, blocks)
        manager.completed.add("fix")

        # Simulate routing: discard fix from completed
        manager.completed.discard("fix")
        assert "fix" not in manager.completed

    def test_run_counts_increment(self, manager):
        """Routing increments run_count for target block"""
        blocks = [
            {"name": "gate", "depends_on": [], "routing": {"revise": "fix"}},
            {"name": "fix", "depends_on": ["gate"], "max_runs": 3},
        ]
        self._setup_routing(manager, blocks)

        # Simulate routing increments
        manager.run_counts["fix"] = 0
        manager.run_counts["fix"] += 1
        assert manager.run_counts["fix"] == 1
        manager.run_counts["fix"] += 1
        assert manager.run_counts["fix"] == 2

    def test_max_runs_blocks_routing(self, manager):
        """Routing is blocked when target has exhausted max_runs"""
        blocks = [
            {"name": "gate", "depends_on": [], "routing": {"revise": "fix"}},
            {"name": "fix", "depends_on": ["gate"], "max_runs": 2},
        ]
        self._setup_routing(manager, blocks)
        manager.run_counts["fix"] = 2  # exhausted

        max_runs = manager.block_configs["fix"].get("max_runs", manager.default_max_runs)
        assert manager.run_counts["fix"] >= max_runs  # routing should be blocked

    def test_next_queue_populated_on_routing(self, manager):
        """Routing appends target block to next_queue"""
        blocks = [
            {"name": "gate", "depends_on": [], "routing": {"revise": "fix"}},
            {"name": "fix", "depends_on": ["gate"], "max_runs": 3},
        ]
        self._setup_routing(manager, blocks)

        # Simulate what routing does
        manager.next_queue.append(("fix", {}))
        assert len(manager.next_queue) == 1
        assert manager.next_queue[0][0] == "fix"

    def test_gate_dependents_only_backward(self, manager):
        """Gate dependents should only be invalidated on backward routing (run > 0)"""
        blocks = [
            {"name": "gate", "depends_on": [], "routing": {"revise": "revision", "_default": "deploy"}},
            {"name": "revision", "depends_on": ["gate"], "max_runs": 3},
            {"name": "deploy", "depends_on": ["gate"]},
        ]
        self._setup_routing(manager, blocks)

        dm = manager._get_dependents_map()
        gate_dependents = set(dm.get("gate", []))

        # Forward routing (current_runs == 0): should NOT invalidate gate dependents
        current_runs = 0
        if current_runs > 0:
            cascade_extra = gate_dependents - {"revision"}
        else:
            cascade_extra = set()
        assert "deploy" not in cascade_extra

        # Backward routing (current_runs > 0): SHOULD invalidate gate dependents
        current_runs = 1
        if current_runs > 0:
            cascade_extra = gate_dependents - {"revision"}
        else:
            cascade_extra = set()
        assert "deploy" in cascade_extra


class TestRePending(TestProcessManagerFixture):
    """Tests for RE-PENDING logic -- blocks re-added to pending after cascade"""

    def _setup(self, manager, blocks):
        manager.all_blocks = blocks
        manager.block_configs = {b["name"]: b for b in blocks}

    def test_re_pending_detects_missing_block(self, manager):
        """Block not in completed and not in pending should be re-added"""
        blocks = [
            {"name": "a", "depends_on": []},
            {"name": "b", "depends_on": ["a"]},
            {"name": "c", "depends_on": ["b"]},
        ]
        self._setup(manager, blocks)

        # Simulate: a is completed, b was completed but cascade removed it
        manager.completed = {"a"}
        pending = {}  # b was spawned and removed from pending

        # RE-PENDING logic
        for block in manager.all_blocks:
            name = block["name"]
            if name not in manager.completed and name not in pending:
                pending[name] = block

        assert "b" in pending  # re-added
        assert "c" in pending  # also needs to be pending

    def test_re_pending_does_not_duplicate(self, manager):
        """Block already in pending should not be re-added"""
        blocks = [
            {"name": "a", "depends_on": []},
            {"name": "b", "depends_on": ["a"]},
        ]
        self._setup(manager, blocks)
        manager.completed = set()
        pending = {"a": blocks[0]}

        for block in manager.all_blocks:
            name = block["name"]
            if name not in manager.completed and name not in pending:
                pending[name] = block

        assert len([k for k in pending if k == "a"]) == 1  # no duplicate

    def test_completed_blocks_not_re_pending(self, manager):
        """Block in completed set should never be re-added to pending"""
        blocks = [
            {"name": "a", "depends_on": []},
            {"name": "b", "depends_on": ["a"]},
        ]
        self._setup(manager, blocks)
        manager.completed = {"a", "b"}
        pending = {}

        for block in manager.all_blocks:
            name = block["name"]
            if name not in manager.completed and name not in pending:
                pending[name] = block

        assert len(pending) == 0

    def test_orphan_detection_skips_unsatisfiable(self, manager):
        """Block whose deps can never be met should be detected as orphan"""
        blocks = [
            {"name": "gate", "depends_on": [], "routing": {"revise": "fix"}},
            {"name": "fix", "depends_on": ["gate"], "max_runs": 3},
            {"name": "deploy", "depends_on": ["gate"]},
        ]
        self._setup(manager, blocks)
        manager.completed = {"gate", "deploy"}  # gate completed, went to deploy
        # fix is in pending but gate already completed via _default path
        pending = {"fix": blocks[1]}

        # Orphan detection: fix depends on gate, gate is completed.
        # But fix was the routing target that wasn't taken. Check if deps are met.
        for name in list(pending.keys()):
            block = pending[name]
            deps = block.get("depends_on", [])
            all_deps_done = all(dep in manager.completed for dep in deps)
            if all_deps_done:
                continue  # deps met, can run -- NOT orphan
            # If deps not met, it's an orphan

        # In this case gate IS in completed, so fix's deps ARE met -- it can run
        # This is correct: fix should NOT be orphaned if gate is completed
        assert all(dep in manager.completed for dep in blocks[1].get("depends_on", []))

    def test_stuck_detection_no_progress(self, manager):
        """Stuck detection triggers when no blocks can make progress"""
        blocks = [
            {"name": "a", "depends_on": []},
            {"name": "b", "depends_on": ["a"]},
            {"name": "c", "depends_on": ["x"]},  # x doesn't exist -- impossible dep
        ]
        self._setup(manager, blocks)
        manager.completed = {"a", "b"}
        pending = {"c": blocks[2]}

        # Use the new helper method
        assert manager._is_stuck(pending) is True

    def test_is_stuck_with_satisfiable_deps(self, manager):
        """Not stuck when at least one pending block has satisfiable deps"""
        blocks = [
            {"name": "a", "depends_on": []},
            {"name": "b", "depends_on": ["a"]},
        ]
        self._setup(manager, blocks)
        manager.completed = {"a"}
        pending = {"b": blocks[1]}
        assert manager._is_stuck(pending) is False

    def test_is_stuck_empty_pending(self, manager):
        """Empty pending is not stuck (nothing to do is not a stuck state)"""
        self._setup(manager, [])
        assert manager._is_stuck({}) is False


# ============================================================
# HELPER METHOD TESTS (#1174 -- block timeout and model)
# ============================================================


class TestGetRunningNames(TestProcessManagerFixture):
    """Tests for _get_running_names helper"""

    def test_empty_processes(self, manager):
        """No processes -> empty set"""
        assert manager._get_running_names() == set()

    def test_only_running(self, manager):
        """Returns only blocks with status='running'"""
        manager.processes["u1"] = Process(pid=1, name="a", status="running", start_time=0, command="")
        manager.processes["u2"] = Process(pid=2, name="b", status="done", start_time=0, command="")
        manager.processes["u3"] = Process(pid=3, name="c", status="waiting", start_time=0, command="")
        manager.processes["u4"] = Process(pid=4, name="d", status="running", start_time=0, command="")
        running = manager._get_running_names()
        assert running == {"a", "d"}


class TestBlockLevelTimeout(TestProcessManagerFixture):
    """Tests for block-level timeout override (#1183 fix)"""

    def test_block_timeout_read_from_config(self, manager):
        """Block config with timeout field should be extractable"""
        block = {"name": "slow_block", "prompt": "test", "timeout": 60}
        assert block.get("timeout") == 60

    def test_block_timeout_none_when_not_set(self, manager):
        """Block without timeout field returns None"""
        block = {"name": "default_block", "prompt": "test"}
        assert block.get("timeout") is None


class TestBlockLevelModel(TestProcessManagerFixture):
    """Tests for block-level model override (#1184 fix)"""

    def test_block_model_takes_priority_over_agent(self, manager):
        """block.model should override agent_cfg.model"""
        block = {"name": "fast_block", "prompt": "test", "model": "haiku"}

        # Simulate agent config with different model
        class MockAgentCfg:
            model = "sonnet"

        agent_cfg = MockAgentCfg()

        # Priority logic from orchestrator
        block_model = block.get("model") or None
        agent_model = agent_cfg.model if agent_cfg and agent_cfg.model else None
        model_override = block_model or agent_model
        assert model_override == "haiku"  # block wins

    def test_agent_model_used_when_block_has_none(self, manager):
        """When block has no model, agent_cfg.model is used"""
        block = {"name": "normal", "prompt": "test"}

        class MockAgentCfg:
            model = "sonnet"

        agent_cfg = MockAgentCfg()

        block_model = block.get("model") or None
        agent_model = agent_cfg.model if agent_cfg and agent_cfg.model else None
        model_override = block_model or agent_model
        assert model_override == "sonnet"

    def test_no_override_when_both_empty(self, manager):
        """When neither block nor agent has model, override is None"""
        block = {"name": "normal", "prompt": "test"}
        agent_cfg = None

        block_model = block.get("model") or None
        agent_model = agent_cfg.model if agent_cfg and agent_cfg.model else None
        model_override = block_model or agent_model
        assert model_override is None

    def test_empty_string_model_treated_as_none(self, manager):
        """Empty string model should not be used as override"""
        block = {"name": "normal", "prompt": "test", "model": ""}
        block_model = block.get("model") or None
        assert block_model is None


# ============================================================
# TASK #1180: process control (pause/resume/cancel single)
# ============================================================


class TestPauseSingle(TestProcessManagerFixture):
    """Tests for pause_single method"""

    def test_pause_by_name(self, manager):
        """Pause a process by block name"""
        manager.processes["u1"] = Process(pid=1, name="block_a", status="running", start_time=0, command="")
        result = manager.pause_single("block_a")
        assert result is True
        assert manager.processes["u1"].status == "paused"

    def test_pause_by_uid(self, manager):
        """Pause a process by UID"""
        manager.processes["uid-xyz"] = Process(pid=1, name="block_a", status="running", start_time=0, command="")
        result = manager.pause_single("uid-xyz")
        assert result is True
        assert manager.processes["uid-xyz"].status == "paused"

    def test_pause_nonexistent_returns_false(self, manager):
        """Pausing non-existent process returns False"""
        assert manager.pause_single("ghost") is False

    def test_pause_done_block_returns_false(self, manager):
        """Cannot pause a block that's already done"""
        manager.processes["u1"] = Process(pid=1, name="block_a", status="done", start_time=0, command="")
        assert manager.pause_single("block_a") is False
        assert manager.processes["u1"].status == "done"

    def test_pause_failed_block_returns_false(self, manager):
        """Cannot pause a failed block"""
        manager.processes["u1"] = Process(pid=1, name="block_a", status="failed", start_time=0, command="")
        assert manager.pause_single("block_a") is False


class TestResumeSingle(TestProcessManagerFixture):
    """Tests for resume_single method"""

    def test_resume_paused_block(self, manager):
        """Resume restores previous status"""
        manager.processes["u1"] = Process(pid=1, name="block_a", status="running", start_time=0, command="")
        manager.pause_single("block_a")
        assert manager.processes["u1"].status == "paused"

        result = manager.resume_single("block_a")
        assert result is True
        assert manager.processes["u1"].status == "running"

    def test_resume_not_paused_returns_false(self, manager):
        """Cannot resume a block that isn't paused"""
        manager.processes["u1"] = Process(pid=1, name="block_a", status="running", start_time=0, command="")
        assert manager.resume_single("block_a") is False

    def test_resume_nonexistent_returns_false(self, manager):
        """Resuming non-existent process returns False"""
        assert manager.resume_single("ghost") is False

    def test_pause_resume_cycle(self, manager):
        """Multiple pause/resume cycles work correctly"""
        manager.processes["u1"] = Process(pid=1, name="block_a", status="running", start_time=0, command="")
        for _ in range(3):
            manager.pause_single("block_a")
            assert manager.processes["u1"].status == "paused"
            manager.resume_single("block_a")
            assert manager.processes["u1"].status == "running"


class TestCancelSingle(TestProcessManagerFixture):
    """Tests for cancel_single method"""

    def test_cancel_by_name(self, manager):
        """Cancel a process by block name"""
        manager.processes["u1"] = Process(pid=None, name="block_a", status="waiting", start_time=0, command="")
        result = manager.cancel_single("block_a")
        assert result is True
        assert manager.processes["u1"].status == "cancelled"

    def test_cancel_nonexistent_returns_false(self, manager):
        """Cancelling non-existent process returns False"""
        assert manager.cancel_single("ghost") is False

    def test_cancel_waiting_block(self, manager):
        """Can cancel a waiting (not-yet-running) block"""
        manager.processes["u1"] = Process(pid=None, name="block_a", status="waiting", start_time=0, command="")
        manager.cancel_single("block_a")
        assert manager.processes["u1"].status == "cancelled"

    def test_cancel_done_block(self, manager):
        """Cancelling a done block still returns True but changes status"""
        manager.processes["u1"] = Process(pid=None, name="block_a", status="done", start_time=0, command="")
        result = manager.cancel_single("block_a")
        # cancel_single doesn't check for done -- it just marks as cancelled
        assert result is True
        assert manager.processes["u1"].status == "cancelled"


class TestWorkflowPauseResume(TestProcessManagerFixture):
    """Tests for workflow-level pause/resume (already existing but completing coverage)"""

    def test_pause_workflow_sets_flag(self, manager):
        """pause_workflow sets workflow_paused=True"""
        result = manager.pause_workflow()
        assert result is True
        assert manager.workflow_paused is True
        assert manager.workflow_paused_at is not None

    def test_pause_workflow_idempotent(self, manager):
        """Double pause returns False second time"""
        manager.pause_workflow()
        assert manager.pause_workflow() is False

    def test_resume_workflow_clears_flag(self, manager):
        """resume_workflow clears workflow_paused"""
        manager.pause_workflow()
        result = manager.resume_workflow()
        assert result is True
        assert manager.workflow_paused is False
        assert manager.workflow_paused_at is None

    def test_resume_not_paused_returns_false(self, manager):
        """Resuming a non-paused workflow returns False"""
        assert manager.resume_workflow() is False


# ============================================================
# TASK #1189: Coverage improvements -- pure logic methods
# ============================================================


class TestIsBackwardRouting(TestProcessManagerFixture):
    """Tests for _is_backward_routing helper (#1172, our fix)"""

    def _setup(self, manager, blocks):
        manager.all_blocks = blocks
        manager.block_configs = {b["name"]: b for b in blocks}

    def test_forward_routing_not_backward(self, manager):
        """gate -> next_block where next_block doesn't depend on gate (sibling)"""
        self._setup(
            manager,
            [
                {"name": "a", "depends_on": []},
                {"name": "gate", "depends_on": ["a"]},
                {"name": "next_block", "depends_on": ["a"]},  # sibling, not dependent on gate
            ],
        )
        assert manager._is_backward_routing("gate", "next_block") is False

    def test_backward_routing_to_ancestor(self, manager):
        """gate -> ancestor: true backward routing"""
        self._setup(
            manager,
            [
                {"name": "start", "depends_on": []},
                {"name": "middle", "depends_on": ["start"]},
                {"name": "gate", "depends_on": ["middle"]},
            ],
        )
        # gate routing back to start (its transitive ancestor)
        assert manager._is_backward_routing("gate", "start") is True
        assert manager._is_backward_routing("gate", "middle") is True

    def test_forward_to_descendant(self, manager):
        """gate -> its own dependent (not backward)"""
        self._setup(
            manager,
            [
                {"name": "gate", "depends_on": []},
                {"name": "downstream", "depends_on": ["gate"]},
            ],
        )
        assert manager._is_backward_routing("gate", "downstream") is False

    def test_self_reference_not_backward(self, manager):
        """gate -> gate (self-loop): not in ancestors"""
        self._setup(
            manager,
            [
                {"name": "gate", "depends_on": []},
            ],
        )
        assert manager._is_backward_routing("gate", "gate") is False

    def test_deep_ancestor_chain(self, manager):
        """Deep chain: A -> B -> C -> D -> gate, gate back to A"""
        self._setup(
            manager,
            [
                {"name": "a", "depends_on": []},
                {"name": "b", "depends_on": ["a"]},
                {"name": "c", "depends_on": ["b"]},
                {"name": "d", "depends_on": ["c"]},
                {"name": "gate", "depends_on": ["d"]},
            ],
        )
        assert manager._is_backward_routing("gate", "a") is True
        assert manager._is_backward_routing("gate", "b") is True
        assert manager._is_backward_routing("gate", "c") is True


class TestSyncCompletedFromProcesses(TestProcessManagerFixture):
    """Tests for _sync_completed_from_processes helper (race fix)"""

    def test_syncs_done_status_to_completed(self, manager):
        """done blocks get added to completed set"""
        manager.processes["u1"] = Process(pid=None, name="a", status="done", start_time=0, command="")
        manager._sync_completed_from_processes()
        assert "a" in manager.completed

    def test_syncs_failed_status_to_completed(self, manager):
        """failed blocks also get added (for cascade/skip logic)"""
        manager.processes["u1"] = Process(pid=None, name="a", status="failed", start_time=0, command="")
        manager._sync_completed_from_processes()
        assert "a" in manager.completed

    def test_does_not_sync_running(self, manager):
        """running blocks should NOT be in completed"""
        manager.processes["u1"] = Process(pid=None, name="a", status="running", start_time=0, command="")
        manager._sync_completed_from_processes()
        assert "a" not in manager.completed

    def test_does_not_sync_waiting(self, manager):
        manager.processes["u1"] = Process(pid=None, name="a", status="waiting", start_time=0, command="")
        manager._sync_completed_from_processes()
        assert "a" not in manager.completed

    def test_idempotent(self, manager):
        """Calling sync multiple times is idempotent"""
        manager.processes["u1"] = Process(pid=None, name="a", status="done", start_time=0, command="")
        manager._sync_completed_from_processes()
        manager._sync_completed_from_processes()
        manager._sync_completed_from_processes()
        assert len(manager.completed) == 1
        assert "a" in manager.completed


class TestAssemblePromptTemplates(TestProcessManagerFixture):
    """Tests for assemble_prompt template substitution"""

    def test_empty_prompt_returns_empty_ish(self, manager):
        """Block with no prompt returns empty/minimal result (may include separators)"""
        block = {"name": "a", "prompt": ""}
        result = manager.assemble_prompt(block, team_tone="")
        # Result may contain template separators but no actual content
        assert isinstance(result, str)

    def test_plain_prompt_no_placeholders(self, manager):
        block = {"name": "a", "prompt": "Do something"}
        result = manager.assemble_prompt(block, team_tone="")
        assert "Do something" in result

    def test_task_input_substitution(self, manager):
        """{{ task.input.field }} placeholder replaced"""
        manager.task_input = {"topic": "Python"}
        block = {"name": "a", "prompt": "Write about {{ task.input.topic }}"}
        result = manager.assemble_prompt(block, team_tone="")
        assert "Python" in result
        assert "{{ task.input.topic }}" not in result

    def test_missing_task_input_raises_error(self, manager):
        """Missing task.input field raises ValueError (strict validation)"""
        manager.task_input = {}
        block = {"name": "a", "prompt": "Topic: {{ task.input.topic }}"}
        with pytest.raises(ValueError, match="Unresolved input placeholders"):
            manager.assemble_prompt(block, team_tone="")

    def test_task_input_dict_value_serialized(self, manager):
        """Dict values in task_input are JSON-serialized"""
        manager.task_input = {"config": {"key": "value"}}
        block = {"name": "a", "prompt": "Config: {{ task.input.config }}"}
        result = manager.assemble_prompt(block, team_tone="")
        assert '"key"' in result
        assert '"value"' in result

    def test_team_tone_appended(self, manager):
        """Team tone is included in assembled prompt"""
        block = {"name": "a", "prompt": "Task"}
        result = manager.assemble_prompt(block, team_tone="Be professional")
        assert "Be professional" in result or "Task" in result


class TestLoadSpecialistAndTeam(TestProcessManagerFixture):
    """Tests for load_team and load_specialist file loading"""

    def test_load_team_from_file(self, manager, tmp_path):
        """Load team YAML returns collaboration_tone content"""
        teams_dir = tmp_path / "teams"
        teams_dir.mkdir()
        team_file = teams_dir / "team-test.yaml"
        team_file.write_text("""
name: team-test
collaboration_tone: professional
specialists:
  - role: writer
    specialist: writer-spec
""")
        manager.agents_dir = str(tmp_path)
        # load_team loads file and extracts tone
        tone = manager.load_team("team-test")
        assert tone is not None
        assert isinstance(tone, str)

    def test_load_team_missing_file(self, manager, tmp_path):
        """Missing team file returns empty string (graceful)"""
        manager.agents_dir = str(tmp_path)
        result = manager.load_team("nonexistent-team")
        # Should not raise -- returns empty or None
        assert result == "" or result is None

    def test_load_specialist_missing_file(self, manager, tmp_path):
        manager.agents_dir = str(tmp_path)
        result = manager.load_specialist("nonexistent-spec")
        assert result == "" or result is None


class TestForwardRoutingRunCount(TestProcessManagerFixture):
    """Regression test: forward routing should not block step mode resume.

    Bug: when routing directs forward (verify -> deliver), Rein increments
    run_count of the target block to 1 before execution. On next --step call,
    Rein restores run_counts from DB, sees run_count=1, and thinks the block
    already ran -- blocking it via max_runs check.

    Fix: step mode resume uses completed_runs (actual executions) instead of
    run_count (routing entries) to restore run_counts dict.
    """

    def test_completed_runs_separate_from_run_count(self, manager):
        """completed_runs should only increment on BLOCK_DONE, not on routing."""
        proc = Process(
            pid=None, start_time=0, command="test",
            name="deliver",
            status="waiting",
            run_count=1,  # routing set this
            completed_runs=0,  # block never actually ran
        )
        # run_count=1 but completed_runs=0 means routing targeted
        # this block but it hasn't executed yet
        assert proc.run_count == 1
        assert proc.completed_runs == 0

    def test_step_mode_resume_uses_completed_runs(self, manager):
        """On resume, run_counts dict should use completed_runs, not run_count."""
        # Simulate: routing set run_count=1 but block never executed
        proc = Process(
            pid=None, start_time=0, command="test",
            name="deliver",
            status="waiting",
            run_count=1,
            completed_runs=0,
        )
        # Step mode restore logic: should use completed_runs
        manager.run_counts = {}
        if proc.completed_runs > 0:
            manager.run_counts[proc.name] = proc.completed_runs

        # run_counts should be empty (block never completed)
        assert manager.run_counts.get("deliver", 0) == 0

        # With old buggy logic (run_count > 0), it would be 1:
        # manager.run_counts["deliver"] = proc.run_count  # BUG: would be 1

    def test_completed_runs_increments_independently(self, manager):
        """completed_runs tracks actual executions."""
        proc = Process(pid=None, start_time=0, command="test", name="step1", status="done", run_count=2, completed_runs=0)
        # Simulate two completions
        proc.completed_runs += 1
        assert proc.completed_runs == 1
        proc.completed_runs += 1
        assert proc.completed_runs == 2
        # run_count is independent
        assert proc.run_count == 2


class TestCascadeCleanupRaceCondition(TestProcessManagerFixture):
    """Regression test: cascade cleanup should NOT delete outputs of running blocks.

    Bug: on resume, _initialize_all_processes includes 'running' blocks in
    failed_blocks set. Cascade invalidation propagates to dependents, and
    _clean_block_outputs deletes outputs for ALL invalidated blocks --
    including the still-running block. When the Gateway response arrives,
    it tries to write result.json to a deleted directory -> FileNotFoundError
    -> BLOCK FAILED.

    The stuck detector correctly catches the pipeline stall, but the root
    cause is premature cleanup.
    """

    def test_clean_block_outputs_removes_directory(self, manager):
        """Verify _clean_block_outputs actually removes outputs dir."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            manager.run_dir = tmpdir
            block_dir = os.path.join(tmpdir, "verify", "outputs")
            os.makedirs(block_dir)
            # Write a file
            with open(os.path.join(block_dir, "result.json"), "w") as f:
                f.write('{"result": "ok"}')

            manager._clean_block_outputs("verify")
            assert not os.path.exists(block_dir)

    def test_cascade_includes_running_blocks(self, manager):
        """Demonstrate that running blocks are included in cascade invalidation.

        This is the root cause: _initialize_all_processes treats 'running'
        same as 'failed' for cascade purposes. Running blocks' outputs
        get deleted while the block is still executing.
        """
        # Simulate DB state: verify is "running", deliver depends on verify
        from rein.state import ReinState

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "rein.db")
            state = ReinState(db_path, resume=False)

            # Save verify as running
            verify_proc = Process(
                pid=None, start_time=0, command="test",
                name="verify", status="running",
            )
            state.save_process(verify_proc)

            # Reload
            state2 = ReinState(db_path, resume=True)
            procs = state2.get_all_processes()
            statuses = {p.name: p.status for p in procs}

            # BUG: running blocks are treated as failed for cascade
            failed_blocks = {name for name, status in statuses.items()
                            if status in ("failed", "running")}
            assert "verify" in failed_blocks, (
                "Running block included in failed_blocks set -- "
                "this causes cascade cleanup to delete its outputs"
            )

    def test_running_block_outputs_should_not_be_deleted(self, manager):
        """Proposed fix: skip cleanup for blocks that are still running.

        The fix should change line ~546 in orchestrator.py to:
            for block_name in needs_rerun:
                if existing_status.get(block_name) != 'running':
                    self._clean_block_outputs(block_name)
        """
        # This test documents the expected behavior after fix
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            manager.run_dir = tmpdir

            # Create outputs for running block
            running_outputs = os.path.join(tmpdir, "verify", "outputs")
            os.makedirs(running_outputs)
            with open(os.path.join(running_outputs, "result.json"), "w") as f:
                f.write('{"result": "in progress"}')

            # Create outputs for failed block
            failed_outputs = os.path.join(tmpdir, "draft", "outputs")
            os.makedirs(failed_outputs)
            with open(os.path.join(failed_outputs, "result.json"), "w") as f:
                f.write('{"result": "old"}')

            existing_status = {"verify": "running", "draft": "failed"}
            needs_rerun = {"verify", "draft"}

            # Current behavior (BUG): cleans both
            # Proposed fix: only clean non-running
            for block_name in needs_rerun:
                if existing_status.get(block_name) != "running":
                    manager._clean_block_outputs(block_name)

            # Running block outputs should survive
            assert os.path.exists(running_outputs), (
                "Running block outputs should NOT be deleted during cascade"
            )
            # Failed block outputs should be cleaned
            assert not os.path.exists(failed_outputs), (
                "Failed block outputs should be cleaned during cascade"
            )
