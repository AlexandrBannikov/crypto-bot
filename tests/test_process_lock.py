import errno
import json
import os
import select
import subprocess
import sys
from pathlib import Path

import pytest

from app.process_lock import (
    ProcessAlreadyRunningError,
    ProcessLock,
    ProcessLockError,
)


HOLDER_CODE = """
import sys
from app.process_lock import ProcessLock
with ProcessLock(sys.argv[1]):
    print("locked", flush=True)
    sys.stdin.read()
"""


def start_holder(path: Path) -> subprocess.Popen:
    process = subprocess.Popen(
        [sys.executable, "-c", HOLDER_CODE, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    ready, _, _ = select.select([process.stdout], [], [], 5)
    assert ready, "lock-holder process did not become ready"
    assert process.stdout.readline().strip() == "locked"
    return process


def stop_holder(process: subprocess.Popen) -> None:
    try:
        if process.stdin is not None:
            process.stdin.close()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_lock_is_acquired_and_released(tmp_path) -> None:
    path = tmp_path / "controller.lock"
    with ProcessLock(path):
        contender = subprocess.run(
            [sys.executable, "-c", HOLDER_CODE, str(path)],
            input="",
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert contender.returncode != 0

    with ProcessLock(path):
        pass


def test_independent_process_cannot_acquire_held_lock(tmp_path) -> None:
    path = tmp_path / "controller.lock"
    holder = start_holder(path)
    try:
        with pytest.raises(ProcessAlreadyRunningError):
            with ProcessLock(path):
                pass
    finally:
        stop_holder(holder)


def test_lock_can_be_reacquired_after_process_exits(tmp_path) -> None:
    path = tmp_path / "controller.lock"
    holder = start_holder(path)
    stop_holder(holder)

    with ProcessLock(path):
        pass


def test_existing_unlocked_file_does_not_block(tmp_path) -> None:
    path = tmp_path / "controller.lock"
    path.write_text("stale metadata", encoding="utf-8")

    with ProcessLock(path):
        pass


def test_parent_directory_is_created(tmp_path) -> None:
    path = tmp_path / "nested/state/controller.lock"

    with ProcessLock(path):
        assert path.exists()


def test_metadata_contains_pid_and_utc_timestamp(tmp_path) -> None:
    path = tmp_path / "controller.lock"

    with ProcessLock(path):
        metadata = json.loads(path.read_text(encoding="utf-8"))

    assert metadata["pid"] == os.getpid()
    assert metadata["started_at"].endswith("+00:00")


def test_descriptor_is_closed_after_body_exception(tmp_path) -> None:
    path = tmp_path / "controller.lock"

    with pytest.raises(ValueError, match="body failed"):
        with ProcessLock(path):
            raise ValueError("body failed")

    with ProcessLock(path):
        pass


def test_metadata_write_error_releases_lock(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "controller.lock"

    with monkeypatch.context() as context:
        context.setattr(
            json,
            "dump",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                OSError(errno.ENOSPC, "no space")
            ),
        )
        with pytest.raises(ProcessLockError) as captured:
            with ProcessLock(path):
                pass

    assert isinstance(captured.value.__cause__, OSError)
    with ProcessLock(path):
        pass


def test_open_error_is_wrapped_and_contains_path(tmp_path) -> None:
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("content", encoding="utf-8")
    path = parent_file / "controller.lock"

    with pytest.raises(ProcessLockError, match=str(path)):
        with ProcessLock(path):
            pass


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_control_flow_exceptions_are_not_wrapped(
    tmp_path,
    exception_type,
) -> None:
    path = tmp_path / "controller.lock"

    with pytest.raises(exception_type):
        with ProcessLock(path):
            raise exception_type()

    with ProcessLock(path):
        pass


def test_same_object_cannot_be_entered_twice(tmp_path) -> None:
    lock = ProcessLock(tmp_path / "controller.lock")

    with lock:
        with pytest.raises(ProcessLockError, match="already entered"):
            lock.__enter__()
