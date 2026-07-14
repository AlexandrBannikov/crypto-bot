import pytest

from app.engine import BacktestEngine, Candle, Signal


class BuyAndSellStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return Signal.BUY

        if index == len(candles) - 1:
            return Signal.SELL

        return Signal.HOLD


class BuyOnlyStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return Signal.BUY

        return Signal.HOLD


class HoldStrategy:
    def generate_signal(self, candles, index):
        return Signal.HOLD


def make_candles(*prices: float) -> list[Candle]:
    return [
        Candle(
            timestamp=index,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1.0,
        )
        for index, price in enumerate(prices)
    ]


def test_engine_makes_profitable_trade():
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    result = engine.run(
        make_candles(100, 110, 120),
        BuyAndSellStrategy(),
    )

    assert result.final_balance == pytest.approx(1_200)
    assert result.total_profit == pytest.approx(200)
    assert result.total_return_percent == pytest.approx(20)
    assert len(result.trades) == 1
    assert result.winning_trades == 1
    assert result.losing_trades == 0
    assert result.win_rate_percent == pytest.approx(100)


def test_engine_makes_losing_trade():
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    result = engine.run(
        make_candles(100, 90, 80),
        BuyAndSellStrategy(),
    )

    assert result.final_balance == pytest.approx(800)
    assert result.total_profit == pytest.approx(-200)
    assert result.total_return_percent == pytest.approx(-20)
    assert result.winning_trades == 0
    assert result.losing_trades == 1
    assert result.win_rate_percent == pytest.approx(0)


def test_engine_accounts_for_commission():
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0.001,
    )

    result = engine.run(
        make_candles(100, 100),
        BuyAndSellStrategy(),
    )

    expected_quantity = 999 / 100
    expected_exit_value = expected_quantity * 100
    expected_exit_fee = expected_exit_value * 0.001
    expected_final_balance = expected_exit_value - expected_exit_fee

    assert result.final_balance == pytest.approx(
        expected_final_balance
    )
    assert result.total_profit < 0
    assert result.trades[0].entry_fee == pytest.approx(1)
    assert result.trades[0].exit_fee == pytest.approx(
        expected_exit_fee
    )


def test_engine_closes_open_position_on_last_candle():
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    result = engine.run(
        make_candles(100, 110, 120),
        BuyOnlyStrategy(),
    )

    assert result.final_balance == pytest.approx(1_200)
    assert len(result.trades) == 1
    assert result.trades[0].exit_timestamp == 2


def test_hold_strategy_makes_no_trades():
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    result = engine.run(
        make_candles(100, 110, 90),
        HoldStrategy(),
    )

    assert result.final_balance == pytest.approx(1_000)
    assert result.total_profit == pytest.approx(0)
    assert result.trades == ()
    assert result.win_rate_percent == pytest.approx(0)


def test_engine_calculates_drawdown():
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    result = engine.run(
        make_candles(100, 120, 90, 110),
        BuyOnlyStrategy(),
    )

    assert result.max_drawdown_percent == pytest.approx(25)


def test_engine_rejects_empty_candles():
    engine = BacktestEngine()

    with pytest.raises(
        ValueError,
        match="candles must not be empty",
    ):
        engine.run([], HoldStrategy())


@pytest.mark.parametrize(
    ("initial_balance", "commission_rate"),
    [
        (0, 0.001),
        (-100, 0.001),
        (1_000, -0.001),
        (1_000, 1),
    ],
)
def test_engine_rejects_invalid_configuration(
    initial_balance,
    commission_rate,
):
    with pytest.raises(ValueError):
        BacktestEngine(
            initial_balance=initial_balance,
            commission_rate=commission_rate,
        )


def test_engine_rejects_invalid_close_price():
    engine = BacktestEngine()

    candles = [
        Candle(
            timestamp=1,
            open=0,
            high=0,
            low=0,
            close=0,
            volume=0,
        )
    ]

    with pytest.raises(
        ValueError,
        match="close price",
    ):
        engine.run(candles, HoldStrategy())

