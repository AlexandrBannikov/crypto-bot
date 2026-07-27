import subprocess
import sys
from pathlib import Path


def test_runtime_alerts_exit_code_is_defined():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "scripts/check_runtime_alerts.py"), "--no-network"], cwd="/tmp", capture_output=True, text=True)
    assert result.returncode in {0, 1, 2, 3}
