from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class PaperSessionState:
    last_candle_timestamp: int | None = None
    virtual_balance: float = 1000.0
    recorded_trades: int = 0

    def __post_init__(self) -> None:
        if (
            self.last_candle_timestamp is not None
            and self.last_candle_timestamp < 0
        ):
            raise ValueError(
                "last_candle_timestamp must not be negative"
            )

        if self.virtual_balance <= 0:
            raise ValueError(
                "virtual_balance must be greater than zero"
            )

        if self.recorded_trades < 0:
            raise ValueError(
                "recorded_trades must not be negative"
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

    @staticmethod
    def _from_payload(
        payload: dict[str, Any],
    ) -> PaperSessionState:
        try:
            return PaperSessionState(
                last_candle_timestamp=payload.get(
                    "last_candle_timestamp"
                ),
                virtual_balance=float(
                    payload["virtual_balance"]
                ),
                recorded_trades=int(
                    payload.get(
                        "recorded_trades",
                        0,
                    )
                ),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise ValueError(
                "invalid paper state values"
            ) from error
