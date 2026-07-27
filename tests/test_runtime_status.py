import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cli_works_from_another_cwd_and_hides_secrets(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/runtime_status.py"), "--json", "--no-network",
         "--state-path", str(tmp_path / "missing.json"), "--journal-path", str(tmp_path / "journal"),
         "--shadow-path", str(tmp_path / "shadow")],
        cwd=tmp_path, text=True, capture_output=True,
        env={"PATH": "/usr/bin", "BYBIT_API_SECRET": "do-not-print"},
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["overall_status"] == "CRITICAL"
    assert "do-not-print" not in result.stdout + result.stderr
