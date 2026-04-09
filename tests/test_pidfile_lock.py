"""Tests for daemon PidfileLock (#1164)."""

import os
import tempfile

import pytest

from rein.daemon import PidfileLock


def test_acquire_and_release_creates_and_removes_pidfile():
    with tempfile.TemporaryDirectory() as agents_dir:
        lock = PidfileLock(agents_dir)
        lock.acquire()
        try:
            assert os.path.exists(lock.path)
            with open(lock.path) as f:
                assert f.read().strip() == str(os.getpid())
        finally:
            lock.release()
        assert not os.path.exists(lock.path)


def test_second_acquire_raises_runtime_error():
    with tempfile.TemporaryDirectory() as agents_dir:
        first = PidfileLock(agents_dir)
        first.acquire()
        try:
            second = PidfileLock(agents_dir)
            with pytest.raises(RuntimeError, match="Another Rein daemon"):
                second.acquire()
        finally:
            first.release()


def test_release_is_idempotent():
    with tempfile.TemporaryDirectory() as agents_dir:
        lock = PidfileLock(agents_dir)
        lock.acquire()
        lock.release()
        lock.release()  # must not raise


def test_lock_can_be_reacquired_after_release():
    with tempfile.TemporaryDirectory() as agents_dir:
        first = PidfileLock(agents_dir)
        first.acquire()
        first.release()

        second = PidfileLock(agents_dir)
        second.acquire()
        try:
            assert os.path.exists(second.path)
        finally:
            second.release()


def test_context_manager_releases_on_exit():
    with tempfile.TemporaryDirectory() as agents_dir:
        lock = PidfileLock(agents_dir)
        with lock:
            assert os.path.exists(lock.path)
        assert not os.path.exists(lock.path)


def test_context_manager_releases_on_exception():
    with tempfile.TemporaryDirectory() as agents_dir:
        lock = PidfileLock(agents_dir)
        with pytest.raises(ValueError):
            with lock:
                assert os.path.exists(lock.path)
                raise ValueError("boom")
        assert not os.path.exists(lock.path)


def test_state_dir_is_created_if_missing():
    with tempfile.TemporaryDirectory() as agents_dir:
        # Pass a fresh subdir that does not yet exist -- PidfileLock should mkdir it
        fresh = os.path.join(agents_dir, "new-agents")
        assert not os.path.exists(fresh)
        os.makedirs(fresh)
        lock = PidfileLock(fresh)
        lock.acquire()
        try:
            assert os.path.isdir(os.path.join(fresh, "state"))
            assert os.path.exists(lock.path)
        finally:
            lock.release()
