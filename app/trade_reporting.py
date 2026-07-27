from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Sequence

import matplotlib

matplotlib.use("Agg")

from matplotlib import pyplot as plt

from app.trade_journal import JsonlTradeJournal, TradeJournalEntry
from app.trade_statistics import (
    TradeStatistics,
    calculate_drawdown_curve,
    calculate_trade_statistics,
)


@dataclass(frozen=True, slots=True)
class TradeReportResult:
    text_report: Path
    png_report: Path


class TradeReportError(RuntimeError):
    """Raised when a trade report cannot be created."""


def _format_optional(value: object | None, *, missing: str) -> str:
    return str(value) if value is not None else missing


def format_trade_statistics(statistics: TradeStatistics) -> list[str]:
    return [
        f"Количество записей: {statistics.total_trades}",
        f"Прибыльных: {statistics.winning_trades}",
        f"Убыточных: {statistics.losing_trades}",
        f"Безубыточных: {statistics.breakeven_trades}",
        f"Win rate: {statistics.win_rate}%",
        f"Суммарный gross PnL: {statistics.gross_pnl}",
        f"Суммарные комиссии: {statistics.total_fees}",
        f"Суммарный net PnL: {statistics.net_pnl}",
        f"Средний net PnL: {statistics.average_net_pnl}",
        f"Gross profit: {statistics.gross_profit}",
        f"Gross loss: {statistics.gross_loss}",
        f"Средняя прибыль: {statistics.average_win}",
        f"Средний убыток: {statistics.average_loss}",
        f"Максимальная прибыль: {statistics.largest_win}",
        f"Максимальный убыток: {statistics.largest_loss}",
        "Profit factor: "
        + _format_optional(statistics.profit_factor, missing="не определён"),
        f"Expectancy: {statistics.expectancy}",
        "Максимальная просадка: "
        f"{statistics.max_drawdown_absolute}",
        "Максимальная просадка, %: "
        f"{statistics.max_drawdown_percent}%",
        "Recovery factor: "
        + _format_optional(statistics.recovery_factor, missing="не определён"),
        "Максимальная серия побед: "
        f"{statistics.longest_win_streak}",
        "Максимальная серия поражений: "
        f"{statistics.longest_loss_streak}",
        "Среднее время удержания, сек.: "
        f"{statistics.average_holding_seconds}",
        "Минимальное время удержания, сек.: "
        f"{statistics.min_holding_seconds}",
        "Максимальное время удержания, сек.: "
        f"{statistics.max_holding_seconds}",
        f"Начальный виртуальный баланс: {statistics.starting_balance}",
        f"Конечный виртуальный баланс: {statistics.ending_balance}",
    ]


def _format_trade(entry: TradeJournalEntry | None) -> str:
    if entry is None:
        return "нет"
    return f"{entry.symbol} {entry.net_pnl} ({entry.record_id})"


def format_trade_report(
    entries: Sequence[TradeJournalEntry],
    statistics: TradeStatistics,
) -> str:
    best = max(
        entries,
        key=lambda entry: entry.net_pnl,
        default=None,
    )
    worst = min(
        entries,
        key=lambda entry: entry.net_pnl,
        default=None,
    )

    return "\n".join(
        format_trade_statistics(statistics)
        + [
            f"Лучшая сделка: {_format_trade(best)}",
            f"Худшая сделка: {_format_trade(worst)}",
            "Итоговый виртуальный баланс: "
            + (
                str(statistics.ending_balance)
                if entries
                else "нет"
            ),
        ]
    )


def _plot_statistics_text(statistics: TradeStatistics) -> str:
    return (
        f"Total trades: {statistics.total_trades}  |  "
        f"Net PnL: {statistics.net_pnl}  |  "
        f"Win rate: {statistics.win_rate}%  |  "
        "Profit factor: "
        f"{_format_optional(statistics.profit_factor, missing='N/A')}\n"
        f"Max drawdown absolute: {statistics.max_drawdown_absolute}  |  "
        f"Max drawdown percent: {statistics.max_drawdown_percent}%  |  "
        f"Starting balance: {statistics.starting_balance}  |  "
        f"Ending balance: {statistics.ending_balance}"
    )


