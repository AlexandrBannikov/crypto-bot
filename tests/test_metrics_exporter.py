from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
from urllib.request import urlopen

import pytest

from app.metrics_exporter import (
    CryptoMetricsCollector,
    ExporterPaths,
    V2_CORRECTNESS_FORWARD_TIMESTAMP,
    create_server,
)


LAST = 1787454000
NOW = datetime.fromtimestamp(LAST + 5400, timezone.utc)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(value) + "\n" for value in values), encoding="utf-8")


def runtime_paths(tmp_path: Path, *, long: bool = True) -> ExporterPaths:
    paths = ExporterPaths.from_root(tmp_path)
    write_json(paths.production_state, {
        "position_quantity": "1" if long else "0",
        "entry_price": "90" if long else None,
        "virtual_balance": "900" if long else "1010",
        "realized_pnl": "5" if long else "10",
        "closed_trades": 2,
        "opened_at": "2026-08-22T00:00:00+00:00" if long else None,
    })
    write_jsonl(paths.production_journal, [
        {"net_pnl": "-1"}, {"net_pnl": "2"},
    ])
    write_json(paths.v2_state, {
        "cash": "1005", "equity": "1005", "quantity": "0",
        "weighted_average_entry": None, "last_score": "67.5",
        "realised_pnl": "5", "unrealised_pnl": "0",
        "pending_action": None,
    })
    write_jsonl(paths.v2_journal, [
        {
            "candle_timestamp": V2_CORRECTNESS_FORWARD_TIMESTAMP - 3600,
            "max_drawdown_pct": "99",
            "closed_trade": {"net_pnl": "500"},
        },
        {
            "candle_timestamp": V2_CORRECTNESS_FORWARD_TIMESTAMP,
            "max_drawdown_pct": "1",
            "closed_trade": {"net_pnl": "-2"},
        },
        {
            "candle_timestamp": V2_CORRECTNESS_FORWARD_TIMESTAMP + 3600,
            "max_drawdown_pct": "2",
            "closed_trade": {"net_pnl": "3"},
        },
    ])
    write_json(paths.runtime_state, {
        "maximum_drawdown_percent": "3.5",
        "active_halt_reason": None,
        "counters": {
            "stale_data_rejections": 2,
            "api_error_halts": 3,
            "risk_limit_halts": 4,
        },
    })
    paths.last_candle.parent.mkdir(parents=True, exist_ok=True)
    paths.last_candle.write_text(str(LAST) + "\n", encoding="utf-8")
    write_jsonl(paths.canonical_features, [{
        "candle_timestamp": LAST,
        "score_total": 67.5,
        "feature_version": "scored_features_v1",
    }])
    write_jsonl(paths.production_decisions, [{
        "candle_timestamp": LAST,
        "price": "110",
    }])
    return paths


def collect(paths: ExporterPaths) -> str:
    return CryptoMetricsCollector(paths, clock=lambda: NOW).collect()


def sample(text: str, name: str) -> float:
    match = re.search(rf"^{re.escape(name)}(?:\{{[^}}]*\}})? ([^\n]+)$", text, re.MULTILINE)
    assert match, f"missing sample {name}"
    return float(match.group(1))


