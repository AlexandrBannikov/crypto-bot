from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from app.paper_session import (
    PaperPosition,
    PaperSessionSnapshot,
)
from app.trading_types import (
    ExitReason,
    PositionSide,
    TradeAction,
)


@dataclass(frozen=True, slots=True)
class PaperSessionState:
    last_candle_timestamp: int | None = None
    virtual_balance: float = 1000.0
    recorded_trades: int = 0
    session_snapshot: PaperSessionSnapshot | None = None

    def __post_init__(self) -> None:
        if (
            self.last_candle_timestamp is not None
            and self.last_candle_timestamp < 0
        ):
            raise ValueError(
                "last_candle_timestamp must not be negative"
            )

        if self.virtual_balance < 0:
            raise ValueError(
                "virtual_balance must not be negative"
            )

        if self.recorded_trades < 0:
            raise ValueError(
                "recorded_trades must not be negative"
            )

        snapshot = self.session_snapshot

        if snapshot is None:
            snapshot = PaperSessionSnapshot(
                balance=self.virtual_balance,
                last_candle_timestamp=(
                    self.last_candle_timestamp
                ),
            )

            object.__setattr__(
                self,
                "session_snapshot",
                snapshot,
            )
            return

        if (
            snapshot.last_candle_timestamp
            != self.last_candle_timestamp
        ):
            raise ValueError(
                "session snapshot timestamp does not match "
                "state timestamp"
            )

        if snapshot.balance != self.virtual_balance:
            raise ValueError(
                "session snapshot balance does not match "
                "virtual balance"
            )


class PaperStateStore:
    def __init__(
        self,
        file_path: str | Path,
    ) -> None:
        self.file_path = Path(file_path)

    def load(
        self,
        *,
        default_balance: float = 1000.0,
    ) -> PaperSessionState:
        if default_balance <= 0:
            raise ValueError(
                "default_balance must be greater than zero"
            )

        if not self.file_path.exists():
            return PaperSessionState(
                virtual_balance=default_balance,
            )

        try:
            payload = json.loads(
                self.file_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise ValueError(
                "invalid paper state file"
            ) from error

        if not isinstance(payload, dict):
            raise ValueError(
                "paper state must be a JSON object"
            )

        return self._from_payload(payload)

    def save(
        self,
        state: PaperSessionState,
    ) -> None:
        self.file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.file_path.with_suffix(
            self.file_path.suffix + ".tmp"
        )

        temporary_path.write_text(
            json.dumps(
                asdict(state),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        temporary_path.replace(self.file_path)

    @classmethod
    def _from_payload(
        cls,
        payload: dict[str, Any],
    ) -> PaperSessionState:
        try:
            last_candle_timestamp = payload.get(
                "last_candle_timestamp"
            )
            virtual_balance = float(
                payload["virtual_balance"]
            )
            recorded_trades = int(
                payload.get(
                    "recorded_trades",
                    0,
                )
            )

            snapshot_payload = payload.get(
                "session_snapshot"
            )

            if snapshot_payload is None:
                snapshot = PaperSessionSnapshot(
                    balance=virtual_balance,
                    last_candle_timestamp=(
                        last_candle_timestamp
                    ),
                )
            else:
                snapshot = cls._snapshot_from_payload(
                    snapshot_payload
                )

            return PaperSessionState(
                last_candle_timestamp=(
                    last_candle_timestamp
                ),
                virtual_balance=virtual_balance,
                recorded_trades=recorded_trades,
                session_snapshot=snapshot,
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise ValueError(
                "invalid paper state values"
            ) from error

    @staticmethod
    def _snapshot_from_payload(
        payload: Any,
    ) -> PaperSessionSnapshot:
        if not isinstance(payload, dict):
            raise ValueError(
                "invalid session snapshot"
            )

        position_payload = payload.get("position")

        position = (
            None
            if position_payload is None
            else PaperStateStore._position_from_payload(
                position_payload
            )
        )

        return PaperSessionSnapshot(
            balance=float(payload["balance"]),
            last_candle_timestamp=payload.get(
                "last_candle_timestamp"
            ),
            pending_action=TradeAction(
                payload.get(
                    "pending_action",
                    TradeAction.HOLD.value,
                )
            ),
            pending_stop_loss=(
                None
                if payload.get("pending_stop_loss") is None
                else float(
                    payload["pending_stop_loss"]
                )
            ),
            pending_reference_price=(
                None
                if payload.get(
                    "pending_reference_price"
                ) is None
                else float(
                    payload["pending_reference_price"]
                )
            ),
            pending_trailing_stop_percent=(
                None
                if payload.get(
                    "pending_trailing_stop_percent"
                ) is None
                else float(
                    payload[
                        "pending_trailing_stop_percent"
                    ]
                )
            ),
            position=position,
        )

    @staticmethod
    def _position_from_payload(
        payload: Any,
    ) -> PaperPosition:
        if not isinstance(payload, dict):
            raise ValueError(
                "invalid paper position"
            )

        stop_reason_value = payload.get(
            "stop_reason"
        )

        return PaperPosition(
            side=PositionSide(payload["side"]),
            entry_timestamp=int(
                payload["entry_timestamp"]
            ),
            entry_price=float(
                payload["entry_price"]
            ),
            quantity=float(payload["quantity"]),
            entry_fee=float(payload["entry_fee"]),
            entry_cost=float(payload["entry_cost"]),
            initial_stop_loss=(
                None
                if payload.get(
                    "initial_stop_loss"
                ) is None
                else float(
                    payload["initial_stop_loss"]
                )
            ),
            active_stop_loss=(
                None
                if payload.get(
                    "active_stop_loss"
                ) is None
                else float(
                    payload["active_stop_loss"]
                )
            ),
            stop_reason=(
                None
                if stop_reason_value is None
                else ExitReason(stop_reason_value)
            ),
            trailing_stop_percent=(
                None
                if payload.get(
                    "trailing_stop_percent"
                ) is None
                else float(
                    payload["trailing_stop_percent"]
                )
            ),
        )
