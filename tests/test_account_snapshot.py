from datetime import datetime, timezone
from decimal import Decimal
import json

from app.account_snapshot import (
    calculate_account_snapshot,
    format_position_age,
    market_from_decisions,
)
from app.paper_comparator import _deltas, write_comparison_report


NOW = datetime(2026, 7, 29, 16, tzinfo=timezone.utc)


def snapshot(**changes):
    values = {
        "initial_balance": "1000",
        "cash_balance": "980.7351544",
        "position_side": "LONG",
        "position_quantity": "0.01",
        "entry_price": "1950",
        "current_price": "1912.45",
        "realized_pnl": "0",
        "opened_at": "2026-07-29T07:00:00+00:00",
        "now": NOW,
        "stop_loss_price": "1885",
    }
    values.update(changes)
    return calculate_account_snapshot(**values)


def test_long_profit_loss_and_account_totals():
    profit = snapshot(current_price="2000")
    loss = snapshot()
    assert profit.unrealized_pnl == Decimal("0.50")
    assert loss.unrealized_pnl == Decimal("-0.3755")
    assert loss.position_market_value == Decimal("19.1245")
    assert loss.equity == Decimal("999.8596544")
    assert loss.realized_pnl == 0
    assert loss.total_pnl == loss.unrealized_pnl
    assert loss.total_return_pct == Decimal("-0.03755")


def test_flat_and_missing_prices_are_safe():
    flat = snapshot(position_side="FLAT", position_quantity=0, entry_price=None)
    missing_price = snapshot(current_price=None)
    missing_entry = snapshot(entry_price=None)
    assert flat.position_market_value == 0
    assert flat.equity == flat.cash_balance
    assert flat.unrealized_pnl == 0
    assert missing_price.equity is None
    assert missing_price.unrealized_pnl is None
    assert missing_entry.position_market_value == Decimal("19.1245")
    assert missing_entry.unrealized_pnl is None


def test_stop_take_profit_and_runtime_flags():
    item = snapshot(
        stop_loss_price="1920",
        take_profit_price="2050",
        break_even_active=True,
        trailing_stop_active=True,
    )
    assert item.distance_to_stop_value == Decimal("-7.55")
    assert item.distance_to_stop_pct < 0
    assert item.distance_to_take_profit_value == Decimal("137.55")
    assert item.break_even_active is True
    assert item.trailing_stop_active is True


def test_missing_opened_at_and_age_formatting():
    assert snapshot(opened_at=None).position_age_seconds is None
    assert format_position_age(42 * 60) == "42m"
    assert format_position_age(9 * 3600 + 15 * 60) == "9h 15m"
    assert format_position_age(2 * 86400 + 4 * 3600) == "2d 4h"


def test_market_uses_latest_runtime_row_without_io():
    market = market_from_decisions(
        [
            {"candle_timestamp": 1, "price": "1900"},
            {"candle_timestamp": 2, "close": "1912.45"},
        ]
    )
    assert market["price"] == "1912.45"
    assert market["source"] == "Bybit"


def test_candidate_production_delta_is_based_on_equity():
    production = {
        "balance": "980",
        "cumulative_pnl": "0",
        "return_percent": "0",
        "equity": "999.86",
        "total_pnl": "-0.14",
        "total_return_pct": "-0.014",
        "unrealized_pnl": "-0.14",
        "realized_pnl": "0",
        "fees": "0",
        "max_drawdown_percent": "0",
        "closed_trades": 0,
    }
    candidate = production | {
        "balance": "1000",
        "equity": "1000",
        "total_pnl": "0",
        "total_return_pct": "0",
        "unrealized_pnl": "0",
    }
    delta = _deltas(production, candidate)
    assert delta["balance"] == "20"
    assert delta["equity"] == "0.14"
    assert delta["total_pnl"] == "0.14"


def test_json_snapshot_serialization(tmp_path):
    report = {
        "generated_at": NOW.isoformat(),
        "period": {},
        "market": {},
        "production": {"snapshot": snapshot().to_dict()},
        "candidate": {},
        "comparison": {},
        "health": {},
        "decision_agreement": {},
    }
    output = tmp_path / "evening_report_2026-07-29.json"
    write_comparison_report(report, output)
    loaded = json.loads(output.read_text())
    assert loaded["production"]["snapshot"]["equity"] == "999.8596544"
