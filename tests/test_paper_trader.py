import csv
from pathlib import Path

import pytest

from app.engine import (
    BacktestEngine,
    Candle,
    Signal,
    Trade,
)
from app.paper_trader import (
    PaperTrader,
    PaperTraderConfig,
)
from app.trading_types import (
    ExitReason,
    PositionSide,
)


class StaticFeed:
    def __init__(
        self,
        candles: tuple[Candle, ...],
    ) -> None:
        self.candles = candles

    def get_candles(self) -> tuple[Candle, ...]:
        return self.candles


class BuyOnlyStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return Signal.BUY

        return Signal.HOLD


class HoldStrategy:
    def generate_signal(self, candles, index):
        return Signal.HOLD


def make_trade(
    *,
    entry_timestamp: int = 1,
    exit_timestamp: int = 2,
    profit: float = 10,
) -> Trade:
    return Trade(
        entry_timestamp=entry_timestamp,
        exit_timestamp=exit_timestamp,
        entry_price=100,
        exit_price=110,
        quantity=1,
        entry_fee=0,
        exit_fee=0,
        profit=profit,
        profit_percent=10,
        side=PositionSide.LONG,
        exit_reason=ExitReason.SIGNAL,
    )


def make_candles() -> tuple[Candle, ...]:
    return (
        Candle(1, 100, 101, 99, 100, 1),
        Candle(2, 110, 111, 109, 110, 1),
        Candle(3, 120, 121, 119, 120, 1),
    )


def test_records_trade_to_csv(
    tmp_path: Path,
) -> None:
    trader = PaperTrader(
        PaperTraderConfig(
            log_file=tmp_path / "paper.csv",
        )
    )

    trader.record_trade(make_trade())

    rows = list(
        csv.reader(
            (tmp_path / "paper.csv").open(
                encoding="utf-8",
            )
        )
    )

    assert rows[0] == [
        "entry_timestamp",
        "exit_timestamp",
        "side",
        "entry_price",
        "exit_price",
        "quantity",
        "entry_fee",
        "exit_fee",
        "profit",
        "profit_percent",
        "exit_reason",
    ]

    assert rows[1][2] == "long"
    assert rows[1][4] == "110"
    assert rows[1][-1] == "signal"


def test_records_header_only_once(
    tmp_path: Path,
) -> None:
    trader = PaperTrader(
        PaperTraderConfig(
            log_file=tmp_path / "paper.csv",
        )
    )

    trader.record_trade(
        make_trade(
            entry_timestamp=1,
            exit_timestamp=2,
        )
    )

    trader.record_trade(
        make_trade(
            entry_timestamp=3,
            exit_timestamp=4,
        )
    )

    rows = list(
        csv.reader(
            (tmp_path / "paper.csv").open(
                encoding="utf-8",
            )
        )
    )

    assert len(rows) == 3
    assert rows[0][0] == "entry_timestamp"
    assert rows[1][0] == "1"
    assert rows[2][0] == "3"


def test_records_multiple_trades(
    tmp_path: Path,
) -> None:
    trader = PaperTrader(
        PaperTraderConfig(
            log_file=tmp_path / "paper.csv",
        )
    )

    trader.record_trades(
        (
            make_trade(
                entry_timestamp=1,
                exit_timestamp=2,
            ),
            make_trade(
                entry_timestamp=3,
                exit_timestamp=4,
            ),
        )
    )

    rows = list(
        csv.reader(
            (tmp_path / "paper.csv").open(
                encoding="utf-8",
            )
        )
    )

    assert len(rows) == 3


def test_run_session_executes_engine_and_logs_trade(
    tmp_path: Path,
) -> None:
    log_file = tmp_path / "session.csv"

    trader = PaperTrader(
        PaperTraderConfig(
            log_file=log_file,
        )
    )

    result = trader.run_session(
        feed=StaticFeed(make_candles()),
        strategy=BuyOnlyStrategy(),
        engine=BacktestEngine(
            initial_balance=1_000,
            commission_rate=0,
        ),
    )

    assert len(result.trades) == 1
    assert result.final_balance == pytest.approx(
        1_000 / 110 * 120
    )

    rows = list(
        csv.reader(
            log_file.open(
                encoding="utf-8",
            )
        )
    )

    assert len(rows) == 2
    assert rows[1][-1] == "end_of_data"


def test_run_session_with_no_trades_writes_no_file(
    tmp_path: Path,
) -> None:
    log_file = tmp_path / "session.csv"

    trader = PaperTrader(
        PaperTraderConfig(
            log_file=log_file,
        )
    )

    result = trader.run_session(
        feed=StaticFeed(make_candles()),
        strategy=HoldStrategy(),
        engine=BacktestEngine(
            initial_balance=1_000,
            commission_rate=0,
        ),
    )

    assert result.trades == ()
    assert not log_file.exists()


def test_run_session_rejects_empty_feed(
    tmp_path: Path,
) -> None:
    trader = PaperTrader(
        PaperTraderConfig(
            log_file=tmp_path / "session.csv",
        )
    )

    with pytest.raises(
        ValueError,
        match="no candles",
    ):
        trader.run_session(
            feed=StaticFeed(()),
            strategy=HoldStrategy(),
        )


def test_does_not_record_same_trade_twice(
    tmp_path: Path,
) -> None:
    trader = PaperTrader(
        PaperTraderConfig(
            log_file=tmp_path / "paper.csv",
        )
    )

    trade = make_trade()

    assert trader.record_trade(trade) is True
    assert trader.record_trade(trade) is False

    rows = list(
        csv.reader(
            (tmp_path / "paper.csv").open(
                encoding="utf-8",
            )
        )
    )

    assert len(rows) == 2


def test_record_trades_returns_number_of_new_rows(
    tmp_path: Path,
) -> None:
    trader = PaperTrader(
        PaperTraderConfig(
            log_file=tmp_path / "paper.csv",
        )
    )

    first = make_trade(
        entry_timestamp=1,
        exit_timestamp=2,
    )
    second = make_trade(
        entry_timestamp=3,
        exit_timestamp=4,
    )

    assert trader.record_trades(
        (first, second)
    ) == 2

    assert trader.record_trades(
        (first, second)
    ) == 0


def test_counts_recorded_trades(
    tmp_path: Path,
) -> None:
    trader = PaperTrader(
        PaperTraderConfig(
            log_file=tmp_path / "paper.csv",
        )
    )

    assert trader.count_recorded_trades() == 0

    trader.record_trades(
        (
            make_trade(
                entry_timestamp=1,
                exit_timestamp=2,
            ),
            make_trade(
                entry_timestamp=3,
                exit_timestamp=4,
            ),
        )
    )

    assert trader.count_recorded_trades() == 2
