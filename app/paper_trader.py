from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence
import csv

from app.engine import (
    BacktestEngine,
    BacktestResult,
    Strategy,
    Trade,
)
from app.market_data import MarketDataFeed


class TradeRecorder(Protocol):
    def record_trade(
        self,
        trade: Trade,
    ) -> bool:
        ...


@dataclass(frozen=True, slots=True)
class PaperTraderConfig:
    log_file: Path = Path("logs/paper_trades.csv")


class PaperTrader:
    HEADER = [
        "entry_timestamp",
        "exit_timestamp",
        "side",
        "entry_price",
        "exit_price",
        "quantity",
        "entry_fee",
        "exit_fee",
        "profit",
        "profit_percent",
        "exit_reason",
    ]

    def __init__(
        self,
        config: PaperTraderConfig | None = None,
    ) -> None:
        self.config = config or PaperTraderConfig()

        self.config.log_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def trade_key(
        trade: Trade,
    ) -> tuple[int, int, str, float, float]:
        return (
            trade.entry_timestamp,
            trade.exit_timestamp,
            trade.side.value,
            trade.entry_price,
            trade.exit_price,
        )

    def record_trade(
        self,
        trade: Trade,
    ) -> bool:
        existing_keys = self._read_existing_keys()
        key = self.trade_key(trade)

        if key in existing_keys:
            return False

        file_exists = self.config.log_file.exists()

        with self.config.log_file.open(
            "a",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.writer(file)

            if not file_exists:
                writer.writerow(self.HEADER)

            writer.writerow(
                [
                    trade.entry_timestamp,
                    trade.exit_timestamp,
                    trade.side.value,
                    trade.entry_price,
                    trade.exit_price,
                    trade.quantity,
                    trade.entry_fee,
                    trade.exit_fee,
                    trade.profit,
                    trade.profit_percent,
                    trade.exit_reason.value,
                ]
            )

        return True

    def record_trades(
        self,
        trades: Sequence[Trade],
    ) -> int:
        recorded = 0

        for trade in trades:
            if self.record_trade(trade):
                recorded += 1

        return recorded

    def run_session(
        self,
        *,
        feed: MarketDataFeed,
        strategy: Strategy,
        engine: BacktestEngine | None = None,
    ) -> BacktestResult:
        candles = tuple(feed.get_candles())

        if not candles:
            raise ValueError(
                "market data feed returned no candles"
            )

        trading_engine = engine or BacktestEngine()

        result = trading_engine.run(
            candles,
            strategy,
        )

        self.record_trades(result.trades)

        return result

    def count_recorded_trades(self) -> int:
        return len(self._read_existing_keys())

    def _read_existing_keys(
        self,
    ) -> set[
        tuple[int, int, str, float, float]
    ]:
        if not self.config.log_file.exists():
            return set()

        keys: set[
            tuple[int, int, str, float, float]
        ] = set()

        with self.config.log_file.open(
            newline="",
            encoding="utf-8",
        ) as file:
            reader = csv.DictReader(file)

            required = {
                "entry_timestamp",
                "exit_timestamp",
                "side",
                "entry_price",
                "exit_price",
            }

            if not required.issubset(
                reader.fieldnames or []
            ):
                raise ValueError(
                    "paper trade log has invalid header"
                )

            for row in reader:
                try:
                    key = (
                        int(row["entry_timestamp"]),
                        int(row["exit_timestamp"]),
                        row["side"],
                        float(row["entry_price"]),
                        float(row["exit_price"]),
                    )
                except (
                    KeyError,
                    TypeError,
                    ValueError,
                ) as error:
                    raise ValueError(
                        "paper trade log contains "
                        "invalid row"
                    ) from error

                keys.add(key)

        return keys
