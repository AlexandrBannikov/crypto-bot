from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
from time import perf_counter

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.candle_mapper import dataframe_to_candles
from app.data_loader import load_market_data
from app.regime_filter_research import atomic_write
from app.strategy_v2_research import (
    StrategyV2Config,
    build_windows,
    fingerprint_candles,
    run_period,
)
from app.strategy_v2_relaxed import (
    RelaxedPullbackConfig,
    precompute_features,
    relaxed_grid,
    simulate,
)


DATA_PATH = PROJECT_ROOT / "data/eth_usdt_1h_full.csv"
OUTPUT = PROJECT_ROOT / "reports/strategy_v2"
GROUPS = {
    "pullback": (False, False, "baseline"),
    "atr_pullback": (True, False, "atr"),
    "adx_pullback": (False, True, "adx"),
    "atr_adx_pullback": (True, True, "atr_adx"),
}


def git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def result_metrics(simulation, start_timestamp: int, end_timestamp: int):
    result = simulation.result
    years = max(1, end_timestamp - start_timestamp) / (
        365.2425 * 24 * 60 * 60
    )
    annualized = (
        (result.final_balance / result.initial_balance) ** (1 / years)
        - 1
    ) * 100
    return {
        "return_percent": result.total_return_percent,
        "annualized_return_percent": annualized,
        "final_balance": result.final_balance,
        "maximum_drawdown_percent": result.max_drawdown_percent,
        "profit_factor": result.profit_factor,
        "win_rate_percent": result.win_rate_percent,
        "average_trade": simulation.average_trade,
        "exposure_percent": simulation.exposure_percent,
        "fees": simulation.total_fees,
        "trades": len(result.trades),
    }


def pullback_metrics(simulation):
    stats = simulation.stats
    return {
        "blocked_entries": stats.blocked_entries,
        "ema_signals": stats.ema_signals,
        "confirmed_pullbacks": stats.confirmed,
        "confirmation_rate_percent": (
            stats.confirmed / stats.ema_signals * 100
            if stats.ema_signals
            else 0.0
        ),
        "timeout_count": stats.timed_out,
        "cancelled_count": stats.cancelled,
        "average_wait_bars": (
            statistics.fmean(stats.wait_bars) if stats.wait_bars else 0.0
        ),
        "median_wait_bars": (
            statistics.median(stats.wait_bars) if stats.wait_bars else 0.0
        ),
        "average_entry_improvement_percent": (
            statistics.fmean(stats.improvements)
            if stats.improvements
            else 0.0
        ),
        "median_entry_improvement_percent": (
            statistics.median(stats.improvements)
            if stats.improvements
            else 0.0
        ),
        "worst_entry_deterioration_percent": (
            min(stats.improvements) if stats.improvements else 0.0
        ),
        "worse_entry_count": stats.worse_entries,
        "worse_entry_percent": (
            stats.worse_entries / len(stats.improvements) * 100
            if stats.improvements
            else 0.0
        ),
    }


def run_control(features, trade_start_index: int):
    controls = {}
    for group, (use_atr, use_adx, control_name) in GROUPS.items():
        controls[control_name] = simulate(
            features,
            trade_start_index=trade_start_index,
            use_atr=use_atr,
            use_adx=use_adx,
        )
    return controls


