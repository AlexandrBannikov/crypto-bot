from __future__ import annotations

import fcntl
import json
from pathlib import Path
import sqlite3

import pytest

from app.equity_history import SnapshotStorage, load_equity_history_config
from app.read_only_self_check import run_read_only_self_check
from app.runtime_health import check_lock
from scripts import runtime_status, show_equity_history, show_scored_candidate, show_strategy_lab


def test_observer_lock_is_shared_read_only_and_never_created(tmp_path, monkeypatch):
    lock = tmp_path / "controller.lock"
    assert check_lock(lock).details == {}
    assert not lock.exists()
    lock.write_text("{}", encoding="utf-8")
    calls = []
    real_flock = fcntl.flock

    def record(fd, operation):
        calls.append(operation)
        return real_flock(fd, operation)

    monkeypatch.setattr("app.runtime_health.fcntl.flock", record)
    result = check_lock(lock)
    assert result.details == {"held": False}
    assert fcntl.LOCK_SH | fcntl.LOCK_NB in calls
    assert all(not operation & fcntl.LOCK_EX for operation in calls)


def test_observer_lock_permission_error_is_structured(tmp_path, monkeypatch):
    lock = tmp_path / "controller.lock"
    lock.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("denied")))
    assert "cannot be inspected" in check_lock(lock).message


def _database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sample(value INTEGER)")
        connection.execute("INSERT INTO sample VALUES (1)")


def test_sqlite_readonly_uses_query_only_and_creates_no_sidecars(tmp_path):
    database = tmp_path / "history.db"
    _database(database)
    before = set(tmp_path.iterdir())
    with SnapshotStorage(database).connect(readonly=True) as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("INSERT INTO sample VALUES (2)")
    assert set(tmp_path.iterdir()) == before


def test_sqlite_immutable_only_without_wal(tmp_path, monkeypatch):
    database = tmp_path / "history.db"
    _database(database)
    uris = []
    real_connect = sqlite3.connect

    def record(database_name, *args, **kwargs):
        uris.append(str(database_name))
        return real_connect(database_name, *args, **kwargs)

    monkeypatch.setattr("app.equity_history.sqlite3.connect", record)
    SnapshotStorage(database).connect(readonly=True).close()
    assert "mode=ro&immutable=1" in uris[-1]
    Path(f"{database}-wal").touch()
    SnapshotStorage(database).connect(readonly=True).close()
    assert uris[-1].endswith("mode=ro")


def test_live_wal_is_visible_and_not_replaced(tmp_path):
    database = tmp_path / "history.db"
    writer = sqlite3.connect(database)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE sample(value INTEGER)")
    writer.execute("INSERT INTO sample VALUES (7)")
    writer.commit()
    wal = Path(f"{database}-wal")
    assert wal.exists()
    before = wal.stat()
    with SnapshotStorage(database).connect(readonly=True) as reader:
        assert reader.execute("SELECT value FROM sample").fetchone()[0] == 7
    after = wal.stat()
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)
    writer.close()


def test_writer_validation_is_preserved_and_observer_can_bypass(tmp_path, monkeypatch):
    monkeypatch.delenv("EQUITY_HISTORY_DB_PATH", raising=False)
    config = tmp_path / "config.json"
    config.write_text('{"database_path":"state/history.db"}', encoding="utf-8")
    monkeypatch.setattr("app.equity_history.os.access", lambda *_: False)
    with pytest.raises(ValueError, match="not writable"):
        load_equity_history_config(config, root=tmp_path)
    loaded = load_equity_history_config(config, root=tmp_path, require_writable_database_parent=False)
    assert loaded.database_path == tmp_path / "state/history.db"


def test_self_check_missing_and_invalid_inputs_are_safe(tmp_path):
    missing = tmp_path / "missing.json"
    result = run_read_only_self_check([(missing, "json")])
    assert result["status"] == "error"
    assert result["error_codes"] == ["MISSING_PATH"]
    assert result["write_operations"] == []
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert run_read_only_self_check([(invalid, "json")])["error_codes"] == ["INVALID_INPUT"]


def test_self_check_permission_denied_is_structured(tmp_path, monkeypatch):
    denied = tmp_path / "denied.json"
    original_stat = Path.stat

    def deny(path, *args, **kwargs):
        if path == denied:
            raise PermissionError("denied")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", deny)
    result = run_read_only_self_check([(denied, "json")])
    assert result["status"] == "error"
    assert result["error_codes"] == ["PERMISSION_DENIED"]
    assert result["write_operations"] == []


def test_four_cli_self_checks_do_not_mutate_inputs(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("EQUITY_HISTORY_DB_PATH", raising=False)
    state = tmp_path / "state.json"
    journal = tmp_path / "journal.jsonl"
    state.write_text("{}", encoding="utf-8")
    journal.write_text('{"candle_timestamp":1}\n', encoding="utf-8")
    database = tmp_path / "equity.db"
    _database(database)
    equity_config = tmp_path / "equity.json"
    equity_config.write_text(json.dumps({"database_path": str(database)}), encoding="utf-8")
    lab_config = tmp_path / "lab.json"
    lab_config.write_text(json.dumps({"strategies":[{"strategy_id":"production","display_name":"p","enabled":True,"kind":"production","state":str(state),"trades":str(journal),"decisions":str(journal)}]}), encoding="utf-8")
    before = {path: path.read_bytes() for path in (state, journal, database, equity_config, lab_config)}
    assert runtime_status.main(["--read-only-self-check", "--json", "--state-path", str(state), "--journal-path", str(journal), "--shadow-path", str(journal)]) == 0
    assert show_strategy_lab.main(["--read-only-self-check", "--json", "--config", str(lab_config)]) == 0
    assert show_equity_history.main(["--read-only-self-check", "--json", "--config", str(equity_config)]) == 0
    assert show_scored_candidate.main(["--read-only-self-check", "--json", "--decisions", str(journal)]) == 0
    for path, content in before.items():
        assert path.read_bytes() == content
    for output in capsys.readouterr().out.split("}\n{"):
        assert "write_operations" in output
