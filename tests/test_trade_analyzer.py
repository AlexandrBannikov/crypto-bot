import pytest

from app.engine import Candle, Trade
from app.trade_analyzer import TradeAnalyzer
from app.trading_types import PositionSide


def make_candle(
    timestamp: int,
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> Candle:
    return Candle(
        timestamp=timestamp,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1.0,
    )


def make_trade(
    *,
    side: PositionSide,
    entry_timestamp: int,
    exit_timestamp: int,
    entry_price: float,
    exit_price: float,
) -> Trade:
    return Trade(
        entry_timestamp=entry_timestamp,
        exit_timestamp=exit_timestamp,
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=1.0,
        entry_fee=0.0,
        exit_fee=0.0,
        profit=exit_price - entry_price,
        profit_percent=(
            (exit_price - entry_price)
            / entry_price
            * 100
        ),
        side=side,
    )


def test_analyzes_long_trade_excursions() -> None:
    candles = [
        make_candle(
            1,
            open_price=100,
            high=103,
            low=98,
            close=102,
        ),
        make_candle(
            2,
            open_price=102,
            high=108,
            low=97,
            close=106,
        ),
        make_candle(
            3,
            open_price=106,
            high=110,
            low=104,
            close=109,
        ),
    ]

    trade = make_trade(
        side=PositionSide.LONG,
        entry_timestamp=1,
        exit_timestamp=3,
        entry_price=100,
        exit_price=109,
    )

    result = TradeAnalyzer().analyze(
        candles,
        [trade],
    )

    item = result.trades[0]

    assert item.candles_held == 3
    assert item.mae_percent == pytest.approx(-3)
    assert item.mfe_percent == pytest.approx(10)
    assert result.average_candles_held == pytest.approx(3)
    assert result.maximum_candles_held == 3


def test_analyzes_short_trade_excursions() -> None:
    candles = [
        make_candle(
            1,
            open_price=100,
            high=102,
            low=96,
            close=98,
        ),
        make_candle(
            2,
            open_price=98,
            high=105,
            low=90,
            close=92,
        ),
        make_candle(
            3,
            open_price=92,
            high=94,
            low=88,
            close=89,
        ),
    ]

    trade = make_trade(
        side=PositionSide.SHORT,
        entry_timestamp=1,
        exit_timestamp=3,
        entry_price=100,
        exit_price=89,
    )

    result = TradeAnalyzer().analyze(
        candles,
        [trade],
    )

    item = result.trades[0]

    assert item.candles_held == 3
    assert item.mae_percent == pytest.approx(-5)
    assert item.mfe_percent == pytest.approx(12)


def test_calculates_summary_for_multiple_trades() -> None:
    candles = [
        make_candle(
            1,
            open_price=100,
            high=105,
            low=95,
            close=102,
        ),
        make_candle(
            2,
            open_price=102,
            high=110,
            low=100,
            close=108,
        ),
        make_candle(
            3,
            open_price=108,
            high=112,
            low=104,
            close=106,
        ),
        make_candle(
            4,
            open_price=106,
            high=108,
            low=90,
            close=92,
        ),
    ]

    trades = [
        make_trade(
            side=PositionSide.LONG,
            entry_timestamp=1,
            exit_timestamp=2,
            entry_price=100,
            exit_price=108,
        ),
        make_trade(
            side=PositionSide.SHORT,
            entry_timestamp=3,
            exit_timestamp=4,
            entry_price=108,
            exit_price=92,
        ),
    ]

    result = TradeAnalyzer().analyze(
        candles,
        trades,
    )

    assert len(result.trades) == 2
    assert result.average_candles_held == pytest.approx(2)
    assert result.maximum_candles_held == 2
    assert result.worst_mae_percent <= 0
    assert result.best_mfe_percent > 0


def test_returns_empty_result_without_trades() -> None:
    result = TradeAnalyzer().analyze(
        candles=[],
        trades=[],
    )

    assert result.trades == ()
    assert result.average_candles_held == pytest.approx(0)
    assert result.maximum_candles_held == 0
    assert result.average_mae_percent == pytest.approx(0)
    assert result.worst_mae_percent == pytest.approx(0)
    assert result.average_mfe_percent == pytest.approx(0)
    assert result.best_mfe_percent == pytest.approx(0)


def test_rejects_missing_entry_timestamp() -> None:
    candles = [
        make_candle(
            1,
            open_price=100,
            high=101,
            low=99,
            close=100,
        )
    ]

    trade = make_trade(
        side=PositionSide.LONG,
        entry_timestamp=10,
        exit_timestamp=10,
        entry_price=100,
        exit_price=100,
    )

    with pytest.raises(
        ValueError,
        match="entry timestamp",
    ):
        TradeAnalyzer().analyze(
            candles,
            [trade],
        )


def test_rejects_duplicate_candle_timestamps() -> None:
    candles = [
        make_candle(
            1,
            open_price=100,
            high=101,
            low=99,
            close=100,
        ),
        make_candle(
            1,
            open_price=100,
            high=102,
            low=98,
            close=101,
        ),
    ]

    trade = make_trade(
        side=PositionSide.LONG,
        entry_timestamp=1,
        exit_timestamp=1,
        entry_price=100,
        exit_price=101,
    )

    with pytest.raises(
        ValueError,
        match="timestamps must be unique",
    ):
        TradeAnalyzer().analyze(
            candles,
            [trade],
        )
