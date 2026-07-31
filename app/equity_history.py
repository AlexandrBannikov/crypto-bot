from __future__ import annotations

from dataclasses import InitVar, asdict, dataclass, fields, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import sqlite3
from statistics import pstdev
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.account_snapshot import calculate_account_snapshot
from app.candidate_runtime import CandidateStateStore
from app.runtime_health import read_jsonl_safely
from app.trade_journal import TradeJournalEntry
from app.trading_controller_store import TradingControllerStateStore


# Keep the public schema version stable for existing readers; the canonical
# index is additive and created idempotently by the migration script.
SCHEMA_VERSION = 1
ENVIRONMENTS = {"production", "candidate"}
SNAPSHOT_REASONS = {
    "cycle", "daily_close", "trade_open", "trade_close",
    "startup_recovery", "manual_backfill",
}
QUALITY_STATUSES = {"VALID", "PARTIAL", "INVALID"}
WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7),
           "14d": timedelta(days=14), "30d": timedelta(days=30)}
NA = "N/A"
LOGGER = logging.getLogger(__name__)


class SnapshotConflictError(ValueError):
    """A canonical candle already has materially different equity state."""


def _snapshots_equivalent(left: "EquitySnapshot", right: "EquitySnapshot") -> bool:
    fields_to_compare = (
        "cash_balance", "asset_quantity", "position_value", "equity",
        "realized_pnl", "unrealized_pnl", "total_pnl", "return_pct",
        "position_side", "entry_price", "closed_trades", "cumulative_fees",
    )
    tolerance = Decimal("0.000001")
    for name in fields_to_compare:
        a, b = getattr(left, name), getattr(right, name)
        if isinstance(a, Decimal) or isinstance(b, Decimal):
            if a is None or b is None:
                if a != b:
                    return False
            elif abs(a - b) > tolerance:
                return False
        elif a != b:
            return False
    return True


@dataclass(frozen=True, slots=True)
class EquityHistoryConfig:
    enabled: bool = True
    database_path: Path = Path("state/equity_history.db")
    timezone: str = "Asia/Yekaterinburg"
    create_cycle_snapshots: bool = True
    create_trade_snapshots: bool = True
    create_daily_snapshots: bool = True
    daily_snapshot_hour: int = 23
    daily_snapshot_minute: int = 59
    reconciliation_tolerance: Decimal = Decimal("0.000001")
    max_boundary_age_seconds: int = 7200
    minimum_window_completeness_pct: float = 80.0
    snapshot_retention_days: int | None = None
    allow_partial_snapshots: bool = True
    require_writable_database_parent: InitVar[bool] = True

    def __post_init__(self, require_writable_database_parent: bool) -> None:
        if not str(self.database_path).strip():
            raise ValueError("database_path must not be empty")
        database_path = Path(self.database_path)
        object.__setattr__(self, "database_path", database_path)
        ancestor = database_path.parent
        while not ancestor.exists() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        if (
            require_writable_database_parent
            and (not ancestor.exists() or not os.access(ancestor, os.W_OK))
        ):
            raise ValueError("equity history database parent is not writable")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("equity history timezone is invalid") from exc
        if self.reconciliation_tolerance <= 0:
            raise ValueError("reconciliation_tolerance must be positive")
        if self.max_boundary_age_seconds <= 0:
            raise ValueError("max_boundary_age_seconds must be positive")
        if not 0 <= self.minimum_window_completeness_pct <= 100:
            raise ValueError("minimum_window_completeness_pct must be in 0..100")
        if not 0 <= self.daily_snapshot_hour <= 23:
            raise ValueError("daily_snapshot_hour must be in 0..23")
        if not 0 <= self.daily_snapshot_minute <= 59:
            raise ValueError("daily_snapshot_minute must be in 0..59")
        if (
            self.snapshot_retention_days is not None
            and self.snapshot_retention_days < 30
        ):
            raise ValueError("snapshot_retention_days must be null or at least 30")


