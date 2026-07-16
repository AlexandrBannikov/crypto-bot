from pathlib import Path

import pytest

from app.paper_session import (
    PaperPosition,
    PaperSessionSnapshot,
)
from app.trading_types import (
    ExitReason,
    PositionSide,
    TradeAction,
)

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


def test_saves_and_loads_full_session_snapshot(
    tmp_path: Path,
) -> None:
    store = PaperStateStore(
        tmp_path / "state.json"
    )

    position = PaperPosition(
        side=PositionSide.LONG,
        entry_timestamp=100,
        entry_price=2000,
        quantity=0.5,
        entry_fee=1,
        entry_cost=501,
        initial_stop_loss=1900,
        active_stop_loss=1950,
        stop_reason=ExitReason.TRAILING_STOP,
        trailing_stop_percent=0.025,
    )

    snapshot = PaperSessionSnapshot(
        balance=499,
        last_candle_timestamp=200,
        pending_action=TradeAction.HOLD,
        position=position,
    )

    state = PaperSessionState(
        last_candle_timestamp=200,
        virtual_balance=499,
        recorded_trades=3,
        session_snapshot=snapshot,
    )

    store.save(state)

    loaded = store.load()

    assert loaded == state
    assert loaded.session_snapshot == snapshot
    assert loaded.session_snapshot.position == position


def test_saves_pending_open_action(
    tmp_path: Path,
) -> None:
    store = PaperStateStore(
        tmp_path / "state.json"
    )

    snapshot = PaperSessionSnapshot(
        balance=1000,
        last_candle_timestamp=100,
        pending_action=TradeAction.OPEN_LONG,
        pending_stop_loss=95,
        pending_reference_price=100,
        pending_trailing_stop_percent=0.05,
    )

    state = PaperSessionState(
        last_candle_timestamp=100,
        virtual_balance=1000,
        recorded_trades=0,
        session_snapshot=snapshot,
    )

    store.save(state)

    loaded = store.load()

    assert (
        loaded.session_snapshot.pending_action
        == TradeAction.OPEN_LONG
    )
    assert (
        loaded.session_snapshot.pending_stop_loss
        == pytest.approx(95)
    )
    assert (
        loaded.session_snapshot
        .pending_reference_price
        == pytest.approx(100)
    )


def test_legacy_state_creates_snapshot() -> None:
    state = PaperSessionState(
        last_candle_timestamp=123,
        virtual_balance=900,
        recorded_trades=2,
    )

    assert state.session_snapshot is not None
    assert (
        state.session_snapshot.last_candle_timestamp
        == 123
    )
    assert state.session_snapshot.balance == pytest.approx(
        900
    )
