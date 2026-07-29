from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

import pytest

from app.equity_history import (
    SCHEMA_VERSION,
    EquityHistoryConfig,
    EquitySnapshot,
    SnapshotMetrics,
    SnapshotService,
    SnapshotStorage,
    load_equity_history_config,
    safe_state_hash,
    validate_snapshot,
)
from app.trade_journal import TradeJournalEntry
from app.trading_controller import TradingControllerState
from scripts import backfill_equity_history, show_equity_history


NOW = datetime(2026, 7, 29, 12, tzinfo=timezone.utc)


def history_config(tmp_path, **changes):
    values = {"database_path": tmp_path / "equity.db"}
    values.update(changes)
    return EquityHistoryConfig(**values)


def snapshot(**changes):
    values = {
        "id": None,
        "created_at_utc": NOW.isoformat(),
        "snapshot_at_utc": NOW.isoformat(),
        "strategy_name": "production",
        "environment": "production",
        "symbol": "ETHUSDT",
        "timeframe": "60",
        "candle_open_timestamp": int(NOW.timestamp()) - 3600,
        "candle_close_timestamp": int(NOW.timestamp()),
        "market_price": Decimal("100"),
        "cash_balance": Decimal("1000"),
        "asset_quantity": Decimal("0"),
        "position_side": "FLAT",
        "entry_price": None,
        "position_value": Decimal("0"),
        "equity": Decimal("1000"),
        "realized_pnl": Decimal("0"),
        "unrealized_pnl": Decimal("0"),
        "total_pnl": Decimal("0"),
        "return_pct": Decimal("0"),
        "peak_equity": Decimal("1000"),
        "drawdown_pct": Decimal("0"),
        "cumulative_fees": Decimal("0"),
        "closed_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "win_rate": None,
        "profit_factor": None,
        "gross_profit": Decimal("0"),
        "gross_loss": Decimal("0"),
        "exposure_pct": Decimal("0"),
        "state_version": "1",
        "state_hash": "a" * 64,
        "source_cycle_id": "cycle-1",
        "snapshot_reason": "cycle",
        "is_complete": True,
        "data_quality_status": "VALID",
        "warning_code": None,
    }
    values.update(changes)
    return EquitySnapshot(**values)


def trade(timestamp=1, pnl="10", balance="1010"):
    closed = NOW + timedelta(seconds=timestamp)
    return TradeJournalEntry(
        record_id=f"trade-{timestamp}", symbol="ETHUSDT",
        opened_at=(closed - timedelta(hours=1)).isoformat(),
        closed_at=closed.isoformat(), entry_price=Decimal("100"),
        exit_price=Decimal("110"), quantity=Decimal("1"),
        entry_notional=Decimal("100"), exit_notional=Decimal("110"),
        gross_pnl=Decimal("10"), entry_fee=Decimal(".1"),
        exit_fee=Decimal(".11"), total_fee=Decimal(".21"),
        net_pnl=Decimal(pnl), pnl_percent=Decimal("10"),
        exit_reason="signal", remaining_position_quantity=Decimal("0"),
        virtual_balance_after=Decimal(balance),
        realized_pnl_after=Decimal(pnl), closed_trades_after=1,
    )


def insert_series(
    storage, environment="production", values=(1000, 1010), start=None,
    interval=timedelta(hours=1),
):
    start = start or NOW - timedelta(days=1)
    rows = []
    peak = Decimal("0")
    for index, value in enumerate(values):
        equity = Decimal(str(value))
        peak = max(peak, equity)
        at = start + interval * index
        item = snapshot(
            environment=environment,
            strategy_name=("production" if environment == "production" else "candidate_adx_hybrid"),
            snapshot_at_utc=at.isoformat(),
            candle_open_timestamp=int(at.timestamp()) - 3600,
            candle_close_timestamp=int(at.timestamp()),
            source_cycle_id=f"{environment}-{index}",
            equity=equity, cash_balance=equity,
            total_pnl=equity - Decimal("1000"),
            return_pct=(equity - Decimal("1000")) / Decimal("10"),
            peak_equity=peak,
            drawdown_pct=(peak - equity) / peak * 100 if peak else Decimal("0"),
        )
        rows.append(storage.insert(item)[0])
    return rows


def test_storage_creates_db_schema_and_version(tmp_path):
    storage = SnapshotStorage(tmp_path / "nested/equity.db")
    storage.connect().close()
    assert storage.schema_version() == SCHEMA_VERSION
    assert storage.path.exists()
    with storage.connect() as connection:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {"schema_version", "equity_snapshots"} <= tables


