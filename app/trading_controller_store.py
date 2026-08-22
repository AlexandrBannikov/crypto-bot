from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from app.trading_controller import TradingControllerState
from app.trading_types import TradeAction


CONTROLLER_DECIMAL_FIELDS = {
    "position_quantity", "entry_price", "stop_loss", "virtual_balance",
    "total_fees", "realized_pnl", "entry_fee", "pending_signal_price",
}


def controller_state_to_dict(state: TradingControllerState) -> dict:
    payload = asdict(state)
    for name in CONTROLLER_DECIMAL_FIELDS:
        if payload[name] is not None:
            payload[name] = str(payload[name])
    payload["pending_action"] = state.pending_action.value
    return payload


def controller_state_from_dict(payload: dict) -> TradingControllerState:
    values = dict(payload)
    for name in CONTROLLER_DECIMAL_FIELDS:
        if values.get(name) is not None:
            values[name] = Decimal(str(values[name]))
    values["pending_action"] = TradeAction(values.get("pending_action", "hold"))
    return TradingControllerState(**values)


class TradingControllerStateStore:
    """
    Хранит состояние торгового контроллера в JSON.

    Decimal сохраняется строкой, чтобы не терять точность.
    Старые файлы, где есть только position_quantity,
    продолжают поддерживаться.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> TradingControllerState:
        if not self.path.exists():
            return TradingControllerState()

        try:
            payload = json.loads(
                self.path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"failed to load controller state: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise ValueError(
                "controller state must be a JSON object"
            )

        position_quantity = self._parse_decimal(
            payload.get("position_quantity", "0"),
            field_name="position_quantity",
            allow_none=False,
        )

        entry_price = self._parse_decimal(
            payload.get("entry_price"),
            field_name="entry_price",
            allow_none=True,
        )

        stop_loss = self._parse_decimal(
            payload.get("stop_loss"),
            field_name="stop_loss",
            allow_none=True,
        )

        virtual_balance = self._parse_decimal(
            payload.get("virtual_balance", "1000"),
            field_name="virtual_balance",
            allow_none=False,
        )
        total_fees = self._parse_decimal(
            payload.get("total_fees", "0"),
            field_name="total_fees",
            allow_none=False,
        )
        realized_pnl = self._parse_decimal(
            payload.get("realized_pnl", "0"),
            field_name="realized_pnl",
            allow_none=False,
        )
        entry_fee = self._parse_decimal(
            payload.get("entry_fee", "0"),
            field_name="entry_fee",
            allow_none=False,
        )

        assert position_quantity is not None
        assert virtual_balance is not None
        assert total_fees is not None
        assert realized_pnl is not None
        assert entry_fee is not None

        return TradingControllerState(
            position_quantity=position_quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            virtual_balance=virtual_balance,
            total_fees=total_fees,
            realized_pnl=realized_pnl,
            closed_trades=self._parse_int(
                payload.get("closed_trades", 0),
                field_name="closed_trades",
            ),
            entry_fee=entry_fee,
            opened_at=payload.get("opened_at"),
            pending_action=TradeAction(payload.get("pending_action", "hold")),
            pending_signal_timestamp=payload.get("pending_signal_timestamp"),
            pending_signal_price=self._parse_decimal(
                payload.get("pending_signal_price"),
                field_name="pending_signal_price", allow_none=True,
            ),
            position_signal_timestamp=payload.get("position_signal_timestamp"),
            position_fill_timestamp=payload.get("position_fill_timestamp"),
            position_lifecycle_version=payload.get("position_lifecycle_version"),
            strategy_logic_version=str(payload.get(
                "strategy_logic_version", "strategy_logic_v2_causal"
            )),
            execution_policy_version=str(payload.get(
                "execution_policy_version", "next_candle_open_v1"
            )),
            ledger_schema_version=str(payload.get(
                "ledger_schema_version", "ledger_v2"
            )),
            last_processed_candle_timestamp=payload.get(
                "last_processed_candle_timestamp"
            ),
        )

    def save(
        self,
        state: TradingControllerState,
    ) -> None:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = controller_state_to_dict(state)
        if state.opened_at is None:
            payload.pop("opened_at")

        temporary_path = self.path.with_suffix(
            self.path.suffix + ".tmp"
        )

        try:
            temporary_path.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            temporary_path.replace(self.path)

        except OSError as exc:
            try:
                temporary_path.unlink(
                    missing_ok=True
                )
            except OSError:
                pass

            raise ValueError(
                f"failed to save controller state: {exc}"
            ) from exc

    @staticmethod
    def _parse_decimal(
        value,
        *,
        field_name: str,
        allow_none: bool,
    ) -> Decimal | None:
        if value is None and allow_none:
            return None

        try:
            return Decimal(str(value))
        except Exception as exc:
            raise ValueError(
                f"invalid {field_name} "
                "in controller state"
            ) from exc

    @staticmethod
    def _parse_int(
        value,
        *,
        field_name: str,
    ) -> int:
        if isinstance(value, bool):
            raise ValueError(
                f"invalid {field_name} "
                "in controller state"
            )

        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid {field_name} "
                "in controller state"
            ) from exc

        if parsed != value and str(parsed) != str(value):
            raise ValueError(
                f"invalid {field_name} "
                "in controller state"
            )

        return parsed
