from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from app.candidate_runtime import CandidateStateStore
from app.strategy_lab import (
    LaboratoryConfig,
    NormalizedDecision,
    RankingThresholds,
    StrategySpec,
    build_report,
    compare_decisions,
    load_config,
    max_drawdown_percent,
    rank_strategies,
)
from app.trading_controller import TradingControllerState
from app.trading_controller_store import TradingControllerStateStore
from scripts import show_strategy_lab


NOW = datetime(2026, 7, 29, 12, tzinfo=timezone.utc)


def decision(timestamp, strategy, action="HOLD", status="produced", reason="test"):
    return NormalizedDecision(
        timestamp, strategy, action, action, "FLAT", "FLAT",
        reason, Decimal("100"), status,
    )


def test_comparison_excludes_missing_and_error_from_denominator():
    production = [
        decision(1, "production"),
        decision(2, "production", "ENTER_LONG"),
        decision(3, "production", status="error"),
    ]
    candidate = [
        decision(1, "candidate"),
        decision(2, "candidate"),
        decision(3, "candidate", status="missing"),
        decision(4, "candidate"),
    ]
    result = compare_decisions(
        production, candidate, zone=timezone.utc
    )
    assert result["matched_candles"] == 3
    assert result["comparable_candles"] == 2
    assert result["agreement_count"] == 1
    assert result["agreement_percent"] == 50
    assert result["production_only_decisions"] == 0
    assert result["candidate_only_decisions"] == 1
    assert result["missing_count"] == 1
    assert result["error_count"] == 1
    assert result["categories"]["production_enter_candidate_hold"] == 1
    assert result["recent_differences"][0]["production_reason"] == "test"


@pytest.mark.parametrize(
    ("left", "right", "category"),
    [
        ("HOLD", "HOLD", "same_hold"),
        ("EXIT_LONG", "HOLD", "production_exit_candidate_hold"),
        ("HOLD", "ENTER_LONG", "candidate_enter_production_hold"),
        ("EXIT_LONG", "EXIT_SHORT", "different_exit"),
        ("ENTER_LONG", "ENTER_SHORT", "opposite_directions"),
    ],
)
def test_decision_categories(left, right, category):
    result = compare_decisions(
        [decision(1, "production", left)],
        [decision(1, "candidate", right)],
        zone=timezone.utc,
    )
    assert result["categories"][category] == 1


def test_drawdown_uses_equity_curve():
    assert max_drawdown_percent(
        [Decimal("1000"), Decimal("1100"), Decimal("880"), Decimal("900")]
    ) == Decimal("20.0")


def _metrics(trades=5, days=8, *, ret="1", drawdown="2", pf=2, errors=0):
    return {
        "closed_trades_count": trades,
        "observation_start": (NOW - timedelta(days=days)).isoformat(),
        "return_percent": ret,
        "max_drawdown_percent": drawdown,
        "profit_factor": pf,
        "number_of_errors": errors,
    }


def test_ranking_unavailable_and_available_after_thresholds():
    thresholds = RankingThresholds(20, 5, 7)
    unavailable = rank_strategies(
        {"production": _metrics(trades=0)},
        {"candidate": {"comparable_candles": 2}},
        thresholds,
        NOW,
    )
    assert unavailable["message"] == "Недостаточно данных для рейтинга"
    available = rank_strategies(
        {
            "production": _metrics(ret="1", pf=1),
            "candidate": _metrics(ret="4", pf=2),
        },
        {"candidate": {"comparable_candles": 20}},
        thresholds,
        NOW,
    )
    assert available["available"] is True
    assert available["leader"] == "candidate"


def test_legacy_candidate_state_and_open_position_finances(tmp_path):
    production_state = tmp_path / "production.json"
    TradingControllerStateStore(production_state).save(
        TradingControllerState(
            position_quantity=Decimal("1"),
            entry_price=Decimal("100"),
            virtual_balance=Decimal("899.9"),
            entry_fee=Decimal("0.1"),
            opened_at=NOW.isoformat(),
        )
    )
    candidate_state = tmp_path / "candidate.json"
    candidate_state.write_text(
        json.dumps(
            {
                "controller": {
                    "position_quantity": "0",
                    "entry_price": None,
                    "stop_loss": None,
                    "virtual_balance": "1000",
                    "total_fees": "0",
                    "realized_pnl": "0",
                    "closed_trades": 0,
                    "entry_fee": "0"
                },
                "last_processed_candle": 1
            }
        )
    )
    prod_decisions = tmp_path / "prod.jsonl"
    prod_decisions.write_text(
        json.dumps(
            {
                "candle_timestamp": 1,
                "effective_action": "hold",
                "position_state_after": "long",
                "price": "110"
            }
        ) + "\n"
    )
    cand_decisions = tmp_path / "cand.jsonl"
    cand_decisions.write_text(
        json.dumps(
            {"candle_timestamp": 1, "decision": "HOLD", "close": 110}
        ) + "\n"
    )
    config = LaboratoryConfig(
        Decimal("1000"), Decimal("0.001"), RankingThresholds(),
        (
            StrategySpec(
                "production", "Production", True, "production",
                production_state, tmp_path / "pt.jsonl", prod_decisions,
            ),
            StrategySpec(
                "candidate_adx_hybrid", "Candidate", True, "candidate",
                candidate_state, tmp_path / "ct.jsonl", cand_decisions,
            ),
        ),
    )
    report = build_report(config, period="all", now=NOW)
    production = report["strategies"]["production"]
    assert production["cash_balance"] == "899.9"
    assert production["position_market_value"] == "110"
    assert production["equity"] == "1009.9"
    assert production["unrealized_pnl"] == "9.9"
    assert production["total_pnl"] == "9.9"
    assert production["fees_paid"] == "0.1"
    assert production["open_position_status"] == "OPEN"
    assert report["strategies"]["candidate_adx_hybrid"]["profit_factor"] == "N/A"


def test_registry_supports_multiple_candidates_and_cli_is_read_only(tmp_path):
    root = tmp_path
    (root / "state").mkdir()
    for name in ("production", "one", "two"):
        TradingControllerStateStore(root / f"state/{name}.json").save(
            TradingControllerState()
        )
        (root / f"state/{name}.jsonl").write_text("")
    config_path = root / "lab.json"
    config_path.write_text(
        json.dumps(
            {
                "strategies": [
                    {
                        "strategy_id": "production", "display_name": "P",
                        "enabled": True, "kind": "production",
                        "state": "state/production.json",
                        "trades": "state/p-trades", "decisions": "state/production.jsonl"
                    },
                    {
                        "strategy_id": "one", "display_name": "One",
                        "enabled": True, "kind": "production",
                        "state": "state/one.json",
                        "trades": "state/o-trades", "decisions": "state/one.jsonl"
                    },
                    {
                        "strategy_id": "two", "display_name": "Two",
                        "enabled": False, "kind": "production",
                        "state": "state/two.json",
                        "trades": "state/t-trades", "decisions": "state/two.jsonl"
                    }
                ]
            }
        )
    )
    config = load_config(config_path, root=root)
    before = {
        path: path.read_bytes() for path in (root / "state").iterdir()
    }
    assert show_strategy_lab.main(
        ["--config", str(config_path), "--period", "all", "--json"]
    ) == 0
    after = {path: path.read_bytes() for path in (root / "state").iterdir()}
    assert before == after
    assert [item.strategy_id for item in config.strategies if item.enabled] == [
        "production", "one"
    ]
