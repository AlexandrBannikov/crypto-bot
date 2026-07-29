from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ShadowDecisionRecord:
    candle_timestamp: int
    symbol: str
    timeframe: str
    strategy_mode: str
    baseline_signal: str
    filtered_signal: str
    execution_signal: str
    regime: str | None
    confidence: float | None
    allowed: bool | None
    blocked: bool
    blocked_reason: str | None
    current_position: str
    virtual_balance: str
    detector_parameters: dict[str, float | int]
    filter_parameters_fingerprint: str
    unique_candle_identifier: str
    controller_run_identifier: str | None = None
    detector_error: str | None = None
    effective_action: str | None = None
    filter_mode: str | None = None
    price: str | None = None
    position_state_before: str | None = None
    position_state_after: str | None = None
    strategy_name: str = "ema_cross"
    strategy_version: str = "1"
    detector_version: str = "market_regime_v1"
    data_age_seconds: float | None = None
    runtime_instance_id: str | None = None
    shadow_would_block: bool = False
    shadow_block_reason: str | None = None
    baseline_trade_executed: bool = False
    journal_sequence: int | None = None
    strategy_id: str = "production"
    signal: str | None = None
    action: str | None = None
    position_before: str | None = None
    position_after: str | None = None
    reason: str | None = None
    decision_status: str = "produced"
    status_reason: str | None = None

    @property
    def deduplication_key(self) -> str:
        return "|".join(
            (
                self.symbol,
                self.timeframe,
                str(self.candle_timestamp),
                self.strategy_mode,
                self.filter_parameters_fingerprint,
            )
        )


class ShadowDecisionJournal:
    """Append-only JSONL with restart-safe last-key deduplication."""

    def __init__(
        self,
        path: str | Path,
        *,
        state_path: str | Path | None = None,
    ) -> None:
        self.path = Path(path)
        self.state_path = (
            Path(state_path)
            if state_path is not None
            else self.path.with_suffix(self.path.suffix + ".state")
        )
        self._last_key = self._load_last_key()

    def append(self, record: ShadowDecisionRecord) -> bool:
        key = record.deduplication_key
        if key == self._last_key:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("a", encoding="utf-8") as file:
                os.fchmod(file.fileno(), 0o640)
                json.dump(
                    asdict(record),
                    file,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            self._last_key = key
            self._save_state(key)
        except OSError as exc:
            raise ValueError(
                f"failed to append shadow diagnostics: {exc}"
            ) from exc
        return True

    def read_all(self) -> list[ShadowDecisionRecord]:
        if not self.path.exists():
            return []
        records: list[ShadowDecisionRecord] = []
        raw_lines = self.path.read_bytes().splitlines(keepends=True)
        valid_size = 0
        for index, raw_line in enumerate(raw_lines):
            try:
                line = raw_line.decode("utf-8")
                if not line.strip():
                    valid_size += len(raw_line)
                    continue
                records.append(
                    ShadowDecisionRecord(**json.loads(line))
                )
            except (
                TypeError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                ValueError,
            ) as exc:
                if index == len(raw_lines) - 1:
                    self._truncate(valid_size)
                    break
                raise ValueError(
                    f"corrupt shadow diagnostics line {index + 1}"
                ) from exc
            valid_size += len(raw_line)
        return records

    def _load_last_key(self) -> str | None:
        journal_size = (
            self.path.stat().st_size if self.path.exists() else 0
        )
        try:
            payload = json.loads(
                self.state_path.read_text(encoding="utf-8")
            )
            if (
                isinstance(payload, dict)
                and isinstance(payload.get("last_key"), str)
                and payload.get("journal_size") == journal_size
            ):
                return payload["last_key"]
        except (OSError, json.JSONDecodeError):
            pass
        records = self.read_all()
        return records[-1].deduplication_key if records else None

    def _save_state(self, key: str) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            dir=self.state_path.parent,
            prefix=f".{self.state_path.name}.",
            suffix=".tmp",
        )
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(
                    {
                        "last_key": key,
                        "journal_size": self.path.stat().st_size,
                    },
                    file,
                    separators=(",", ":"),
                )
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.state_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _truncate(self, size: int) -> None:
        try:
            with self.path.open("r+b") as file:
                file.truncate(size)
                file.flush()
                os.fsync(file.fileno())
        except OSError as exc:
            raise ValueError(
                f"failed to repair shadow diagnostics: {exc}"
            ) from exc
