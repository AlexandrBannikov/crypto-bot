from datetime import datetime, timezone
from dataclasses import replace
from decimal import Decimal
import json
import math
from pathlib import Path

import pytest

import app.paper_comparator as comparator
from app.candidate_runtime import CandidateStateStore
from app.paper_comparator import (
    compare_paper_runtimes,
    render_comparison_markdown,
    write_comparison_report,
)
from app.trade_journal import TradeJournalEntry
from app.trading_controller_store import TradingControllerStateStore


NOW = datetime(2026, 7, 29, 12, tzinfo=timezone.utc)
BASE = int(NOW.timestamp()) - 7200


def _decision(timestamp: int, action: str, *, candidate: bool, reason="none"):
    if candidate:
        return {
            "candle_timestamp": timestamp,
            "decision": action,
            "reason": reason,
            "position_after": "FLAT",
            "close": 2000,
            "ema20": 1990,
            "ema50": 1980,
            "adx": 25,
            "pullback_pending": action == "WAIT_PULLBACK",
            "bars_waited": 2,
        }
    mapping = {"ENTER": "open_long", "EXIT": "close_long", "HOLD": "hold"}
    return {
        "candle_timestamp": timestamp,
        "effective_action": mapping[action],
        "reason": reason,
        "position_state_after": "flat",
        "price": "2000",
    }


def _write_jsonl(path: Path, rows) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def _trade(timestamp: int, pnl: str, balance: str, fee: str = "1"):
    return TradeJournalEntry(
        record_id=f"id-{timestamp}-{pnl}",
        symbol="ETHUSDT",
        opened_at=datetime.fromtimestamp(
            timestamp - 60, timezone.utc
        ).isoformat(),
        closed_at=datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
        entry_price=Decimal("2000"),
        exit_price=Decimal("2001"),
        quantity=Decimal("0.01"),
        entry_notional=Decimal("20"),
        exit_notional=Decimal("20"),
        gross_pnl=Decimal(pnl) + Decimal(fee),
        entry_fee=Decimal(fee) / 2,
        exit_fee=Decimal(fee) / 2,
        total_fee=Decimal(fee),
        net_pnl=Decimal(pnl),
        pnl_percent=Decimal("1"),
        exit_reason="EMA",
        remaining_position_quantity=Decimal("0"),
        virtual_balance_after=Decimal(balance),
        realized_pnl_after=Decimal(pnl),
        closed_trades_after=1,
    )


def _setup(tmp_path: Path):
    paths = {
        "production_state": tmp_path / "production.json",
        "production_trades": tmp_path / "prod-trades.jsonl",
        "production_decisions": tmp_path / "prod-decisions.jsonl",
        "candidate_state": tmp_path / "candidate.json",
        "candidate_trades": tmp_path / "cand-trades.jsonl",
        "candidate_decisions": tmp_path / "cand-decisions.jsonl",
    }
    TradingControllerStateStore(paths["production_state"]).save(
        TradingControllerStateStore(paths["production_state"]).load()
    )
    candidate = CandidateStateStore(paths["candidate_state"]).load()
    candidate.baseline_candle = BASE
    candidate.last_processed_candle = BASE + 3600
    CandidateStateStore(paths["candidate_state"]).save(candidate)
    for key in (
        "production_trades",
        "production_decisions",
        "candidate_trades",
        "candidate_decisions",
    ):
        paths[key].write_text("", encoding="utf-8")
    return paths


def _compare(paths, **kwargs):
    return compare_paper_runtimes(
        **paths,
        now=NOW,
        period="all_available",
        **kwargs,
    )


