import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from scripts import compare_regime_filters
from app.candle import Candle
from app.market_regime import (
    MarketRegime,
    MarketTrend,
    MarketVolatility,
)


def write_market_data(path: Path, *, periods: int = 320) -> None:
    datetimes = pd.date_range(
        "2024-09-01",
        periods=periods,
        freq="12h",
        tz="UTC",
    )
    closes = [
        100.0 + index * 0.05 + (index % 24 - 12) * 0.3
        for index in range(periods)
    ]
    frame = pd.DataFrame(
        {
            "datetime": datetimes,
            "open": closes,
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
            "close": closes,
            "volume": 10.0,
        }
    )
    frame.to_csv(path, index=False)


def test_run_comparison_contains_all_periods_and_variants(
    tmp_path,
) -> None:
    data_path = tmp_path / "market.csv"
    write_market_data(data_path)
    args = compare_regime_filters.build_parser().parse_args(
        ["--data", str(data_path)]
    )
    data = compare_regime_filters.load_market_data(data_path)
    data = data.iloc[:-1].copy()

    results = compare_regime_filters.run_comparison(data, args)

    assert {
        (item.period, item.variant) for item in results
    } == {
        (period, variant)
        for period in ("full", "train", "test")
        for variant in (
            "baseline",
            "detector_only",
            "filtered",
        )
    }


def test_detector_only_financial_results_equal_baseline(
    tmp_path,
) -> None:
    data_path = tmp_path / "market.csv"
    write_market_data(data_path)
    args = compare_regime_filters.build_parser().parse_args(
        ["--data", str(data_path)]
    )
    data = compare_regime_filters.load_market_data(data_path)

    results = compare_regime_filters.run_comparison(data, args)

    for period in ("full", "train", "test"):
        by_variant = {
            item.variant: item
            for item in results
            if item.period == period
        }
        baseline = by_variant["baseline"]
        detector_only = by_variant["detector_only"]
        assert detector_only.final_balance == baseline.final_balance
        assert detector_only.return_percent == baseline.return_percent
        assert detector_only.trades == baseline.trades
        assert detector_only.win_rate_percent == baseline.win_rate_percent
        assert detector_only.profit_factor == baseline.profit_factor
        assert (
            detector_only.maximum_drawdown_percent
            == baseline.maximum_drawdown_percent
        )
        assert detector_only.total_fees == baseline.total_fees


def test_detector_cache_does_not_mix_equal_timestamp_ohlc() -> None:
    regime = MarketRegime(
        MarketTrend.TREND_UP,
        MarketVolatility.NORMAL,
        1.0,
    )
    detector = Mock()
    detector.detect.return_value = regime
    cached = compare_regime_filters.CachingRegimeDetector(detector)
    first = [
        Candle(1, 100.0, 101.0, 99.0, 100.0, 1.0),
        Candle(2, 100.0, 102.0, 99.0, 101.0, 1.0),
    ]
    changed = [
        first[0],
        Candle(2, 100.0, 103.0, 98.0, 102.0, 2.0),
    ]

    cached.detect(first)
    cached.detect(first)
    cached.detect(changed)

    assert detector.detect.call_count == 2


def test_results_sort_by_return_drawdown_and_profit_factor() -> None:
    result = compare_regime_filters.ComparisonResult
    common = {
        "period": "full",
        "final_balance": 1000.0,
        "trades": 1,
        "win_rate_percent": 50.0,
        "total_fees": 1.0,
        "allowed_entries": 1,
        "blocked_entries": 0,
        "blocked_range": 0,
        "blocked_downtrend": 0,
        "blocked_high_volatility": 0,
        "blocked_low_confidence": 0,
        "blocked_unknown_regime": 0,
    }
    items = [
        result(
            variant="lower-return",
            return_percent=1.0,
            maximum_drawdown_percent=1.0,
            profit_factor=5.0,
            **common,
        ),
        result(
            variant="lower-pf",
            return_percent=2.0,
            maximum_drawdown_percent=2.0,
            profit_factor=1.0,
            **common,
        ),
        result(
            variant="higher-pf",
            return_percent=2.0,
            maximum_drawdown_percent=2.0,
            profit_factor=2.0,
            **common,
        ),
        result(
            variant="lower-dd",
            return_percent=2.0,
            maximum_drawdown_percent=1.0,
            profit_factor=1.0,
            **common,
        ),
    ]

    assert [
        item.variant
        for item in compare_regime_filters.sorted_results(items)
    ] == [
        "lower-dd",
        "higher-pf",
        "lower-pf",
        "lower-return",
    ]


def test_json_report_is_saved_atomically(
    tmp_path,
) -> None:
    data_path = tmp_path / "market.csv"
    output_path = tmp_path / "nested/report.json"
    write_market_data(data_path)

    assert compare_regime_filters.main(
        [
            "--data",
            str(data_path),
            "--output",
            str(output_path),
        ]
    ) == 0

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(report["results"]) == 9
    assert not list(output_path.parent.glob("*.tmp"))
    assert not list(output_path.parent.glob(f".{output_path.name}.*"))


def test_cli_works_from_any_cwd_without_project_writes(
    tmp_path,
) -> None:
    data_path = tmp_path / "market.csv"
    output_path = tmp_path / "report.csv"
    write_market_data(data_path)
    script = Path(compare_regime_filters.__file__).resolve()

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--data",
            str(data_path),
            "--output",
            str(output_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Period: full" in completed.stdout
    assert output_path.exists()


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--fast-ema", "50", "--slow-ema", "20"], "fast EMA"),
        (["--adx-period", "0"], "greater than zero"),
        (
            [
                "--low-volatility-threshold",
                "0.03",
                "--high-volatility-threshold",
                "0.02",
            ],
            "low volatility threshold",
        ),
        (["--minimum-confidence", "1.1"], "between 0 and 1"),
    ],
)
def test_invalid_periods_and_thresholds_are_clear(
    arguments,
    message,
    capsys,
) -> None:
    with pytest.raises(SystemExit) as captured:
        compare_regime_filters.main(arguments)

    assert captured.value.code == 2
    assert message in capsys.readouterr().err
