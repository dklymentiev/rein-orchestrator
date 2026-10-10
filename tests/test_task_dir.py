"""Tests for task directory creation: two runs never share a directory.

The clock is stopped in these tests. A task directory is named after the
time, so "two runs in the same second" is reproduced exactly instead of
being left to how fast the machine happens to be.
"""

import json
import os
import re
from datetime import datetime

import pytest

import rein.orchestrator as orchestrator_module
import rein.tasks as tasks_module
from rein.orchestrator import ProcessManager

FROZEN = datetime(2026, 1, 2, 3, 4, 5)
FROZEN_STAMP = "20260102-030405"


class FrozenDatetime(datetime):
    """datetime whose now() always returns the same second."""

    @classmethod
    def now(cls, tz=None):
        return FROZEN.replace(tzinfo=tz)


@pytest.fixture
def frozen_clock(monkeypatch):
    monkeypatch.setattr(orchestrator_module, "datetime", FrozenDatetime)


@pytest.fixture
def manager(tmp_path):
    return ProcessManager(max_parallel=1, flow_name="demo", agents_dir=str(tmp_path))


def _suffixes(monkeypatch, values):
    """Make new_task_dir draw its random suffixes from `values`, in order."""
    it = iter(values)
    monkeypatch.setattr(tasks_module, "_task_suffix", lambda: next(it))


def _read_input(tasks_root, task_id):
    with open(os.path.join(tasks_root, task_id, "input", "task.json")) as f:
        return json.load(f)


class TestCreateTaskSameSecond:
    """ProcessManager.create_task, the door behind `rein --flow`."""

    def test_two_tasks_in_the_same_second_get_separate_directories(self, manager, frozen_clock):
        first = manager.create_task("demo", {"who": "first"})
        second = manager.create_task("demo", {"who": "second"})

        assert first != second
        assert os.path.isdir(os.path.join(manager.tasks_root, first))
        assert os.path.isdir(os.path.join(manager.tasks_root, second))

    def test_second_task_does_not_overwrite_the_input_of_the_first(self, manager, frozen_clock):
        first = manager.create_task("demo", {"who": "first"})
        second = manager.create_task("demo", {"who": "second"})

        assert _read_input(manager.tasks_root, first)["input"] == {"who": "first"}
        assert _read_input(manager.tasks_root, second)["input"] == {"who": "second"}
        assert _read_input(manager.tasks_root, first)["id"] == first
        assert _read_input(manager.tasks_root, second)["id"] == second

    def test_many_tasks_in_the_same_second(self, manager, frozen_clock):
        ids = [manager.create_task("demo", {"n": n}) for n in range(20)]

        assert len(set(ids)) == 20
        for n, task_id in enumerate(ids):
            assert _read_input(manager.tasks_root, task_id)["input"] == {"n": n}

    def test_existing_directory_is_never_taken_for_a_new_one(self, manager, frozen_clock, monkeypatch):
        # Another run already holds the name the next call would pick first.
        taken = os.path.join(manager.tasks_root, f"task-{FROZEN_STAMP}-aaaaaa")
        os.makedirs(os.path.join(taken, "input"))
        with open(os.path.join(taken, "input", "task.json"), "w") as f:
            json.dump({"id": "someone-else", "input": {"who": "owner"}}, f)
        _suffixes(monkeypatch, ["aaaaaa", "bbbbbb"])

        task_id = manager.create_task("demo", {"who": "newcomer"})

        assert task_id == f"task-{FROZEN_STAMP}-bbbbbb"
        assert _read_input(manager.tasks_root, task_id)["input"] == {"who": "newcomer"}
        # The directory that was already there is untouched.
        assert _read_input(manager.tasks_root, f"task-{FROZEN_STAMP}-aaaaaa") == {
            "id": "someone-else",
            "input": {"who": "owner"},
        }
        assert sorted(os.listdir(taken)) == ["input"]


class TestNewTaskDir:
    def test_name_is_time_then_random_suffix(self, tmp_path):
        task_id, task_dir = tasks_module.new_task_dir(str(tmp_path), FROZEN)

        assert re.fullmatch(rf"task-{FROZEN_STAMP}-[0-9a-f]{{6}}", task_id)
        assert task_dir == os.path.join(str(tmp_path), task_id)
        assert os.path.isdir(task_dir)

    def test_uses_the_current_time_when_none_is_given(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tasks_module, "datetime", FrozenDatetime)

        task_id, _ = tasks_module.new_task_dir(str(tmp_path))

        assert task_id.startswith(f"task-{FROZEN_STAMP}-")

    def test_creates_the_tasks_root(self, tmp_path):
        tasks_root = os.path.join(str(tmp_path), "agents", "tasks")

        _, task_dir = tasks_module.new_task_dir(tasks_root, FROZEN)

        assert os.path.dirname(task_dir) == tasks_root
        assert os.path.isdir(task_dir)

    def test_names_sort_by_time_whatever_the_suffix(self, tmp_path, monkeypatch):
        _suffixes(monkeypatch, ["ffffff", "000000"])

        earlier, _ = tasks_module.new_task_dir(str(tmp_path), datetime(2026, 1, 2, 3, 4, 5))
        later, _ = tasks_module.new_task_dir(str(tmp_path), datetime(2026, 1, 2, 3, 4, 6))

        assert sorted([later, earlier]) == [earlier, later]

    def test_retries_with_a_new_name_when_the_first_is_taken(self, tmp_path, monkeypatch):
        os.mkdir(os.path.join(str(tmp_path), f"task-{FROZEN_STAMP}-aaaaaa"))
        _suffixes(monkeypatch, ["aaaaaa", "aaaaaa", "cccccc"])

        task_id, task_dir = tasks_module.new_task_dir(str(tmp_path), FROZEN)

        assert task_id == f"task-{FROZEN_STAMP}-cccccc"
        assert os.path.isdir(task_dir)

    def test_gives_up_with_an_error_instead_of_reusing_a_directory(self, tmp_path, monkeypatch):
        taken = os.path.join(str(tmp_path), f"task-{FROZEN_STAMP}-aaaaaa")
        os.mkdir(taken)
        monkeypatch.setattr(tasks_module, "_task_suffix", lambda: "aaaaaa")

        with pytest.raises(RuntimeError, match="Could not create a new task directory"):
            tasks_module.new_task_dir(str(tmp_path), FROZEN)

        assert os.listdir(str(tmp_path)) == [os.path.basename(taken)]
        assert os.listdir(taken) == []

    def test_number_of_attempts_is_bounded(self, tmp_path, monkeypatch):
        os.mkdir(os.path.join(str(tmp_path), f"task-{FROZEN_STAMP}-aaaaaa"))
        calls = []

        def same_suffix():
            calls.append(1)
            return "aaaaaa"

        monkeypatch.setattr(tasks_module, "_task_suffix", same_suffix)

        with pytest.raises(RuntimeError):
            tasks_module.new_task_dir(str(tmp_path), FROZEN)

        assert len(calls) == tasks_module.NEW_TASK_DIR_ATTEMPTS
