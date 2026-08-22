from decimal import Decimal as D
import json

import pytest

from app.candle import Candle
from app.strategy_v2_shadow import (
    MAX_QUANTITY, StrategyV2Journal, StrategyV2State, StrategyV2StateStore,
    comparison, process_candle,
)
from app.telegram_notifications import TelegramPaths, _strategy_v2_report_block


def candle(n, close, *, low=None, high=None):
    return Candle(n * 3600, float(close), float(high if high is not None else close),
                  float(low if low is not None else close), float(close))


def score(value=70, decision="ENTER_LONG", trend=1, ema=1, adx=1):
    return {"decision": decision, "score_total": value, "components": {
        "trend_score": trend, "ema_alignment_score": ema, "adx_score": adx}}


def step(state, n, close, scored=None, **prices):
    return process_candle(state, candle=candle(n, close, **prices), score=scored)[0]


def opened(price=100):
    state, row = process_candle(StrategyV2State(), candle=candle(1, price), score=score(65))
    assert row["event"] == "entry"
    return state


@pytest.mark.parametrize("scored", [score(64), score(70, "HOLD"), score(70, trend=0), None])
def test_flat_requires_enter_long_score65_and_positive_components(scored):
    state, row = process_candle(StrategyV2State(), candle=candle(1, 100), score=scored)
    assert not state.is_long
    assert row["event"] == "hold"


def test_valid_entry_fees_cash_equity_and_no_duplicate():
    state = opened()
    assert state.quantity == D("0.01")
    assert state.cash == D("998.99900")
    assert state.entry_fees == state.fees == D("0.00100")
    assert state.equity == D("999.99900")
    same, row = process_candle(state, candle=candle(1, 999), score=score())
    assert same.quantity == D("0.01") and row["event"] == "already_processed"


def test_add_requires_score_profit_cooldown_and_no_averaging_down():
    state = opened()
    state = step(state, 2, 99, score())
    assert state.add_count == 0
    state = step(state, 3, 101, score())
    assert state.add_count == 0
    state = step(state, 4, 101, score(69))
    assert state.add_count == 0
    state = step(state, 5, 101, score(70))
    assert state.add_count == 1 and state.quantity == D("0.02")
    assert state.weighted_average_entry == D("100.5")


def test_max_three_adds_and_max_exposure():
    state = opened()
    for n, price in ((4, 110), (7, 120), (10, 130), (13, 140)):
        state = step(state, n, price, score())
    assert state.add_count == 3
    assert state.quantity == MAX_QUANTITY
    assert D(state.current_trade["max_exposure"]) == state.cost_basis


def test_hard_stop_exit_accounting_and_diagnostics():
    state = opened()
    state, row = process_candle(state, candle=candle(2, 99, low=97), score=score(20, "HOLD"))
    trade = row["closed_trade"]
    assert row["reason"] == "hard_stop" and D(trade["exit_price"]) == D("98")
    assert state.closed_trades == 1 and state.quantity == 0
    assert state.cash == state.equity == D("999.9780200")
    for key in ("initial_entry", "add_ons", "weighted_average_progression", "final_quantity",
                "exit_reason", "fees", "net_pnl", "return_pct", "mfe", "mae",
                "max_exposure", "hold_seconds"):
        assert key in trade


def test_profit_floor_fee_aware_activation_and_next_candle_trigger():
    state = opened()
    state, row = process_candle(state, candle=candle(2, 100.4, low=99, high=100.6), score=None)
    expected = D("100") * D("1.001") / D("0.999") * D("1.001")
    assert state.profit_floor == expected
    assert state.is_long  # new floor did not inspect this candle's low
    state, row = process_candle(state, candle=candle(3, 101, low=expected), score=None)
    assert row["reason"] == "protective_floor"


def test_trailing_effective_floor_peak_and_floor_are_monotonic():
    state = opened()
    state = step(state, 2, 105, None, low=100, high=106)
    assert state.trailing_active and state.trailing_floor == D("100.7")
    first_peak, first_floor = state.peak, state.effective_floor
    state = step(state, 3, 104, None, low=102, high=105)
    assert state.peak == first_peak and state.effective_floor == first_floor


def test_peak_candle_floor_is_only_active_next_candle():
    state = opened()
    state, row = process_candle(state, candle=candle(2, 104, low=99, high=106), score=None)
    assert state.is_long and row["event"] == "hold"
    state, row = process_candle(state, candle=candle(3, 101, low=100), score=None)
    assert row["reason"] == "protective_floor"


def test_ema_reversal_exits_at_close():
    state = opened()
    state, row = process_candle(state, candle=candle(2, 101), score=None, bearish_ema_cross=True)
    assert row["reason"] == "ema_reversal" and row["closed_trade"]["exit_price"] == "101.0"


def test_add_candle_cannot_trigger_recalculated_floor():
    state = opened()
    state.profit_active = True
    state.profit_floor = state.effective_floor = D("99")
    state, row = process_candle(state, candle=candle(4, 110, low=99.5, high=111), score=score())
    assert row["event"] == "add" and state.is_long
    assert state.effective_floor > D("99.5")


def test_restart_idempotent_and_journal_isolated(tmp_path):
    state = opened()
    path, journal_path = tmp_path / "strategy.json", tmp_path / "strategy.jsonl"
    StrategyV2StateStore(path).save(state)
    restored = StrategyV2StateStore(path).load()
    assert restored == state
    journal = StrategyV2Journal(journal_path)
    row = {"candle_timestamp": 1, "event": "entry"}
    assert journal.append(row) and not journal.append(row)
    assert len(journal_path.read_text().splitlines()) == 1
    assert not (tmp_path / "controller_trade_journal.jsonl").exists()


def test_comparison_and_telegram_format(tmp_path):
    state = opened()
    result = comparison(state, production_equity=D("990"), production_realised_pnl=D("-10"))
    assert result["delta"]["equity"] == state.equity - D("990")
    paths = TelegramPaths(*(tmp_path / name for name in ("controller", "runtime", "last", "trades", "decisions", "notify")), strategy_v2_shadow_state=tmp_path / "v2.json")
    StrategyV2StateStore(paths.strategy_v2_shadow_state).save(state)
    paths.controller_state.write_text(json.dumps({"virtual_balance": "1000"}))
    text = _strategy_v2_report_block(paths)
    assert "🧪 Strategy V2 Shadow" in text and "vs Production:" in text and "Adds: 0/3" in text


def test_known_strong_trade_regression_is_independent_and_causal():
    state = StrategyV2State()
    # Production's historical 1902.52 region is deliberately only a benchmark:
    # V2 must stay flat when its scored decision was HOLD.
    state = step(state, 1, D("1902.52"), score(32, "HOLD"), low=1880, high=1920)
    assert not state.is_long
    state = step(state, 2, D("2050"), score(65), low=2000, high=2070)
    assert state.last_entry_timestamp == 7200
    for n, price in ((5, D("2150")), (8, D("2300")), (11, D("2450")), (14, D("2520"))):
        state = step(state, n, price, score(75), low=price - 5, high=price + 10)
    assert state.add_count == 3 and state.quantity == D("0.04")
    assert len(state.current_trade["weighted_average_progression"]) == 4
