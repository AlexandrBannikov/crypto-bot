from datetime import datetime, timezone
from decimal import Decimal
import json

import pytest

from app.candle import Candle
from app.trade_accounting import calculate_long_trade_accounting
from app.trade_diagnostics import (
    TradeDiagnosticsJournal, aggregate_trade_diagnostics, build_trade_card,
)
from app.trade_journal import TradeJournalEntry
from app.telegram_notifications import TelegramPaths, _trade_diagnostics_period_block


D = Decimal


def trade(*, entry="100", exit="98", quantity="1",
          opened="1970-01-01T01:00:00+00:00",
          closed="1970-01-01T04:00:00+00:00") -> TradeJournalEntry:
    accounting = calculate_long_trade_accounting(D(entry), D(exit), D(quantity), D("0.001"))
    return TradeJournalEntry(
        record_id="source", symbol="ETHUSDT", opened_at=opened, closed_at=closed,
        entry_price=accounting.entry_price, exit_price=accounting.exit_price,
        quantity=accounting.quantity, entry_notional=accounting.entry_notional,
        exit_notional=accounting.exit_notional, gross_pnl=accounting.gross_pnl,
        entry_fee=accounting.entry_fee, exit_fee=accounting.exit_fee,
        total_fee=accounting.entry_fee + accounting.exit_fee,
        net_pnl=accounting.net_pnl,
        pnl_percent=accounting.net_pnl / accounting.entry_notional * 100,
        exit_reason="signal", remaining_position_quantity=D("0"),
        virtual_balance_after=D("1000"), realized_pnl_after=accounting.net_pnl,
        closed_trades_after=1,
    )


def candle(ts, high, low, close=100):
    return Candle(ts, close, high, low, close, 1)


def score(value=70, *, blocked=False):
    return {
        "candle_timestamp": 0, "score_total": value,
        "hard_blocks": ["blocked"] if blocked else [],
        "components": {f"{name}_score": index for index, name in enumerate(
            ("trend", "ema_alignment", "adx", "pullback", "momentum", "volatility", "cost"), 1)},
    }


def card(**kwargs):
    defaults = dict(
        candles=(candle(3600, 100.5, 99), candle(7200, 101.5, 97), candle(10800, 99, 98)),
        exit_candle_timestamp=10800,
        production_decisions=({"candle_timestamp": 0, "baseline_signal": "open_long", "execution_signal": "open_long"},),
        scored65_observations=(score(),), scored62_observations=(score(),),
        break_even_observations=(),
    )
    defaults.update(kwargs)
    return build_trade_card(trade=defaults.pop("trade", trade()), **defaults)


def test_profitable_trade_and_possible_exit_issue():
    result = card(
        trade=trade(exit="100.1"),
        candles=(candle(3600, 102, 99), candle(7200, 100.1, 99.5)),
        exit_candle_timestamp=7200,
    )
    assert D(result["exit"]["net_pnl"]) < 0  # fees turn the tiny gross winner negative
    assert result["preliminary_classification"] == "possible_exit_issue"


def test_winner_is_counted_by_aggregates():
    result = card(trade=trade(exit="103"))
    stats = aggregate_trade_diagnostics([result])
    assert stats["winners"] == 1 and stats["losers"] == 0


def test_loser_reaches_half_percent_but_not_one_percent():
    result = card(candles=(candle(3600, 100.6, 98),), exit_candle_timestamp=3600)
    assert result["excursion"]["reached_0_5_pct"] is True
    assert result["excursion"]["reached_1_0_pct"] is False


@pytest.mark.parametrize(
    "be,effect,armed,triggered",
    [
        ({"opened_at": "1970-01-01T01:00:00+00:00", "candle_timestamp": 10800,
          "armed_at_candle": 3600, "triggered_at_candle": None}, "no_effect", True, False),
        ({"opened_at": "1970-01-01T01:00:00+00:00", "candle_timestamp": 10800,
          "armed_at_candle": 3600, "triggered_at_candle": 7200}, "no_effect", True, True),
        ({"opened_at": "1970-01-01T01:00:00+00:00", "candle_timestamp": 10800,
          "armed_at_candle": 3600, "triggered_at_candle": 7200, "saved_loss": True}, "saved_loss", True, True),
        ({"opened_at": "1970-01-01T01:00:00+00:00", "candle_timestamp": 10800,
          "armed_at_candle": 3600, "triggered_at_candle": 7200, "worsened_winner": True}, "worsened_winner", True, True),
    ],
)
def test_break_even_lifecycle_and_effect(be, effect, armed, triggered):
    result = card(break_even_observations=(be,))
    assert result["break_even_shadow"]["effect"] == effect
    assert result["break_even_shadow"]["armed"] is armed
    assert result["break_even_shadow"]["triggered"] is triggered


