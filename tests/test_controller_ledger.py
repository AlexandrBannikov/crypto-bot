from decimal import Decimal
from pathlib import Path

import pytest

from app.controller_ledger import ControllerLedger
from app.trade_journal import JsonlTradeJournal
from app.trading_controller import TradingControllerState
from app.trading_controller_store import TradingControllerStateStore
from tests.test_trade_journal import make_entry


@pytest.mark.parametrize("crash_stage", ["after_prepare", "after_journal", "after_state"])
def test_controller_ledger_recovers_each_crash_boundary(
    tmp_path: Path, crash_stage: str,
) -> None:
    store = TradingControllerStateStore(tmp_path / "state.json")
    journal = JsonlTradeJournal(tmp_path / "trades.jsonl")
    target = TradingControllerState(
        virtual_balance=Decimal("1009.79"), realized_pnl=Decimal("9.79"),
        total_fees=Decimal("0.21"), closed_trades=1,
        last_processed_candle_timestamp=7200,
    )

    def crash(stage: str) -> None:
        if stage == crash_stage:
            raise RuntimeError("injected crash")

    ledger = ControllerLedger(store, journal, crash_hook=crash)
    with pytest.raises(RuntimeError, match="injected"):
        ledger.commit(target, make_entry())

    recovered = ControllerLedger(store, journal).recover()
    assert recovered == target
    assert store.load() == target
    assert [item.record_id for item in journal.read_all()] == ["record-1"]
    assert not ledger.wal_path.exists()


def test_duplicate_trade_record_is_idempotent(tmp_path: Path) -> None:
    journal = JsonlTradeJournal(tmp_path / "trades.jsonl")
    journal.append(make_entry())
    journal.append(make_entry())
    assert len(journal.read_all()) == 1
