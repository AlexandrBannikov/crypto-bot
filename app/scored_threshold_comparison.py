"""Read-only comparison of the threshold-65 and threshold-60 shadow journals."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Sequence

from app.candle import Candle
from app.runtime_health import read_jsonl_safely


HORIZONS = (3, 6, 12, 24)


def _decision(row: dict) -> str:
    return str(row.get("decision", row.get("action", "UNKNOWN")))


def _score(row: dict) -> float:
    return float(row.get("signal_score", row.get("score", 0)))


def _summary(rows: list[dict], *, minimum_risk_fraction: float, minimum_order_value: float, fee_rate: float, stop_distance_pct: float) -> dict:
    decisions = Counter(_decision(row) for row in rows)
    allocations = [float(row.get("risk_fraction", 0)) for row in rows]
    entries = [row for row in rows if _decision(row) == "ENTER_LONG"]
    positions = [float(row["potential_position_size"]) for row in entries if row.get("potential_position_size") is not None]
    hard_blocks = Counter(block for row in rows for block in row.get("hard_blocks", []))
    fees = [position * 2 * fee_rate for position in positions]
    fee_burdens = [fee / (position * stop_distance_pct) * 100 for position, fee in zip(positions, fees) if position > 0]
    return {
        "decisions": len(rows),
        "ENTER": decisions["ENTER_LONG"],
        "HOLD": decisions["HOLD"],
        "EXIT": decisions["EXIT_LONG"],
        "average_score": mean(_score(row) for row in rows) if rows else None,
        "average_allocation": mean(allocations) if allocations else None,
        "average_hypothetical_position": mean(positions) if positions else None,
        "hard_blocks": dict(hard_blocks),
        "no_signal": hard_blocks["no_signal"],
        "insufficient_data": hard_blocks["insufficient_data"],
        "allocation_distribution": dict(sorted(Counter(f"{value * 100:.2f}%" for value in allocations).items())),
        "economic": {
            "minimum_allocation_entries": sum(float(row.get("risk_fraction", 0)) <= minimum_risk_fraction for row in entries),
            "positions_below_minimum_order": sum(position < minimum_order_value for position in positions),
            "minimum_order_value": minimum_order_value,
            "average_round_trip_commission": mean(fees) if fees else None,
            "total_round_trip_commission": sum(fees),
            "average_commission_to_stop_risk_percent": mean(fee_burdens) if fee_burdens else None,
            "commission_substantial_entries": sum(round(burden, 8) >= 10 for burden in fee_burdens),
        },
    }


def _future_outcome(row: dict, candles: Sequence[Candle]) -> dict:
    by_timestamp = {candle.timestamp: index for index, candle in enumerate(candles)}
    signal_timestamp = int(row.get("candle_timestamp", int(row["candle_close_timestamp"]) - 3600))
    index = by_timestamp.get(signal_timestamp)
    result = {f"return_{hours}h": None for hours in HORIZONS}
    result.update({"mfe_24h": None, "mae_24h": None})
    if index is None:
        return result
    entry = float(candles[index].close)
    for hours in HORIZONS:
        target = index + hours
        if target < len(candles):
            result[f"return_{hours}h"] = (float(candles[target].close) / entry - 1) * 100
    future = candles[index + 1:index + 25]
    if len(future) == 24:
        result["mfe_24h"] = (max(float(candle.high) for candle in future) / entry - 1) * 100
        result["mae_24h"] = (min(float(candle.low) for candle in future) / entry - 1) * 100
    return result


def compare(
    threshold65_path: Path,
    threshold60_path: Path,
    *,
    candles: Sequence[Candle] = (),
    minimum_order_value: float = 5.0,
    fee_rate: float = 0.001,
    stop_distance_pct: float = 0.02,
    minimum_risk_fraction: float = 0.10,
) -> dict:
    rows65 = read_jsonl_safely(threshold65_path)[0] if threshold65_path.exists() else []
    rows60 = read_jsonl_safely(threshold60_path)[0] if threshold60_path.exists() else []
    by65 = {int(row["candle_close_timestamp"]): row for row in rows65}
    by60 = {int(row["candle_close_timestamp"]): row for row in rows60}
    common = sorted(by65.keys() & by60.keys())
    aligned65 = [by65[timestamp] for timestamp in common]
    aligned60 = [by60[timestamp] for timestamp in common]
    mismatches = [timestamp for timestamp in common if _score(by65[timestamp]) != _score(by60[timestamp]) or by65[timestamp].get("components") != by60[timestamp].get("components")]
    extra = [
        by60[timestamp] for timestamp in common
        if 60 <= _score(by60[timestamp]) < 65
        and _decision(by60[timestamp]) == "ENTER_LONG"
        and _decision(by65[timestamp]) != "ENTER_LONG"
    ]
    outcomes = [{"candle_close_timestamp": row["candle_close_timestamp"], "score": _score(row), **_future_outcome(row, candles)} for row in extra]
    aggregate_outcomes = {
        key: mean(float(row[key]) for row in outcomes if row[key] is not None) if any(row[key] is not None for row in outcomes) else None
        for key in [*(f"return_{hours}h" for hours in HORIZONS), "mfe_24h", "mae_24h"]
    }
    return {
        "threshold_65": _summary(aligned65, minimum_risk_fraction=minimum_risk_fraction, minimum_order_value=minimum_order_value, fee_rate=fee_rate, stop_distance_pct=stop_distance_pct),
        "threshold_60": _summary(aligned60, minimum_risk_fraction=minimum_risk_fraction, minimum_order_value=minimum_order_value, fee_rate=fee_rate, stop_distance_pct=stop_distance_pct),
        "alignment": {
            "common_decisions": len(common),
            "threshold_65_only": len(by65.keys() - by60.keys()),
            "threshold_60_only": len(by60.keys() - by65.keys()),
            "score_or_component_mismatches": len(mismatches),
        },
        "near_threshold": {
            "range": "60 <= score < 65",
            "additional_entries": len(extra),
            "average_score": mean(_score(row) for row in extra) if extra else None,
            "signals": outcomes,
            "future_outcomes_percent": aggregate_outcomes,
        },
    }


def render_text(report: dict) -> str:
    lines = ["Scored Candidate threshold comparison (shadow only)"]
    for label, key in (("Threshold 65", "threshold_65"), ("Threshold 60", "threshold_60")):
        item = report[key]
        lines.extend([
            "", label,
            f"Decisions: {item['decisions']}; ENTER: {item['ENTER']}; HOLD: {item['HOLD']}; EXIT: {item['EXIT']}",
            f"Average score: {item['average_score']}; average allocation: {item['average_allocation']}",
            f"Average hypothetical position: {item['average_hypothetical_position']}",
            f"Hard blocks: {item['hard_blocks']}; no_signal: {item['no_signal']}; insufficient_data: {item['insufficient_data']}",
            f"Allocation: {item['allocation_distribution']}",
            f"Economic: {item['economic']}",
        ])
    near = report["near_threshold"]
    lines.extend([
        "", "Near-threshold 60–65",
        f"Additional entries: {near['additional_entries']}; average score: {near['average_score']}",
        f"Future outcomes %: {near['future_outcomes_percent']}",
        f"Alignment: {report['alignment']}",
    ])
    return "\n".join(lines)
