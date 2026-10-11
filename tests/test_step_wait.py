"""Tests for a step and the scripts of its blocks.

A step must never walk away from a script that is still working: the next
step would find the block unfinished and start it a second time next to
itself. Either the step waits (a time budget says how long), or it stops the
script and fails the block.
"""

import json
import os
import subprocess
import sys
import time

import psutil
import pytest

from rein.children import ChildRegistry
from rein.logic import LogicRunner
from rein.orchestrator import ProcessManager
from tests.test_time_budget import Stand

# Writes its pid, appends one line per run, then works for as long as told.
SCRIPT = """import json, os, sys, time
context = json.load(sys.stdin)
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "pid"), "w") as f:
    f.write(str(os.getpid()))
with open(os.path.join(here, "runs.log"), "a") as f:
    f.write("run\\n")
first = not os.path.exists(os.path.join(here, "second"))
open(os.path.join(here, "second"), "w").close()
time.sleep(FIRST if first else LATER)
with open(context["output_file"], "w") as f:
    json.dump({"result": "ok"}, f)
"""


def script_block(**extra):
    block = {"name": "slow", "depends_on": [], "logic": {"custom": "slow.py"}}
    block.update(extra)
    return block


def make_stand(tmp_path, first, later=0, **block_extra):
    stand = Stand(tmp_path, [script_block(**block_extra)])
    with open(os.path.join(stand.flow_dir, "slow.py"), "w") as f:
        f.write(SCRIPT.replace("FIRST", repr(first)).replace("LATER", repr(later)))
    stand.clock = time.time  # real scripts take real time
    return stand


def runs(stand):
    path = os.path.join(stand.flow_dir, "runs.log")
    if not os.path.exists(path):
        return 0
    with open(path) as f:
        return len(f.read().split())


def script_pid(stand):
    with open(os.path.join(stand.flow_dir, "pid")) as f:
        return int(f.read())


def gone(pid, within=5.0):
    """True once no live process has this pid (a zombie does not count as live)."""
    deadline = time.time() + within
    while time.time() < deadline:
        try:
            if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                return True
        except psutil.NoSuchProcess:
            return True
        time.sleep(0.05)
    return False


class TestStepWaitsForABudgetedBlock:
    def test_script_longer_than_the_plain_wait_limit_is_not_interrupted(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ProcessManager, "STEP_WAIT_WITHOUT_BUDGET", 0.3)
        stand = make_stand(tmp_path, first=1.5, time_budget="1m")

        assert stand.step() is True

        assert stand.status("slow") == "done"
        assert runs(stand) == 1
        assert "WAIT TIMEOUT" not in stand.log()

    def test_run_budget_alone_is_enough_to_wait(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ProcessManager, "STEP_WAIT_WITHOUT_BUDGET", 0.3)
        stand = Stand(tmp_path, [script_block()], time_budget="1m")
        with open(os.path.join(stand.flow_dir, "slow.py"), "w") as f:
            f.write(SCRIPT.replace("FIRST", "1.5").replace("LATER", "0"))
        stand.clock = time.time

        assert stand.step() is True

        assert stand.status("slow") == "done"
        assert runs(stand) == 1

    def test_block_is_not_started_again_by_the_next_step(self, tmp_path):
        stand = make_stand(tmp_path, first=0.5, time_budget="1m")
        stand.step()

        stand.step()

        assert runs(stand) == 1

    def test_block_budget_lifts_the_default_script_limit(self, tmp_path):
        stand = make_stand(tmp_path, first=0, time_budget="1m")
        seen = {}
        original = LogicRunner.run

        def spy(self, *args, **kwargs):
            seen.update(kwargs)
            return original(self, *args, **kwargs)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(LogicRunner, "run", spy)
            stand.step()

        assert seen["no_timeout"] is True

    def test_own_timeout_of_a_block_still_applies_next_to_a_budget(self, tmp_path):
        stand = make_stand(tmp_path, first=30, time_budget="1m", timeout=1)

        stand.step()

        assert stand.status("slow") == "failed"
        assert gone(script_pid(stand))


class TestBudgetStopsTheScript:
    def test_script_over_its_block_budget_is_stopped(self, tmp_path):
        stand = make_stand(tmp_path, first=60, time_budget="1s")
        began = time.time()

        stand.step()

        assert time.time() - began < 20
        assert gone(script_pid(stand))
        assert stand.status("slow") == "failed"
        assert "SCRIPT STOPPED | slow" in stand.log()

    def test_error_handler_runs_once(self, tmp_path):
        stand = make_stand(tmp_path, first=60, time_budget="1s")

        stand.step()

        assert [e["block"] for e in stand.errors()] == ["slow"]
        assert "time budget exceeded" in stand.errors()[0]["error"]

    def test_timeout_route_is_taken(self, tmp_path):
        stand = Stand(
            tmp_path,
            [
                script_block(time_budget="1s", routing={"timeout": "after"}),
                {"name": "after", "specialist": "spec-a", "prompt": "AFTER", "depends_on": ["slow"]},
            ],
        )
        with open(os.path.join(stand.flow_dir, "slow.py"), "w") as f:
            f.write(SCRIPT.replace("FIRST", "60").replace("LATER", "0"))
        stand.clock = time.time
        stand.answers = {"AFTER": "done"}

        stand.step(0)

        assert gone(script_pid(stand))
        assert stand.calls == ["AFTER"]
        assert runs(stand) == 1

    def test_run_budget_stops_the_script(self, tmp_path):
        stand = Stand(tmp_path, [script_block()], time_budget="1s")
        with open(os.path.join(stand.flow_dir, "slow.py"), "w") as f:
            f.write(SCRIPT.replace("FIRST", "60").replace("LATER", "0"))
        stand.clock = time.time

        stand.step()

        assert gone(script_pid(stand))
        assert stand.status("slow") == "failed"


