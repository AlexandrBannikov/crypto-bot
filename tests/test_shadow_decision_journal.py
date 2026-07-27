import json
from dataclasses import asdict

import pytest

from app.shadow_decision_journal import (
    ShadowDecisionJournal,
    ShadowDecisionRecord,
)


def record(timestamp=1, **changes):
    values = {
        "candle_timestamp": timestamp,
        "symbol": "ETHUSDT",
        "timeframe": "60",
        "strategy_mode": "shadow",
        "baseline_signal": "open_long",
        "filtered_signal": "hold",
        "execution_signal": "open_long",
        "regime": "RANGE/NORMAL",
        "confidence": 1.0,
        "allowed": False,
        "blocked": True,
        "blocked_reason": "range",
        "current_position": "flat",
        "virtual_balance": "1000",
        "detector_parameters": {"adx_period": 14},
        "filter_parameters_fingerprint": "abc",
        "unique_candle_identifier": f"ETHUSDT:60:{timestamp}",
        "controller_run_identifier": "run",
        "detector_error": None,
    }
    values.update(changes)
    return ShadowDecisionRecord(**values)


def test_append_and_read_jsonl(tmp_path) -> None:
    journal = ShadowDecisionJournal(tmp_path / "shadow.jsonl")

    assert journal.append(record()) is True

    assert journal.read_all() == [record()]


def test_same_candle_is_not_appended_twice(tmp_path) -> None:
    journal = ShadowDecisionJournal(tmp_path / "shadow.jsonl")

    assert journal.append(record()) is True
    assert journal.append(record()) is False
    assert len(journal.read_all()) == 1


def test_deduplication_survives_restart(tmp_path) -> None:
    path = tmp_path / "shadow.jsonl"
    ShadowDecisionJournal(path).append(record())

    restarted = ShadowDecisionJournal(path)

    assert restarted.append(record()) is False


def test_stale_or_corrupt_optional_state_recovers_from_jsonl(
    tmp_path,
) -> None:
    path = tmp_path / "shadow.jsonl"
    journal = ShadowDecisionJournal(path)
    journal.append(record())
    journal.state_path.write_text("{broken", encoding="utf-8")

    restarted = ShadowDecisionJournal(path)

    assert restarted.append(record()) is False


def test_partial_last_line_is_ignored(tmp_path) -> None:
    path = tmp_path / "shadow.jsonl"
    journal = ShadowDecisionJournal(path)
    journal.append(record())
    with path.open("a", encoding="utf-8") as file:
        file.write('{"partial":')

    restarted = ShadowDecisionJournal(path)

    assert restarted.read_all() == [record()]
    assert restarted.append(record()) is False
    assert restarted.append(record(2)) is True
    assert restarted.read_all() == [record(), record(2)]


def test_corrupt_middle_line_is_rejected(tmp_path) -> None:
    path = tmp_path / "shadow.jsonl"
    path.write_text(
        json.dumps(asdict(record())) + "\n{broken\n{}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="corrupt shadow"):
        ShadowDecisionJournal(path).read_all()


def test_invalid_utf8_last_line_is_repaired(tmp_path) -> None:
    path = tmp_path / "shadow.jsonl"
    journal = ShadowDecisionJournal(path)
    journal.append(record())
    with path.open("ab") as file:
        file.write(b"\xff\xfe")

    restarted = ShadowDecisionJournal(path)

    assert restarted.read_all() == [record()]
    assert restarted.append(record(2)) is True
