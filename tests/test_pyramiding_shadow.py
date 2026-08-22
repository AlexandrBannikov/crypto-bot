from dataclasses import replace
from decimal import Decimal
import json

from app.candle import Candle
from app.pyramiding_shadow import (
    PyramidingShadowJournal, PyramidingShadowState, PyramidingShadowStateStore,
    aggregate_pyramiding_statistics, observe_pyramiding_shadow,
    reconcile_pyramiding_shadow,
)
from app.trading_controller import TradingControllerState


D = Decimal


def flat(): return TradingControllerState()
def position(price="100", qty="0.01", balance="1000"):
    return TradingControllerState(position_quantity=D(qty), entry_price=D(price),
        stop_loss=D(price) * D("0.98"), virtual_balance=D(balance),
        entry_fee=D(price) * D(qty) * D("0.001"), opened_at="2026-08-17T03:00:04+00:00")
def candle(ts, close, low=None, high=None):
    close = float(close)
    return Candle(ts, close, float(high if high is not None else close),
                  float(low if low is not None else close), close)
def score(total=80, trend=1, ema=1, adx=1):
    return {"score_total": total, "components": {"trend_score": trend,
        "ema_alignment_score": ema, "adx_score": adx}}
def opened():
    return observe_pyramiding_shadow(PyramidingShadowState(), candle=candle(0, 100),
        production_before=flat(), production_after=position(), score=score(20)).state
def step(state, ts=3600, close=110, scored=None, before=None, after=None, equity=None):
    return observe_pyramiding_shadow(state, candle=candle(ts, close, close-2, close+2),
        production_before=before or position(), production_after=after or position(),
        score=scored if scored is not None else score(), available_equity=equity).observation, \
        observe_pyramiding_shadow(state, candle=candle(ts, close, close-2, close+2),
        production_before=before or position(), production_after=after or position(),
        score=scored if scored is not None else score(), available_equity=equity).state


def test_no_production_long_and_no_averaging_down():
    observation = observe_pyramiding_shadow(PyramidingShadowState(), candle=candle(3600, 110),
        production_before=flat(), production_after=flat(), score=score()).observation
    assert observation["variants"] == ()
    row, _ = step(opened(), close=99)
    assert {v["decision_reason"] for v in row["variants"]} == {"position_not_profitable"}


def test_thresholds_and_confirmation_gates_are_independent():
    row, state = step(opened(), scored=score(67))
    assert [v["add_count"] for v in row["variants"]] == [0, 0, 0]
    assert [v["decision_reason"] for v in row["variants"]] == ["add_pending", "score_below_threshold", "score_below_threshold"]
    row, state = step(state, ts=7200, close=111, scored=score(20))
    assert [v["add_count"] for v in row["variants"]] == [1, 0, 0]
    for name, kwargs in (("trend_not_confirmed", {"trend": 0}),
                         ("ema_alignment_not_confirmed", {"ema": 0}),
                         ("adx_not_confirmed", {"adx": 0})):
        row, _ = step(opened(), scored=score(80, **kwargs))
        assert {v["decision_reason"] for v in row["variants"]} == {name}


def test_threshold_70_and_75():
    _, state70 = step(opened(), scored=score(70))
    row70, _ = step(state70, ts=7200, close=111, scored=score(20))
    _, state75 = step(opened(), scored=score(75))
    row75, _ = step(state75, ts=7200, close=111, scored=score(20))
    assert [v["add_count"] for v in row70["variants"]] == [1, 1, 0]
    assert [v["add_count"] for v in row75["variants"]] == [1, 1, 1]


def test_cooldown_three_closed_candles_max_three_and_weighted_average():
    state = opened()
    _, state = step(state, 3600, 110)
    _, state = step(state, 7200, 110, scored=score(20))
    first = state.variants[0]
    assert first.weighted_average_entry == D("105")
    for ts in (10800, 14400):
        row, state = step(state, ts, 120)
        assert row["variants"][0]["decision_reason"] == "cooldown"
    _, state = step(state, 18000, 120)
    _, state = step(state, 21600, 120, scored=score(20))
    _, state = step(state, 32400, 130)
    _, state = step(state, 36000, 130, scored=score(20))
    row, state = step(state, 46800, 140)
    row, state = step(state, 50400, 140, scored=score(20))
    assert len(state.variants[0].add_ons) == 3
    assert row["variants"][0]["decision_reason"] == "maximum_add_ons"


def test_fees_capital_exit_accounting_and_excursions():
    row, state = step(opened(), close=110, equity=D("2"))
    assert {v["decision_reason"] for v in row["variants"]} == {"insufficient_capital"}
    _, state = step(opened(), close=110)
    _, state = step(state, ts=7200, close=110, scored=score(20))
    closed = observe_pyramiding_shadow(state, candle=candle(10800, 120, 90, 130),
        production_before=position(), production_after=flat(), score=score(),
        production_net_pnl=D("0.1")).observation
    item = closed["variants"][0]
    assert item["add_count"] == 1
    assert item["total_entry_fees"] == D("0.0021")
    assert item["exit_fee"] == D("0.00240")
    assert item["net_pnl"] == D("0.29550")
    assert item["delta_pnl_vs_production"] == D("0.19550")
    assert item["mae"] < 0 < item["mfe"]
    assert item["peak_exposure_pct"] == D("0.2600")