def test_migration_is_idempotent(tmp_path):
    storage = SnapshotStorage(tmp_path / "equity.db")
    storage.connect().close()
    assert storage.schema_version() == storage.schema_version() == 1
    with storage.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 1


def test_indexes_exist(tmp_path):
    storage = SnapshotStorage(tmp_path / "equity.db")
    storage.connect().close()
    with storage.connect() as connection:
        names = {
            row[1] for row in connection.execute(
                "PRAGMA index_list(equity_snapshots)"
            )
        }
    assert {
        "idx_equity_strategy", "idx_equity_environment",
        "idx_equity_snapshot_at", "idx_equity_candle_close",
        "idx_equity_cycle", "idx_equity_state_hash",
        "idx_equity_env_snapshot", "idx_equity_env_candle",
    } <= names


def test_insert_and_duplicate_prevention(tmp_path):
    storage = SnapshotStorage(tmp_path / "equity.db")
    first, created = storage.insert(snapshot())
    second, duplicated = storage.insert(snapshot(state_hash="b" * 64))
    assert created is True
    assert duplicated is False
    assert first.id == second.id
    assert storage.count() == 1
    assert SnapshotMetrics(storage, history_config(tmp_path)).quality()[
        "duplicates_prevented"
    ] == 1


def test_query_environment_and_date_range(tmp_path):
    storage = SnapshotStorage(tmp_path / "equity.db")
    insert_series(storage, "production")
    insert_series(storage, "candidate")
    rows = storage.query(
        environment="production",
        start=NOW - timedelta(days=1),
        end=NOW,
    )
    assert len(rows) == 2
    assert {item.environment for item in rows} == {"production"}


def test_concurrent_insert_is_atomic(tmp_path):
    storage = SnapshotStorage(tmp_path / "equity.db")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: storage.insert(snapshot())[1], range(8)))
    assert sum(results) == 1
    assert storage.count() == 1


@pytest.mark.parametrize(
    ("change", "warning"),
    [
        ({"cash_balance": Decimal("-1")}, "NEGATIVE_BALANCE_OR_QUANTITY"),
        ({"asset_quantity": Decimal("-1")}, "NEGATIVE_BALANCE_OR_QUANTITY"),
        ({"cumulative_fees": Decimal("-1")}, "NEGATIVE_FEES_OR_DRAWDOWN"),
        ({"drawdown_pct": Decimal("-1")}, "NEGATIVE_FEES_OR_DRAWDOWN"),
        ({"closed_trades": 0, "winning_trades": 1}, "TRADE_COUNTS_INCONSISTENT"),
        ({"candle_close_timestamp": int(NOW.timestamp()) - 7200}, "CANDLE_TIMESTAMPS_INVALID"),
        ({"position_side": "LONG", "asset_quantity": Decimal("0")}, "POSITION_INCONSISTENT"),
        ({"position_side": "FLAT", "asset_quantity": Decimal("1")}, "FLAT_WITH_QUANTITY"),
        ({"equity": Decimal("NaN")}, "NON_FINITE"),
        ({"state_hash": "not-a-hash"}, "STATE_HASH_INVALID"),
    ],
)
def test_data_quality_validation(change, warning):
    result = validate_snapshot(snapshot(**change))
    assert result.data_quality_status == "INVALID"
    assert result.is_complete is False
    assert result.warning_code == warning


@pytest.mark.parametrize("environment", ["unknown", "", "PRODUCTION"])
def test_unknown_environment_rejected(environment):
    with pytest.raises(ValueError):
        validate_snapshot(snapshot(environment=environment))


@pytest.mark.parametrize("reason", ["unknown", "", "hold"])
def test_unknown_reason_rejected(reason):
    with pytest.raises(ValueError):
        validate_snapshot(snapshot(snapshot_reason=reason))


@pytest.mark.parametrize(
    "changes",
    [
        {"database_path": ""},
        {"timezone": "Mars/Olympus"},
        {"reconciliation_tolerance": Decimal("0")},
        {"max_boundary_age_seconds": 0},
        {"minimum_window_completeness_pct": -1},
        {"minimum_window_completeness_pct": 101},
        {"daily_snapshot_hour": 24},
        {"daily_snapshot_minute": 60},
        {"snapshot_retention_days": 7},
    ],
)
def test_config_validation(tmp_path, changes):
    changes.setdefault("database_path", tmp_path / "x.db")
    with pytest.raises(ValueError):
        EquityHistoryConfig(**changes)


