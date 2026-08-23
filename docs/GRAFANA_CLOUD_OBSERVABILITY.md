# Grafana Cloud observability

This observability contour is read-only. The exporter imports no controller,
executor, exchange, order, or Telegram modules and never reads credential
files. It binds only to `127.0.0.1:9476`.

## Data flow

`persisted state/JSONL -> localhost exporter -> Alloy scrape -> outbound Grafana Cloud remote_write`

The exporter reads small JSON state files and the newest JSONL records. Closed
trade aggregates are cached by file size and mtime, so journals are not scanned
on every scrape. Strategy V2 historical aggregates exclude rows before
correctness-forward timestamp `1787400000`. SQLite equity history remains
available to other reporting code but is intentionally not opened by the
exporter, avoiding WAL contention.

`crypto_api_ok` is a gauge derived from the controller's persisted active halt;
it is not a live public API probe. Closed-trade totals are exported as gauges
because persisted runtimes can be explicitly rebaselined. Runtime stale/API/
risk counters retain their genuine cumulative semantics and are counters.

## Exporter deployment

Install the committed unit as `/etc/systemd/system/crypto-metrics-exporter.service`,
run `systemctl daemon-reload`, then enable and start it. The service uses a
`DynamicUser` plus the existing read-only `crypto-bot-runtime` supplementary
group. State files stay `0640`; no global permission relaxation is needed.

Verify locally:

```sh
curl --fail --silent http://127.0.0.1:9476/metrics
```

## Alloy activation

Alloy is intentionally not started until Grafana Cloud credentials exist.
Install the official Grafana Alloy package, copy `deploy/alloy/crypto-bot.alloy`
to `/etc/alloy/config.alloy`, and copy the populated environment template to
`/etc/crypto-bot/grafana-cloud.env` with ownership `root:alloy` and mode `0640`.
Install the systemd drop-in and validate the configuration with the installed
Alloy version before starting it.

Required values are:

- `GRAFANA_CLOUD_PROM_URL`
- `GRAFANA_CLOUD_PROM_USER`
- `GRAFANA_CLOUD_PROM_TOKEN`

Never paste the token into source, dashboard JSON, command-line arguments, or
ordinary logs. The dashboard can be imported from
`grafana/crypto-bot-dashboard.json`; select the Grafana Cloud Prometheus
datasource when prompted. Alert rules are prepared in
`grafana/crypto-bot-alert-rules.yaml` but are not activated automatically.