def load_equity_history_config(
    path: Path,
    *,
    root: Path | None = None,
    require_writable_database_parent: bool = True,
) -> EquityHistoryConfig:
    if not path.exists():
        return EquityHistoryConfig(
            database_path=(root or path.parent.parent) / "state/equity_history.db",
            require_writable_database_parent=require_writable_database_parent,
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    base = root or path.parent.parent
    configured_path = Path(
        os.environ.get(
            "EQUITY_HISTORY_DB_PATH",
            raw.get("database_path", "state/equity_history.db"),
        )
    )
    return EquityHistoryConfig(
        enabled=bool(raw.get("enabled", True)),
        database_path=(
            configured_path if configured_path.is_absolute()
            else base / configured_path
        ),
        timezone=str(raw.get("timezone", "Asia/Yekaterinburg")),
        create_cycle_snapshots=bool(raw.get("create_cycle_snapshots", True)),
        create_trade_snapshots=bool(raw.get("create_trade_snapshots", True)),
        create_daily_snapshots=bool(raw.get("create_daily_snapshots", True)),
        daily_snapshot_hour=int(raw.get("daily_snapshot_hour", 23)),
        daily_snapshot_minute=int(raw.get("daily_snapshot_minute", 59)),
        reconciliation_tolerance=Decimal(
            str(raw.get("reconciliation_tolerance", "0.000001"))
        ),
        max_boundary_age_seconds=int(raw.get("max_boundary_age_seconds", 7200)),
        minimum_window_completeness_pct=float(
            raw.get("minimum_window_completeness_pct", 80)
        ),
        snapshot_retention_days=raw.get("snapshot_retention_days"),
        allow_partial_snapshots=bool(raw.get("allow_partial_snapshots", True)),
        require_writable_database_parent=require_writable_database_parent,
    )


@dataclass(frozen=True, slots=True)
class EquitySnapshot:
    id: int | None
    created_at_utc: str
    snapshot_at_utc: str
    strategy_name: str
    environment: str
    symbol: str
    timeframe: str
    candle_open_timestamp: int | None
    candle_close_timestamp: int | None
    market_price: Decimal | None
    cash_balance: Decimal
    asset_quantity: Decimal
    position_side: str
    entry_price: Decimal | None
    position_value: Decimal
    equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    return_pct: Decimal
    peak_equity: Decimal
    drawdown_pct: Decimal
    cumulative_fees: Decimal
    closed_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal | None
    profit_factor: Decimal | None
    gross_profit: Decimal
    gross_loss: Decimal
    exposure_pct: Decimal
    state_version: str | None
    state_hash: str | None
    source_cycle_id: str | None
    snapshot_reason: str
    is_complete: bool
    data_quality_status: str
    warning_code: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            key: (
                str(value) if isinstance(value, Decimal)
                else int(value) if isinstance(value, bool)
                else value
            )
            for key, value in asdict(self).items()
        }


MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS equity_history_stats (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
INSERT OR IGNORE INTO equity_history_stats(key,value)
VALUES ('duplicates_prevented',0);
CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY,
    created_at_utc TEXT NOT NULL,
    snapshot_at_utc TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    environment TEXT NOT NULL CHECK(environment IN ('production','candidate')),
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    candle_open_timestamp INTEGER NULL,
    candle_close_timestamp INTEGER NULL,
    market_price REAL NULL,
    cash_balance REAL NOT NULL,
    asset_quantity REAL NOT NULL,
    position_side TEXT NOT NULL,
    entry_price REAL NULL,
    position_value REAL NOT NULL,
    equity REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    total_pnl REAL NOT NULL,
    return_pct REAL NOT NULL,
    peak_equity REAL NOT NULL,
    drawdown_pct REAL NOT NULL,
    cumulative_fees REAL NOT NULL,
    closed_trades INTEGER NOT NULL,
    winning_trades INTEGER NOT NULL,
    losing_trades INTEGER NOT NULL,
    win_rate REAL NULL,
    profit_factor REAL NULL,
    gross_profit REAL NOT NULL,
    gross_loss REAL NOT NULL,
    exposure_pct REAL NOT NULL,
    state_version TEXT NULL,
    state_hash TEXT NULL,
    source_cycle_id TEXT NULL,
    snapshot_reason TEXT NOT NULL CHECK(snapshot_reason IN
      ('cycle','daily_close','trade_open','trade_close','startup_recovery','manual_backfill')),
    is_complete INTEGER NOT NULL CHECK(is_complete IN (0,1)),
    data_quality_status TEXT NOT NULL CHECK(data_quality_status IN ('VALID','PARTIAL','INVALID')),
    warning_code TEXT NULL,
    UNIQUE(environment, strategy_name, candle_close_timestamp, snapshot_reason),
    UNIQUE(environment, strategy_name, source_cycle_id, snapshot_reason)
);
CREATE INDEX IF NOT EXISTS idx_equity_strategy ON equity_snapshots(strategy_name);
CREATE INDEX IF NOT EXISTS idx_equity_environment ON equity_snapshots(environment);
CREATE INDEX IF NOT EXISTS idx_equity_snapshot_at ON equity_snapshots(snapshot_at_utc);
CREATE INDEX IF NOT EXISTS idx_equity_candle_close ON equity_snapshots(candle_close_timestamp);
CREATE INDEX IF NOT EXISTS idx_equity_cycle ON equity_snapshots(source_cycle_id);
CREATE INDEX IF NOT EXISTS idx_equity_state_hash ON equity_snapshots(state_hash);
CREATE INDEX IF NOT EXISTS idx_equity_env_snapshot ON equity_snapshots(environment, snapshot_at_utc);
CREATE INDEX IF NOT EXISTS idx_equity_env_candle ON equity_snapshots(environment, candle_close_timestamp);
CREATE INDEX IF NOT EXISTS idx_equity_canonical ON equity_snapshots(environment, strategy_name, candle_close_timestamp);
"""


class SnapshotMigration:
    @staticmethod
    def migrate(connection: sqlite3.Connection) -> int:
        with connection:
            connection.executescript(MIGRATION_1)
            row = connection.execute(
                "SELECT MAX(version) FROM schema_version"
            ).fetchone()
            current = int(row[0] or 0)
            if current < SCHEMA_VERSION:
                connection.execute(
                    "INSERT INTO schema_version(version, applied_at_utc) VALUES (?,?)",
                    (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
                )
        return SCHEMA_VERSION


DECIMAL_COLUMNS = {
    "market_price", "cash_balance", "asset_quantity", "entry_price",
    "position_value", "equity", "realized_pnl", "unrealized_pnl",
    "total_pnl", "return_pct", "peak_equity", "drawdown_pct",
    "cumulative_fees", "win_rate", "profit_factor", "gross_profit",
    "gross_loss", "exposure_pct",
}


class SnapshotStorage:
    def __init__(self, path: Path):
        self.path = Path(path)

    def connect(self, *, readonly: bool = False) -> sqlite3.Connection:
        if readonly:
            connection = sqlite3.connect(
                f"file:{self.path}?mode=ro", uri=True, timeout=30
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            return connection
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        SnapshotMigration.migrate(connection)
        try:
            self.path.chmod(0o660)
        except OSError:
            pass
        return connection

    def schema_version(self) -> int:
        if not self.path.exists():
            return 0
        with self.connect(readonly=True) as connection:
            row = connection.execute(
                "SELECT MAX(version) FROM schema_version"
            ).fetchone()
            return int(row[0] or 0)

    def insert(self, snapshot: EquitySnapshot) -> tuple[EquitySnapshot, bool]:
        validated = validate_snapshot(snapshot)
        columns = [field.name for field in fields(EquitySnapshot) if field.name != "id"]
        values = [
            float(getattr(validated, name))
            if isinstance(getattr(validated, name), Decimal)
            else int(getattr(validated, name))
            if isinstance(getattr(validated, name), bool)
            else getattr(validated, name)
            for name in columns
        ]
        placeholders = ",".join("?" for _ in columns)
        with self.connect() as connection:
            # One canonical snapshot is allowed per environment/strategy and
            # processed closed candle. Legacy databases may contain multiple
            # rows from different snapshot reasons; keep the oldest row and
            # report equivalent repeats as ignored until repair is run.
            existing_rows = connection.execute(
                "SELECT * FROM equity_snapshots WHERE environment=? "
                "AND strategy_name=? AND candle_close_timestamp=? "
                "ORDER BY id ASC",
                (
                    validated.environment,
                    validated.strategy_name,
                    validated.candle_close_timestamp,
                ),
            ).fetchall()
            if existing_rows:
                existing = self._from_row(existing_rows[0])
                if not _snapshots_equivalent(existing, validated):
                    raise SnapshotConflictError(
                        "equity snapshot canonical timestamp conflict: "
                        f"environment={validated.environment}, "
                        f"strategy={validated.strategy_name}, "
                        f"candle_close={validated.candle_close_timestamp}"
                    )
                connection.execute(
                    "UPDATE equity_history_stats SET value=value+1 "
                    "WHERE key='duplicates_prevented'"
                )
                LOGGER.info(
                    "equity_snapshot_duplicate_ignored mode=%s strategy=%s timestamp=%s",
                    validated.environment, validated.strategy_name,
                    validated.candle_close_timestamp,
                )
                return existing, False
            cursor = connection.execute(
                f"INSERT OR IGNORE INTO equity_snapshots "
                f"({','.join(columns)}) VALUES ({placeholders})",
                values,
            )
            created = cursor.rowcount == 1
            if created:
                result = replace(validated, id=int(cursor.lastrowid))
            else:
                connection.execute(
                    "UPDATE equity_history_stats SET value=value+1 "
                    "WHERE key='duplicates_prevented'"
                )
                row = connection.execute(
                    "SELECT * FROM equity_snapshots WHERE environment=? "
                    "AND strategy_name=? AND "
                    "((candle_close_timestamp=? AND snapshot_reason=?) "
                    "OR (source_cycle_id=? AND snapshot_reason=?)) "
                    "ORDER BY id DESC LIMIT 1",
                    (
                        validated.environment, validated.strategy_name,
                        validated.candle_close_timestamp, validated.snapshot_reason,
                        validated.source_cycle_id, validated.snapshot_reason,
                    ),
                ).fetchone()
                result = self._from_row(row)
        return result, created

    def query(
        self, *, environment: str | None = None,
        strategy_name: str | None = None,
        start: datetime | None = None, end: datetime | None = None,
        valid_only: bool = False, canonical_only: bool = False,
    ) -> list[EquitySnapshot]:
        if not self.path.exists():
            return []
        clauses, values = [], []
        if environment:
            clauses.append("environment=?")
            values.append(environment)
        if strategy_name:
            clauses.append("strategy_name=?")
            values.append(strategy_name)
        if start:
            clauses.append("snapshot_at_utc>=?")
            values.append(start.astimezone(timezone.utc).isoformat())
        if end:
            clauses.append("snapshot_at_utc<=?")
            values.append(end.astimezone(timezone.utc).isoformat())
        if valid_only:
            clauses.append("data_quality_status='VALID' AND is_complete=1")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect(readonly=True) as connection:
            rows = connection.execute(
                "SELECT * FROM equity_snapshots" + where
                + " ORDER BY snapshot_at_utc,id", values
            ).fetchall()
        result = [self._from_row(row) for row in rows]
        if canonical_only:
            seen: set[tuple[str, str, int | None]] = set()
            result = [
                item for item in result
                if not ((_key := (item.environment, item.strategy_name, item.candle_close_timestamp)) in seen or seen.add(_key))
            ]
        return result

    def latest(self, environment: str, *, valid_only: bool = True) -> EquitySnapshot | None:
        rows = self.query(environment=environment, valid_only=valid_only, canonical_only=True)
        return rows[-1] if rows else None

    def boundary(self, environment: str, at: datetime) -> EquitySnapshot | None:
        if not self.path.exists():
            return None
        with self.connect(readonly=True) as connection:
            row = connection.execute(
                "SELECT * FROM equity_snapshots WHERE environment=? "
                "AND data_quality_status='VALID' AND is_complete=1 "
                "AND snapshot_at_utc<=? ORDER BY snapshot_at_utc DESC,id DESC LIMIT 1",
                (environment, at.astimezone(timezone.utc).isoformat()),
            ).fetchone()
        return self._from_row(row) if row else None

    def count(self, environment: str | None = None) -> int:
        if not self.path.exists():
            return 0
        with self.connect(readonly=True) as connection:
            if environment:
                return int(connection.execute(
                    "SELECT COUNT(*) FROM equity_snapshots WHERE environment=?",
                    (environment,),
                ).fetchone()[0])
            return int(connection.execute(
                "SELECT COUNT(*) FROM equity_snapshots"
            ).fetchone()[0])

    def has_candle(
        self, environment: str, strategy_name: str, candle_close_timestamp: int
    ) -> bool:
        if not self.path.exists():
            return False
        with self.connect(readonly=True) as connection:
            row = connection.execute(
                "SELECT 1 FROM equity_snapshots WHERE environment=? "
                "AND strategy_name=? AND candle_close_timestamp=? "
                "AND data_quality_status='VALID' LIMIT 1",
                (environment, strategy_name, candle_close_timestamp),
            ).fetchone()
        return row is not None

    def rebuild_equity_peaks(self, environment: str) -> int:
        rows = self.query(environment=environment)
        peak: Decimal | None = None
        updates = []
        for item in rows:
            if item.data_quality_status != "VALID":
                continue
            peak = item.equity if peak is None else max(peak, item.equity)
            drawdown = (
                max(Decimal("0"), (peak - item.equity) / peak * Decimal("100"))
                if peak > 0 else Decimal("0")
            )
            updates.append((float(peak), float(drawdown), item.id))
        with self.connect() as connection:
            connection.executemany(
                "UPDATE equity_snapshots SET peak_equity=?,drawdown_pct=? WHERE id=?",
                updates,
            )
        return len(updates)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> EquitySnapshot:
        values = dict(row)
        for name in DECIMAL_COLUMNS:
            if values[name] is not None:
                values[name] = Decimal(str(values[name]))
        values["is_complete"] = bool(values["is_complete"])
        return EquitySnapshot(**values)


def validate_snapshot(snapshot: EquitySnapshot) -> EquitySnapshot:
    warning = snapshot.warning_code
    quality = snapshot.data_quality_status
    if snapshot.environment not in ENVIRONMENTS:
        raise ValueError("unknown snapshot environment")
    if snapshot.snapshot_reason not in SNAPSHOT_REASONS:
        raise ValueError("unknown snapshot reason")
    if quality not in QUALITY_STATUSES:
        raise ValueError("unknown data quality status")
    numeric = (
        snapshot.cash_balance, snapshot.asset_quantity, snapshot.position_value,
        snapshot.equity, snapshot.realized_pnl, snapshot.unrealized_pnl,
        snapshot.total_pnl, snapshot.return_pct, snapshot.peak_equity,
        snapshot.drawdown_pct, snapshot.cumulative_fees, snapshot.gross_profit,
        snapshot.gross_loss, snapshot.exposure_pct,
    )
    if not all(value.is_finite() for value in numeric):
        quality, warning = "INVALID", "NON_FINITE"
    elif snapshot.cash_balance < 0 or snapshot.asset_quantity < 0:
        quality, warning = "INVALID", "NEGATIVE_BALANCE_OR_QUANTITY"
    elif snapshot.cumulative_fees < 0 or snapshot.drawdown_pct < 0:
        quality, warning = "INVALID", "NEGATIVE_FEES_OR_DRAWDOWN"
    elif snapshot.closed_trades < snapshot.winning_trades + snapshot.losing_trades:
        quality, warning = "INVALID", "TRADE_COUNTS_INCONSISTENT"
    elif (
        snapshot.candle_open_timestamp is not None
        and snapshot.candle_close_timestamp is not None
        and snapshot.candle_close_timestamp <= snapshot.candle_open_timestamp
    ):
        quality, warning = "INVALID", "CANDLE_TIMESTAMPS_INVALID"
    elif snapshot.position_side == "LONG" and (
        snapshot.asset_quantity <= 0 or snapshot.market_price is None
        or snapshot.market_price <= 0 or snapshot.entry_price is None
    ):
        quality, warning = "INVALID", "POSITION_INCONSISTENT"
    elif snapshot.position_side == "FLAT" and snapshot.asset_quantity != 0:
        quality, warning = "INVALID", "FLAT_WITH_QUANTITY"
    elif snapshot.state_hash is not None and (
        len(snapshot.state_hash) != 64
        or any(character not in "0123456789abcdef" for character in snapshot.state_hash)
    ):
        quality, warning = "INVALID", "STATE_HASH_INVALID"
    return replace(
        snapshot, data_quality_status=quality, warning_code=warning,
        is_complete=snapshot.is_complete and quality == "VALID",
    )


def safe_state_hash(
    *, balance: Any, quantity: Any, entry_price: Any,
    last_candle: Any, fees: Any, trades: Any,
    environment: str, strategy: str,
) -> str:
    payload = {
        "balance": str(balance), "quantity": str(quantity),
        "entry_price": None if entry_price is None else str(entry_price),
        "last_candle": last_candle, "fees": str(fees), "trades": int(trades),
        "environment": environment, "strategy": strategy,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class SnapshotService:
    def __init__(self, storage: SnapshotStorage, config: EquityHistoryConfig):
        self.storage = storage
        self.config = config

    def capture(
        self, *, environment: str, strategy_name: str,
        state: Any, trades: list[TradeJournalEntry],
        market_price: Decimal | None, candle_open_timestamp: int | None,
        timeframe_minutes: int = 60, symbol: str = "ETHUSDT",
        reason: str = "cycle", source_cycle_id: str | None = None,
        snapshot_at: datetime | None = None,
    ) -> tuple[EquitySnapshot | None, bool]:
        if not self.config.enabled:
            return None, False
        if environment not in ENVIRONMENTS:
            raise ValueError("unknown environment")
        if state.has_open_position and (
            market_price is None or market_price <= 0
        ):
            return None, False
        current = snapshot_at or datetime.now(timezone.utc)
        side = "LONG" if state.has_open_position else "FLAT"
        account = calculate_account_snapshot(
            initial_balance="1000", cash_balance=state.virtual_balance,
            position_side=side, position_quantity=state.position_quantity,
            entry_price=state.entry_price, current_price=market_price,
            realized_pnl=state.realized_pnl, opened_at=state.opened_at,
            now=current, stop_loss_price=state.stop_loss,
        )
        if account.equity is None or account.position_market_value is None:
            if not self.config.allow_partial_snapshots:
                return None, False
            return None, False
        total = account.equity - account.initial_balance
        unrealized = total - account.realized_pnl
        wins = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
        losses = [trade.net_pnl for trade in trades if trade.net_pnl < 0]
        gross_profit = sum(wins, Decimal("0"))
        gross_loss = sum(losses, Decimal("0"))
        pf = gross_profit / abs(gross_loss) if gross_loss else None
        win_rate = (
            Decimal(len(wins)) / Decimal(len(trades)) * Decimal("100")
            if trades else None
        )
        previous = self.storage.latest(environment)
        peak = max(
            account.equity,
            previous.peak_equity if previous else account.equity,
        )
        drawdown = (
            max(Decimal("0"), (peak - account.equity) / peak * Decimal("100"))
            if peak > 0 else Decimal("0")
        )
        exposure = (
            account.position_market_value / account.equity * Decimal("100")
            if account.equity else Decimal("0")
        )
        cumulative_fees = state.total_fees + (
            state.entry_fee if state.has_open_position else Decimal("0")
        )
        candle_close = (
            candle_open_timestamp + timeframe_minutes * 60
            if candle_open_timestamp is not None else None
        )
        expected_equity = state.virtual_balance + (
            state.position_quantity * market_price
            if state.has_open_position and market_price is not None
            else Decimal("0")
        )
        reconciled = abs(account.equity - expected_equity) <= (
            self.config.reconciliation_tolerance
        )
        snapshot = EquitySnapshot(
            None, datetime.now(timezone.utc).isoformat(), current.isoformat(),
            strategy_name, environment, symbol, str(timeframe_minutes),
            candle_open_timestamp, candle_close, market_price,
            account.cash_balance, account.position_quantity, side,
            account.entry_price, account.position_market_value, account.equity,
            account.realized_pnl, unrealized, total,
            total / account.initial_balance * Decimal("100"),
            peak, drawdown, cumulative_fees, state.closed_trades,
            len(wins), len(losses), win_rate, pf, gross_profit, gross_loss,
            exposure, "1", safe_state_hash(
                balance=state.virtual_balance, quantity=state.position_quantity,
                entry_price=state.entry_price, last_candle=candle_open_timestamp,
                fees=cumulative_fees, trades=state.closed_trades,
                environment=environment, strategy=strategy_name,
            ), source_cycle_id, reason, reconciled,
            "VALID" if reconciled else "INVALID",
            None if reconciled else "EQUITY_RECONCILIATION_FAILED",
        )
        if not reconciled:
            return (self.storage.insert(snapshot)[0], True)
        return self.storage.insert(snapshot)

    def daily_close(
        self, snapshot: EquitySnapshot, *, local_day: str
    ) -> tuple[EquitySnapshot, bool]:
        daily = replace(
            snapshot, id=None, created_at_utc=datetime.now(timezone.utc).isoformat(),
            snapshot_reason="daily_close", source_cycle_id=f"daily:{local_day}",
        )
        return self.storage.insert(daily)

    def maybe_daily_close(
        self, snapshot: EquitySnapshot, *, now: datetime
    ) -> tuple[EquitySnapshot | None, bool]:
        if not self.config.create_daily_snapshots:
            return None, False
        local = now.astimezone(ZoneInfo(self.config.timezone))
        threshold = local.replace(
            hour=self.config.daily_snapshot_hour,
            minute=self.config.daily_snapshot_minute,
            second=0,
            microsecond=0,
        )
        if local < threshold:
            return None, False
        return self.daily_close(snapshot, local_day=local.date().isoformat())


def _iso(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


class SnapshotMetrics:
    def __init__(self, storage: SnapshotStorage, config: EquityHistoryConfig):
        self.storage = storage
        self.config = config

    def rolling(self, environment: str, window: str, *, now: datetime | None = None) -> dict[str, Any]:
        if window != "all" and window not in WINDOWS:
            raise ValueError("unsupported equity history window")
        current = now or datetime.now(timezone.utc)
        end = self.storage.latest(environment)
        if end is None:
            return self._insufficient(window, "no valid snapshots")
        if window == "all":
            rows = self.storage.query(environment=environment, valid_only=True, canonical_only=True)
            start = rows[0] if rows else None
            boundary_exact = True
            boundary_age = 0
        else:
            boundary_time = current - WINDOWS[window]
            start = self.storage.boundary(environment, boundary_time)
            if start is None:
                return self._insufficient(window, "no snapshot at or before window boundary")
            boundary_age = int((boundary_time - _iso(start.snapshot_at_utc)).total_seconds())
            if boundary_age > self.config.max_boundary_age_seconds:
                return self._insufficient(window, "boundary snapshot is too old")
            boundary_exact = boundary_age == 0
            rows = self.storage.query(
                environment=environment, start=_iso(start.snapshot_at_utc),
                end=current, valid_only=True,
            )
        if start is None or len(rows) < 2:
            return self._insufficient(window, "fewer than two valid snapshots")
        pnl = end.equity - start.equity
        ret = pnl / start.equity * Decimal("100") if start.equity else None
        equities = [item.equity for item in rows]
        max_dd = max(item.drawdown_pct for item in rows)
        fees = end.cumulative_fees - start.cumulative_fees
        trades = end.closed_trades - start.closed_trades
        days = self._daily(rows)
        expected_seconds = (
            (WINDOWS[window].total_seconds() if window != "all"
             else max(1, (_iso(end.snapshot_at_utc) - _iso(start.snapshot_at_utc)).total_seconds()))
        )
        observed = max(0, (_iso(end.snapshot_at_utc) - _iso(start.snapshot_at_utc)).total_seconds())
        expected_intervals = max(2, int(expected_seconds // 3600) + 1)
        completeness = min(100.0, len(rows) / expected_intervals * 100)
        local_zone = ZoneInfo(self.config.timezone)
        local_dates = {
            _iso(item.snapshot_at_utc).astimezone(local_zone).date() for item in rows
        }
        span_days = max(1, (_iso(end.snapshot_at_utc).date() - _iso(start.snapshot_at_utc).date()).days + 1)
        missing_days = max(0, span_days - len(local_dates))
        gaps = [
            (_iso(right.snapshot_at_utc) - _iso(left.snapshot_at_utc)).total_seconds()
            for left, right in zip(rows, rows[1:])
        ]
        return {
            "window": window, "status": "AVAILABLE",
            "source": "SNAPSHOT_HISTORY", "start_snapshot_id": start.id,
            "end_snapshot_id": end.id, "start_equity": str(start.equity),
            "end_equity": str(end.equity), "pnl": str(pnl),
            "return_percent": str(ret) if ret is not None else NA,
            "max_drawdown_percent": str(max_dd),
            "current_drawdown_percent": str(end.drawdown_pct),
            "peak_equity": str(end.peak_equity), "fees": str(fees),
            "closed_trades": trades, "win_rate": (
                str(end.win_rate) if end.win_rate is not None else NA
            ), "profit_factor": (
                str(end.profit_factor) if end.profit_factor is not None else NA
            ), "exposure_percent": str(end.exposure_pct),
            "daily_volatility": (
                pstdev([float(item["return_percent"]) for item in days])
                if len(days) >= 2 else NA
            ), "boundary_exact": boundary_exact,
            "boundary_age_seconds": boundary_age,
            "completeness_pct": completeness, "missing_days": missing_days,
            "missing_intervals": sum(gap > 7200 for gap in gaps),
            "insufficient_reason": None,
        }

    def aggregate(self, environment: str) -> dict[str, Any]:
        rows = self.storage.query(environment=environment, valid_only=True, canonical_only=True)
        if not rows:
            return {"environment": environment, "status": "INSUFFICIENT_HISTORY"}
        days = self._daily(rows)
        daily_returns = [float(item["return_percent"]) for item in days]
        max_dd = max(item.drawdown_pct for item in rows)
        longest, recovery = self._drawdown_durations(rows)
        return {
            "environment": environment, "status": "AVAILABLE",
            "snapshot_count": len(rows), "first_snapshot": rows[0].snapshot_at_utc,
            "last_snapshot": rows[-1].snapshot_at_utc,
            "latest_candle": rows[-1].candle_close_timestamp,
            "latest_equity": str(rows[-1].equity),
            "return_percent": str(
                (rows[-1].equity - rows[0].equity) / rows[0].equity * Decimal("100")
            ) if len(rows) >= 2 and rows[0].equity else NA,
            "max_drawdown_percent": str(max_dd),
            "current_drawdown_percent": str(rows[-1].drawdown_pct),
            "peak_equity": str(rows[-1].peak_equity),
            "daily_returns": days,
            "best_day": max(days, key=lambda item: item["return_percent"]) if days else None,
            "worst_day": min(days, key=lambda item: item["return_percent"]) if days else None,
            "positive_days": sum(item["return_percent"] > 0 for item in days),
            "negative_days": sum(item["return_percent"] < 0 for item in days),
            "flat_days": sum(item["return_percent"] == 0 for item in days),
            "daily_volatility": pstdev(daily_returns) if len(daily_returns) >= 2 else NA,
            "recovery_duration_seconds": recovery,
            "longest_drawdown_duration_seconds": longest,
            "fees": str(rows[-1].cumulative_fees),
            "trades": rows[-1].closed_trades,
            "win_rate": str(rows[-1].win_rate) if rows[-1].win_rate is not None else NA,
            "profit_factor": str(rows[-1].profit_factor) if rows[-1].profit_factor is not None else NA,
            "exposure_percent": str(rows[-1].exposure_pct),
        }

    def quality(self, environment: str | None = None) -> dict[str, Any]:
        rows = self.storage.query(environment=environment, canonical_only=True)
        counts = {status: sum(item.data_quality_status == status for item in rows)
                  for status in QUALITY_STATUSES}
        valid = [item for item in rows if item.data_quality_status == "VALID"]
        gaps = [
            (_iso(right.snapshot_at_utc) - _iso(left.snapshot_at_utc)).total_seconds()
            for left, right in zip(valid, valid[1:])
            if left.environment == right.environment
        ]
        return {
            "total_snapshots": len(rows), "valid": counts["VALID"],
            "partial": counts["PARTIAL"], "invalid": counts["INVALID"],
            "duplicates_prevented": self._duplicates_prevented(),
            "missing_days": self._missing_days(valid),
            "gap_count": sum(gap > 7200 for gap in gaps),
            "largest_gap_seconds": max(gaps) if gaps else NA,
        }

    def _duplicates_prevented(self) -> int | str:
        if not self.storage.path.exists():
            return NA
        try:
            with self.storage.connect(readonly=True) as connection:
                row = connection.execute(
                    "SELECT value FROM equity_history_stats "
                    "WHERE key='duplicates_prevented'"
                ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.Error:
            return NA

    def compare(self, production: str = "production", candidate: str = "candidate") -> dict[str, Any]:
        left = self.storage.query(environment=production, valid_only=True, canonical_only=True)
        right = self.storage.query(environment=candidate, valid_only=True, canonical_only=True)
        left_map = {item.candle_close_timestamp: item for item in left if item.candle_close_timestamp}
        right_map = {item.candle_close_timestamp: item for item in right if item.candle_close_timestamp}
        common = sorted(left_map.keys() & right_map.keys())
        if not common:
            return {"comparable_history_status": "INSUFFICIENT", "comparable_snapshot_count": 0}
        compatible = [
            ts for ts in common
            if left_map[ts].timeframe == right_map[ts].timeframe
            and left_map[ts].market_price == right_map[ts].market_price
        ]
        status = (
            "INCOMPATIBLE" if not compatible else
            "COMPATIBLE" if len(compatible) == len(left_map) == len(right_map)
            else "PARTIAL"
        )
        if not compatible:
            return {"comparable_history_status": status, "comparable_snapshot_count": 0}
        first, last = compatible[0], compatible[-1]
        p0, p1 = left_map[first], left_map[last]
        c0, c1 = right_map[first], right_map[last]
        p_return = (p1.equity - p0.equity) / p0.equity * Decimal("100") if p0.equity else None
        c_return = (c1.equity - c0.equity) / c0.equity * Decimal("100") if c0.equity else None
        p_changes = [
            float(
                (left_map[right].equity - left_map[left].equity)
                / left_map[left].equity * Decimal("100")
            )
            for left, right in zip(compatible, compatible[1:])
            if left_map[left].equity
        ]
        c_changes = [
            float(
                (right_map[right].equity - right_map[left].equity)
                / right_map[left].equity * Decimal("100")
            )
            for left, right in zip(compatible, compatible[1:])
            if right_map[left].equity
        ]
        volatility_delta = (
            pstdev(c_changes) - pstdev(p_changes)
            if len(p_changes) >= 2 and len(c_changes) >= 2 else NA
        )
        p_rows = [left_map[item] for item in compatible]
        c_rows = [right_map[item] for item in compatible]
        p_recovery = self._drawdown_durations(p_rows)[1]
        c_recovery = self._drawdown_durations(c_rows)[1]
        return {
            "comparable_history_status": status,
            "comparable_snapshot_count": len(compatible),
            "equity_curve_overlap": len(compatible),
            "return_delta": str(c_return - p_return) if p_return is not None and c_return is not None else NA,
            "drawdown_delta": str(c1.drawdown_pct - p1.drawdown_pct),
            "volatility_delta": volatility_delta,
            "fees_delta": str((c1.cumulative_fees - c0.cumulative_fees) - (p1.cumulative_fees - p0.cumulative_fees)),
            "exposure_delta": str(c1.exposure_pct - p1.exposure_pct),
            "daily_win_count": sum(value > 0 for value in c_changes),
            "monthly_return_delta": (
                str(c_return - p_return)
                if (
                    p_return is not None and c_return is not None
                    and (_iso(p1.snapshot_at_utc).year, _iso(p1.snapshot_at_utc).month)
                    != (_iso(p0.snapshot_at_utc).year, _iso(p0.snapshot_at_utc).month)
                ) else NA
            ),
            "recovery_duration_delta": (
                c_recovery - p_recovery
                if c_recovery is not None and p_recovery is not None else NA
            ),
        }

    def period_returns(
        self, environment: str, frequency: str
    ) -> list[dict[str, Any]]:
        if frequency not in {"daily", "weekly", "monthly"}:
            raise ValueError("unsupported return aggregation")
        rows = self.storage.query(environment=environment, valid_only=True, canonical_only=True)
        zone = ZoneInfo(self.config.timezone)
        closes: dict[str, EquitySnapshot] = {}
        for item in rows:
            local = _iso(item.snapshot_at_utc).astimezone(zone)
            if frequency == "daily":
                key = local.date().isoformat()
            elif frequency == "weekly":
                iso = local.isocalendar()
                key = f"{iso.year}-W{iso.week:02d}"
            else:
                key = f"{local.year:04d}-{local.month:02d}"
            closes[key] = item
        result = []
        previous: EquitySnapshot | None = None
        for period, item in sorted(closes.items()):
            value = (
                (item.equity - previous.equity) / previous.equity
                * Decimal("100")
                if previous is not None and previous.equity else None
            )
            result.append(
                {
                    "period": period,
                    "end_equity": str(item.equity),
                    "return_percent": str(value) if value is not None else NA,
                }
            )
            previous = item
        return result

    @staticmethod
    def _insufficient(window: str, reason: str) -> dict[str, Any]:
        return {
            "window": window, "status": "INSUFFICIENT_HISTORY",
            "source": "SNAPSHOT_HISTORY", "start_equity": NA, "end_equity": NA,
            "return_percent": NA, "pnl": NA, "max_drawdown_percent": NA,
            "current_drawdown_percent": NA, "fees": NA, "closed_trades": NA,
            "win_rate": NA, "profit_factor": NA, "exposure_percent": NA,
            "daily_volatility": NA, "boundary_exact": NA,
            "boundary_age_seconds": NA, "completeness_pct": NA,
            "missing_days": NA, "missing_intervals": NA,
            "insufficient_reason": reason,
        }

    def _daily(self, rows: list[EquitySnapshot]) -> list[dict[str, Any]]:
        zone = ZoneInfo(self.config.timezone)
        closes: dict[str, EquitySnapshot] = {}
        for item in rows:
            day = _iso(item.snapshot_at_utc).astimezone(zone).date().isoformat()
            closes[day] = item
        result = []
        previous = None
        for day, item in sorted(closes.items()):
            if previous is not None and previous.equity:
                value = (item.equity - previous.equity) / previous.equity * Decimal("100")
                result.append({"date": day, "return_percent": float(value)})
            previous = item
        return result

    @staticmethod
    def _drawdown_durations(rows: list[EquitySnapshot]) -> tuple[int | None, int | None]:
        start = None
        longest = 0
        last_recovery = None
        for item in rows:
            timestamp = _iso(item.snapshot_at_utc)
            if item.drawdown_pct > 0 and start is None:
                start = timestamp
            elif item.drawdown_pct == 0 and start is not None:
                duration = int((timestamp - start).total_seconds())
                longest = max(longest, duration)
                last_recovery = duration
                start = None
        if start is not None:
            longest = max(longest, int((_iso(rows[-1].snapshot_at_utc) - start).total_seconds()))
        return (longest if longest else None, last_recovery)

    def _missing_days(self, rows: list[EquitySnapshot]) -> int | str:
        if not rows:
            return NA
        zone = ZoneInfo(self.config.timezone)
        dates = {_iso(item.snapshot_at_utc).astimezone(zone).date() for item in rows}
        span = (max(dates) - min(dates)).days + 1
        return max(0, span - len(dates))


def load_strategy_state(environment: str, path: Path):
    if environment == "production":
        return TradingControllerStateStore(path).load()
    return CandidateStateStore(path).load().controller


def read_trades(path: Path) -> list[TradeJournalEntry]:
    if not path.exists():
        return []
    rows, _ = read_jsonl_safely(path, parser=TradeJournalEntry.from_dict)
    return rows
