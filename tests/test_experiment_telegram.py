from pathlib import Path
from app.telegram_notifications import TelegramPaths,command_response,format_experiments
from tests.test_telegram_notifications import snapshot

def paths(tmp_path):
 return TelegramPaths(tmp_path/"controller",tmp_path/"runtime",tmp_path/"last",tmp_path/"trades",tmp_path/"decisions",tmp_path/"notify",experiments_root=tmp_path/"experiments")

def test_experiments_compact_disabled_no_paths_or_secrets(tmp_path):
 text=command_response("/experiments",snapshot(),paths(tmp_path))
 assert "Experiments — Paper Research" in text and "Status: disabled" in text
 assert str(tmp_path) not in text and "token" not in text.lower() and len(text)<4096

def test_experiment_detail_and_unknown(tmp_path):
 assert "Control Baseline" in command_response("/experiment control_baseline_v1",snapshot(),paths(tmp_path))
 assert command_response("/experiment nope",snapshot(),paths(tmp_path))=="Experiment not found."
