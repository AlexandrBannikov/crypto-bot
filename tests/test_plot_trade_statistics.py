from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import subprocess
import sys

import matplotlib

from app.trade_journal import JsonlTradeJournal
from scripts import plot_trade_statistics
from tests.test_trade_journal import make_entry


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def assert_png(path: Path) -> None:
    assert path.exists()
    assert path.stat().st_size > len(PNG_SIGNATURE)
    assert path.read_bytes().startswith(PNG_SIGNATURE)


def test_uses_headless_backend() -> None:
    assert matplotlib.get_backend().lower() == "agg"


def test_custom_journal_output_and_parent_creation(tmp_path) -> None:
    journal_path = tmp_path / "custom.jsonl"
    output = tmp_path / "new" / "nested" / "report.png"
    journal = JsonlTradeJournal(journal_path)
    first = make_entry()
    journal.append(first)
    journal.append(
        replace(
            make_entry(record_id="loss", net_pnl=Decimal("-5")),
            virtual_balance_after=Decimal("1004.790"),
        )
    )

    exit_code = plot_trade_statistics.main(
        [
            "--journal",
            str(journal_path),
            "--output",
            str(output),
            "--title",
            "Custom title",
            "--dpi",
            "72",
            "--width",
            "7",
            "--height",
            "6",
        ]
    )

    assert exit_code == 0
    assert_png(output)


def test_empty_journal_creates_png(tmp_path) -> None:
    output = tmp_path / "empty.png"

    assert plot_trade_statistics.main(
        [
            "--journal",
            str(tmp_path / "missing.jsonl"),
            "--output",
            str(output),
        ]
    ) == 0

    assert_png(output)


def test_corrupt_journal_returns_nonzero_without_png(
    tmp_path,
    capsys,
) -> None:
    journal_path = tmp_path / "broken.jsonl"
    output = tmp_path / "reports" / "broken.png"
    journal_path.write_text("{broken\n", encoding="utf-8")

    exit_code = plot_trade_statistics.main(
        [
            "--journal",
            str(journal_path),
            "--output",
            str(output),
        ]
    )

    assert exit_code != 0
    assert "corrupt trade journal line 1" in capsys.readouterr().err
    assert not output.exists()
    assert not output.parent.exists()


def test_cli_runs_from_project_root_and_creates_png(tmp_path) -> None:
    output = tmp_path / "subprocess.png"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/plot_trade_statistics.py",
            "--journal",
            str(tmp_path / "missing.jsonl"),
            "--output",
            str(output),
            "--title",
            "Subprocess title",
            "--dpi",
            "72",
            "--width",
            "6",
            "--height",
            "5",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert_png(output)