def test_decision_categories_matching_missing_and_agreement(tmp_path):
    paths = _setup(tmp_path)
    _write_jsonl(
        paths["production_decisions"],
        [
            _decision(BASE, "HOLD", candidate=False),
            _decision(BASE + 3600, "ENTER", candidate=False),
            _decision(BASE + 7200, "HOLD", candidate=False),
        ],
    )
    _write_jsonl(
        paths["candidate_decisions"],
        [
            _decision(BASE, "HOLD", candidate=True),
            _decision(BASE + 3600, "ENTER", candidate=True),
            _decision(BASE + 10800, "HOLD", candidate=True),
        ],
    )

    report = _compare(paths)
    categories = report["decisions"]["categories"]

    assert categories["BOTH_HOLD"] == 1
    assert categories["BOTH_ENTER"] == 1
    assert categories["MISSING_CANDIDATE_DECISION"] == 1
    assert categories["MISSING_PRODUCTION_DECISION"] == 1
    assert report["decisions"]["matched_candles"] == 2
    assert report["decisions"]["unmatched_records"] == 2
    assert report["decisions"]["agreement_rate_percent"] == 100


@pytest.mark.parametrize(
    ("production", "candidate", "category"),
    [
        ("ENTER", "HOLD", "PRODUCTION_ENTER_CANDIDATE_HOLD"),
        ("ENTER", "WAIT_PULLBACK", "PRODUCTION_ENTER_CANDIDATE_WAIT"),
        ("HOLD", "ENTER", "CANDIDATE_ENTER_PRODUCTION_HOLD"),
        ("EXIT", "HOLD", "PRODUCTION_EXIT_CANDIDATE_HOLD"),
        ("HOLD", "EXIT", "CANDIDATE_EXIT_PRODUCTION_HOLD"),
    ],
)
def test_different_decisions_are_categorized(
    tmp_path, production, candidate, category
):
    paths = _setup(tmp_path)
    _write_jsonl(
        paths["production_decisions"],
        [_decision(BASE, production, candidate=False)],
    )
    _write_jsonl(
        paths["candidate_decisions"],
        [_decision(BASE, candidate, candidate=True)],
    )
    assert _compare(paths)["decisions"]["categories"][category] == 1


def test_different_exit_reason_and_last_twenty(tmp_path):
    paths = _setup(tmp_path)
    production = []
    candidate = []
    for index in range(25):
        timestamp = BASE + index * 3600
        production.append(
            _decision(timestamp, "EXIT", candidate=False, reason="stop")
        )
        candidate.append(
            _decision(timestamp, "EXIT", candidate=True, reason="cross")
        )
    _write_jsonl(paths["production_decisions"], production)
    _write_jsonl(paths["candidate_decisions"], candidate)
    report = _compare(paths)
    assert report["decisions"]["categories"]["DIFFERENT_EXIT_REASON"] == 25
    assert len(report["recent_differences"]) == 20
    assert report["recent_differences"][-1]["bars_waited"] == 2


def test_duplicate_and_damaged_jsonl_are_reported(tmp_path):
    paths = _setup(tmp_path)
    row = _decision(BASE, "HOLD", candidate=False)
    _write_jsonl(paths["production_decisions"], [row, row])
    paths["candidate_decisions"].write_text("{broken}\n", encoding="utf-8")
    report = _compare(paths)
    assert report["status"] == "WARNING"
    assert any("duplicate candle" in item for item in report["warnings"])
    assert any(
        "candidate decision journal unavailable" in item
        for item in report["warnings"]
    )


def test_empty_journals_use_na_not_misleading_zero(tmp_path):
    report = _compare(_setup(tmp_path))
    assert report["production"]["profit_factor"] == "N/A"
    assert report["candidate"]["win_rate_percent"] == "N/A"
    assert report["production"]["max_drawdown_percent"] == "N/A"
    assert report["production"]["data_status"] == "insufficient data"
    assert report["decisions"]["agreement_rate_percent"] == "N/A"


