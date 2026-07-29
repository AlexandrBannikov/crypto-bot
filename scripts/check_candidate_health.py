from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.candidate_runtime import CandidateStateStore, ensure_paper_only
from app.bybit_market_data import BybitMarketDataConfig, BybitMarketDataFeed
from app.runtime_health import check_lock
from app.telegram_config import TelegramConfig
from app.telegram_notifications import TelegramClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check isolated candidate runtime")
    parser.add_argument("--no-network", action="store_true")
    args = parser.parse_args(argv)
    problems: list[str] = []
    state_path = ROOT / "state/bybit_candidate_controller.json"
    lock_path = ROOT / "state/bybit_candidate.lock"
    try:
        ensure_paper_only()
    except RuntimeError as exc:
        problems.append(str(exc))
    try:
        state = CandidateStateStore(state_path).load()
        if state.last_processed_candle is None:
            problems.append("candidate has no baseline candle")
        elif datetime.now(timezone.utc).timestamp() - state.last_processed_candle > 7200:
            problems.append("candidate runtime/state is stale")
        if state.active_halt:
            problems.append(f"active halt: {state.active_halt}")
    except (OSError, ValueError) as exc:
        problems.append(f"state invalid: {exc}")
    lock = check_lock(lock_path)
    if lock.status.name == "CRITICAL":
        problems.append(lock.message)
    if not args.no_network:
        try:
            BybitMarketDataFeed(
                BybitMarketDataConfig(
                    symbol="ETHUSDT", interval="60", category="spot",
                    limit=2, max_retries=1, closed_candles_only=True,
                )
            ).get_latest_candle()
        except Exception as exc:
            problems.append(f"public Bybit API unavailable: {type(exc).__name__}")
    for unit in ("crypto-paper-candidate.timer", "crypto-paper-candidate.service"):
        shown = subprocess.run(
            ["/usr/bin/systemctl", "show", unit, "-p", "ActiveState", "-p", "Result"],
            check=False, capture_output=True, text=True,
        )
        if shown.returncode != 0:
            problems.append(f"{unit} status unavailable")
        if unit.endswith(".timer") and "ActiveState=active" not in shown.stdout:
            problems.append("candidate timer inactive")
        if unit.endswith(".service") and "Result=success" not in shown.stdout:
            problems.append("candidate service result is not success")
    if problems:
        message = "Candidate runtime problem\n" + "\n".join(problems)
        print(message, file=sys.stderr)
        config = TelegramConfig.from_env()
        if config.enabled:
            TelegramClient(config.token or "").send_message(
                config.chat_id or "", message
            )
        return 1
    print("Candidate runtime health: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
