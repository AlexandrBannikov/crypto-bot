from decimal import Decimal
import json
from types import SimpleNamespace

from app.candle import Candle
from app.trailing_stop_shadow import (
    TrailingShadowJournal, TrailingShadowState, TrailingShadowStateStore,
    observe_trailing_shadow, reconcile_trailing_shadow,
)
from app.trading_controller import TradingControllerState
from app.telegram_notifications import _trailing_shadow_report_block
from scripts.run_bybit_controller import run_trailing_shadow_observer

D = Decimal


def candle(ts, high, low, close=100):
    return Candle(ts, close, high, low, close, 1)


def flat():
    return TradingControllerState()


def position(opened_at="1970-01-01T01:00:00+00:00"):
    return TradingControllerState(
        position_quantity=D("2"), entry_price=D("100"), stop_loss=D("98"),
        opened_at=opened_at,
    )


def entered():
    return observe_trailing_shadow(
        TrailingShadowState(), candle=candle(0, 110, 90),
        production_before=flat(), production_after=position(),
    ).state


def advance(state, ts, high, low):
    return observe_trailing_shadow(
        state, candle=candle(ts, high, low), production_before=position(),
        production_after=position(),
    ).state


def test_inactive_until_half_percent_then_all_variants_activate():
    inactive = advance(entered(), 3600, 100.49, 99)
    assert {item.status for item in inactive.variants} == {"inactive"}
    active = advance(inactive, 7200, 100.5, 90)
    assert {item.status for item in active.variants} == {"trailing"}
    assert {item.activated_at_candle for item in active.variants} == {7200}


def test_peak_and_floors_only_increase():
    first = advance(entered(), 3600, 105, 104)
    second = advance(first, 7200, 110, 106)
    third = advance(second, 10800, 108, 107)
    assert (first.peak_price, second.peak_price, third.peak_price) == (D("105"), D("110"), D("110"))
    for a, b, c in zip(first.variants, second.variants, third.variants):
        assert a.current_floor <= b.current_floor == c.current_floor


def test_four_thresholds_trigger_independently():
    active = advance(entered(), 3600, 110, 109)
    one = advance(active, 7200, 110, 109.3)
    assert [item.status for item in one.variants] == ["triggered", "trailing", "trailing", "trailing"]
    two = advance(one, 10800, 110, 108.8)
    three = advance(two, 14400, 110, 108.2)
    four = advance(three, 18000, 110, 107.7)
    assert [item.status for item in four.variants] == ["triggered"] * 4


def test_new_high_and_low_same_candle_cannot_use_new_floor():
    active = advance(entered(), 3600, 101, 100.6)
    # Old 2% floor is 98.98; low crosses the new 107.8 floor but not old floor.
    update = advance(active, 7200, 110, 100)
    assert update.variants[3].status == "trailing"
    assert update.variants[3].current_floor == D("107.800")


def test_old_floor_can_trigger_on_candle_that_also_sets_new_high():
    active = advance(entered(), 3600, 105, 104)
    update = advance(active, 7200, 110, 104)
    assert update.variants[0].status == "triggered"
    assert update.variants[0].hypothetical_exit_price == D("104.475")


def test_fees_and_exit_comparisons_and_classifications():
    active = advance(entered(), 3600, 110, 109)
    triggered = advance(active, 7200, 110, 107)
    item = triggered.variants[0]
    expected = (item.hypothetical_exit_price - D("100")) * 2 - (D("100") + item.hypothetical_exit_price) * 2 * D("0.001")
    assert item.hypothetical_net_pnl == expected
    closed = observe_trailing_shadow(
        triggered, candle=candle(10800, 100, 90), production_before=position(),
        production_after=flat(), production_net_pnl=D("-5"),
    )
    assert closed.state == TrailingShadowState()
    assert closed.observation.variants[0]["effect"] == "saved_loss"
    assert closed.observation.variants[3]["effect"] == "saved_loss"
    assert closed.observation.variants[0]["delta_usdt"] == expected + 5


