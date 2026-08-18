from decimal import Decimal
import json
from types import SimpleNamespace

from app.candle import Candle
from app.profit_lock_shadow import (
    ProfitLockShadowJournal, ProfitLockShadowState, ProfitLockShadowStateStore,
    aggregate_profit_lock_statistics, observe_profit_lock_shadow,
    reconcile_profit_lock_shadow,
)
from app.telegram_notifications import _profit_lock_shadow_report_block
from app.trading_controller import TradingControllerState
from scripts.run_bybit_controller import run_profit_lock_shadow_observer


D = Decimal


def candle(ts, high, low, close=100):
    return Candle(ts, close, high, low, close, 1)


def flat():
    return TradingControllerState()


def position(entry="100", quantity="2", opened_at="1970-01-01T01:00:00+00:00"):
    return TradingControllerState(
        position_quantity=D(quantity), entry_price=D(entry),
        stop_loss=D(entry) * D(".98"), opened_at=opened_at,
    )


def entered(production=None):
    production = production or position()
    return observe_profit_lock_shadow(
        ProfitLockShadowState(), candle=candle(0, 110, 90),
        production_before=flat(), production_after=production,
    ).state


def advance(state, ts, high, low, production=None):
    production = production or position()
    return observe_profit_lock_shadow(
        state, candle=candle(ts, high, low), production_before=production,
        production_after=production,
    ).state


def test_eight_variants_and_inactive_before_half_percent():
    state = advance(entered(), 3600, D("100.49"), 99)
    assert len(state.variants) == 8
    assert {v.status for v in state.variants} == {"inactive"}
    assert [v.buffer for v in state.variants[:4]] == [D("0")] * 4
    assert [v.buffer for v in state.variants[4:]] == [D(".001")] * 4


def test_activation_is_causal_and_low_cannot_trigger_same_candle():
    state = advance(entered(), 3600, D("100.5"), D("90"))
    assert {v.status for v in state.variants} == {"locked"}
    assert {v.activated_at_candle for v in state.variants} == {3600}
    assert all(v.triggered_at_candle is None for v in state.variants)
    triggered = advance(state, 7200, 100, 90)
    assert {v.status for v in triggered.variants} == {"triggered"}


def test_effective_floor_is_max_and_all_floors_are_monotonic():
    first = advance(entered(), 3600, 105, 104)
    second = advance(first, 7200, 110, 109)
    third = advance(second, 10800, 108, 107.9)
    for a, b, c in zip(first.variants, second.variants, third.variants):
        assert a.effective_floor == max(a.trailing_floor, a.profit_lock_floor)
        assert a.trailing_floor <= b.trailing_floor == c.trailing_floor
        assert a.profit_lock_floor == b.profit_lock_floor == c.profit_lock_floor
        assert a.effective_floor <= b.effective_floor == c.effective_floor
        assert a.effective_floor >= a.profit_lock_floor


def test_buffered_variant_is_never_below_be_variant():
    state = advance(entered(), 3600, D("100.5"), 100)
    for be, buffered in zip(state.variants[:4], state.variants[4:]):
        assert buffered.profit_lock_floor == be.profit_lock_floor * D("1.001")
        assert buffered.effective_floor >= be.effective_floor


def test_known_1902_52_regression_exact_accounting():
    production = position("1902.52", ".01", "2026-08-17T03:00:04.640377+00:00")
    state = entered(production)
    active = advance(state, 1786946400, D("1912.74"), D("1898.00"), production)
    be = D("1902.52") * D("1.001") / D(".999")
    assert active.fee_aware_be == be
    assert active.variants[0].effective_floor == be
    assert active.variants[4].effective_floor == be * D("1.001")
    triggered = advance(active, 1786950000, D("1908.08"), D("1900.69"), production)
    assert all(v.status == "triggered" for v in triggered.variants)
    assert triggered.variants[0].hypothetical_net_pnl == 0
    buffered = triggered.variants[4]
    expected = (
        (buffered.effective_floor - D("1902.52")) * D(".01")
        - D("1902.52") * D(".01") * D(".001")
        - buffered.effective_floor * D(".01") * D(".001")
    )
    assert buffered.hypothetical_net_pnl == expected
    assert expected == D("0.01904422520000000000000000302")