def hashes(paths: ExporterPaths) -> dict[str, str]:
    result = {}
    for path in paths.__dict__.values() if hasattr(paths, "__dict__") else (
        paths.production_state, paths.production_journal, paths.v2_state,
        paths.v2_journal, paths.runtime_state, paths.last_candle,
        paths.canonical_features, paths.production_decisions,
    ):
        if path.exists():
            result[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def test_exporter_endpoint_http_200(tmp_path: Path) -> None:
    collector = CryptoMetricsCollector(runtime_paths(tmp_path), clock=lambda: NOW)
    server = create_server("127.0.0.1", 0, collector)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/metrics", timeout=2) as response:
            body = response.read().decode()
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/plain; version=0.0.4")
            assert "crypto_metrics_exporter_up 1" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_production_metrics_and_delta(tmp_path: Path) -> None:
    text = collect(runtime_paths(tmp_path))
    assert sample(text, "crypto_production_cash_usdt") == 900
    assert sample(text, "crypto_production_equity_usdt") == 1010
    assert sample(text, "crypto_production_realized_pnl_usdt") == 5
    assert sample(text, "crypto_production_unrealized_pnl_usdt") == 5
    assert sample(text, "crypto_production_total_pnl_usdt") == 10
    assert sample(text, "crypto_production_total_return_ratio") == pytest.approx(.01)
    assert sample(text, "crypto_v2_vs_production_equity_delta_usdt") == -5


def test_v2_metrics_and_correctness_forward_boundary(tmp_path: Path) -> None:
    text = collect(runtime_paths(tmp_path))
    assert sample(text, "crypto_v2_equity_usdt") == 1005
    assert sample(text, "crypto_v2_score") == 67.5
    assert sample(text, "crypto_v2_closed_trades_total") == 2
    assert sample(text, "crypto_v2_win_rate_ratio") == .5
    assert sample(text, "crypto_v2_max_drawdown_ratio") == .02


def test_flat_positions(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path, long=False)
    text = collect(paths)
    assert sample(text, "crypto_production_position_open") == 0
    assert sample(text, "crypto_production_position_quantity_eth") == 0
    assert "crypto_production_position_entry_price_usdt " not in text
    assert sample(text, "crypto_v2_position_open") == 0
    assert "crypto_v2_position_avg_entry_usdt " not in text


def test_long_positions_and_pending_lifecycle(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path)
    state = json.loads(paths.v2_state.read_text())
    state.update({"quantity": "0.01", "weighted_average_entry": "100", "pending_action": "exit"})
    write_json(paths.v2_state, state)
    text = collect(paths)
    assert sample(text, "crypto_production_position_open") == 1
    assert sample(text, "crypto_production_position_entry_price_usdt") == 90
    assert sample(text, "crypto_production_position_market_value_usdt") == 110
    assert sample(text, "crypto_v2_position_open") == 1
    assert sample(text, "crypto_v2_position_avg_entry_usdt") == 100
    assert sample(text, "crypto_v2_pending_exit") == 1
    assert sample(text, "crypto_v2_pending_entry") == 0


def test_optional_v2_state_missing_keeps_endpoint_usable(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path)
    paths.v2_state.unlink()
    text = collect(paths)
    assert sample(text, "crypto_metrics_exporter_up") == 1
    assert sample(text, "crypto_metrics_exporter_errors_total") >= 1
    assert "crypto_v2_equity_usdt " not in text
    assert "crypto_production_equity_usdt 1010" in text


@pytest.mark.parametrize("content", ["{bad\n", '{"equity":"secret","cash":"1"}\n'])
def test_corrupted_optional_v2_state_is_omitted(tmp_path: Path, content: str) -> None:
    paths = runtime_paths(tmp_path)
    paths.v2_state.write_text(content, encoding="utf-8")
    text = collect(paths)
    assert sample(text, "crypto_metrics_exporter_up") == 1
    assert sample(text, "crypto_metrics_exporter_errors_total") >= 1
    assert "crypto_v2_equity_usdt " not in text
    assert "secret" not in text


def test_no_secrets_or_high_cardinality_labels(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path)
    production = json.loads(paths.production_state.read_text())
    production.update({"api_key": "sk-secret", "account_id": "account-123", "order_id": "order-456"})
    write_json(paths.production_state, production)
    text = collect(paths)
    assert all(secret not in text for secret in ("sk-secret", "account-123", "order-456"))
    label_sets = re.findall(r"^crypto_[^{\n]+\{([^}]*)\}", text, re.MULTILINE)
    assert len(label_sets) == 1
    assert set(re.findall(r"([a-z_]+)=", label_sets[0])) == {
        "strategy_logic_version", "feature_version",
        "execution_policy_version", "ledger_schema_version",
    }
    series = [line for line in text.splitlines() if line.startswith("crypto_")]
    assert len(series) < 100


def test_health_metrics_and_version_info(tmp_path: Path) -> None:
    text = collect(runtime_paths(tmp_path))
    assert sample(text, "crypto_market_lag_candles") == 0
    assert sample(text, "crypto_market_data_ok") == 1
    assert sample(text, "crypto_api_ok") == 1
    assert sample(text, "crypto_trading_health_ok") == 1
    assert sample(text, "crypto_canonical_snapshot_ready") == 1
    assert sample(text, "crypto_stale_events_total") == 2
    assert sample(text, "crypto_api_errors_total") == 3
    assert sample(text, "crypto_risk_halts_total") == 4
    assert 'strategy_logic_version="strategy_logic_v2_causal"' in text
    assert 'execution_policy_version="next_candle_open_v1"' in text


def test_exporter_does_not_mutate_persisted_sources(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path)
    before = hashes(paths)
    collect(paths)
    collect(paths)
    assert hashes(paths) == before


def test_dashboard_json_is_valid_and_covers_required_rows() -> None:
    path = Path(__file__).parents[1] / "grafana/crypto-bot-dashboard.json"
    dashboard = json.loads(path.read_text(encoding="utf-8"))
    assert dashboard["uid"] == "crypto-bot-prod-v2"
    assert dashboard["title"] == "Crypto Bot — Production vs Strategy V2"
    rows = {panel["title"] for panel in dashboard["panels"] if panel["type"] == "row"}
    assert rows == {"Overview", "Equity", "PnL", "Position", "Strategy", "Health"}
    expressions = "\n".join(
        target.get("expr", "")
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    )
    for metric in (
        "crypto_production_equity_usdt", "crypto_v2_equity_usdt",
        "crypto_v2_vs_production_equity_delta_usdt", "crypto_eth_price_usdt",
        "crypto_trading_health_ok", "crypto_market_lag_candles",
        "crypto_v2_pending_entry", "crypto_canonical_score",
        "crypto_api_errors_total", "crypto_risk_halts_total",
    ):
        assert metric in expressions


def test_systemd_unit_is_localhost_only_and_has_no_secret_env() -> None:
    root = Path(__file__).parents[1]
    unit = (root / "deploy/systemd/crypto-metrics-exporter.service").read_text()
    assert "--host 127.0.0.1 --port 9476" in unit
    assert "DynamicUser=yes" in unit
    assert "SupplementaryGroups=crypto-bot-runtime" in unit
    assert "IPAddressAllow=localhost" in unit
    assert "Restart=on-failure" in unit
    assert "EnvironmentFile=" not in unit
    assert all(word not in unit for word in ("BYBIT", "TELEGRAM", "OPENAI"))


def test_non_loopback_bind_is_rejected(tmp_path: Path) -> None:
    collector = CryptoMetricsCollector(runtime_paths(tmp_path), clock=lambda: NOW)
    with pytest.raises(ValueError, match="127.0.0.1"):
        create_server("0.0.0.0", 0, collector)
