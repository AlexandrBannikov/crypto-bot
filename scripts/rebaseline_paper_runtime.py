from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.paper_runtime_reports import atomic_write
from app.regime_runtime import (
    RegimeRuntimeCounters,
    RegimeRuntimeStateStore,
)
from app.trading_controller_store import TradingControllerStateStore


TEST_CANDLE_TIMESTAMP = 123


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Remove confirmed test-only runtime artifacts and establish "
            "a clean paper baseline; dry-run unless --confirm is supplied"
        )
    )
    result.add_argument("--confirm", action="store_true")
    result.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    return result


def _paths(root: Path) -> dict[str, Path]:
    return {
        "controller": root / "state/trading_controller.json",
        "runtime": root / "state/regime_runtime.json",
        "marker": root / "state/trading_controller_last_candle.txt",
        "decisions": root / "state/shadow_decisions.jsonl",
        "trade_journal": root / "state/controller_trade_journal.jsonl",
    }


def _load_decisions(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _validate(paths: dict[str, Path]) -> tuple:
    controller = TradingControllerStateStore(paths["controller"]).load()
    runtime = RegimeRuntimeStateStore(paths["runtime"]).load()
    marker = int(paths["marker"].read_text(encoding="utf-8").strip())
    decisions = _load_decisions(paths["decisions"])
    if controller.has_open_position:
        raise ValueError("rebaseline refused: paper position is open")
    if controller.virtual_balance != Decimal("1000"):
        raise ValueError("rebaseline refused: virtual balance is not 1000")
    if any(
        value != 0
        for value in (
            controller.realized_pnl,
            controller.total_fees,
            controller.closed_trades,
        )
    ):
        raise ValueError("rebaseline refused: real accounting history exists")
    if paths["trade_journal"].exists() and paths["trade_journal"].stat().st_size:
        raise ValueError("rebaseline refused: trade journal is not empty")
    if runtime.active_halt_reason is not None:
        raise ValueError("rebaseline refused: active halt exists")

    test_records = [
        item
        for item in decisions
        if item.get("candle_timestamp") == TEST_CANDLE_TIMESTAMP
        and item.get("baseline_signal") == "hold"
        and item.get("baseline_trade_executed") is False
        and item.get("current_position") == "flat"
    ]
    unexpected_test_timestamp = [
        item
        for item in decisions
        if item.get("candle_timestamp") == TEST_CANDLE_TIMESTAMP
        and item not in test_records
    ]
    if unexpected_test_timestamp:
        raise ValueError("rebaseline refused: ambiguous timestamp=123 record")
    retained = [item for item in decisions if item not in test_records]
    if any(
        item.get("baseline_trade_executed")
        or item.get("baseline_signal") in {"open_long", "open_short"}
        for item in retained
    ):
        raise ValueError("rebaseline refused: decision journal contains entries")
    if runtime.last_processed_closed_candle != marker:
        raise ValueError("rebaseline refused: candle markers disagree")
    return controller, runtime, marker, decisions, test_records, retained


def _backup(root: Path, paths: dict[str, Path], timestamp: str) -> Path:
    backup = root / "backups" / f"runtime-rebaseline-{timestamp}"
    backup.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(backup, 0o700)
    copied: list[Path] = []
    for path in paths.values():
        if not path.exists():
            continue
        target = backup / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied.append(target)
    checksums = []
    for path in sorted(copied):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksums.append(f"{digest}  {path.relative_to(backup)}")
    atomic_write(backup / "SHA256SUMS", "\n".join(checksums) + "\n")
    os.chmod(backup / "SHA256SUMS", 0o600)
    return backup


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.project_root.resolve()
    paths = _paths(root)
    try:
        (
            controller,
            runtime,
            marker,
            decisions,
            test_records,
            retained,
        ) = _validate(paths)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"mode={'CONFIRM' if args.confirm else 'DRY-RUN'}")
    print(f"decision_records_before={len(decisions)}")
    print(f"confirmed_test_records={len(test_records)}")
    print(f"decision_records_after={len(retained)}")
    print(f"last_processed_closed_candle={marker}")
    print(f"position_quantity={controller.position_quantity}")
    print(f"virtual_balance={controller.virtual_balance}")
    if not args.confirm:
        print("no files changed; pass --confirm to apply")
        return 0

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    backup = _backup(root, paths, timestamp)
    content = "".join(
        json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
        for item in retained
    )
    atomic_write(paths["decisions"], content)
    runtime.counters = RegimeRuntimeCounters()
    runtime.peak_balance = str(controller.virtual_balance)
    runtime.current_drawdown_percent = "0"
    runtime.maximum_drawdown_percent = "0"
    runtime.daily_starting_balance = str(controller.virtual_balance)
    runtime.daily_loss_percent = "0"
    runtime.daily_utc_date = now.date().isoformat()
    runtime.active_halt_reason = None
    runtime.drawdown_halt_latched = False
    runtime.last_processed_closed_candle = marker
    runtime.last_journal_sequence = len(retained)
    runtime.rebaseline_at = now.isoformat()
    runtime.rebaseline_note = (
        "clean production baseline after removal of confirmed test artifacts"
    )
    RegimeRuntimeStateStore(paths["runtime"]).save(runtime)
    print(f"backup={backup}")
    print(f"journal_sequence={runtime.last_journal_sequence}")
    print(f"rebaseline_at={runtime.rebaseline_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
