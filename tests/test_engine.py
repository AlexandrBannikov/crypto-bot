import pytest

from app.risk import RiskConfig
from app.engine import BacktestEngine, Candle, TradeSignal, Signal


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



class LongWithStopStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return TradeSignal(
                action=TradeAction.OPEN_LONG,
                stop_loss=95.0,
            )

        return TradeAction.HOLD


class ShortWithStopStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return TradeSignal(
                action=TradeAction.OPEN_SHORT,
                stop_loss=105.0,
            )

        return TradeAction.HOLD


class InvalidLongStopStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return TradeSignal(
                action=TradeAction.OPEN_LONG,
                stop_loss=105.0,
            )

        return TradeAction.HOLD


def test_long_stop_loss_is_triggered_inside_candle() -> None:
    candles = [
        Candle(1, 100, 101, 99, 100, 1),
        Candle(2, 100, 104, 94, 102, 1),
        Candle(3, 102, 103, 101, 102, 1),
    ]

    result = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    ).run(
        candles,
        LongWithStopStrategy(),
    )

    assert len(result.trades) == 1
    assert result.trades[0].side == PositionSide.LONG
    assert result.trades[0].exit_timestamp == 2
    assert result.trades[0].exit_price == pytest.approx(95)


def test_long_stop_uses_open_price_after_gap() -> None:
    candles = [
        Candle(1, 100, 101, 99, 100, 1),
        Candle(2, 90, 94, 88, 92, 1),
    ]

    result = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    ).run(
        candles,
        LongWithStopStrategy(),
    )

    assert result.trades[0].exit_price == pytest.approx(90)


def test_short_stop_loss_is_triggered_inside_candle() -> None:
    candles = [
        Candle(1, 100, 101, 99, 100, 1),
        Candle(2, 100, 106, 96, 98, 1),
        Candle(3, 98, 99, 97, 98, 1),
    ]

    result = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    ).run(
        candles,
        ShortWithStopStrategy(),
    )

    assert len(result.trades) == 1
    assert result.trades[0].side == PositionSide.SHORT
    assert result.trades[0].exit_timestamp == 2
    assert result.trades[0].exit_price == pytest.approx(105)


def test_rejects_long_stop_above_entry_price() -> None:
    candles = [
        Candle(1, 100, 101, 99, 100, 1),
        Candle(2, 100, 102, 98, 101, 1),
    ]

    with pytest.raises(
        ValueError,
        match="long stop_loss",
    ):
        BacktestEngine(
            initial_balance=1_000,
            commission_rate=0,
        ).run(
            candles,
            InvalidLongStopStrategy(),
        )


class RiskSizedLongStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return TradeSignal(
                action=TradeAction.OPEN_LONG,
                stop_loss=98.0,
            )

        return TradeAction.HOLD


class RiskSizedShortStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return TradeSignal(
                action=TradeAction.OPEN_SHORT,
                stop_loss=102.0,
            )

        return TradeAction.HOLD


def test_engine_sizes_long_position_by_risk() -> None:
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
        risk_config=RiskConfig(
            risk_per_trade=0.01,
        ),
    )

    result = engine.run(
        make_candles(100, 100, 110),
        RiskSizedLongStrategy(),
    )

    trade = result.trades[0]

    # Риск 10 USDT, расстояние до стопа 2%.
    # Размер позиции: 10 / 0.02 = 500 USDT.
    assert trade.quantity == pytest.approx(5)
    assert trade.profit == pytest.approx(50)
    assert result.final_balance == pytest.approx(1_050)


def test_engine_sizes_short_position_by_risk() -> None:
    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
        risk_config=RiskConfig(
            risk_per_trade=0.01,
        ),
    )

    result = engine.run(
        make_candles(100, 100, 90),
        RiskSizedShortStrategy(),
    )

    trade = result.trades[0]

    assert trade.quantity == pytest.approx(5)
    assert trade.profit == pytest.approx(50)
    assert result.final_balance == pytest.approx(1_050)


class LongTrailingStopStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return TradeSignal(
                action=TradeAction.OPEN_LONG,
                stop_loss=95.0,
                trailing_stop_percent=0.05,
            )

        return TradeAction.HOLD


class ShortTrailingStopStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return TradeSignal(
                action=TradeAction.OPEN_SHORT,
                stop_loss=105.0,
                trailing_stop_percent=0.05,
            )

        return TradeAction.HOLD


def test_rejects_trailing_stop_without_initial_stop() -> None:
    with pytest.raises(
        ValueError,
        match="stop_loss is required",
    ):
        TradeSignal(
            action=TradeAction.OPEN_LONG,
            trailing_stop_percent=0.05,
        )


@pytest.mark.parametrize(
    "trailing_stop_percent",
    [0, -0.01, 1, 1.1],
)
def test_rejects_invalid_trailing_stop_percent(
    trailing_stop_percent: float,
) -> None:
    with pytest.raises(
        ValueError,
        match="trailing_stop_percent",
    ):
        TradeSignal(
            action=TradeAction.OPEN_LONG,
            stop_loss=95,
            trailing_stop_percent=trailing_stop_percent,
        )


def test_long_trailing_stop_protects_profit() -> None:
    candles = [
        Candle(1, 100, 101, 99, 100, 1),
        Candle(2, 100, 111, 99, 110, 1),
        Candle(3, 108, 109, 104, 105, 1),
    ]

    result = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    ).run(
        candles,
        LongTrailingStopStrategy(),
    )

    trade = result.trades[0]

    # После закрытия свечи по 110 стоп становится:
    # 110 * 0.95 = 104.5.
    assert trade.entry_price == pytest.approx(100)
    assert trade.exit_price == pytest.approx(104.5)
    assert trade.quantity == pytest.approx(2)
    assert trade.profit == pytest.approx(9)
    assert result.final_balance == pytest.approx(1_009)


def test_short_trailing_stop_protects_profit() -> None:
    candles = [
        Candle(1, 100, 101, 99, 100, 1),
        Candle(2, 100, 101, 89, 90, 1),
        Candle(3, 92, 95, 91, 94, 1),
    ]

    result = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0,
    ).run(
        candles,
        ShortTrailingStopStrategy(),
    )

    trade = result.trades[0]

    # После закрытия свечи по 90 стоп становится:
    # 90 * 1.05 = 94.5.
    assert trade.entry_price == pytest.approx(100)
    assert trade.exit_price == pytest.approx(94.5)
    assert trade.quantity == pytest.approx(2)
    assert trade.profit == pytest.approx(11)
    assert result.final_balance == pytest.approx(1_011)


def test_long_trailing_stop_never_moves_down() -> None:
    assert BacktestEngine._trail_stop(
        side=PositionSide.LONG,
        current_stop=105,
        close_price=100,
        trailing_stop_percent=0.05,
    ) == pytest.approx(105)


def test_short_trailing_stop_never_moves_up() -> None:
    assert BacktestEngine._trail_stop(
        side=PositionSide.SHORT,
        current_stop=95,
        close_price=100,
        trailing_stop_percent=0.05,
    ) == pytest.approx(95)


def test_rejects_break_even_without_stop_loss() -> None:
    with pytest.raises(
        ValueError,
        match="stop_loss is required",
    ):
        TradeSignal(
            action=TradeAction.OPEN_LONG,
            break_even_r_multiple=1.0,
        )


@pytest.mark.parametrize(
    "break_even_r_multiple",
    [0, -1],
)
def test_rejects_invalid_break_even(
    break_even_r_multiple,
) -> None:
    with pytest.raises(
        ValueError,
        match="break_even_r_multiple",
    ):
        TradeSignal(
            action=TradeAction.OPEN_LONG,
            stop_loss=95,
            break_even_r_multiple=break_even_r_multiple,
        )


def test_accepts_break_even_configuration() -> None:
    signal = TradeSignal(
        action=TradeAction.OPEN_LONG,
        stop_loss=95,
        break_even_r_multiple=1.5,
    )

    assert signal.break_even_r_multiple == pytest.approx(1.5)


def test_trade_default_exit_reason_is_signal() -> None:
    from app.engine import Trade
    from app.trading_types import ExitReason

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
    )

    assert trade.exit_reason == ExitReason.SIGNAL
