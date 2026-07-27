# Paper shadow operations

Shadow mode evaluates the regime filter and writes diagnostics, while paper
execution remains identical to baseline. It never enables real-money execution
and needs no private Bybit keys: the controller reads public closed candles and
uses `PaperExecutor` with live execution disabled.

## Configuration and manual operation

```bash
cd /opt/crypto-bot
source venv/bin/activate
cp deploy/crypto-paper-shadow.env.example /tmp/crypto-paper-shadow.env
set -a; source /tmp/crypto-paper-shadow.env; set +a
python scripts/run_bybit_controller.py --strategy-mode shadow
python scripts/runtime_status.py
python scripts/report_paper_daily.py
python scripts/report_paper_weekly.py
python scripts/check_runtime_alerts.py
```

The daily command reports the current calendar date in the requested timezone
(UTC by default). The periodic driver intentionally produces yesterday's
completed daily report and the previous completed Monday-to-Monday week.
Daily and weekly JSON/TXT files are stored under `reports/runtime/daily/` and
`reports/runtime/weekly/`. Writes are atomic. Existing periodic reports are not
replaced unless `--force` is supplied.

Runtime data is in `state/trading_controller.json`,
`state/trading_controller_last_candle.txt`,
`state/controller_trade_journal.jsonl`, and `state/shadow_decisions.jsonl`.
Controller output and errors go to stdout/stderr (journald under systemd).
Shadow JSONL records show baseline, filtered, and execution signals, regime,
confidence, block reason, and detector errors. Reports summarize their
agreement and preserve the invariant that block-reason counts equal blocked
entries.

`WARNING` means attention is needed (for example a moderately stale candle or
missing empty journal); `CRITICAL` means state/data is unusable, severely stale,
or public market data is unavailable. Use `--no-network` to diagnose local
files without any API request. Neither status, alerts, nor reports modify
controller state or trade.

## systemd installation

Review paths and the example environment first. Installation requires root and
is deliberately not performed by project scripts:

```bash
sudo install -d -m 0750 /etc/crypto-bot
sudo install -m 0640 deploy/crypto-paper-shadow.env.example /etc/crypto-bot/paper-shadow.env
sudo install -m 0644 deploy/systemd/crypto-paper-*.service deploy/systemd/crypto-paper-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now crypto-paper-shadow.timer crypto-paper-reports.timer crypto-paper-health.timer
systemctl list-timers 'crypto-paper-*'
journalctl -u crypto-paper-shadow.service
```

To stop scheduling:

```bash
sudo systemctl disable --now crypto-paper-shadow.timer crypto-paper-reports.timer crypto-paper-health.timer
```

To return to baseline, stop the shadow timer and run the controller without
`--strategy-mode shadow`, or set `PAPER_STRATEGY_MODE=baseline`. The filter is
not used for real money and is not enabled for filtered execution by default.