def test_trailing_variants_are_added_to_closed_trade_card():
    variants = tuple({
        "variant": name, "status": "triggered", "current_floor": "104",
        "activated_at_candle": 3600, "triggered_at_candle": 7200,
        "hypothetical_exit_price": "104", "comparison_hypothetical_net_pnl": "3.7",
        "production_net_pnl": "-2.2", "delta_usdt": "5.9",
        "delta_pct": "5.9", "effect": "saved_loss",
    } for name in ("0.5%", "1.0%", "1.5%", "2.0%"))
    result = card(trailing_observations=({
        "opened_at": "1970-01-01T01:00:00+00:00",
        "candle_timestamp": 10800, "variants": variants,
    },))
    assert tuple(result["trailing_shadows"]) == ("0.5%", "1.0%", "1.5%", "2.0%")
    assert result["trailing_shadows"]["0.5%"]["effect"] == "saved_loss"
    assert result["trailing_shadows"]["2.0%"]["delta_usdt"] == "5.9"


def test_profit_lock_variants_are_added_to_closed_trade_card():
    names = tuple(
        f"{trail} + {lock}"
        for lock in ("BE", "BE+0.1%")
        for trail in ("0.5%", "1.0%", "1.5%", "2.0%")
    )
    variants = tuple({
        "variant": name, "status": "triggered", "trailing_floor": "99",
        "profit_lock_floor": "100.2", "effective_floor": "100.2",
        "activated_at_candle": 3600, "triggered_at_candle": 7200,
        "hypothetical_exit_price": "100.2", "hypothetical_net_pnl": "0",
        "hypothetical_gross_pnl": ".2", "hypothetical_entry_fee": ".1",
        "hypothetical_exit_fee": ".1", "hypothetical_return_pct": "0",
        "comparison_hypothetical_net_pnl": "0", "production_net_pnl": "-2.2",
        "delta_usdt": "2.2", "delta_pct": "2.2", "effect": "saved_loss",
    } for name in names)
    result = card(profit_lock_observations=({
        "opened_at": "1970-01-01T01:00:00+00:00",
        "candle_timestamp": 10800, "variants": variants,
    },))
    assert tuple(result["profit_lock_shadows"]) == names
    assert result["profit_lock_shadows"]["0.5% + BE"]["effect"] == "saved_loss"
    assert result["profit_lock_shadows"]["2.0% + BE+0.1%"]["delta_usdt"] == "2.2"


def test_scored_65_hold_and_62_hold():
    result = card(scored65_observations=(score(61),), scored62_observations=(score(61),))
    assert result["decision_comparison"] == {"production": "entered", "score65": "HOLD", "score62": "HOLD"}


def test_scored_65_hold_and_62_enter_long():
    result = card(scored65_observations=(score(63),), scored62_observations=(score(63),))
    assert result["decision_comparison"]["score65"] == "HOLD"
    assert result["decision_comparison"]["score62"] == "ENTER_LONG"


def test_missing_scored_observation_is_explicit():
    result = card(scored65_observations=(), scored62_observations=())
    assert result["scored_entry_observation"] == "unavailable"
    assert result["preliminary_classification"] == "insufficient"


def test_mfe_mae_and_no_lookahead_after_exit():
    result = card(
        candles=(candle(3600, 105, 95), candle(7200, 103, 96), candle(10800, 999, 1)),
        exit_candle_timestamp=7200,
    )
    assert D(result["excursion"]["mfe_pct"]) == D("5.00")
    assert D(result["excursion"]["mae_pct"]) == D("-5.00")
    assert result["excursion"]["mfe_candle_timestamp"] == 3600


def test_journal_idempotency_survives_restart(tmp_path):
    path = tmp_path / "diagnostics.jsonl"
    result = card()
    assert TradeDiagnosticsJournal(path).append(result) is True
    assert TradeDiagnosticsJournal(path).append(result) is False
    assert len(path.read_text().splitlines()) == 1


def test_tests_write_only_to_tmp_journal(tmp_path):
    path = tmp_path / "not-production.jsonl"
    TradeDiagnosticsJournal(path).append(card())
    assert path.exists()
    assert path.parent == tmp_path


