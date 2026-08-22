"""Write-ahead recovery for the Production controller state/trade pair."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from app.trade_journal import JsonlTradeJournal, TradeJournalEntry
from app.trading_controller import TradingControllerState
from app.trading_controller_store import (
    TradingControllerStateStore,
    controller_state_from_dict,
    controller_state_to_dict,
)


class ControllerLedger:
    def __init__(
        self,
        state_store: TradingControllerStateStore,
        journal: JsonlTradeJournal,
        *,
        wal_path: str | Path | None = None,
        crash_hook: Callable[[str], None] | None = None,
    ) -> None:
        self.state_store = state_store
        self.journal = journal
        self.wal_path = Path(wal_path) if wal_path else state_store.path.with_suffix(
            state_store.path.suffix + ".wal"
        )
        self.crash_hook = crash_hook

    def _hook(self, stage: str) -> None:
        if self.crash_hook is not None:
            self.crash_hook(stage)

    def commit(
        self, state: TradingControllerState, journal_entry: TradeJournalEntry,
    ) -> None:
        self.wal_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.wal_path.with_suffix(self.wal_path.suffix + ".tmp")
        temporary.write_text(json.dumps({
            "state": controller_state_to_dict(state),
            "journal_entry": journal_entry.to_dict(),
        }, separators=(",", ":")) + "\n", encoding="utf-8")
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        temporary.replace(self.wal_path)
        self._hook("after_prepare")
        self.journal.append(journal_entry)
        self._hook("after_journal")
        self.state_store.save(state)
        self._hook("after_state")
        self.wal_path.unlink(missing_ok=True)

    def recover(self) -> TradingControllerState | None:
        if not self.wal_path.exists():
            return None
        try:
            payload = json.loads(self.wal_path.read_text(encoding="utf-8"))
            state = controller_state_from_dict(payload["state"])
            entry = TradeJournalEntry.from_dict(payload["journal_entry"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid controller WAL: {exc}") from exc
        self.journal.append(entry)
        self.state_store.save(state)
        self.wal_path.unlink(missing_ok=True)
        return state