def test_protected_profit_worsened_winner_and_no_effect():
    active = advance(entered(), 3600, 110, 109)
    triggered = advance(active, 7200, 110, 107)
    for production_pnl, effect in ((D("5"), "protected_profit"), (D("30"), "worsened_winner")):
        result = observe_trailing_shadow(
            triggered, candle=candle(10800, 100, 90),
            production_before=position(), production_after=flat(),
            production_net_pnl=production_pnl,
        )
        assert result.observation.variants[0]["effect"] == effect
    untriggered = advance(entered(), 3600, 101, 100)
    result = observe_trailing_shadow(
        untriggered, candle=candle(7200, 101, 100.8), production_before=position(),
        production_after=flat(), production_net_pnl=D("1"),
    )
    assert all(item["effect"] == "no_effect" and item["delta_usdt"] == 0 for item in result.observation.variants)


def test_production_exit_before_trailing_and_trailing_before_production():
    inactive = advance(entered(), 3600, 100.4, 99)
    early = observe_trailing_shadow(
        inactive, candle=candle(7200, 99, 98), production_before=position(),
        production_after=flat(), production_net_pnl=D("-4"),
    )
    assert all(item["effect"] == "no_effect" for item in early.observation.variants)
    triggered = advance(advance(entered(), 3600, 110, 109), 7200, 110, 107)
    assert any(item.status == "triggered" for item in triggered.variants)
    assert position().has_open_position


def test_restart_reconciliation_and_idempotency_do_not_touch_trade_journal(tmp_path):
    candles = (candle(3600, 101, 100), candle(7200, 110, 100), candle(10800, 109, 107))
    restored = reconcile_trailing_shadow(TrailingShadowState(), production=position(), candles=candles)
    assert restored.peak_price == D("110")
    assert restored.variants[0].status == "triggered"
    path = tmp_path / "state.json"
    TrailingShadowStateStore(path).save(restored)
    assert TrailingShadowStateStore(path).load() == restored
    assert reconcile_trailing_shadow(restored, production=position(), candles=candles) == restored
    journal = tmp_path / "trailing.jsonl"
    trade_journal = tmp_path / "production-trades.jsonl"
    trade_journal.write_text('{"production":true}\n')
    for _ in range(2):
        assert run_trailing_shadow_observer(
            candle=candles[-1], production_before=position(), production_after=position(),
            production_exit_pnl=None, historical_candles=candles,
            state_path=path, journal_path=journal,
        )
    assert len(journal.read_text().splitlines()) == 1
    assert trade_journal.read_text() == '{"production":true}\n'


def test_journal_identity_allows_same_candle_for_different_positions(tmp_path):
    journal = TrailingShadowJournal(tmp_path / "trailing.jsonl")
    first = observe_trailing_shadow(entered(), candle=candle(3600, 101, 100), production_before=position(), production_after=position()).observation
    other_position = position("1970-01-01T02:00:00+00:00")
    other = observe_trailing_shadow(TrailingShadowState(), candle=candle(3600, 101, 100), production_before=flat(), production_after=other_position).observation
    assert journal.append(first)
    assert journal.append(first) is False
    assert journal.append(other)
    assert len(journal.path.read_text().splitlines()) == 2


def test_telegram_open_position_and_cumulative_formatting(tmp_path):
    active = advance(entered(), 3600, 110, 109)
    observation = observe_trailing_shadow(
        active, candle=candle(7200, 110, 107), production_before=position(),
        production_after=position(),
    ).observation
    path = tmp_path / "trailing.jsonl"
    TrailingShadowJournal(path).append(observation)
    report = _trailing_shadow_report_block(SimpleNamespace(trailing_shadow_journal=path))
    assert "Trailing shadow" in report
    assert "Peak: 110" in report
    assert "Activation +0.5%: reached" in report
    for name in ("0.5%", "1.0%", "1.5%", "2.0%"):
        assert f"{name}: floor" in report
    assert "observed 1, activated 1" in report
    assert "Mode: observation only; production exits unchanged" in report
