from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence
import csv

from app.engine import (
    BacktestEngine,
    BacktestResult,
    Candle,
    Strategy,
    Trade,
)
from app.market_data import MarketDataFeed


class TradeRecorder(Protocol):
    def record_trade(
        self,
        trade: Trade,
    ) -> None:
        ...


@dataclass(frozen=True, slots=True)
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
            encoding="utf-8",
        ) as file:
            writer = csv.writer(file)

            if not file_exists:
                writer.writerow(
                    [
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
                )

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

    def record_trades(
        self,
        trades: Sequence[Trade],
    ) -> None:
        for trade in trades:
            self.record_trade(trade)

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
