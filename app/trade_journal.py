from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, fields
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Protocol


DECIMAL_FIELDS = {
    "entry_price",
    "exit_price",
    "quantity",
    "entry_notional",
    "exit_notional",
    "gross_pnl",
    "entry_fee",
    "exit_fee",
    "total_fee",
    "net_pnl",
    "pnl_percent",
    "remaining_position_quantity",
    "virtual_balance_after",
    "realized_pnl_after",
    "signal_price",
    "fill_price",
}


@dataclass(frozen=True, slots=True)
class TradeJournalEntry:
    record_id: str
    symbol: str
    opened_at: str
    closed_at: str
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    entry_notional: Decimal
    exit_notional: Decimal
    gross_pnl: Decimal
    entry_fee: Decimal
    exit_fee: Decimal
    total_fee: Decimal
    net_pnl: Decimal
    pnl_percent: Decimal
    exit_reason: str
    remaining_position_quantity: Decimal
    virtual_balance_after: Decimal
    realized_pnl_after: Decimal
    closed_trades_after: int
    signal_timestamp: int | None = None
    fill_timestamp: int | None = None
    signal_price: Decimal | None = None
    fill_price: Decimal | None = None
    strategy_logic_version: str = "legacy"
    execution_policy_version: str = "legacy_same_close_v1"
    ledger_schema_version: str = "ledger_v1"

    def to_dict(self) -> dict[str, str | int]:
        payload = asdict(self)
        for field_name in DECIMAL_FIELDS:
            if payload[field_name] is not None:
                payload[field_name] = str(payload[field_name])
        return payload

    @classmethod
    def from_dict(cls, payload: object) -> TradeJournalEntry:
        if not isinstance(payload, dict):
            raise ValueError("trade journal entry must be a JSON object")

        expected = {field.name for field in fields(cls)}
        required = {
            field.name for field in fields(cls)
            if field.default is MISSING and field.default_factory is MISSING
        }
        missing = required - payload.keys()
        if missing:
            raise ValueError(
                "trade journal entry is missing fields: "
                + ", ".join(sorted(missing))
            )

        values = {
            field.name: payload.get(field.name, field.default)
            for field in fields(cls)
        }
        try:
            for field_name in DECIMAL_FIELDS:
                value = values[field_name]
                if value is None:
                    continue
                if not isinstance(value, str):
                    raise ValueError(
                        f"{field_name} must be stored as a string"
                    )
                values[field_name] = Decimal(value)

            closed_trades = values["closed_trades_after"]
            if isinstance(closed_trades, bool):
                raise ValueError(
                    "closed_trades_after must be an integer"
                )
            values["closed_trades_after"] = int(closed_trades)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid trade journal entry: {exc}"
            ) from exc

        return cls(**values)


class TradeJournalProtocol(Protocol):
    def append(self, entry: TradeJournalEntry) -> None:
        ...


class JsonlTradeJournal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, entry: TradeJournalEntry) -> None:
        if any(item.record_id == entry.record_id for item in self.read_all()):
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("a", encoding="utf-8") as file:
                json.dump(
                    entry.to_dict(),
                    file,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                file.write("\n")
                file.flush()
                import os
                os.fsync(file.fileno())
        except OSError as exc:
            raise ValueError(
                f"failed to append trade journal {self.path}: {exc}"
            ) from exc

    def read_all(self) -> list[TradeJournalEntry]:
        if not self.path.exists():
            return []

        entries: list[TradeJournalEntry] = []
        try:
            with self.path.open(encoding="utf-8") as file:
                for line_number, line in enumerate(file, start=1):
                    if not line.strip():
                        continue
                    try:
                        payload = json.loads(line)
                        entries.append(
                            TradeJournalEntry.from_dict(payload)
                        )
                    except (
                        json.JSONDecodeError,
                        ValueError,
                    ) as exc:
                        raise ValueError(
                            "corrupt trade journal line "
                            f"{line_number} in {self.path}: {exc}"
                        ) from exc
        except OSError as exc:
            raise ValueError(
                f"failed to read trade journal {self.path}: {exc}"
            ) from exc

        return entries
