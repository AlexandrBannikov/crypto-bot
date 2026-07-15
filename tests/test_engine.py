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

    assert result.final_balance == pytest.approx(1_000 / 110 * 120)
    assert result.total_profit == pytest.approx(1_000 / 110 * 120 - 1_000)
    assert result.total_return_percent == pytest.approx(100 / 11)
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

    assert result.final_balance == pytest.approx(1_000 / 90 * 80)
    assert result.total_profit == pytest.approx(1_000 / 90 * 80 - 1_000)
    assert result.total_return_percent == pytest.approx(-100 / 9)
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

    assert result.final_balance == pytest.approx(1_000 / 110 * 120)
    assert len(result.trades) == 1
    assert result.trades[0].entry_timestamp == 1
    assert result.trades[0].entry_price == pytest.approx(110)
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
        match="prices must be greater than zero",
    ):
        engine.run(candles, HoldStrategy())



def test_signal_executes_at_next_candle_open():
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    candles = [
        Candle(
            timestamp=0,
            open=100,
            high=105,
            low=95,
            close=100,
            volume=1,
        ),
        Candle(
            timestamp=1,
            open=125,
            high=135,
            low=120,
            close=130,
            volume=1,
        ),
        Candle(
            timestamp=2,
            open=140,
            high=150,
            low=135,
            close=150,
            volume=1,
        ),
    ]

    result = engine.run(
        candles,
        BuyOnlyStrategy(),
    )

    trade = result.trades[0]

    assert trade.entry_timestamp == 1
    assert trade.entry_price == pytest.approx(125)
    assert trade.exit_price == pytest.approx(150)
    assert result.final_balance == pytest.approx(1_200)


def test_engine_calculates_trade_quality_metrics():
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    result = engine.run(
        make_candles(100, 110, 120),
        BuyAndSellStrategy(),
    )

    assert result.gross_profit == pytest.approx(
        result.total_profit
    )
    assert result.gross_loss == pytest.approx(0)
    assert result.profit_factor == float("inf")
    assert result.average_winning_trade_percent == pytest.approx(
        result.trades[0].profit_percent
    )
    assert result.average_losing_trade_percent == pytest.approx(0)
    assert result.payoff_ratio == float("inf")
    assert result.expectancy_percent == pytest.approx(
        result.trades[0].profit_percent
    )


def test_engine_metrics_for_no_trades():
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    result = engine.run(
        make_candles(100, 110, 120),
        HoldStrategy(),
    )

    assert result.gross_profit == pytest.approx(0)
    assert result.gross_loss == pytest.approx(0)
    assert result.profit_factor == pytest.approx(0)
    assert result.average_winning_trade_percent == pytest.approx(0)
    assert result.average_losing_trade_percent == pytest.approx(0)
    assert result.payoff_ratio == pytest.approx(0)
    assert result.expectancy_percent == pytest.approx(0)


from app.trading_types import PositionSide, TradeAction


class ProfitableShortStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return TradeAction.OPEN_SHORT

        if index == 1:
            return TradeAction.CLOSE_SHORT

        return TradeAction.HOLD


class LosingShortStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return TradeAction.OPEN_SHORT

        if index == 1:
            return TradeAction.CLOSE_SHORT

        return TradeAction.HOLD


def test_engine_makes_profitable_short_trade():
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    result = engine.run(
        make_candles(100, 90, 80),
        ProfitableShortStrategy(),
    )

    assert result.final_balance == pytest.approx(
        1_000 + (1_000 / 90) * 10
    )

    assert len(result.trades) == 1
    assert result.trades[0].side == PositionSide.SHORT
    assert result.trades[0].entry_price == pytest.approx(90)
    assert result.trades[0].exit_price == pytest.approx(80)
    assert result.trades[0].profit > 0


def test_engine_makes_losing_short_trade():
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    result = engine.run(
        make_candles(100, 90, 100),
        LosingShortStrategy(),
    )

    assert result.final_balance == pytest.approx(
        1_000 - (1_000 / 90) * 10
    )

    assert len(result.trades) == 1
    assert result.trades[0].side == PositionSide.SHORT
    assert result.trades[0].profit < 0


def test_short_position_is_closed_at_end():
    class OpenShortOnlyStrategy:
        def generate_signal(self, candles, index):
            if index == 0:
                return TradeAction.OPEN_SHORT

            return TradeAction.HOLD

    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    result = engine.run(
        make_candles(100, 90, 80),
        OpenShortOnlyStrategy(),
    )

    assert len(result.trades) == 1
    assert result.trades[0].side == PositionSide.SHORT
    assert result.trades[0].exit_timestamp == 2
    assert result.trades[0].exit_price == pytest.approx(80)


def test_legacy_buy_sell_signals_still_open_long():
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    result = engine.run(
        make_candles(100, 110, 120),
        BuyAndSellStrategy(),
    )

    assert len(result.trades) == 1
    assert result.trades[0].side == PositionSide.LONG


from app.trading_types import PositionSide, TradeAction


class ProfitableShortStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return TradeAction.OPEN_SHORT

        if index == 1:
            return TradeAction.CLOSE_SHORT

        return TradeAction.HOLD


class LosingShortStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return TradeAction.OPEN_SHORT

        if index == 1:
            return TradeAction.CLOSE_SHORT

        return TradeAction.HOLD


def test_engine_makes_profitable_short_trade():
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    result = engine.run(
        make_candles(100, 90, 80),
        ProfitableShortStrategy(),
    )

    assert result.final_balance == pytest.approx(
        1_000 + (1_000 / 90) * 10
    )

    assert len(result.trades) == 1
    assert result.trades[0].side == PositionSide.SHORT
    assert result.trades[0].entry_price == pytest.approx(90)
    assert result.trades[0].exit_price == pytest.approx(80)
    assert result.trades[0].profit > 0


def test_engine_makes_losing_short_trade():
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    result = engine.run(
        make_candles(100, 90, 100),
        LosingShortStrategy(),
    )

    assert result.final_balance == pytest.approx(
        1_000 - (1_000 / 90) * 10
    )

    assert len(result.trades) == 1
    assert result.trades[0].side == PositionSide.SHORT
    assert result.trades[0].profit < 0


def test_short_position_is_closed_at_end():
    class OpenShortOnlyStrategy:
        def generate_signal(self, candles, index):
            if index == 0:
                return TradeAction.OPEN_SHORT

            return TradeAction.HOLD

    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    result = engine.run(
        make_candles(100, 90, 80),
        OpenShortOnlyStrategy(),
    )

    assert len(result.trades) == 1
    assert result.trades[0].side == PositionSide.SHORT
    assert result.trades[0].exit_timestamp == 2
    assert result.trades[0].exit_price == pytest.approx(80)


def test_legacy_buy_sell_signals_still_open_long():
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    )

    result = engine.run(
        make_candles(100, 110, 120),
        BuyAndSellStrategy(),
    )

    assert len(result.trades) == 1
    assert result.trades[0].side == PositionSide.LONG
