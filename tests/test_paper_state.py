from pathlib import Path

import pytest

from app.paper_state import (
    PaperSessionState,
    PaperStateStore,
)


def test_loads_default_state_when_file_missing(
    tmp_path: Path,
) -> None:
    store = PaperStateStore(
        tmp_path / "state.json"
    )

    state = store.load(
        default_balance=2500,
    )

    assert state.last_candle_timestamp is None
    assert state.virtual_balance == pytest.approx(
        2500
    )
    assert state.recorded_trades == 0


def test_saves_and_loads_state(
    tmp_path: Path,
) -> None:
    store = PaperStateStore(
        tmp_path / "state.json"
    )

    expected = PaperSessionState(
        last_candle_timestamp=123,
        virtual_balance=1050.5,
        recorded_trades=7,
    )

    store.save(expected)

    assert store.load() == expected


def test_rejects_invalid_state_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        "not json",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="invalid paper state",
    ):
        PaperStateStore(path).load()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("last_candle_timestamp", -1),
        ("virtual_balance", 0),
        ("recorded_trades", -1),
    ],
)
def test_rejects_invalid_state_values(
    field: str,
    value,
) -> None:
    kwargs = {field: value}

    with pytest.raises(ValueError):
        PaperSessionState(**kwargs)