def test_new_peak_floor_only_applies_to_following_candle():
    active = advance(entered(), 3600, 105, 104)
    # Existing 2%+BE floor is fee-aware BE (~100.20). New trailing floor is 107.8.
    update = advance(active, 7200, 110, 103)
    assert update.variants[3].status == "locked"
    assert update.variants[3].effective_floor == D("107.80")
    assert advance(update, 10800, 109, 107).variants[3].status == "triggered"


def test_production_exit_before_lock_and_trigger_before_exit():
    inactive = advance(entered(), 3600, D("100.4"), 99)
    early = observe_profit_lock_shadow(
        inactive, candle=candle(7200, 99, 98), production_before=position(),
        production_after=flat(), production_net_pnl=D("-4"),
    )
    assert all(v["effect"] == "no_effect" and v["delta_usdt"] == 0 for v in early.observation.variants)
    active = advance(entered(), 3600, 105, 104)
    triggered = advance(active, 7200, 104, 100)
    assert any(v.status == "triggered" for v in triggered.variants)
    assert position().has_open_position


def test_exit_classifications_and_commissions():
    triggered = advance(advance(entered(), 3600, 105, 104), 7200, 104, 100)
    hypothetical = triggered.variants[0].hypothetical_net_pnl
    cases = (
        (D("-5"), "saved_loss"),
        (D("5"), "protected_profit"),
        (D("10"), "worsened_winner"),
    )
    for production_pnl, effect in cases:
        closed = observe_profit_lock_shadow(
            triggered, candle=candle(10800, 99, 90), production_before=position(),
            production_after=flat(), production_net_pnl=production_pnl,
        )
        item = closed.observation.variants[0]
        assert item["effect"] == effect
        assert item["delta_usdt"] == hypothetical - production_pnl
        assert item["hypothetical_entry_fee"] == D(".2")
        assert item["hypothetical_exit_fee"] > 0
    equal = observe_profit_lock_shadow(
        triggered, candle=candle(10800, 99, 90), production_before=position(),
        production_after=flat(), production_net_pnl=hypothetical,
    )
    assert equal.observation.variants[0]["effect"] == "no_effect"


def test_restart_reconciliation_identity_idempotency_and_journal_isolation(tmp_path):
    candles = (candle(3600, 100.4, 99), candle(7200, 105, 104), candle(10800, 104, 100))
    restored = reconcile_profit_lock_shadow(
        ProfitLockShadowState(), production=position(), candles=candles,
    )
    assert all(v.status == "triggered" for v in restored.variants)
    state_path = tmp_path / "state.json"
    ProfitLockShadowStateStore(state_path).save(restored)
    assert ProfitLockShadowStateStore(state_path).load() == restored
    assert reconcile_profit_lock_shadow(restored, production=position(), candles=candles) == restored

    other = position(opened_at="1970-01-01T02:00:00+00:00")
    replaced = reconcile_profit_lock_shadow(restored, production=other, candles=candles)
    assert replaced.opened_at == other.opened_at

    journal_path = tmp_path / "profit-lock.jsonl"
    production_journal = tmp_path / "production.jsonl"
    production_journal.write_text('{"production":true}\n')
    for _ in range(2):
        assert run_profit_lock_shadow_observer(
            candle=candles[-1], production_before=position(), production_after=position(),
            production_exit_pnl=None, historical_candles=candles,
            state_path=state_path, journal_path=journal_path,
        )
    assert len(journal_path.read_text().splitlines()) == 1
    assert production_journal.read_text() == '{"production":true}\n'


def test_journal_identity_statistics_and_telegram(tmp_path):
    state = advance(advance(entered(), 3600, 105, 104), 7200, 104, 100)
    closed = observe_profit_lock_shadow(
        state, candle=candle(10800, 99, 90), production_before=position(),
        production_after=flat(), production_net_pnl=D("-5"),
    ).observation
    path = tmp_path / "profit-lock.jsonl"
    journal = ProfitLockShadowJournal(path)
    assert journal.append(closed)
    assert journal.append(closed) is False
    rows = [json.loads(path.read_text())]
    stats = aggregate_profit_lock_statistics(rows)
    assert len(stats) == 8
    assert all(value["positions_observed"] == 1 for value in stats.values())
    assert all(value["saved_losses"] == 1 for value in stats.values())
    report = _profit_lock_shadow_report_block(SimpleNamespace(profit_lock_shadow_journal=path))
    assert "Profit Lock shadow" in report
    assert "BE group:" in report and "BE+0.1 group:" in report
    assert "Mode: observation only" in report