def test_config_defaults_and_old_missing_file(tmp_path):
    loaded = load_equity_history_config(tmp_path / "missing.json", root=tmp_path)
    assert loaded.database_path == tmp_path / "state/equity_history.db"
    assert loaded.snapshot_retention_days is None


def test_state_hash_is_deterministic_and_secret_free():
    kwargs = dict(
        balance="1000", quantity="1", entry_price="100", last_candle=1,
        fees=".1", trades=2, environment="production", strategy="production",
    )
    first = safe_state_hash(**kwargs)
    second = safe_state_hash(**kwargs)
    assert first == second
    assert len(first) == 64
    assert "1000" not in first


@pytest.mark.parametrize(
    ("price", "expected_equity", "expected_unrealized"),
    [("110", "1009.9", "9.9"), ("90", "989.9", "-10.1")],
)
def test_service_open_long_profit_and_loss(
    tmp_path, price, expected_equity, expected_unrealized
):
    config = history_config(tmp_path)
    service = SnapshotService(SnapshotStorage(config.database_path), config)
    state = TradingControllerState(
        position_quantity=Decimal("1"), entry_price=Decimal("100"),
        virtual_balance=Decimal("899.9"), entry_fee=Decimal(".1"),
        opened_at=NOW.isoformat(),
    )
    result, created = service.capture(
        environment="production", strategy_name="production", state=state,
        trades=[], market_price=Decimal(price),
        candle_open_timestamp=int(NOW.timestamp()) - 3600,
        snapshot_at=NOW,
    )
    assert created is True
    assert str(result.equity) == expected_equity
    assert str(result.unrealized_pnl) == expected_unrealized
    assert result.position_value == Decimal(price)
    assert result.cumulative_fees == Decimal(".1")


def test_service_flat_and_closed_trade_metrics(tmp_path):
    config = history_config(tmp_path)
    service = SnapshotService(SnapshotStorage(config.database_path), config)
    state = TradingControllerState(
        virtual_balance=Decimal("1010"), total_fees=Decimal(".21"),
        realized_pnl=Decimal("10"), closed_trades=1,
    )
    result, _ = service.capture(
        environment="production", strategy_name="production", state=state,
        trades=[trade()], market_price=Decimal("110"),
        candle_open_timestamp=int(NOW.timestamp()) - 3600,
    )
    assert result.position_side == "FLAT"
    assert result.asset_quantity == 0
    assert result.realized_pnl == 10
    assert result.winning_trades == 1
    assert result.win_rate == 100
    assert result.profit_factor is None


def test_service_reconciliation_and_tolerance(tmp_path):
    config = history_config(tmp_path, reconciliation_tolerance=Decimal(".000001"))
    service = SnapshotService(SnapshotStorage(config.database_path), config)
    state = TradingControllerState()
    result, _ = service.capture(
        environment="production", strategy_name="production", state=state,
        trades=[], market_price=Decimal("100"),
        candle_open_timestamp=int(NOW.timestamp()) - 3600,
    )
    assert result.data_quality_status == "VALID"
    assert result.equity == state.virtual_balance


@pytest.mark.parametrize("market_price", [None, Decimal("0"), Decimal("-1")])
def test_open_position_invalid_price_is_not_fabricated(tmp_path, market_price):
    service = SnapshotService(
        SnapshotStorage(tmp_path / "x.db"), history_config(tmp_path)
    )
    state = TradingControllerState(
        position_quantity=Decimal("1"), entry_price=Decimal("100"),
        virtual_balance=Decimal("899.9"), entry_fee=Decimal(".1"),
        opened_at=NOW.isoformat(),
    )
    result, created = service.capture(
        environment="production", strategy_name="production", state=state,
        trades=[], market_price=market_price,
        candle_open_timestamp=int(NOW.timestamp()) - 3600,
    )
    assert result is None
    assert created is False


@pytest.mark.parametrize(
    ("values", "expected_peak", "expected_last_dd"),
    [
        ((1000, 1100), "1100.0", "0.0"),
        ((1000, 1000), "1000.0", "0.0"),
        ((1000, 900), "1000.0", "10.0"),
        ((1000, 900, 1100), "1100.0", "0.0"),
    ],
)
def test_peak_and_drawdown_rebuild(tmp_path, values, expected_peak, expected_last_dd):
    storage = SnapshotStorage(tmp_path / "equity.db")
    rows = insert_series(storage, values=values)
    with storage.connect() as connection:
        connection.execute(
            "UPDATE equity_snapshots SET peak_equity=1,drawdown_pct=0"
        )
    assert storage.rebuild_equity_peaks("production") == len(values)
    latest = storage.latest("production")
    assert str(latest.peak_equity) == expected_peak
    assert str(latest.drawdown_pct) == expected_last_dd
    assert storage.rebuild_equity_peaks("production") == len(values)


