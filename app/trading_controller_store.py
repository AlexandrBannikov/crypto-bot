from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from app.trading_controller import TradingControllerState


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

        assert position_quantity is not None

        return TradingControllerState(
            position_quantity=position_quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
        )

    def save(
        self,
        state: TradingControllerState,
    ) -> None:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "position_quantity": str(
                state.position_quantity
            ),
            "entry_price": (
                str(state.entry_price)
                if state.entry_price is not None
                else None
            ),
            "stop_loss": (
                str(state.stop_loss)
                if state.stop_loss is not None
                else None
            ),
        }

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
