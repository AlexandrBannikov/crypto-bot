from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.regime_runtime import RegimeRuntimeStateStore
from app.trading_controller_store import TradingControllerStateStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Explicitly reset a latched paper-runtime drawdown halt"
    )
    parser.add_argument(
        "--confirm-maximum-drawdown-reset",
        action="store_true",
        help="required acknowledgement; does not run a trading cycle",
    )
    args = parser.parse_args(argv)
    if not args.confirm_maximum_drawdown_reset:
        print("reset refused: explicit confirmation flag is required", file=sys.stderr)
        return 2

    runtime_store = RegimeRuntimeStateStore(
        PROJECT_ROOT / "state/regime_runtime.json"
    )
    state = runtime_store.load()
    if state.active_halt_reason != "maximum_drawdown":
        print(
            "reset refused: active halt is not maximum_drawdown",
            file=sys.stderr,
        )
        return 2
    controller = TradingControllerStateStore(
        PROJECT_ROOT / "state/trading_controller.json"
    ).load()
    equity_floor = Decimal(controller.virtual_balance)
    state.reset_drawdown_halt(equity_floor)
    runtime_store.save(state)
    print("maximum_drawdown halt reset; live trading remains disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