def render_trade_statistics_figure(
    statistics: TradeStatistics,
    *,
    title: str,
    width: float,
    height: float,
):
    figure = None
    try:
        equity = (statistics.starting_balance,) + statistics.equity_curve
        drawdown = calculate_drawdown_curve(
            statistics.starting_balance,
            statistics.equity_curve,
        )
        trade_numbers = range(len(equity))

        figure, (equity_axis, drawdown_axis) = plt.subplots(
            2,
            1,
            figsize=(width, height),
            sharex=True,
        )
        figure.suptitle(
            f"{title}\n{_plot_statistics_text(statistics)}"
        )

        equity_axis.plot(
            trade_numbers,
            [float(value) for value in equity],
            marker="o",
            linewidth=1.8,
        )
        equity_axis.set_title("Equity Curve")
        equity_axis.set_ylabel("Balance")
        equity_axis.grid(True, alpha=0.3)
        equity_axis.annotate(
            f"Starting balance: {statistics.starting_balance}",
            (0, float(equity[0])),
            xytext=(8, 10),
            textcoords="offset points",
        )
        equity_axis.annotate(
            f"Ending balance: {statistics.ending_balance}",
            (len(equity) - 1, float(equity[-1])),
            xytext=(8, -16),
            textcoords="offset points",
            ha="right" if len(equity) > 1 else "left",
        )

        drawdown_values = [float(value) for value in drawdown]
        drawdown_axis.plot(
            trade_numbers,
            drawdown_values,
            color="tab:red",
            marker="o",
            linewidth=1.8,
        )
        drawdown_axis.fill_between(
            trade_numbers,
            drawdown_values,
            color="tab:red",
            alpha=0.15,
        )
        drawdown_axis.set_title("Drawdown Curve")
        drawdown_axis.set_xlabel("Trade number")
        drawdown_axis.set_ylabel("Absolute drawdown")
        drawdown_axis.grid(True, alpha=0.3)

        max_index = drawdown.index(statistics.max_drawdown_absolute)
        drawdown_axis.annotate(
            f"Maximum drawdown: {statistics.max_drawdown_absolute}",
            (max_index, float(drawdown[max_index])),
            xytext=(8, 10),
            textcoords="offset points",
        )

        if statistics.total_trades == 0:
            for axis in (equity_axis, drawdown_axis):
                axis.text(
                    0.5,
                    0.5,
                    "No closed trades",
                    transform=axis.transAxes,
                    ha="center",
                    va="center",
                    fontsize=12,
                    bbox={"facecolor": "white", "alpha": 0.8},
                )

        figure.tight_layout(rect=(0, 0, 1, 0.88))
        return figure
    except BaseException:
        if figure is not None:
            plt.close(figure)
        raise


def _temporary_path(output: Path, *, suffix: str) -> Path:
    descriptor, name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=suffix,
    )
    os.close(descriptor)
    return Path(name)


def save_text_report(report: str, output: str | Path) -> None:
    path = Path(output)
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = _temporary_path(path, suffix=".tmp")
        temporary.write_text(report + "\n", encoding="utf-8")
        temporary.replace(path)
    except Exception as exc:
        raise TradeReportError(
            f"failed to create text trade report {path}: {exc}"
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_trade_statistics_plot(
    statistics: TradeStatistics,
    output: str | Path,
    *,
    title: str = "Trade Statistics",
    dpi: int = 150,
    width: float = 12.0,
    height: float = 9.0,
) -> None:
    path = Path(output)
    temporary: Path | None = None
    figure = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = _temporary_path(path, suffix=".tmp.png")
        figure = render_trade_statistics_figure(
            statistics,
            title=title,
            width=width,
            height=height,
        )
        figure.savefig(temporary, dpi=dpi, format="png")
        temporary.replace(path)
    except Exception as exc:
        raise TradeReportError(
            f"failed to create PNG trade report {path}: {exc}"
        ) from exc
    finally:
        if figure is not None:
            plt.close(figure)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def generate_trade_reports(
    journal_path: str | Path,
    text_report_path: str | Path,
    png_report_path: str | Path,
    *,
    title: str = "Trade Statistics",
    dpi: int = 150,
    width: float = 12.0,
    height: float = 9.0,
) -> TradeReportResult:
    journal = Path(journal_path)
    try:
        entries = JsonlTradeJournal(journal).read_all()
        statistics = calculate_trade_statistics(entries)
    except Exception as exc:
        raise TradeReportError(
            f"failed to process trade journal {journal}: {exc}"
        ) from exc

    text_path = Path(text_report_path)
    png_path = Path(png_report_path)

    try:
        text_report = format_trade_report(entries, statistics)
    except Exception as exc:
        raise TradeReportError(
            f"failed to format text trade report {text_path}: {exc}"
        ) from exc

    save_text_report(text_report, text_path)

    try:
        save_trade_statistics_plot(
            statistics,
            png_path,
            title=title,
            dpi=dpi,
            width=width,
            height=height,
        )
    except TradeReportError:
        raise
    except Exception as exc:
        raise TradeReportError(
            f"failed to create PNG trade report {png_path}: {exc}"
        ) from exc

    return TradeReportResult(
        text_report=text_path,
        png_report=png_path,
    )
