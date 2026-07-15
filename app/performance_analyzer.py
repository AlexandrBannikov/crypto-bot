from dataclasses import dataclass
from statistics import mean, median
from typing import Sequence

from app.engine import Trade
from app.trading_types import PositionSide


@dataclass(frozen=True)
class SidePerformance:
    trades: int
    winning_trades: int
    losing_trades: int
    total_profit: float
    average_profit: float
    average_profit_percent: float
    win_rate_percent: float


@dataclass(frozen=True)
class PerformanceAnalysisResult:
    trades: int
    winning_trades: int
    losing_trades: int
    break_even_trades: int

    total_profit: float
    average_profit: float
    median_profit: float

    average_profit_percent: float
    median_profit_percent: float

    best_trade_percent: float
    worst_trade_percent: float

    maximum_winning_streak: int
    maximum_losing_streak: int

    long: SidePerformance
    short: SidePerformance


class PerformanceAnalyzer:
    def analyze(
        self,
        trades: Sequence[Trade],
    ) -> PerformanceAnalysisResult:
        if not trades:
            empty_side = self._analyze_side([])

            return PerformanceAnalysisResult(
                trades=0,
                winning_trades=0,
                losing_trades=0,
                break_even_trades=0,
                total_profit=0.0,
                average_profit=0.0,
                median_profit=0.0,
                average_profit_percent=0.0,
                median_profit_percent=0.0,
                best_trade_percent=0.0,
                worst_trade_percent=0.0,
                maximum_winning_streak=0,
                maximum_losing_streak=0,
                long=empty_side,
                short=empty_side,
            )

        winning_trades = [
            trade
            for trade in trades
            if trade.profit > 0
        ]

        losing_trades = [
            trade
            for trade in trades
            if trade.profit < 0
        ]

        break_even_trades = [
            trade
            for trade in trades
            if trade.profit == 0
        ]

        long_trades = [
            trade
            for trade in trades
            if trade.side == PositionSide.LONG
        ]

        short_trades = [
            trade
            for trade in trades
            if trade.side == PositionSide.SHORT
        ]

        return PerformanceAnalysisResult(
            trades=len(trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            break_even_trades=len(break_even_trades),
            total_profit=sum(
                trade.profit
                for trade in trades
            ),
            average_profit=mean(
                trade.profit
                for trade in trades
            ),
            median_profit=median(
                trade.profit
                for trade in trades
            ),
            average_profit_percent=mean(
                trade.profit_percent
                for trade in trades
            ),
            median_profit_percent=median(
                trade.profit_percent
                for trade in trades
            ),
            best_trade_percent=max(
                trade.profit_percent
                for trade in trades
            ),
            worst_trade_percent=min(
                trade.profit_percent
                for trade in trades
            ),
            maximum_winning_streak=self._maximum_streak(
                trades=trades,
                profitable=True,
            ),
            maximum_losing_streak=self._maximum_streak(
                trades=trades,
                profitable=False,
            ),
            long=self._analyze_side(long_trades),
            short=self._analyze_side(short_trades),
        )

    @staticmethod
    def _maximum_streak(
        *,
        trades: Sequence[Trade],
        profitable: bool,
    ) -> int:
        maximum = 0
        current = 0

        for trade in trades:
            matches = (
                trade.profit > 0
                if profitable
                else trade.profit < 0
            )

            if matches:
                current += 1
                maximum = max(maximum, current)
            else:
                current = 0

        return maximum

    @staticmethod
    def _analyze_side(
        trades: Sequence[Trade],
    ) -> SidePerformance:
        if not trades:
            return SidePerformance(
                trades=0,
                winning_trades=0,
                losing_trades=0,
                total_profit=0.0,
                average_profit=0.0,
                average_profit_percent=0.0,
                win_rate_percent=0.0,
            )

        winning_trades = [
            trade
            for trade in trades
            if trade.profit > 0
        ]

        losing_trades = [
            trade
            for trade in trades
            if trade.profit < 0
        ]

        return SidePerformance(
            trades=len(trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            total_profit=sum(
                trade.profit
                for trade in trades
            ),
            average_profit=mean(
                trade.profit
                for trade in trades
            ),
            average_profit_percent=mean(
                trade.profit_percent
                for trade in trades
            ),
            win_rate_percent=(
                len(winning_trades)
                / len(trades)
                * 100
            ),
        )