def test_peaks_are_separate_by_environment(tmp_path):
    storage = SnapshotStorage(tmp_path / "equity.db")
    insert_series(storage, "production", (1000, 1200))
    insert_series(storage, "candidate", (1000, 900))
    storage.rebuild_equity_peaks("candidate")
    assert storage.latest("production").peak_equity == Decimal("1200.0")
    assert storage.latest("candidate").peak_equity == Decimal("1000.0")


def test_daily_snapshot_once_per_local_day(tmp_path):
    config = history_config(tmp_path, daily_snapshot_hour=10, daily_snapshot_minute=0)
    service = SnapshotService(SnapshotStorage(config.database_path), config)
    base = snapshot(id=1)
    first, created = service.maybe_daily_close(base, now=NOW)
    second, duplicate = service.maybe_daily_close(base, now=NOW)
    assert created is True
    assert duplicate is False
    assert first.id == second.id


def test_daily_snapshot_before_threshold_is_skipped(tmp_path):
    config = history_config(tmp_path, daily_snapshot_hour=18)
    service = SnapshotService(SnapshotStorage(config.database_path), config)
    assert service.maybe_daily_close(snapshot(), now=NOW) == (None, False)


@pytest.mark.parametrize("window", ["24h", "7d", "14d", "30d"])
def test_rolling_windows_exact_boundary(tmp_path, window):
    config = history_config(tmp_path)
    storage = SnapshotStorage(config.database_path)
    duration = {"24h": timedelta(hours=24), "7d": timedelta(days=7),
                "14d": timedelta(days=14), "30d": timedelta(days=30)}[window]
    insert_series(
        storage, values=(1000, 1100), start=NOW - duration,
        interval=duration,
    )
    result = SnapshotMetrics(storage, config).rolling(
        window=window, environment="production", now=NOW
    )
    assert result["status"] == "AVAILABLE"
    assert result["boundary_exact"] is True
    assert result["pnl"] == "100.0"


def test_rolling_all(tmp_path):
    config = history_config(tmp_path)
    storage = SnapshotStorage(config.database_path)
    insert_series(storage, values=(1000, 900, 1100))
    result = SnapshotMetrics(storage, config).rolling("production", "all")
    assert result["status"] == "AVAILABLE"
    assert result["return_percent"] == "10.0"
    assert Decimal(result["max_drawdown_percent"]) >= 0


def test_rolling_missing_boundary_and_old_boundary(tmp_path):
    config = history_config(tmp_path, max_boundary_age_seconds=60)
    storage = SnapshotStorage(config.database_path)
    insert_series(storage, values=(1000, 1010), start=NOW - timedelta(hours=1))
    metrics = SnapshotMetrics(storage, config)
    assert metrics.rolling("production", "7d", now=NOW)["status"] == "INSUFFICIENT_HISTORY"
    storage.insert(snapshot(
        snapshot_at_utc=(NOW - timedelta(days=7, hours=1)).isoformat(),
        candle_open_timestamp=int((NOW - timedelta(days=7, hours=2)).timestamp()),
        candle_close_timestamp=int((NOW - timedelta(days=7, hours=1)).timestamp()),
        source_cycle_id="old",
    ))
    result = metrics.rolling("production", "7d", now=NOW)
    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert "too old" in result["insufficient_reason"]


def test_gaps_completeness_and_no_artificial_fill(tmp_path):
    config = history_config(tmp_path, max_boundary_age_seconds=100000)
    storage = SnapshotStorage(config.database_path)
    insert_series(
        storage, values=(1000, 1010), start=NOW - timedelta(days=7),
        interval=timedelta(days=7),
    )
    result = SnapshotMetrics(storage, config).rolling(
        "production", "7d", now=NOW
    )
    assert result["completeness_pct"] < 100
    assert result["missing_days"] >= 0
    assert result["missing_intervals"] == 1


