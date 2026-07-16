from pathlib import Path

from app.engine import Trade
from app.paper_trader import (
    PaperTrader,
    PaperTraderConfig,
)
from app.trading_types import (
    ExitReason,
    PositionSide,
)


def test_records_trade_to_csv(tmp_path: Path) -> None:
    trader = PaperTrader(
        PaperTraderConfig(
            log_file=tmp_path / "paper.csv",
        )
    )

    trade = Trade(
        entry_timestamp=1,
        exit_timestamp=2,
        entry_price=100,
        exit_price=110,
        quantity=1,
        entry_fee=0,
        exit_fee=0,
        profit=10,
        profit_percent=10,
        side=PositionSide.LONG,
        exit_reason=ExitReason.SIGNAL,
    )

    trader.record_trade(trade)

    text = (
        tmp_path / "paper.csv"
    ).read_text()

    assert "entry_timestamp" in text
    assert "signal" in text
    assert "110" in text
