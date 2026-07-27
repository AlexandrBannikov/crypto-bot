from __future__ import annotations

import errno
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import IO


class ProcessLockError(RuntimeError):
    """Base error raised while managing a process lock."""


class ProcessAlreadyRunningError(ProcessLockError):
    """Raised when another process holds the requested lock."""


class ProcessLock:
    """A non-blocking, Linux advisory process lock."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._file: IO[str] | None = None

    def __enter__(self) -> ProcessLock:
        if self._file is not None:
            raise ProcessLockError(
                f"Process lock is already entered: {self.path}"
            )

        descriptor: int | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(
                self.path,
                os.O_RDWR | os.O_CREAT,
                0o600,
            )
            lock_file = os.fdopen(
                descriptor,
                "r+",
                encoding="utf-8",
            )
            descriptor = None
        except OSError as exc:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            raise ProcessLockError(
                f"Cannot open process lock {self.path}: {exc}"
            ) from exc
        except BaseException:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            raise

        try:
            fcntl.flock(
                lock_file.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except OSError as exc:
            details = self._read_details(lock_file)
            lock_file.close()
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                suffix = f" ({details})" if details else ""
                raise ProcessAlreadyRunningError(
                    f"Process lock is already held: "
                    f"{self.path}{suffix}"
                ) from exc
            raise ProcessLockError(
                f"Cannot acquire process lock {self.path}: {exc}"
            ) from exc

        try:
            metadata = {
                "pid": os.getpid(),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "command": sys.argv,
            }
            lock_file.truncate(0)
            lock_file.seek(0)
            json.dump(metadata, lock_file, ensure_ascii=False)
            lock_file.write("\n")
            lock_file.flush()
        except OSError as exc:
            try:
                raise ProcessLockError(
                    f"Cannot write process lock {self.path}: {exc}"
                ) from exc
            finally:
                self._release_file(lock_file)
        except BaseException:
            self._release_file(lock_file)
            raise

        self._file = lock_file
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        lock_file = self._file
        self._file = None
        if lock_file is None:
            return

        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except OSError as exc:
            raise ProcessLockError(
                f"Cannot release process lock {self.path}: {exc}"
            ) from exc
        finally:
            lock_file.close()

    @staticmethod
    def _read_details(lock_file: IO[str]) -> str:
        try:
            lock_file.seek(0)
            return lock_file.read().strip()
        except OSError:
            return ""

    @staticmethod
    def _release_file(lock_file: IO[str]) -> None:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()
