import argparse
import json
from pathlib import Path

from scripts.report_paper_daily import create_report


def files(tmp_path: Path, trade: dict | None = None, shadow: dict | None = None):
    state = tmp_path / "trading_controller.json"
    state.write_text(json.dumps({"position_quantity":"0","entry_price":None,"stop_loss":None,"virtual_balance":"1010","total_fees":"2","realized_pnl":"10","closed_trades":1,"entry_fee":"0"}))
    (tmp_path / "trading_controller_last_candle.txt").write_text("1767265200")
    journal = tmp_path / "journal.jsonl"; journal.write_text((json.dumps(trade) + "\n") if trade else "")
    shadow_path = tmp_path / "shadow.jsonl"; shadow_path.write_text((json.dumps(shadow) + "\n") if shadow else "")
    return argparse.Namespace(date="2026-01-01", timezone="UTC", state_path=state, journal_path=journal, shadow_path=shadow_path, json_output=tmp_path/"out.json", text_output=tmp_path/"out.txt")


def trade():
    return {"record_id":"1","symbol":"ETHUSDT","opened_at":"2026-01-01T01:00:00+00:00","closed_at":"2026-01-01T02:00:00+00:00","entry_price":"100","exit_price":"112","quantity":"1","entry_notional":"100","exit_notional":"112","gross_pnl":"12","entry_fee":"1","exit_fee":"1","total_fee":"2","net_pnl":"10","pnl_percent":"10","exit_reason":"signal","remaining_position_quantity":"0","virtual_balance_after":"1010","realized_pnl_after":"10","closed_trades_after":1}


def test_daily_without_trades_is_valid_and_atomic(tmp_path):
    report = create_report(files(tmp_path))
    assert report["trade_count"] == 0
    assert json.loads((tmp_path / "out.json").read_text())["report_type"] == "daily"
    assert (tmp_path / "out.txt").read_text().startswith("DAILY")


def test_daily_trade_fees_pnl_and_shadow(tmp_path):
    shadow = {"candle_timestamp":1767232800,"baseline_signal":"open_long","filtered_signal":"hold","blocked":True,"blocked_reason":"range","allowed":False,"detector_error":None,"regime":"range/normal"}
    report = create_report(files(tmp_path, trade(), shadow))
    assert (report["trade_count"], report["fees"], report["realised_pnl"]) == (1, "2", "10")
    assert report["shadow"]["blocked_reasons"] == {"range": 1}
    assert report["shadow"]["blocked_entries"] == sum(report["shadow"]["blocked_reasons"].values())
