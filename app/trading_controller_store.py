from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from app.trading_controller import TradingControllerState


class TradingControllerStateStore:
    """
    Хранит состояние торгового контроллера в JSON-файле.

    Decimal сохраняется строкой, чтобы не терять точность.
    Запись выполняется через временный файл.
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

        raw_quantity = payload.get(
            "position_quantity",
            "0",
        )

        try:
            position_quantity = Decimal(
                str(raw_quantity)
            )
        except Exception as exc:
            raise ValueError(
                "invalid position_quantity "
                "in controller state"
            ) from exc

        return TradingControllerState(
            position_quantity=position_quantity,
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
