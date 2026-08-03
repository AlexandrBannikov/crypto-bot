from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from typing import Iterable


def _path_result(path: Path, kind: str) -> dict:
    try:
        path.stat()
        exists = True
    except FileNotFoundError:
        exists = False
    except PermissionError:
        return {
            "path": str(path), "kind": kind, "exists": None,
            "readable": False, "writable": False,
            "parent_traversable": False,
            "error_code": "PERMISSION_DENIED",
        }
    optional = kind == "optional_file"
    readable = (exists and os.access(path, os.R_OK)) or (optional and not exists)
    error_code = None
    if not exists and not optional:
        error_code = "MISSING_PATH"
    elif not readable:
        error_code = "PERMISSION_DENIED"
    elif kind in {"json", "jsonl"}:
        try:
            if kind == "json":
                json.loads(path.read_text(encoding="utf-8"))
            else:
                with path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        if line.strip():
                            json.loads(line)
        except (OSError, UnicodeError, json.JSONDecodeError):
            error_code = "INVALID_INPUT"
    return {
        "path": str(path), "kind": kind, "exists": exists,
        "readable": readable, "writable": os.access(path, os.W_OK) if exists else False,
        "parent_traversable": os.access(path.parent, os.X_OK),
        "error_code": error_code,
    }


def run_read_only_self_check(
    paths: Iterable[tuple[Path, str]], *, sqlite_path: Path | None = None
) -> dict:
    required = [_path_result(Path(path), kind) for path, kind in paths]
    sqlite_mode = None
    wal_present = shm_present = False
    sqlite_error = None
    if sqlite_path is not None:
        sqlite_path = Path(sqlite_path)
        try:
            wal_present = Path(f"{sqlite_path}-wal").exists()
            shm_present = Path(f"{sqlite_path}-shm").exists()
        except PermissionError:
            wal_present = shm_present = False
        immutable = not wal_present
        sqlite_mode = "ro" if wal_present else "ro+immutable"
        uri = f"file:{sqlite_path}?mode=ro" + ("&immutable=1" if immutable else "")
        try:
            with sqlite3.connect(uri, uri=True, timeout=5) as connection:
                connection.execute("PRAGMA query_only=ON")
                if connection.execute("PRAGMA query_only").fetchone()[0] != 1:
                    raise sqlite3.OperationalError("query_only unavailable")
                connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        except sqlite3.Error:
            sqlite_error = "SQLITE_READ_ONLY_OPEN_FAILED"
    errors = [item["error_code"] for item in required if item["error_code"]]
    if sqlite_error:
        errors.append(sqlite_error)
    return {
        "status": "ok" if not errors else "error",
        "required_paths": required,
        "readable": all(item["readable"] for item in required),
        "writable": any(item["writable"] for item in required),
        "sqlite_mode": sqlite_mode,
        "wal_present": wal_present,
        "shm_present": shm_present,
        "write_operations": [],
        "error_codes": errors,
    }