def test_daily_aggregate_best_worst_flat_and_volatility(tmp_path):
    config = history_config(tmp_path)
    storage = SnapshotStorage(config.database_path)
    insert_series(
        storage, values=(1000, 1100, 1100, 990),
        start=NOW - timedelta(days=3),
    )
    # Move each snapshot to a separate day without inventing missing days.
    with storage.connect() as connection:
        for index, row in enumerate(connection.execute(
            "SELECT id FROM equity_snapshots ORDER BY id"
        ).fetchall()):
            connection.execute(
                "UPDATE equity_snapshots SET snapshot_at_utc=? WHERE id=?",
                ((NOW - timedelta(days=3-index)).isoformat(), row[0]),
            )
    result = SnapshotMetrics(storage, config).aggregate("production")
    assert result["positive_days"] == 1
    assert result["negative_days"] == 1
    assert result["flat_days"] == 1
    assert result["best_day"]["return_percent"] > 0
    assert result["worst_day"]["return_percent"] < 0
    assert result["daily_volatility"] != "N/A"


@pytest.mark.parametrize(
    ("candidate_prices", "candidate_market", "expected"),
    [
        ((1000, 1100), Decimal("100"), "COMPATIBLE"),
        ((1000,), Decimal("100"), "PARTIAL"),
        ((1000, 1100), Decimal("101"), "INCOMPATIBLE"),
    ],
)
def test_history_comparison_statuses(
    tmp_path, candidate_prices, candidate_market, expected
):
    storage = SnapshotStorage(tmp_path / "equity.db")
    production = insert_series(storage, "production", (1000, 1050))
    candidate = insert_series(storage, "candidate", candidate_prices)
    if candidate_market != Decimal("100"):
        with storage.connect() as connection:
            connection.execute(
                "UPDATE equity_snapshots SET market_price=? WHERE environment='candidate'",
                (float(candidate_market),),
            )
    result = SnapshotMetrics(storage, history_config(tmp_path)).compare()
    assert result["comparable_history_status"] == expected
    if expected == "COMPATIBLE":
        assert result["comparable_snapshot_count"] == 2
        assert result["return_delta"] != "N/A"


def test_history_comparison_no_overlap(tmp_path):
    storage = SnapshotStorage(tmp_path / "equity.db")
    insert_series(storage, "production")
    insert_series(storage, "candidate", start=NOW)
    assert SnapshotMetrics(storage, history_config(tmp_path)).compare()[
        "comparable_history_status"
    ] == "INSUFFICIENT"


def test_quality_summary_counts_invalid_and_gaps(tmp_path):
    storage = SnapshotStorage(tmp_path / "equity.db")
    storage.insert(snapshot())
    storage.insert(snapshot(
        source_cycle_id="bad", candle_close_timestamp=int(NOW.timestamp()) + 10800,
        snapshot_at_utc=(NOW + timedelta(hours=3)).isoformat(),
        cash_balance=Decimal("-1"),
    ))
    result = SnapshotMetrics(storage, history_config(tmp_path)).quality()
    assert result["total_snapshots"] == 2
    assert result["valid"] == 1
    assert result["invalid"] == 1


def test_cli_show_is_read_only_after_schema_exists(
    tmp_path, capsys, monkeypatch
):
    monkeypatch.delenv("EQUITY_HISTORY_DB_PATH")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"database_path": "equity.db"}))
    storage = SnapshotStorage(tmp_path / "equity.db")
    storage.insert(snapshot())
    before = storage.path.read_bytes()
    assert show_equity_history.main(
        ["--config", str(config_path), "--environment", "production", "--json"]
    ) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == 1
    assert storage.path.read_bytes() == before
    assert storage.count("production") == 1


def test_backfill_dry_run_and_apply_are_deterministic(tmp_path, monkeypatch):
    monkeypatch.delenv("EQUITY_HISTORY_DB_PATH")
    journal = tmp_path / "trades.jsonl"
    journal.write_text(json.dumps(trade().to_dict()) + "\n")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"database_path": "equity.db"}))
    dry_args = backfill_equity_history.parser().parse_args(
        ["--environment", "production", "--dry-run", "--trades", str(journal),
         "--config", str(config_path)]
    )
    before = journal.read_bytes()
    dry = backfill_equity_history.execute(dry_args)
    assert dry["would_create"] == 1
    assert not (tmp_path / "equity.db").exists()
    apply_args = backfill_equity_history.parser().parse_args(
        ["--environment", "production", "--apply", "--trades", str(journal),
         "--config", str(config_path)]
    )
    first = backfill_equity_history.execute(apply_args)
    second = backfill_equity_history.execute(apply_args)
    assert first["created"] == 1
    assert second["skipped"] == 1
    assert journal.read_bytes() == before


