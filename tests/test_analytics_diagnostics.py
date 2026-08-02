from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from app.candidate_diagnostics import summarize_candidate
from app.comparison_diagnostics import assess_comparison
from app.equity_integrity import _classify_group
from app.runtime_health import candle_timing_diagnostics


# 20 freshness cases: the expected latest closed candle is fresh regardless
# of how far its open timestamp is behind wall clock within the timeframe.
@pytest.mark.parametrize("minute", range(20))
def test_candle_freshness_uses_expected_closed_candle(minute):
    now = datetime.fromtimestamp(10 * 3600 + minute * 60, timezone.utc)
    result = candle_timing_diagnostics(9 * 3600, timeframe_minutes=60, now=now)
    assert result["market_lag_candles"] == 0
    assert result["stale_state"] is False


# 15 legacy/new reason cases verify aggregation without inventing subreasons.
@pytest.mark.parametrize("reason", [
    "no_signal", "adx_below_threshold", "pullback_not_detected",
    "trend_not_confirmed", "hybrid_score_too_low", "regime_not_allowed",
    "risk_rejected", "position_already_open", "cooldown",
    "insufficient_history", "invalid_indicator", "entry_allowed",
    "exit_signal", "other", "unknown_legacy_reason",
])
def test_candidate_reason_diagnostics_are_read_only(tmp_path: Path, reason):
    path = tmp_path / "decisions.jsonl"
    path.write_text(json.dumps({"candle_timestamp": 1, "reason_code": reason}) + "\n")
    result = summarize_candidate(path)
    assert result["decisions"] == 1
    assert result["observability_status"] == "LEGACY_FIELDS_UNAVAILABLE"
    assert result["no_signal_subreasons"] is None


# 10 multi-reason combinations exercise exact/semantic/expected/backfill rules.
@pytest.mark.parametrize("left,right,expected", [
    ("cycle", "trade_open", "expected_multi_reason"),
    ("trade_open", "cycle", "expected_multi_reason"),
    ("cycle", "trade_close", "expected_multi_reason"),
    ("trade_close", "cycle", "expected_multi_reason"),
    ("cycle", "daily_close", "expected_multi_reason"),
    ("daily_close", "cycle", "expected_multi_reason"),
    ("cycle", "startup_recovery", "expected_multi_reason"),
    ("startup_recovery", "cycle", "expected_multi_reason"),
    ("cycle", "manual_backfill", "backfill_overlap"),
    ("cycle", "cycle", "exact_duplicate"),
])
def test_duplicate_classification(left, right, expected):
    base = dict(cash_balance=1, asset_quantity=0, position_value=0, equity=1,
                realized_pnl=0, unrealized_pnl=0, total_pnl=0, return_pct=0,
                position_side="FLAT", entry_price=None, closed_trades=0,
                cumulative_fees=0)
    assert _classify_group([SimpleNamespace(snapshot_reason=left, **base), SimpleNamespace(snapshot_reason=right, **base)])[0] == expected


# 10 comparison inputs preserve N/A and return structured statuses/error codes.
@pytest.mark.parametrize("pf,wr,matched,prod_only,cand_only,status", [
    (None, None, 0, 0, 0, "INSUFFICIENT"),
    ("N/A", "N/A", 0, 0, 0, "INSUFFICIENT"),
    (None, None, 1, 0, 0, "COMPATIBLE"),
    ("N/A", "N/A", 1, 1, 0, "PARTIAL"),
    (0, 0, 2, 0, 1, "PARTIAL"),
    (1.2, 50.0, 2, 0, 0, "COMPATIBLE"),
    ("1.2", "50", 2, 0, 0, "COMPATIBLE"),
    (None, 0, 3, 0, 0, "COMPATIBLE"),
    (0, None, 3, 0, 0, "COMPATIBLE"),
    ("N/A", None, 3, 1, 1, "PARTIAL"),
])
def test_comparison_statuses_preserve_na(pf, wr, matched, prod_only, cand_only, status):
    metrics = {"equity": 1000, "return_percent": "N/A", "profit_factor": pf, "win_rate": wr}
    result = assess_comparison(metrics, metrics, matched_candles=matched,
                               production_only=prod_only, candidate_only=cand_only)
    assert result["comparison_status"] == status
