import json

from app.shadow_decision_journal import ShadowDecisionJournal
from scripts import report_shadow_decisions
from tests.test_shadow_decision_journal import record


def test_report_counts_decisions_and_reasons(tmp_path) -> None:
    path = tmp_path / "shadow.jsonl"
    journal = ShadowDecisionJournal(path)
    journal.append(record(1))
    journal.append(
        record(
            2,
            filtered_signal="open_long",
            allowed=True,
            blocked=False,
            blocked_reason=None,
        )
    )

    summary = report_shadow_decisions.build_summary(
        journal.read_all()
    )

    assert summary["evaluated_entries"] == 2
    assert summary["allowed_entries"] == 1
    assert summary["blocked_entries"] == 1
    assert summary["blocked_by_reason"] == {"range": 1}
    assert summary["baseline_only_entries"] == 1
    assert summary["identical_decisions"] == 1


def test_blocked_reasons_sum_matches_blocked_entries(tmp_path) -> None:
    path = tmp_path / "shadow.jsonl"
    journal = ShadowDecisionJournal(path)
    journal.append(record(1))
    journal.append(record(2, blocked_reason="high_volatility"))
    summary = report_shadow_decisions.build_summary(
        journal.read_all()
    )

    assert sum(summary["blocked_by_reason"].values()) == summary[
        "blocked_entries"
    ]


def test_report_filters_and_saves_json(tmp_path) -> None:
    path = tmp_path / "shadow.jsonl"
    output = tmp_path / "report.json"
    journal = ShadowDecisionJournal(path)
    journal.append(record(1, symbol="ETHUSDT"))
    journal.append(record(2, symbol="BTCUSDT"))

    assert report_shadow_decisions.main(
        [
            "--input",
            str(path),
            "--symbol",
            "ETHUSDT",
            "--json-output",
            str(output),
        ]
    ) == 0

    assert json.loads(output.read_text())["records"] == 1