def test_restart_reconciliation_already_open_idempotency_and_no_future_score(tmp_path):
    candles = [candle(0, 100), candle(3600, 110), candle(7200, 120)]
    scores = [{"candle_timestamp": 3600, **score(80)},
              {"candle_timestamp": 7200, **score(20)},
              {"candle_timestamp": 10800, **score(99)}]
    restored_position = replace(position(), opened_at="1970-01-01T01:00:04+00:00")
    rebuilt = reconcile_pyramiding_shadow(PyramidingShadowState(), production=restored_position,
        candles=candles, score_rows=scores)
    assert [len(v.add_ons) for v in rebuilt.variants] == [1, 1, 1]
    assert reconcile_pyramiding_shadow(rebuilt, production=restored_position, candles=candles,
        score_rows=scores) == rebuilt
    store = PyramidingShadowStateStore(tmp_path / "state.json")
    store.save(rebuilt)
    assert store.load() == rebuilt
    journal = PyramidingShadowJournal(tmp_path / "shadow.jsonl")
    observation, _ = step(rebuilt, 10800, 130)
    assert journal.append(observation)
    assert not journal.append(observation)


def test_journal_and_aggregate_do_not_touch_production_journal(tmp_path):
    production = tmp_path / "production.jsonl"
    production.write_text('{"keep":true}\n')
    row, state = step(opened(), close=110)
    _, state = step(state, ts=7200, close=110, scored=score(20))
    closed = observe_pyramiding_shadow(state, candle=candle(10800, 120),
        production_before=position(), production_after=flat(), score=score(),
        production_net_pnl=D("0.1")).observation
    path = tmp_path / "pyramiding.jsonl"
    PyramidingShadowJournal(path).append(closed)
    stats = aggregate_pyramiding_statistics([json.loads(path.read_text())])
    assert stats["65"]["positions_observed"] == 1
    assert stats["65"]["positions_with_add_ons"] == 1
    assert production.read_text() == '{"keep":true}\n'


def test_known_1902_52_position_causal_regression_fixture():
    """Static research fixture; it never opens or writes a production journal."""
    prices = [
        (1787166000, "2101.99", "70.64918508788868"),
        (1787169600, "2218.15", "75.21827324954899"),
        (1787173200, "2286.38", "78.315641"),
        (1787176800, "2250.16", "67.962339118884"),
        (1787180400, "2252.64", "74.31661689097673"),
        (1787184000, "2262.69", "77.87065644009385"),
        (1787187600, "2266.63", "75.37108380426531"),
        (1787191200, "2252.06", "68.772339"),
        (1787194800, "2251.54", "73.50255576917131"),
        (1787198400, "2250.43", "73.546313"),
        (1787202000, "2248.65", "73.486217"),
        (1787205600, "2262.60", "79.34192365718626"),
    ]
    production = position("1902.52")
    state = observe_pyramiding_shadow(PyramidingShadowState(),
        candle=candle(1786932000, "1902.52"), production_before=flat(),
        production_after=production, score=score(20)).state
    for ts, close, total in prices:
        _, state = step(state, ts, D(close), scored=score(D(total)),
                        before=production, after=production, equity=D("1000"))
    assert [len(v.add_ons) for v in state.variants] == [3, 3, 2]
    assert state.variants[2].pending_add_signal_timestamp == 1787205600
    assert all(
        add.candle_timestamp > add.signal_timestamp
        for variant in state.variants for add in variant.add_ons
    )
    assert [v.quantity for v in state.variants] == [D("0.04"), D("0.04"), D("0.03")]


def test_missing_score_is_pending_without_advancing_state():
    state = opened()
    update = observe_pyramiding_shadow(
        state, candle=candle(3600, 110), production_before=position(),
        production_after=position(), score=None,
    )
    assert update.state == state
    assert update.observation["processing_status"] == "PENDING"
    assert update.observation["appended"] is False


def test_initial_and_total_notional_caps_are_explicit():
    large = position("100", qty="2")
    state = observe_pyramiding_shadow(
        PyramidingShadowState(), candle=candle(0, 100),
        production_before=flat(), production_after=large, score=score(20),
    ).state
    assert {item.initial_notional for item in state.variants} == {D("100.00")}
    assert {item.quantity for item in state.variants} == {D("1.00")}
    # No variant may schedule an add that would cross 15% of the 1000 account.
    row, _ = step(state, 3600, 6000, scored=score(99), before=large, after=large)
    assert {item["decision_reason"] for item in row["variants"]} == {"insufficient_capital"}