def telegram_paths(tmp_path):
    state = tmp_path / "state"; state.mkdir()
    return TelegramPaths(
        controller_state=state / "controller", runtime_state=state / "runtime",
        last_candle=state / "last", trade_journal=state / "trades",
        decision_journal=state / "decisions", notification_state=state / "notify",
        trade_diagnostics_journal=state / "diagnostics.jsonl",
    )


def test_telegram_block_one_and_multiple_trades(tmp_path):
    paths = telegram_paths(tmp_path)
    first = card(); second = {**first, "trade_id": "second"}
    paths.trade_journal.write_text(json.dumps(trade().to_dict()) + "\n")
    paths.trade_diagnostics_journal.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n")
    block = _trade_diagnostics_period_block(
        paths, datetime(1970, 1, 1, tzinfo=timezone.utc),
        datetime(1970, 1, 2, tzinfo=timezone.utc),
    )
    assert block.count("Последняя закрытая PAPER-сделка") == 2
    assert "ENTRY 100" in block and "Предварительно:" in block


def test_telegram_block_missing_diagnostics_and_no_closed_trades(tmp_path):
    paths = telegram_paths(tmp_path)
    paths.trade_journal.write_text("")
    assert _trade_diagnostics_period_block(
        paths, datetime(1970, 1, 1, tzinfo=timezone.utc),
        datetime(1970, 1, 2, tzinfo=timezone.utc),
    ) == "🔬 Закрытых PAPER-сделок за период нет"


def test_telegram_block_missing_diagnostics_and_closed_trade(tmp_path):
    paths = telegram_paths(tmp_path)
    paths.trade_journal.write_text(json.dumps(trade().to_dict()) + "\n")
    assert _trade_diagnostics_period_block(
        paths, datetime(1970, 1, 1, tzinfo=timezone.utc),
        datetime(1970, 1, 2, tzinfo=timezone.utc),
    ) == "🔬 Закрытые PAPER-сделки: diagnostics unavailable"


def test_telegram_block_empty_diagnostics_and_closed_trade(tmp_path):
    paths = telegram_paths(tmp_path)
    paths.trade_journal.write_text(json.dumps(trade().to_dict()) + "\n")
    paths.trade_diagnostics_journal.write_text("")
    assert _trade_diagnostics_period_block(
        paths, datetime(1970, 1, 1, tzinfo=timezone.utc),
        datetime(1970, 1, 2, tzinfo=timezone.utc),
    ) == "🔬 Закрытые PAPER-сделки: diagnostics unavailable"


def test_telegram_block_corrupt_diagnostics_and_closed_trade(tmp_path):
    paths = telegram_paths(tmp_path)
    paths.trade_journal.write_text(json.dumps(trade().to_dict()) + "\n")
    paths.trade_diagnostics_journal.write_text("not-json\n")
    assert _trade_diagnostics_period_block(
        paths, datetime(1970, 1, 1, tzinfo=timezone.utc),
        datetime(1970, 1, 2, tzinfo=timezone.utc),
    ) == "🔬 Закрытые PAPER-сделки: diagnostics unavailable"


def test_telegram_block_valid_diagnostic_card(tmp_path):
    paths = telegram_paths(tmp_path)
    paths.trade_journal.write_text(json.dumps(trade().to_dict()) + "\n")
    paths.trade_diagnostics_journal.write_text(json.dumps(card()) + "\n")
    block = _trade_diagnostics_period_block(
        paths, datetime(1970, 1, 1, tzinfo=timezone.utc),
        datetime(1970, 1, 2, tzinfo=timezone.utc),
    )
    assert "🔬 Последняя закрытая PAPER-сделка" in block
    assert "ENTRY 100" in block


def test_historical_1915_regression():
    historical = trade(entry="1915.73", exit="1879.37", quantity="0.01")
    result = card(
        trade=historical,
        candles=(candle(3600, 1926.26, 1900), candle(7200, 1905, 1877.85), candle(10800, 1885, 1879.37)),
        scored65_observations=(score(29.341732),),
        scored62_observations=(score(29.341732),),
    )
    assert float(result["exit"]["net_pnl"]) == pytest.approx(-0.401550999, abs=1e-9)
    assert float(result["excursion"]["mfe_pct"]) == pytest.approx(0.549660, abs=1e-6)
    assert float(result["excursion"]["mae_pct"]) == pytest.approx(-1.977314, abs=1e-6)
    assert float(result["scored_entry_observation"]["total_score"]) == pytest.approx(29.341732)
    assert result["decision_comparison"]["score65"] == "HOLD"
    assert result["decision_comparison"]["score62"] == "HOLD"
    assert result["break_even_shadow"]["armed"] is False
    assert result["break_even_shadow"]["triggered"] is False
