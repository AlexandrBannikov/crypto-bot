from scripts.report_paper_daily import create_report as daily_report
from scripts.report_paper_weekly import create_report
from tests.test_report_paper_daily import files, trade


def test_weekly_aggregation_and_daily_breakdown(tmp_path):
    args = files(tmp_path, trade())
    args.week_start = "2025-12-29"
    report = create_report(args)
    assert report["trade_count"] == 1
    assert len(report["daily_breakdown"]) == 7
    assert sum(day["trade_count"] for day in report["daily_breakdown"]) == 1
