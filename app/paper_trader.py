from dataclasses import dataclass
from pathlib import Path
import csv

from app.engine import Trade


@dataclass(slots=True)
class PaperTraderConfig:
    log_file: Path = Path("logs/paper_trades.csv")


class PaperTrader:
    def __init__(
        self,
        config: PaperTraderConfig | None = None,
    ) -> None:
        self.config = config or PaperTraderConfig()

        self.config.log_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def record_trade(
        self,
        trade: Trade,
    ) -> None:
        file_exists = self.config.log_file.exists()

        with self.config.log_file.open(
            "a",
            newline="",
        ) as f:
            writer = csv.writer(f)

            if not file_exists:
                writer.writerow(
                    [
                        "entry_timestamp",
                        "exit_timestamp",
                        "side",
                        "entry_price",
                        "exit_price",
                        "profit",
                        "profit_percent",
                        "exit_reason",
                    ]
                )

            writer.writerow(
                [
                    trade.entry_timestamp,
                    trade.exit_timestamp,
                    trade.side.value,
                    trade.entry_price,
                    trade.exit_price,
                    trade.profit,
                    trade.profit_percent,
                    trade.exit_reason.value,
                ]
            )