def test_backfill_incomplete_source_is_reported(tmp_path):
    args = backfill_equity_history.parser().parse_args(
        ["--environment", "candidate", "--dry-run",
         "--trades", str(tmp_path / "missing.jsonl")]
    )
    result = backfill_equity_history.execute(args)
    assert result["confirmed_records"] == 0
    assert result["would_create"] == 0
    assert "no artificial" in result["reason"]


@pytest.mark.parametrize(
    "reason",
    ["cycle", "daily_close", "trade_open", "trade_close",
     "startup_recovery", "manual_backfill"],
)
def test_all_snapshot_reasons_are_storable(tmp_path, reason):
    storage = SnapshotStorage(tmp_path / "equity.db")
    item, created = storage.insert(snapshot(
        snapshot_reason=reason,
        source_cycle_id=f"{reason}-1",
        candle_close_timestamp=int(NOW.timestamp()) + len(reason),
        candle_open_timestamp=int(NOW.timestamp()) + len(reason) - 3600,
    ))
    assert created is True
    assert item.snapshot_reason == reason


def test_unsupported_rolling_window_rejected(tmp_path):
    metrics = SnapshotMetrics(
        SnapshotStorage(tmp_path / "equity.db"), history_config(tmp_path)
    )
    with pytest.raises(ValueError):
        metrics.rolling("production", "90d")


def test_empty_quality_and_aggregate_are_nullable(tmp_path):
    metrics = SnapshotMetrics(
        SnapshotStorage(tmp_path / "equity.db"), history_config(tmp_path)
    )
    assert metrics.quality()["total_snapshots"] == 0
    assert metrics.quality()["largest_gap_seconds"] == "N/A"
    assert metrics.aggregate("production")["status"] == "INSUFFICIENT_HISTORY"


def test_query_by_strategy_name(tmp_path):
    storage = SnapshotStorage(tmp_path / "equity.db")
    storage.insert(snapshot())
    storage.insert(snapshot(
        strategy_name="other", source_cycle_id="other",
        candle_close_timestamp=int(NOW.timestamp()) + 1,
        candle_open_timestamp=int(NOW.timestamp()) - 3599,
    ))
    rows = storage.query(strategy_name="other")
    assert len(rows) == 1
    assert rows[0].strategy_name == "other"


def test_daily_creation_can_be_disabled(tmp_path):
    config = history_config(tmp_path, create_daily_snapshots=False)
    service = SnapshotService(SnapshotStorage(config.database_path), config)
    assert service.maybe_daily_close(snapshot(), now=NOW) == (None, False)


def test_disabled_history_does_not_write(tmp_path):
    config = history_config(tmp_path, enabled=False)
    service = SnapshotService(SnapshotStorage(config.database_path), config)
    result = service.capture(
        environment="production", strategy_name="production",
        state=TradingControllerState(), trades=[],
        market_price=Decimal("100"),
        candle_open_timestamp=int(NOW.timestamp()) - 3600,
    )
    assert result == (None, False)
    assert not config.database_path.exists()


def test_current_and_longest_drawdown_duration(tmp_path):
    config = history_config(tmp_path)
    storage = SnapshotStorage(config.database_path)
    insert_series(
        storage, values=(1000, 900, 1000),
        start=NOW - timedelta(hours=2),
    )
    result = SnapshotMetrics(storage, config).aggregate("production")
    assert result["longest_drawdown_duration_seconds"] == 3600
    assert result["recovery_duration_seconds"] == 3600


def test_partial_snapshot_is_excluded_from_financial_queries(tmp_path):
    storage = SnapshotStorage(tmp_path / "equity.db")
    storage.insert(snapshot(
        data_quality_status="PARTIAL", is_complete=False,
        source_cycle_id="partial",
    ))
    assert storage.count("production") == 1
    assert storage.query(environment="production", valid_only=True) == []


@pytest.mark.parametrize("frequency", ["daily", "weekly", "monthly"])
def test_period_return_aggregations_do_not_fill_missing_periods(
    tmp_path, frequency
):
    storage = SnapshotStorage(tmp_path / "equity.db")
    insert_series(
        storage, values=(1000, 1100),
        start=NOW - timedelta(days=40), interval=timedelta(days=40),
    )
    result = SnapshotMetrics(
        storage, history_config(tmp_path)
    ).period_returns("production", frequency)
    assert len(result) == 2
    assert result[0]["return_percent"] == "N/A"
    assert Decimal(result[1]["return_percent"]) == Decimal("10")
