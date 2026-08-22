from decimal import Decimal

from app.candle import Candle
from app.parity_harness import run_live_replay_parity
from app.strategies import Signal


HOUR = 3600


def market() -> tuple[Candle, ...]:
    return tuple(
        Candle(i * HOUR, 100 + i, 101 + i, 99 + i, 100.5 + i, 1)
        for i in range(8)
    )


def test_live_like_and_replay_have_identical_causal_ledgers() -> None:
    candles = market()

    def signals(history):
        timestamp = history[-1].timestamp
        signal = (
            Signal.BUY if timestamp == 2 * HOUR
            else Signal.SELL if timestamp == 5 * HOUR
            else Signal.HOLD
        )
        return signal, 1.0, 2.0

    result = run_live_replay_parity(
        candles, initial_cursor=HOUR, signal_function=signals,
    )
    result.assert_identical()
    assert result.identical
    assert result.replay.fills == (
        (3 * HOUR, "open_long", "filled", "0.01", "103"),
        (6 * HOUR, "close_long", "filled", "0.01", "106"),
    )
    assert len(result.replay.trades) == 1
    assert {
        key: result.replay.trades[0][key]
        for key in (
            "strategy_logic_version", "feature_version",
            "execution_policy_version", "ledger_schema_version",
        )
    } == {
        "strategy_logic_version": "strategy_logic_v2_causal",
        "feature_version": "scored_features_v1",
        "execution_policy_version": "next_candle_open_v1",
        "ledger_schema_version": "ledger_v2",
    }
    assert result.replay.fees == Decimal("0.00209")
    assert result.replay.cash == result.replay.equity