class TestBlockWithoutAnyBudget:
    def test_script_is_stopped_at_the_wait_limit_and_the_block_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ProcessManager, "STEP_WAIT_WITHOUT_BUDGET", 0.5)
        stand = make_stand(tmp_path, first=60)

        stand.step()

        assert gone(script_pid(stand))
        assert stand.status("slow") == "failed"
        assert len(stand.errors()) == 1
        assert "time_budget" in stand.errors()[0]["error"]

    def test_next_step_retries_it_once(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ProcessManager, "STEP_WAIT_WITHOUT_BUDGET", 0.5)
        stand = make_stand(tmp_path, first=60, later=0)
        stand.step()
        first_pid = script_pid(stand)

        stand.step()

        assert gone(first_pid)
        assert stand.status("slow") == "done"
        assert runs(stand) == 2

    def test_late_result_of_the_stopped_attempt_is_not_taken(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ProcessManager, "STEP_WAIT_WITHOUT_BUDGET", 0.5)
        stand = make_stand(tmp_path, first=60)

        stand.step()

        assert "BLOCK COMPLETED | slow" not in stand.log()


def sleeper(tmp_path, with_grandchild=False):
    """A process in a session of its own, as the engine starts scripts."""
    if with_grandchild:
        marker = str(tmp_path / "grandchild.pid")
        cmd = ["bash", "-c", f"sleep 60 & echo $! > {marker}; wait"]
    else:
        cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
    return subprocess.Popen(cmd, start_new_session=True)


class TestChildRegistry:
    def test_stop_block_stops_only_that_block(self, tmp_path):
        registry = ChildRegistry(str(tmp_path))
        one, two = sleeper(tmp_path), sleeper(tmp_path)
        registry.started("one", one)
        registry.started("two", two)
        try:
            assert registry.stop_block("one", "test") == 1

            assert one.poll() is not None
            assert two.poll() is None
        finally:
            registry.stop_all("cleanup")

    def test_whatever_the_script_started_is_stopped_with_it(self, tmp_path):
        registry = ChildRegistry(str(tmp_path))
        proc = sleeper(tmp_path, with_grandchild=True)
        registry.started("one", proc)
        marker = tmp_path / "grandchild.pid"
        deadline = time.time() + 5
        while not (marker.exists() and marker.read_text().strip()) and time.time() < deadline:
            time.sleep(0.05)
        grandchild = int(marker.read_text())

        registry.stop_block("one", "test")

        assert gone(grandchild)

    def test_finished_script_leaves_no_record(self, tmp_path):
        registry = ChildRegistry(str(tmp_path))
        proc = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
        registry.started("one", proc)
        proc.wait()

        registry.finished(proc)

        assert os.listdir(registry.dir) == []
        assert registry.stop_all("test") == 0

    def test_script_of_an_engine_that_is_gone_is_stopped_by_the_next_one(self, tmp_path):
        proc = sleeper(tmp_path)
        ChildRegistry(str(tmp_path)).started("one", proc)

        stopped = ChildRegistry(str(tmp_path)).stop_orphans("test")

        proc.wait(timeout=5)
        assert stopped == 1
        assert os.listdir(os.path.join(str(tmp_path), "state", "children")) == []

    def test_own_scripts_are_not_orphans(self, tmp_path):
        registry = ChildRegistry(str(tmp_path))
        proc = sleeper(tmp_path)
        registry.started("one", proc)
        try:
            assert registry.stop_orphans("test") == 0
            assert proc.poll() is None
        finally:
            registry.stop_all("cleanup")

    def test_reused_pid_is_not_touched(self, tmp_path):
        proc = sleeper(tmp_path)
        registry = ChildRegistry(str(tmp_path))
        os.makedirs(registry.dir)
        with open(os.path.join(registry.dir, f"{proc.pid}.json"), "w") as f:
            json.dump({"block": "one", "pid": proc.pid, "create_time": 1.0}, f)
        try:
            assert registry.stop_orphans("test") == 0
            assert proc.poll() is None
            assert os.listdir(registry.dir) == []
        finally:
            proc.kill()
            proc.wait()


class TestOrphanBeforeRerun:
    def test_step_stops_the_script_of_a_dead_engine_before_it_starts_the_block_again(self, tmp_path):
        stand = make_stand(tmp_path, first=0, time_budget="1m")
        left_behind = sleeper(tmp_path)
        ChildRegistry(stand.task_dir).started("slow", left_behind)

        stand.step()

        left_behind.wait(timeout=5)
        assert "ORPHAN SCRIPTS STOPPED | 1" in stand.log()
        assert stand.status("slow") == "done"
