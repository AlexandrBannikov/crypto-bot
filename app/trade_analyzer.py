from dataclasses import dataclass
from statistics import mean
from typing import Sequence

from app.engine import Candle, Trade
from app.trading_types import PositionSide


@dataclass(frozen=True)
class TradeExcursion:
    trade: Trade
    candles_held: int
    mae_percent: float
    mfe_percent: float


@dataclass(frozen=True)
class TradeAnalysisResult:
    trades: tuple[TradeExcursion, ...]
    average_candles_held: float
    maximum_candles_held: int
    average_mae_percent: float
    worst_mae_percent: float
    average_mfe_percent: float
    best_mfe_percent: float


class TradeAnalyzer:
    def analyze(
        self,
        candles: Sequence[Candle],
        trades: Sequence[Trade],
    ) -> TradeAnalysisResult:
        if not trades:
            return TradeAnalysisResult(
                trades=(),
                average_candles_held=0.0,
                maximum_candles_held=0,
                average_mae_percent=0.0,
                worst_mae_percent=0.0,
                average_mfe_percent=0.0,
                best_mfe_percent=0.0,
            )

        if not candles:
            raise ValueError(
                "candles must not be empty when trades exist"
            )

        timestamp_to_index = self._build_timestamp_index(
            candles
        )

        analyses = [
            self._analyze_trade(
                candles=candles,
                trade=trade,
                timestamp_to_index=timestamp_to_index,
            )
            for trade in trades
        ]

        return TradeAnalysisResult(
            trades=tuple(analyses),
            average_candles_held=mean(
                item.candles_held
                for item in analyses
            ),
            maximum_candles_held=max(
                item.candles_held
                for item in analyses
            ),
            average_mae_percent=mean(
                item.mae_percent
                for item in analyses
            ),
            worst_mae_percent=min(
                item.mae_percent
                for item in analyses
            ),
            average_mfe_percent=mean(
                item.mfe_percent
                for item in analyses
            ),
            best_mfe_percent=max(
                item.mfe_percent
                for item in analyses
            ),
        )

    def _analyze_trade(
        self,
        *,
        candles: Sequence[Candle],
        trade: Trade,
        timestamp_to_index: dict[int, int],
    ) -> TradeExcursion:
        try:
            entry_index = timestamp_to_index[
                trade.entry_timestamp
            ]
        except KeyError as error:
            raise ValueError(
                "trade entry timestamp is missing "
                "from candles"
            ) from error

        try:
            exit_index = timestamp_to_index[
                trade.exit_timestamp
            ]
        except KeyError as error:
            raise ValueError(
                "trade exit timestamp is missing "
                "from candles"
            ) from error

        if exit_index < entry_index:
            raise ValueError(
                "trade exit must not be before entry"
            )

        if trade.entry_price <= 0:
            raise ValueError(
                "trade entry price must be greater than zero"
            )

        trade_candles = candles[
            entry_index:exit_index + 1
        ]

        if trade.side == PositionSide.LONG:
            mae_percent = min(
                (
                    candle.low - trade.entry_price
                )
                / trade.entry_price
                * 100
                for candle in trade_candles
            )

            mfe_percent = max(
                (
                    candle.high - trade.entry_price
                )
                / trade.entry_price
                * 100
                for candle in trade_candles
            )

        elif trade.side == PositionSide.SHORT:
            mae_percent = min(
                (
                    trade.entry_price - candle.high
                )
                / trade.entry_price
                * 100
                for candle in trade_candles
            )

            mfe_percent = max(
                (
                    trade.entry_price - candle.low
                )
                / trade.entry_price
                * 100
                for candle in trade_candles
            )

        else:
            raise ValueError(
                f"unsupported position side: {trade.side}"
            )

        return TradeExcursion(
            trade=trade,
            candles_held=(
                exit_index - entry_index + 1
            ),
            mae_percent=mae_percent,
            mfe_percent=mfe_percent,
        )

    @staticmethod
    def _build_timestamp_index(
        candles: Sequence[Candle],
    ) -> dict[int, int]:
        result: dict[int, int] = {}

        for index, candle in enumerate(candles):
            if candle.timestamp in result:
                raise ValueError(
                    "candle timestamps must be unique"
                )

            result[candle.timestamp] = index

        return result