def run_all():
    started = perf_counter()
    config = StrategyV2Config()
    data = load_market_data(DATA_PATH).iloc[:-1].copy()
    candles = dataframe_to_candles(data)
    features_started = perf_counter()
    full_features = precompute_features(candles)
    feature_seconds = perf_counter() - features_started
    boundary = pd.Timestamp(config.train_end, tz="UTC")
    trade_start_index = int((data["datetime"] < boundary).sum())
    controls = run_control(full_features, trade_start_index)
    configurations = relaxed_grid()
    grid_rows = []
    simulations = {}

    for candidate in configurations:
        for group, (use_atr, use_adx, control_name) in GROUPS.items():
            simulation = simulate(
                full_features,
                trade_start_index=trade_start_index,
                pullback=candidate,
                use_atr=use_atr,
                use_adx=use_adx,
            )
            simulations[(candidate.identifier, group)] = simulation
            control = controls[control_name]
            metrics = result_metrics(
                simulation,
                candles[trade_start_index].timestamp,
                candles[-1].timestamp,
            )
            control_metrics = result_metrics(
                control,
                candles[trade_start_index].timestamp,
                candles[-1].timestamp,
            )
            retained = (
                metrics["trades"] / control_metrics["trades"] * 100
                if control_metrics["trades"]
                else 0.0
            )
            primary = (
                retained >= 50
                and metrics["maximum_drawdown_percent"]
                <= control_metrics["maximum_drawdown_percent"]
                and metrics["profit_factor"]
                >= control_metrics["profit_factor"] - 0.03
            )
            grid_rows.append(
                {
                    "configuration_id": candidate.identifier,
                    "group": group,
                    "control": control_name,
                    "mode": candidate.mode.value,
                    "max_wait_bars": candidate.max_wait_bars,
                    "tolerance": candidate.tolerance,
                    "retrace_pct": candidate.retrace_pct,
                    **metrics,
                    **pullback_metrics(simulation),
                    "retained_trades_percent": retained,
                    "control_return_percent": control_metrics[
                        "return_percent"
                    ],
                    "control_maximum_drawdown_percent": control_metrics[
                        "maximum_drawdown_percent"
                    ],
                    "control_profit_factor": control_metrics[
                        "profit_factor"
                    ],
                    "control_trades": control_metrics["trades"],
                    "passes_primary_filter": primary,
                }
            )

    walk_rows = []
    for window in build_windows(data, config):
        history = data[
            (data["datetime"] >= window.train_start)
            & (data["datetime"] < window.test_end)
        ].copy()
        history_candles = dataframe_to_candles(history)
        history_features = precompute_features(history_candles)
        start_index = int(
            (history["datetime"] < window.test_start).sum()
        )
        window_controls = run_control(history_features, start_index)
        for candidate in configurations:
            for group, (use_atr, use_adx, control_name) in GROUPS.items():
                simulation = simulate(
                    history_features,
                    trade_start_index=start_index,
                    pullback=candidate,
                    use_atr=use_atr,
                    use_adx=use_adx,
                )
                candidate_metrics = result_metrics(
                    simulation,
                    history_candles[start_index].timestamp,
                    history_candles[-1].timestamp,
                )
                control_metrics = result_metrics(
                    window_controls[control_name],
                    history_candles[start_index].timestamp,
                    history_candles[-1].timestamp,
                )
                walk_rows.append(
                    {
                        "configuration_id": candidate.identifier,
                        "group": group,
                        "window": window.number,
                        **candidate_metrics,
                        **pullback_metrics(simulation),
                        "control_return_percent": control_metrics[
                            "return_percent"
                        ],
                        "control_profit_factor": control_metrics[
                            "profit_factor"
                        ],
                        "control_trades": control_metrics["trades"],
                    }
                )

    grouped_walk = {}
    for row in walk_rows:
        grouped_walk.setdefault(
            (row["configuration_id"], row["group"]), []
        ).append(row)
    for row in grid_rows:
        windows = grouped_walk[(row["configuration_id"], row["group"])]
        returns = [item["return_percent"] for item in windows]
        deltas = [
            item["return_percent"] - item["control_return_percent"]
            for item in windows
        ]
        compounded = math.prod(1 + value / 100 for value in returns)
        row.update(
            {
                "profitable_walk_forward_windows": sum(
                    value > 0 for value in returns
                ),
                "walk_forward_windows_better_than_control": sum(
                    value >= 0 for value in deltas
                ),
                "compounded_walk_forward_return_percent": (
                    compounded - 1
                )
                * 100,
                "median_walk_forward_profit_factor": statistics.median(
                    item["profit_factor"] for item in windows
                ),
                "worst_walk_forward_return_percent": min(returns),
                "median_walk_forward_return_delta_percent": (
                    statistics.median(deltas)
                ),
            }
        )
        row["passes_success_criteria"] = (
            row["return_percent"] >= row["control_return_percent"]
            and row["maximum_drawdown_percent"]
            <= row["control_maximum_drawdown_percent"]
            and row["profit_factor"] >= row["control_profit_factor"] - 0.03
            and row["retained_trades_percent"] >= 60
            and row["average_entry_improvement_percent"] > 0
            and row["worse_entry_percent"] <= 20
            and row["walk_forward_windows_better_than_control"] >= 3
            and row["median_walk_forward_return_delta_percent"] >= 0
        )

    benchmark_size = min(5000, len(data))
    benchmark_data = data.iloc[:benchmark_size].copy()
    before_started = perf_counter()
    legacy, _ = run_period(
        benchmark_data,
        period="benchmark",
        variant="atr_adx",
        config=config,
    )
    before_seconds = perf_counter() - before_started
    benchmark_candles = dataframe_to_candles(benchmark_data)
    after_started = perf_counter()
    benchmark_features = precompute_features(benchmark_candles)
    optimized = simulate(
        benchmark_features,
        use_atr=True,
        use_adx=True,
    )
    after_seconds = perf_counter() - after_started
    equivalent = (
        math.isclose(
            legacy.final_balance,
            optimized.result.final_balance,
            rel_tol=1e-12,
            abs_tol=1e-9,
        )
        and legacy.trades == len(optimized.result.trades)
        and math.isclose(
            legacy.maximum_drawdown_percent,
            optimized.result.max_drawdown_percent,
            rel_tol=1e-12,
            abs_tol=1e-9,
        )
    )
    if not equivalent:
        raise RuntimeError("optimized control benchmark is not equivalent")

    elapsed = perf_counter() - started
    eligible = [row for row in grid_rows if row["passes_primary_filter"]]
    top = sorted(
        eligible,
        key=lambda row: (
            row["passes_success_criteria"],
            row["walk_forward_windows_better_than_control"],
            row["median_walk_forward_return_delta_percent"],
            row["return_percent"],
        ),
        reverse=True,
    )[:10]
    best_by_group = {}
    for group in GROUPS:
        selected = [row for row in eligible if row["group"] == group]
        best_by_group[group] = (
            sorted(
                selected,
                key=lambda row: (
                    row["passes_success_criteria"],
                    row["walk_forward_windows_better_than_control"],
                    row["median_walk_forward_return_delta_percent"],
                    row["return_percent"],
                ),
                reverse=True,
            )[0]
            if selected
            else None
        )
    summary = {
        "configuration_count": len(configurations),
        "evaluated_strategy_combinations": len(grid_rows),
        "primary_filter_pass_count": len(eligible),
        "success_count": sum(
            row["passes_success_criteria"] for row in grid_rows
        ),
        "top_10_primary_filter": top,
        "best_by_group": best_by_group,
    }
    metadata = {
        "source_commit": git_commit(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_path": str(DATA_PATH.resolve()),
        "data_fingerprint": fingerprint_candles(candles),
        "candles": len(candles),
        "configuration_count": len(configurations),
        "parameters": [asdict(item) for item in configurations],
        "runtime_seconds": elapsed,
        "feature_precompute_seconds": feature_seconds,
        "equivalence_benchmark": {
            "candles": benchmark_size,
            "legacy_seconds": before_seconds,
            "optimized_seconds": after_seconds,
            "speedup": before_seconds / after_seconds,
            "equivalent": equivalent,
        },
        "caching": {
            "ema_atr_adx": "precomputed once per immutable period",
            "dataset_reads": 1,
            "controls": "one simulation per period/group",
            "parallelism": "none; deterministic order",
        },
    }
    return grid_rows, walk_rows, summary, metadata


def write_csv(path: Path, rows):
    output = io.StringIO()
    writer = csv.DictWriter(
        output, fieldnames=list(rows[0]), lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(path, output.getvalue())


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def main() -> int:
    grid, walk, summary, metadata = run_all()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "pullback_relaxed_grid.csv", grid)
    write_csv(OUTPUT / "pullback_relaxed_walk_forward.csv", walk)
    atomic_write(
        OUTPUT / "pullback_relaxed_summary.json",
        json.dumps(json_safe(summary), indent=2) + "\n",
    )
    atomic_write(
        OUTPUT / "pullback_relaxed_metadata.json",
        json.dumps(json_safe(metadata), indent=2) + "\n",
    )
    print(
        json.dumps(
            {
                "configurations": metadata["configuration_count"],
                "combinations": len(grid),
                "walk_forward_rows": len(walk),
                "runtime_seconds": metadata["runtime_seconds"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