def test_profit_factor_infinity_drawdown_fees_and_balance_delta(tmp_path):
    paths = _setup(tmp_path)
    prod_trades = [
        _trade(BASE, "10", "1010", "1"),
        _trade(BASE + 3600, "-20", "990", "2"),
    ]
    cand_trades = [_trade(BASE, "5", "1005", "4")]
    _write_jsonl(paths["production_trades"], [row.to_dict() for row in prod_trades])
    _write_jsonl(paths["candidate_trades"], [row.to_dict() for row in cand_trades])
    production = TradingControllerStateStore(paths["production_state"]).load()
    production = replace(
        production, virtual_balance=Decimal("990"), realized_pnl=Decimal("-10")
    )
    TradingControllerStateStore(paths["production_state"]).save(production)
    candidate = CandidateStateStore(paths["candidate_state"]).load()
    candidate.controller = replace(
        candidate.controller,
        virtual_balance=Decimal("1005"),
        realized_pnl=Decimal("5"),
    )
    CandidateStateStore(paths["candidate_state"]).save(candidate)

    report = _compare(paths)

    assert report["production"]["max_drawdown_percent"] == pytest.approx(
        20 / 1010 * 100
    )
    assert math.isinf(report["candidate"]["profit_factor"])
    assert report["deltas"]["fees"] == "1"
    assert report["deltas"]["balance"] == "15"


def test_candidate_unavailable_does_not_change_production_health(tmp_path):
    paths = _setup(tmp_path)
    paths["candidate_state"].write_text("{broken", encoding="utf-8")
    report = _compare(paths)
    assert report["status"] == "WARNING"
    assert report["production"]["health_status"] in {"OK", "WARNING"}
    assert report["candidate"]["health_status"] == "N/A"
    assert any("Candidate data unavailable" in item for item in report["warnings"])


def test_production_unavailable_is_critical(tmp_path):
    paths = _setup(tmp_path)
    paths["production_state"].unlink()
    report = _compare(paths)
    assert report["status"] == "CRITICAL"
    assert report["production"]["data_status"] == "unavailable"


def test_timezone_determinism_and_atomic_write(tmp_path):
    paths = _setup(tmp_path)
    _write_jsonl(
        paths["production_decisions"],
        [_decision(BASE, "ENTER", candidate=False)],
    )
    _write_jsonl(
        paths["candidate_decisions"],
        [_decision(BASE, "HOLD", candidate=True)],
    )
    first = _compare(paths, timezone_name="Asia/Yekaterinburg")
    second = _compare(paths, timezone_name="Asia/Yekaterinburg")
    assert first == second
    assert first["recent_differences"][0]["time"].endswith("+05:00")

    output = tmp_path / "nested" / "report.json"
    write_comparison_report(first, output)
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == 2
    assert not list(output.parent.glob(".*.tmp"))
    assert "Production vs Candidate" in render_comparison_markdown(first)


def test_atomic_write_failure_preserves_existing_report(tmp_path, monkeypatch):
    output = tmp_path / "report.json"
    output.write_text('{"old": true}\n', encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(comparator.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        write_comparison_report({"new": True}, output)
    assert output.read_text(encoding="utf-8") == '{"old": true}\n'
    assert not list(tmp_path.glob(".*.tmp"))


def test_today_last_24h_and_cumulative_periods(tmp_path):
    paths = _setup(tmp_path)
    old = BASE - 86400
    _write_jsonl(
        paths["production_decisions"],
        [
            _decision(old, "HOLD", candidate=False),
            _decision(BASE, "HOLD", candidate=False),
        ],
    )
    _write_jsonl(
        paths["candidate_decisions"],
        [
            _decision(old, "HOLD", candidate=True),
            _decision(BASE, "HOLD", candidate=True),
        ],
    )
    last_day = compare_paper_runtimes(
        **paths, now=NOW, period="last_24h", timezone_name="UTC"
    )
    cumulative = compare_paper_runtimes(
        **paths, now=NOW, period="since_candidate_start", timezone_name="UTC"
    )
    all_rows = _compare(paths)
    assert last_day["decisions"]["matched_candles"] == 1
    assert cumulative["decisions"]["matched_candles"] == 1
    assert all_rows["decisions"]["matched_candles"] == 2
