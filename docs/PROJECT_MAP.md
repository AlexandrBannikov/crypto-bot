# Карта проекта crypto-bot

> Файл создан автоматически командой `python scripts/build_project_index.py`.
> Не редактировать вручную.

Обновлено: **2026-07-27 19:08 UTC**

## Сводка

- Python-файлов: **159**
- Определений: **1361**
- Строк Python-кода: **31616**
- Тестовых модулей: **70**

## Быстрый каталог

- [`app/__init__.py`](../app/__init__.py) — 0 строк, 0 определений
- [`app/backtester.py`](../app/backtester.py) — 188 строк, 1 определений
- [`app/bybit_account.py`](../app/bybit_account.py) — 302 строк, 15 определений
- [`app/bybit_account_check.py`](../app/bybit_account_check.py) — 195 строк, 9 определений
- [`app/bybit_executor.py`](../app/bybit_executor.py) — 226 строк, 11 определений
- [`app/bybit_instruments.py`](../app/bybit_instruments.py) — 199 строк, 8 определений
- [`app/bybit_market_data.py`](../app/bybit_market_data.py) — 343 строк, 10 определений
- [`app/bybit_orders.py`](../app/bybit_orders.py) — 563 строк, 24 определений
- [`app/candle.py`](../app/candle.py) — 11 строк, 1 определений
- [`app/candle_mapper.py`](../app/candle_mapper.py) — 47 строк, 1 определений
- [`app/config.py`](../app/config.py) — 168 строк, 9 определений
- [`app/data_loader.py`](../app/data_loader.py) — 111 строк, 2 определений
- [`app/ema_cross_stop_strategy.py`](../app/ema_cross_stop_strategy.py) — 60 строк, 3 определений
- [`app/ema_cross_strategy.py`](../app/ema_cross_strategy.py) — 131 строк, 6 определений
- [`app/ema_trend_strategy.py`](../app/ema_trend_strategy.py) — 192 строк, 5 определений
- [`app/engine.py`](../app/engine.py) — 884 строк, 19 определений
- [`app/execution.py`](../app/execution.py) — 217 строк, 14 определений
- [`app/execution_config.py`](../app/execution_config.py) — 88 строк, 5 определений
- [`app/execution_runner.py`](../app/execution_runner.py) — 117 строк, 7 определений
- [`app/executor_factory.py`](../app/executor_factory.py) — 64 строк, 1 определений
- [`app/indicators.py`](../app/indicators.py) — 203 строк, 6 определений
- [`app/market_data.py`](../app/market_data.py) — 45 строк, 6 определений
- [`app/market_regime.py`](../app/market_regime.py) — 218 строк, 12 определений
- [`app/metrics.py`](../app/metrics.py) — 31 строк, 2 определений
- [`app/models.py`](../app/models.py) — 51 строк, 4 определений
- [`app/order_builder.py`](../app/order_builder.py) — 135 строк, 9 определений
- [`app/paper_engine.py`](../app/paper_engine.py) — 81 строк, 3 определений
- [`app/paper_executor.py`](../app/paper_executor.py) — 135 строк, 9 определений
- [`app/paper_runtime_reports.py`](../app/paper_runtime_reports.py) — 103 строк, 7 определений
- [`app/paper_session.py`](../app/paper_session.py) — 882 строк, 19 определений
- [`app/paper_state.py`](../app/paper_state.py) — 314 строк, 9 определений
- [`app/paper_statistics.py`](../app/paper_statistics.py) — 91 строк, 1 определений
- [`app/paper_strategy_router.py`](../app/paper_strategy_router.py) — 175 строк, 7 определений
- [`app/paper_trader.py`](../app/paper_trader.py) — 200 строк, 11 определений
- [`app/performance_analyzer.py`](../app/performance_analyzer.py) — 217 строк, 6 определений
- [`app/process_lock.py`](../app/process_lock.py) — 136 строк, 8 определений
- [`app/regime_filter_research.py`](../app/regime_filter_research.py) — 791 строк, 31 определений
- [`app/regime_filtered_strategy.py`](../app/regime_filtered_strategy.py) — 201 строк, 17 определений
- [`app/risk.py`](../app/risk.py) — 152 строк, 7 определений
- [`app/runtime.py`](../app/runtime.py) — 35 строк, 2 определений
- [`app/runtime_health.py`](../app/runtime_health.py) — 208 строк, 10 определений
- [`app/settings.py`](../app/settings.py) — 66 строк, 4 определений
- [`app/shadow_decision_journal.py`](../app/shadow_decision_journal.py) — 169 строк, 9 определений
- [`app/signal_generator.py`](../app/signal_generator.py) — 35 строк, 5 определений
- [`app/signal_normalizer.py`](../app/signal_normalizer.py) — 49 строк, 1 определений
- [`app/stop_manager.py`](../app/stop_manager.py) — 87 строк, 3 определений
- [`app/strategies.py`](../app/strategies.py) — 89 строк, 3 определений
- [`app/trade_accounting.py`](../app/trade_accounting.py) — 61 строк, 2 определений
- [`app/trade_analyzer.py`](../app/trade_analyzer.py) — 198 строк, 6 определений
- [`app/trade_journal.py`](../app/trade_journal.py) — 147 строк, 9 определений
- [`app/trade_reporting.py`](../app/trade_reporting.py) — 336 строк, 12 определений
- [`app/trade_signal.py`](../app/trade_signal.py) — 44 строк, 2 определений
- [`app/trade_statistics.py`](../app/trade_statistics.py) — 265 строк, 5 определений
- [`app/trading_controller.py`](../app/trading_controller.py) — 465 строк, 13 определений
- [`app/trading_controller_store.py`](../app/trading_controller_store.py) — 205 строк, 6 определений
- [`app/trading_filter.py`](../app/trading_filter.py) — 27 строк, 3 определений
- [`app/trading_runtime.py`](../app/trading_runtime.py) — 65 строк, 4 определений
- [`app/trading_types.py`](../app/trading_types.py) — 23 строк, 3 определений
- [`app/trend_detector.py`](../app/trend_detector.py) — 192 строк, 6 определений
- [`app/trend_pullback_strategy.py`](../app/trend_pullback_strategy.py) — 237 строк, 6 определений
- [`scripts/analyze_trends.py`](../scripts/analyze_trends.py) — 105 строк, 1 определений
- [`scripts/backtest.py`](../scripts/backtest.py) — 116 строк, 1 определений
- [`scripts/build_project_index.py`](../scripts/build_project_index.py) — 578 строк, 12 определений
- [`scripts/check_runtime.py`](../scripts/check_runtime.py) — 74 строк, 3 определений
- [`scripts/check_runtime_alerts.py`](../scripts/check_runtime_alerts.py) — 64 строк, 2 определений
- [`scripts/compare_regime_filter_components.py`](../scripts/compare_regime_filter_components.py) — 282 строк, 11 определений
- [`scripts/compare_regime_filters.py`](../scripts/compare_regime_filters.py) — 559 строк, 23 определений
- [`scripts/compare_strategies.py`](../scripts/compare_strategies.py) — 192 строк, 5 определений
- [`scripts/download_eth_5m.py`](../scripts/download_eth_5m.py) — 195 строк, 4 определений
- [`scripts/download_full_history.py`](../scripts/download_full_history.py) — 138 строк, 1 определений
- [`scripts/download_history.py`](../scripts/download_history.py) — 81 строк, 2 определений
- [`scripts/optimize_ema.py`](../scripts/optimize_ema.py) — 168 строк, 2 определений
- [`scripts/optimize_ma.py`](../scripts/optimize_ma.py) — 212 строк, 4 определений
- [`scripts/plot_trade_statistics.py`](../scripts/plot_trade_statistics.py) — 84 строк, 4 определений
- [`scripts/report_paper_daily.py`](../scripts/report_paper_daily.py) — 74 строк, 3 определений
- [`scripts/report_paper_weekly.py`](../scripts/report_paper_weekly.py) — 77 строк, 3 определений
- [`scripts/report_shadow_decisions.py`](../scripts/report_shadow_decisions.py) — 133 строк, 5 определений
- [`scripts/report_trade_journal.py`](../scripts/report_trade_journal.py) — 57 строк, 4 определений
- [`scripts/run_bybit_controller.py`](../scripts/run_bybit_controller.py) — 624 строк, 11 определений
- [`scripts/run_bybit_paper.py`](../scripts/run_bybit_paper.py) — 208 строк, 3 определений
- [`scripts/run_engine_ema.py`](../scripts/run_engine_ema.py) — 128 строк, 2 определений
- [`scripts/run_periodic_reports.py`](../scripts/run_periodic_reports.py) — 51 строк, 2 определений
- [`scripts/run_strategy_comparison.py`](../scripts/run_strategy_comparison.py) — 102 строк, 3 определений
- [`scripts/run_trend_pullback.py`](../scripts/run_trend_pullback.py) — 115 строк, 2 определений
- [`scripts/run_trend_pullback_5m.py`](../scripts/run_trend_pullback_5m.py) — 176 строк, 2 определений
- [`scripts/runtime_status.py`](../scripts/runtime_status.py) — 96 строк, 3 определений
- [`scripts/validate_ema_out_of_sample.py`](../scripts/validate_ema_out_of_sample.py) — 169 строк, 4 определений
- [`scripts/walk_forward_ema.py`](../scripts/walk_forward_ema.py) — 427 строк, 7 определений
- [`scripts/walk_forward_regime_filter.py`](../scripts/walk_forward_regime_filter.py) — 270 строк, 11 определений
- [`tests/__init__.py`](../tests/__init__.py) — 0 строк, 0 определений
- [`tests/test_backtester.py`](../tests/test_backtester.py) — 164 строк, 9 определений
- [`tests/test_bybit_account.py`](../tests/test_bybit_account.py) — 338 строк, 16 определений
- [`tests/test_bybit_account_check.py`](../tests/test_bybit_account_check.py) — 234 строк, 17 определений
- [`tests/test_bybit_executor.py`](../tests/test_bybit_executor.py) — 378 строк, 18 определений
- [`tests/test_bybit_instruments.py`](../tests/test_bybit_instruments.py) — 118 строк, 4 определений
- [`tests/test_bybit_market_data.py`](../tests/test_bybit_market_data.py) — 310 строк, 12 определений
- [`tests/test_bybit_orders.py`](../tests/test_bybit_orders.py) — 476 строк, 13 определений
- [`tests/test_candle_mapper.py`](../tests/test_candle_mapper.py) — 75 строк, 5 определений
- [`tests/test_check_runtime.py`](../tests/test_check_runtime.py) — 45 строк, 4 определений
- [`tests/test_check_runtime_alerts.py`](../tests/test_check_runtime_alerts.py) — 9 строк, 1 определений
- [`tests/test_compare_regime_filter_components.py`](../tests/test_compare_regime_filter_components.py) — 458 строк, 28 определений
- [`tests/test_compare_regime_filters.py`](../tests/test_compare_regime_filters.py) — 451 строк, 14 определений
- [`tests/test_config.py`](../tests/test_config.py) — 123 строк, 12 определений
- [`tests/test_data_loader.py`](../tests/test_data_loader.py) — 107 строк, 9 определений
- [`tests/test_ema_cross_stop_strategy.py`](../tests/test_ema_cross_stop_strategy.py) — 86 строк, 4 определений
- [`tests/test_ema_cross_strategy.py`](../tests/test_ema_cross_strategy.py) — 160 строк, 9 определений
- [`tests/test_ema_trend_strategy.py`](../tests/test_ema_trend_strategy.py) — 79 строк, 4 определений
- [`tests/test_engine.py`](../tests/test_engine.py) — 850 строк, 61 определений
- [`tests/test_execution.py`](../tests/test_execution.py) — 220 строк, 9 определений
- [`tests/test_execution_config.py`](../tests/test_execution_config.py) — 145 строк, 8 определений
- [`tests/test_execution_runner.py`](../tests/test_execution_runner.py) — 179 строк, 15 определений
- [`tests/test_executor_factory.py`](../tests/test_executor_factory.py) — 156 строк, 10 определений
- [`tests/test_indicators.py`](../tests/test_indicators.py) — 368 строк, 22 определений
- [`tests/test_market_data.py`](../tests/test_market_data.py) — 182 строк, 8 определений
- [`tests/test_market_regime.py`](../tests/test_market_regime.py) — 238 строк, 11 определений
- [`tests/test_metrics.py`](../tests/test_metrics.py) — 34 строк, 6 определений
- [`tests/test_models.py`](../tests/test_models.py) — 27 строк, 1 определений
- [`tests/test_order_builder.py`](../tests/test_order_builder.py) — 151 строк, 9 определений
- [`tests/test_paper_engine.py`](../tests/test_paper_engine.py) — 232 строк, 12 определений
- [`tests/test_paper_executor.py`](../tests/test_paper_executor.py) — 167 строк, 10 определений
- [`tests/test_paper_session.py`](../tests/test_paper_session.py) — 936 строк, 44 определений
- [`tests/test_paper_state.py`](../tests/test_paper_state.py) — 213 строк, 8 определений
- [`tests/test_paper_statistics.py`](../tests/test_paper_statistics.py) — 95 строк, 5 определений
- [`tests/test_paper_strategy_router.py`](../tests/test_paper_strategy_router.py) — 214 строк, 12 определений
- [`tests/test_paper_trader.py`](../tests/test_paper_trader.py) — 339 строк, 18 определений
- [`tests/test_performance_analyzer.py`](../tests/test_performance_analyzer.py) — 136 строк, 6 определений
- [`tests/test_plot_trade_statistics.py`](../tests/test_plot_trade_statistics.py) — 154 строк, 7 определений
- [`tests/test_process_lock.py`](../tests/test_process_lock.py) — 178 строк, 13 определений
- [`tests/test_regime_filtered_strategy.py`](../tests/test_regime_filtered_strategy.py) — 279 строк, 20 определений
- [`tests/test_report_paper_daily.py`](../tests/test_report_paper_daily.py) — 33 строк, 4 определений
- [`tests/test_report_paper_weekly.py`](../tests/test_report_paper_weekly.py) — 12 строк, 1 определений
- [`tests/test_report_trade_journal.py`](../tests/test_report_trade_journal.py) — 82 строк, 4 определений
- [`tests/test_risk.py`](../tests/test_risk.py) — 272 строк, 13 определений
- [`tests/test_run_bybit_controller.py`](../tests/test_run_bybit_controller.py) — 798 строк, 28 определений
- [`tests/test_run_bybit_paper.py`](../tests/test_run_bybit_paper.py) — 122 строк, 7 определений
- [`tests/test_run_periodic_reports.py`](../tests/test_run_periodic_reports.py) — 40 строк, 5 определений
- [`tests/test_runtime.py`](../tests/test_runtime.py) — 41 строк, 4 определений
- [`tests/test_runtime_health.py`](../tests/test_runtime_health.py) — 69 строк, 7 определений
- [`tests/test_runtime_status.py`](../tests/test_runtime_status.py) — 20 строк, 1 определений
- [`tests/test_settings.py`](../tests/test_settings.py) — 66 строк, 4 определений
- [`tests/test_shadow_decision_journal.py`](../tests/test_shadow_decision_journal.py) — 112 строк, 8 определений
- [`tests/test_shadow_report.py`](../tests/test_shadow_report.py) — 66 строк, 3 определений
- [`tests/test_signal_generator.py`](../tests/test_signal_generator.py) — 138 строк, 12 определений
- [`tests/test_signal_normalizer.py`](../tests/test_signal_normalizer.py) — 74 строк, 5 определений
- [`tests/test_stop_manager.py`](../tests/test_stop_manager.py) — 155 строк, 14 определений
- [`tests/test_strategies.py`](../tests/test_strategies.py) — 90 строк, 6 определений
- [`tests/test_trade_accounting.py`](../tests/test_trade_accounting.py) — 74 строк, 4 определений
- [`tests/test_trade_analyzer.py`](../tests/test_trade_analyzer.py) — 282 строк, 8 определений
- [`tests/test_trade_journal.py`](../tests/test_trade_journal.py) — 88 строк, 5 определений
- [`tests/test_trade_reporting.py`](../tests/test_trade_reporting.py) — 314 строк, 15 определений
- [`tests/test_trade_statistics.py`](../tests/test_trade_statistics.py) — 258 строк, 14 определений
- [`tests/test_trading_controller.py`](../tests/test_trading_controller.py) — 702 строк, 38 определений
- [`tests/test_trading_controller_store.py`](../tests/test_trading_controller_store.py) — 254 строк, 11 определений
- [`tests/test_trading_filter.py`](../tests/test_trading_filter.py) — 98 строк, 9 определений
- [`tests/test_trading_runtime.py`](../tests/test_trading_runtime.py) — 96 строк, 6 определений
- [`tests/test_trading_types.py`](../tests/test_trading_types.py) — 22 строк, 3 определений
- [`tests/test_trend_detector.py`](../tests/test_trend_detector.py) — 245 строк, 9 определений
- [`tests/test_trend_pullback_strategy.py`](../tests/test_trend_pullback_strategy.py) — 290 строк, 14 определений
- [`tests/test_walk_forward_regime_filter.py`](../tests/test_walk_forward_regime_filter.py) — 774 строк, 26 определений

## `app/`

### [`app/__init__.py`](../app/__init__.py)

Строк: **0**

_Публичных классов и функций не найдено._
### [`app/backtester.py`](../app/backtester.py)

Строк: **188**

Связанные тесты: [`tests/test_backtester.py`](../tests/test_backtester.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `run_backtest(data: pd.DataFrame, signals: pd.Series, start_balance: float = 1000.0, fee_rate: float = 0.001) -> BacktestResult` | 11 |  |
### [`app/bybit_account.py`](../app/bybit_account.py)

Строк: **302**

Связанные тесты: [`tests/test_bybit_account.py`](../tests/test_bybit_account.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `BybitAccountConfig` | 19 |  |
| method | `__post_init__(self) -> None` | 27 |  |
| dataclass | `WalletBalance` | 52 |  |
| method | `__post_init__(self) -> None` | 57 |  |
| dataclass | `BybitApiKeyInfo` | 75 |  |
| class | `BybitAPIError` | 81 |  |
| method | `__init__(self, ret_code: int \| None, ret_msg: str) -> None` | 82 |  |
| class | `BybitAccountClient` | 99 |  |
| method | `__init__(self, config: BybitAccountConfig, *, http_get_json: HttpGetJSON \| None = None, clock_ms: ClockMS \| None = None) -> None` | 100 |  |
| method | `base_url(self) -> str` | 116 |  |
| method | `get_wallet_balance(self, *, account_type: str = 'UNIFIED', coin: str = 'USDT') -> WalletBalance` | 125 |  |
| method | `get_api_key_info(self) -> BybitApiKeyInfo` | 189 |  |
| method | `_signed_get(self, path: str, params: dict[str, str]) -> dict[str, Any]` | 223 |  |
| method | `_sign_get(self, timestamp: str, recv_window: str, query: str) -> str` | 266 |  |
| method | `_default_http_get_json(url: str, headers: dict[str, str], timeout_seconds: float) -> dict[str, Any]` | 283 |  |
### [`app/bybit_account_check.py`](../app/bybit_account_check.py)

Строк: **195**

Связанные тесты: [`tests/test_bybit_account_check.py`](../tests/test_bybit_account_check.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| enum | `AccountCheckStatus` | 14 |  |
| dataclass | `BybitAccountCheckResult` | 26 |  |
| method | `ok(self) -> bool` | 40 |  |
| class | `BybitAccountChecker` | 44 |  |
| method | `__init__(self, client: BybitAccountClient) -> None` | 53 |  |
| method | `check(self) -> BybitAccountCheckResult` | 56 |  |
| method | `_detect_environment(self) -> str` | 142 |  |
| method | `_trading_allowed(*, read_only: bool, permissions: dict[str, list[str]]) -> bool` | 151 |  |
| method | `_result(*, status: AccountCheckStatus, environment: str, safe_message: str, api_key_valid: bool = False, api_secret_valid: bool = False) -> BybitAccountCheckResult` | 175 |  |
### [`app/bybit_executor.py`](../app/bybit_executor.py)

Строк: **226**

Связанные тесты: [`tests/test_bybit_executor.py`](../tests/test_bybit_executor.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `BybitExecutor` | 28 |  |
| method | `__init__(self, client: BybitOrderClient, *, dry_run: bool = False) -> None` | 29 |  |
| method | `mode(self) -> ExecutionMode` | 39 |  |
| method | `open_position(self, request: ExecutionRequest) -> ExecutionResult` | 45 |  |
| method | `close_position(self, request: ExecutionRequest) -> ExecutionResult` | 52 |  |
| method | `_submit(self, request: ExecutionRequest, *, bybit_side: str) -> ExecutionResult` | 59 |  |
| method | `get_order_status(self, *, symbol: str, order_id: str \| None = None, client_order_id: str \| None = None) -> ExecutionResult` | 110 |  |
| method | `cancel_order(self, *, symbol: str, order_id: str \| None = None, client_order_id: str \| None = None) -> ExecutionResult` | 130 |  |
| method | `_status_to_execution_result(self, status: OrderStatus) -> ExecutionResult` | 173 |  |
| method | `_require_long_position(request: ExecutionRequest) -> None` | 208 |  |
| method | `_position_side_from_order(status: OrderStatus) -> PositionSide` | 218 |  |
### [`app/bybit_instruments.py`](../app/bybit_instruments.py)

Строк: **199**

Связанные тесты: [`tests/test_bybit_instruments.py`](../tests/test_bybit_instruments.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `_default_http_get_json(url: str, timeout_seconds: float) -> dict` | 15 |  |
| function | `_parse_decimal(value: object, *, default: str = '0') -> Decimal` | 39 |  |
| dataclass | `InstrumentInfo` | 56 |  |
| method | `__post_init__(self) -> None` | 65 |  |
| method | `is_trading(self) -> bool` | 99 |  |
| class | `BybitInstrumentClient` | 103 |  |
| method | `__init__(self, *, base_url: str = MAINNET_BASE_URL, timeout_seconds: float = 10.0, http_get_json: Callable[[str, float], dict] = _default_http_get_json) -> None` | 104 |  |
| method | `get_spot_instrument(self, symbol: str) -> InstrumentInfo` | 122 |  |
### [`app/bybit_market_data.py`](../app/bybit_market_data.py)

Строк: **343**

Связанные тесты: [`tests/test_bybit_market_data.py`](../tests/test_bybit_market_data.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `BybitMarketDataConfig` | 44 |  |
| method | `__post_init__(self) -> None` | 55 |  |
| class | `BybitMarketDataFeed` | 103 |  |
| method | `__init__(self, config: BybitMarketDataConfig \| None = None, *, http_get_json: HttpGetJson \| None = None, clock_ms: ClockMilliseconds \| None = None) -> None` | 104 |  |
| method | `get_candles(self) -> tuple[Candle, ...]` | 126 |  |
| method | `get_latest_candle(self) -> Candle` | 193 |  |
| method | `_extract_rows(payload: JsonObject) -> list[list[str]]` | 197 |  |
| method | `_row_to_candle(row: list[str]) -> Candle` | 229 |  |
| method | `_default_clock_ms() -> int` | 292 |  |
| method | `_default_http_get_json(url: str, params: dict[str, str \| int], timeout_seconds: float) -> JsonObject` | 296 |  |
### [`app/bybit_orders.py`](../app/bybit_orders.py)

Строк: **563**

Связанные тесты: [`tests/test_bybit_orders.py`](../tests/test_bybit_orders.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `OrderResult` | 28 |  |
| dataclass | `CancelOrderResult` | 36 |  |
| dataclass | `OrderStatus` | 44 |  |
| class | `BybitOrderClient` | 68 |  |
| method | `__init__(self, config: BybitAccountConfig, *, http_get_json: HttpGetJSON \| None = None, http_post_json: HttpPostJSON \| None = None, clock_ms: ClockMS \| None = None) -> None` | 69 |  |
| method | `base_url(self) -> str` | 89 |  |
| method | `create_limit_order(self, order: SpotLimitOrder, *, order_link_id: str \| None = None, dry_run: bool = True) -> OrderResult` | 98 |  |
| method | `get_order(self, *, symbol: str, order_id: str \| None = None, order_link_id: str \| None = None) -> OrderStatus` | 145 |  |
| method | `cancel_order(self, *, symbol: str, order_id: str \| None = None, order_link_id: str \| None = None, dry_run: bool = True) -> CancelOrderResult` | 221 |  |
| method | `_signed_get(self, path: str, query: dict[str, str]) -> dict[str, Any]` | 284 |  |
| method | `_signed_post(self, path: str, payload: dict[str, str]) -> dict[str, Any]` | 311 |  |
| method | `_signed_headers(self, timestamp: str, recv_window: str, signature: str) -> dict[str, str]` | 344 |  |
| method | `_sign_get(self, timestamp: str, recv_window: str, query_text: str) -> str` | 358 |  |
| method | `_sign_post(self, timestamp: str, recv_window: str, body_text: str) -> str` | 370 |  |
| method | `_create_signature(self, timestamp: str, recv_window: str, request_data: str) -> str` | 382 |  |
| method | `_raise_for_api_error(response: dict[str, Any]) -> None` | 402 |  |
| method | `_require_result_dict(response: dict[str, Any], error_message: str) -> dict[str, Any]` | 428 |  |
| method | `_normalize_symbol(symbol: str) -> str` | 440 |  |
| method | `_normalize_order_identifiers(cls, *, order_id: str \| None, order_link_id: str \| None) -> tuple[str \| None, str \| None]` | 449 |  |
| method | `_normalize_identifier(value: str, field_name: str) -> str` | 480 |  |
| method | `_optional_string(value: Any) -> str \| None` | 494 |  |
| method | `_decimal_or_zero(value: Any) -> Decimal` | 502 |  |
| method | `_default_http_get_json(url: str, headers: dict[str, str], timeout_seconds: float) -> dict[str, Any]` | 514 |  |
| method | `_default_http_post_json(url: str, headers: dict[str, str], body: bytes, timeout_seconds: float) -> dict[str, Any]` | 539 |  |
### [`app/candle.py`](../app/candle.py)

Строк: **11**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `Candle` | 5 |  |
### [`app/candle_mapper.py`](../app/candle_mapper.py)

Строк: **47**

Связанные тесты: [`tests/test_candle_mapper.py`](../tests/test_candle_mapper.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `dataframe_to_candles(data: pd.DataFrame) -> list[Candle]` | 16 |  |
### [`app/config.py`](../app/config.py)

Строк: **168**

Связанные тесты: [`tests/test_config.py`](../tests/test_config.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `BacktestConfig` | 9 |  |
| method | `__post_init__(self) -> None` | 15 |  |
| enum | `PaperStrategyMode` | 34 |  |
| dataclass | `PaperStrategyConfig` | 41 |  |
| method | `__post_init__(self) -> None` | 54 |  |
| method | `from_env(cls, *, mode_override: str \| None = None) -> 'PaperStrategyConfig'` | 102 |  |
| function | `_env_int(name: str, default: int) -> int` | 145 |  |
| function | `_env_float(name: str, default: float) -> float` | 152 |  |
| function | `_env_bool(name: str, default: bool) -> bool` | 159 |  |
### [`app/data_loader.py`](../app/data_loader.py)

Строк: **111**

Связанные тесты: [`tests/test_data_loader.py`](../tests/test_data_loader.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `load_market_data(file_path: str \| Path) -> pd.DataFrame` | 16 |  |
| function | `find_missing_hours(frame: pd.DataFrame) -> pd.DatetimeIndex` | 91 |  |
### [`app/ema_cross_stop_strategy.py`](../app/ema_cross_stop_strategy.py)

Строк: **60**

Связанные тесты: [`tests/test_ema_cross_stop_strategy.py`](../tests/test_ema_cross_stop_strategy.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `EMACrossStopStrategy` | 9 |  |
| method | `__init__(self, short_period: int = 40, long_period: int = 300, stop_loss_percent: float = 5.0) -> None` | 10 |  |
| method | `generate_signal(self, candles: Sequence[Candle], index: int) -> TradeSignal \| TradeAction` | 33 |  |
### [`app/ema_cross_strategy.py`](../app/ema_cross_strategy.py)

Строк: **131**

Связанные тесты: [`tests/test_ema_cross_strategy.py`](../tests/test_ema_cross_strategy.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `EMACrossStrategy` | 7 |  |
| method | `__init__(self, short_period: int = 20, long_period: int = 50) -> None` | 8 |  |
| method | `generate_signal(self, candles: Sequence[Candle], index: int) -> Signal` | 40 |  |
| method | `_update_ema(self, close: float) -> None` | 87 |  |
| method | `_reset(self) -> None` | 106 |  |
| method | `_calculate_ema(values: Sequence[float], period: int) -> float` | 114 |  |
### [`app/ema_trend_strategy.py`](../app/ema_trend_strategy.py)

Строк: **192**

Связанные тесты: [`tests/test_ema_trend_strategy.py`](../tests/test_ema_trend_strategy.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `EMATrendStrategy` | 7 |  |
| method | `__init__(self, fast_period: int = 40, slow_period: int = 300, trend_period: int = 300, trend_slope_lookback: int = 24) -> None` | 8 |  |
| method | `generate_signal(self, candles: Sequence[Candle], index: int) -> TradeAction` | 63 |  |
| method | `_update_emas(self, close: float) -> None` | 141 |  |
| method | `_reset(self) -> None` | 181 |  |
### [`app/engine.py`](../app/engine.py)

Строк: **884**

Связанные тесты: [`tests/test_engine.py`](../tests/test_engine.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `Trade` | 22 |  |
| dataclass | `BacktestResult` | 37 |  |
| protocol | `Strategy` | 56 |  |
| method | `generate_signal(self, candles: Sequence[Candle], index: int) -> Signal \| TradeSignal \| TradeAction` | 57 |  |
| class | `BacktestEngine` | 65 |  |
| method | `__init__(self, initial_balance: float = 10000.0, commission_rate: float = 0.001, risk_config: RiskConfig \| None = None) -> None` | 66 |  |
| method | `run(self, candles: Sequence[Candle], strategy: Strategy) -> BacktestResult` | 87 |  |
| method | `_open_position(self, *, side: PositionSide, balance: float, candle: Candle, stop_loss: float \| None, risk_reference_price: float \| None) -> tuple[PositionSide, float, int, float, float, float, float]` | 359 |  |
| method | `_close_position(self, *, side: PositionSide, quantity: float, exit_timestamp: int, exit_price: float, entry_timestamp: int, entry_price: float, entry_fee: float, entry_cost: float, exit_reason: ExitReason) -> tuple[float, Trade]` | 436 |  |
| method | `_empty_position() -> tuple[None, float, None, None, float, float]` | 499 |  |
| method | `_resolve_pending_action(*, requested_action: TradeAction, position_side: PositionSide \| None) -> TradeAction` | 517 |  |
| method | `_validate_stop_loss(*, side: PositionSide, entry_price: float, stop_loss: float \| None) -> None` | 546 |  |
| method | `_trail_stop(*, side: PositionSide, current_stop: float, close_price: float, trailing_stop_percent: float) -> float` | 574 |  |
| method | `_stop_was_hit(*, side: PositionSide, candle: Candle, stop_loss: float) -> bool` | 603 |  |
| method | `_stop_exit_price(*, side: PositionSide, candle: Candle, stop_loss: float) -> float` | 615 |  |
| method | `_calculate_equity(*, balance: float, position_side: PositionSide \| None, quantity: float, entry_price: float \| None, entry_fee: float, entry_cost: float, current_price: float) -> float` | 633 |  |
| method | `_build_result(self, *, final_balance: float, trades: list[Trade], equity_curve: Sequence[float]) -> BacktestResult` | 667 |  |
| method | `_calculate_max_drawdown(equity_curve: Sequence[float]) -> float` | 814 |  |
| method | `_validate_candle(candle: Candle) -> None` | 842 |  |
### [`app/execution.py`](../app/execution.py)

Строк: **217**

Связанные тесты: [`tests/test_execution.py`](../tests/test_execution.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| enum | `ExecutionMode` | 9 |  |
| enum | `ExecutionStatus` | 15 |  |
| dataclass | `ExecutionRequest` | 26 |  |
| method | `__post_init__(self) -> None` | 33 |  |
| dataclass | `ExecutionResult` | 73 |  |
| method | `__post_init__(self) -> None` | 86 |  |
| method | `is_successful(self) -> bool` | 167 |  |
| method | `is_complete(self) -> bool` | 174 |  |
| protocol | `TradeExecutor` | 184 |  |
| method | `mode(self) -> ExecutionMode` | 186 |  |
| method | `open_position(self, request: ExecutionRequest) -> ExecutionResult` | 189 |  |
| method | `close_position(self, request: ExecutionRequest) -> ExecutionResult` | 195 |  |
| method | `cancel_order(self, *, symbol: str, order_id: str \| None = None, client_order_id: str \| None = None) -> ExecutionResult` | 201 |  |
| method | `get_order_status(self, *, symbol: str, order_id: str \| None = None, client_order_id: str \| None = None) -> ExecutionResult` | 210 |  |
### [`app/execution_config.py`](../app/execution_config.py)

Строк: **88**

Связанные тесты: [`tests/test_execution_config.py`](../tests/test_execution_config.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `ExecutionConfigurationError` | 10 | Небезопасная или неполная конфигурация исполнения. |
| dataclass | `ExecutionConfig` | 15 |  |
| method | `uses_exchange(self) -> bool` | 21 |  |
| method | `submits_orders(self) -> bool` | 25 |  |
| function | `build_execution_config(settings: Settings) -> ExecutionConfig` | 32 |  |
### [`app/execution_runner.py`](../app/execution_runner.py)

Строк: **117**

Связанные тесты: [`tests/test_execution_runner.py`](../tests/test_execution_runner.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `ExecutionRunnerError` | 18 | Ошибка координации исполнения торгового действия. |
| dataclass | `ExecutionCommand` | 23 |  |
| method | `__post_init__(self) -> None` | 30 |  |
| class | `ExecutionRunner` | 53 | Координатор между торговым действием и TradeExecutor. |
| method | `__init__(self, executor: TradeExecutor, *, allow_live: bool = False) -> None` | 65 |  |
| method | `execute(self, command: ExecutionCommand) -> ExecutionResult \| None` | 74 |  |
| method | `_ensure_safe_mode(self) -> None` | 110 |  |
### [`app/executor_factory.py`](../app/executor_factory.py)

Строк: **64**

Связанные тесты: [`tests/test_executor_factory.py`](../tests/test_executor_factory.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `build_executor(config: ExecutionConfig, *, bybit_client_factory: Callable[[BybitAccountConfig], BybitOrderClient] = BybitOrderClient) -> TradeExecutor` | 13 |  |
### [`app/indicators.py`](../app/indicators.py)

Строк: **203**

Связанные тесты: [`tests/test_indicators.py`](../tests/test_indicators.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `sma(series: pd.Series, period: int) -> pd.Series` | 4 |  |
| function | `ema(series: pd.Series, period: int) -> pd.Series` | 11 |  |
| function | `rsi(series: pd.Series, period: int = 14) -> pd.Series` | 22 |  |
| function | `true_range(data: pd.DataFrame) -> pd.Series` | 60 |  |
| function | `atr(data: pd.DataFrame, period: int = 14) -> pd.Series` | 88 |  |
| function | `adx(data: pd.DataFrame, period: int = 14) -> pd.Series` | 106 |  |
### [`app/market_data.py`](../app/market_data.py)

Строк: **45**

Связанные тесты: [`tests/test_market_data.py`](../tests/test_market_data.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| protocol | `MarketDataFeed` | 9 |  |
| method | `get_candles(self) -> Sequence[Candle]` | 10 |  |
| class | `CsvMarketDataFeed` | 14 |  |
| method | `__init__(self, file_path: str \| Path, *, limit: int \| None = None) -> None` | 15 |  |
| method | `get_candles(self) -> tuple[Candle, ...]` | 29 |  |
| method | `get_latest_candle(self) -> Candle` | 39 |  |
### [`app/market_regime.py`](../app/market_regime.py)

Строк: **218**

Связанные тесты: [`tests/test_market_regime.py`](../tests/test_market_regime.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| enum | `MarketTrend` | 11 |  |
| enum | `MarketVolatility` | 18 |  |
| dataclass | `MarketRegime` | 25 |  |
| method | `__post_init__(self) -> None` | 30 |  |
| class | `MarketRegimeDetector` | 35 |  |
| method | `__init__(self, fast_ema_period: int = 20, slow_ema_period: int = 50, adx_period: int = 14, adx_threshold: float = 20.0, atr_period: int = 14, low_volatility_threshold: float = 0.005, high_volatility_threshold: float = 0.02) -> None` | 36 |  |
| method | `detect(self, candles: Sequence[Candle]) -> MarketRegime` | 90 |  |
| method | `_detect_trend_with_adx(self, candles: Sequence[Candle]) -> MarketTrend` | 118 |  |
| method | `_detect_volatility(self, candles: Sequence[Candle]) -> MarketVolatility` | 137 |  |
| method | `_detect_ema_trend(self, candles: Sequence[Candle]) -> MarketTrend` | 166 |  |
| method | `_candles_to_dataframe(candles: Sequence[Candle]) -> pd.DataFrame` | 194 |  |
| method | `_detect_simple_trend(candles: Sequence[Candle]) -> MarketTrend` | 206 |  |
### [`app/metrics.py`](../app/metrics.py)

Строк: **31**

Связанные тесты: [`tests/test_metrics.py`](../tests/test_metrics.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `calculate_return_percent(start_balance: float, final_balance: float) -> float` | 6 |  |
| function | `calculate_max_drawdown(equity_values: Sequence[float]) -> float` | 16 |  |
### [`app/models.py`](../app/models.py)

Строк: **51**

Связанные тесты: [`tests/test_models.py`](../tests/test_models.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| enum | `TradeSide` | 6 |  |
| dataclass | `Trade` | 12 |  |
| dataclass | `BacktestResult` | 22 |  |
| dataclass | `PaperStatistics` | 37 |  |
### [`app/order_builder.py`](../app/order_builder.py)

Строк: **135**

Связанные тесты: [`tests/test_order_builder.py`](../tests/test_order_builder.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `OrderValidationError` | 9 | Ордер не соответствует торговым ограничениям биржи. |
| function | `_floor_to_step(value: Decimal, step: Decimal) -> Decimal` | 13 |  |
| dataclass | `SpotLimitOrder` | 23 |  |
| method | `__post_init__(self) -> None` | 29 |  |
| method | `order_value(self) -> Decimal` | 49 |  |
| method | `to_bybit_payload(self) -> dict[str, str]` | 52 |  |
| class | `SpotOrderBuilder` | 63 |  |
| method | `__init__(self, instrument: InstrumentInfo) -> None` | 64 |  |
| method | `build_limit_order(self, *, side: str, quantity: Decimal, price: Decimal) -> SpotLimitOrder` | 67 |  |
### [`app/paper_engine.py`](../app/paper_engine.py)

Строк: **81**

Связанные тесты: [`tests/test_paper_engine.py`](../tests/test_paper_engine.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `PaperTradingEngine` | 8 |  |
| method | `__init__(self, *, session: PaperTradingSession, strategy: Strategy) -> None` | 9 |  |
| method | `run_iteration(self, candles: Sequence[Candle]) -> tuple[Trade, ...]` | 18 |  |
### [`app/paper_executor.py`](../app/paper_executor.py)

Строк: **135**

Связанные тесты: [`tests/test_paper_executor.py`](../tests/test_paper_executor.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `PaperExecutor` | 15 |  |
| method | `__init__(self) -> None` | 16 |  |
| method | `mode(self) -> ExecutionMode` | 21 |  |
| method | `open_position(self, request: ExecutionRequest) -> ExecutionResult` | 24 |  |
| method | `close_position(self, request: ExecutionRequest) -> ExecutionResult` | 30 |  |
| method | `_execute(self, request: ExecutionRequest) -> ExecutionResult` | 36 |  |
| method | `get_order_status(self, *, symbol: str, order_id: str \| None = None, client_order_id: str \| None = None) -> ExecutionResult` | 60 |  |
| method | `cancel_order(self, *, symbol: str, order_id: str \| None = None, client_order_id: str \| None = None) -> ExecutionResult` | 78 |  |
| method | `_find_order(self, *, symbol: str, order_id: str \| None, client_order_id: str \| None) -> ExecutionResult \| None` | 103 |  |
### [`app/paper_runtime_reports.py`](../app/paper_runtime_reports.py)

Строк: **103**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `atomic_write(path: Path, content: str) -> None` | 19 |  |
| function | `parse_datetime(value: str) -> datetime` | 33 |  |
| function | `load_period_data(state_path: Path, journal_path: Path, shadow_path: Path, start: datetime, end: datetime) -> tuple[Any, list[TradeJournalEntry], list[dict[str, Any]]]` | 40 |  |
| function | `shadow_summary(records: list[dict[str, Any]]) -> dict[str, Any]` | 49 |  |
| function | `trade_summary(trades: list[TradeJournalEntry]) -> dict[str, Any]` | 65 |  |
| function | `render_text(report: dict[str, Any]) -> str` | 91 |  |
| function | `write_report(report: dict[str, Any], json_output: Path \| None, text_output: Path \| None) -> None` | 99 |  |
### [`app/paper_session.py`](../app/paper_session.py)

Строк: **882**

Связанные тесты: [`tests/test_paper_session.py`](../tests/test_paper_session.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `PaperPosition` | 18 |  |
| method | `__post_init__(self) -> None` | 30 |  |
| dataclass | `PaperSessionSnapshot` | 118 |  |
| method | `__post_init__(self) -> None` | 127 |  |
| class | `PaperTradingSession` | 209 |  |
| method | `__init__(self, snapshot: PaperSessionSnapshot \| None = None, *, commission_rate: float = 0.001, risk_config: RiskConfig \| None = None) -> None` | 210 |  |
| method | `snapshot(self) -> PaperSessionSnapshot` | 231 |  |
| method | `accept_closed_candle(self, candle: Candle) -> bool` | 234 |  |
| method | `process_closed_candle(self, candle: Candle) -> Trade \| None` | 269 |  |
| method | `queue_action(self, *, action: TradeAction, reference_price: float, stop_loss: float \| None = None, trailing_stop_percent: float \| None = None) -> None` | 285 |  |
| method | `execute_pending_action(self, candle: Candle) -> Trade \| None` | 377 |  |
| method | `open_position(self, *, side: PositionSide, candle: Candle, stop_loss: float \| None = None, risk_reference_price: float \| None = None, trailing_stop_percent: float \| None = None) -> PaperPosition` | 464 |  |
| method | `close_position(self, *, exit_timestamp: int, exit_price: float, exit_reason: ExitReason) -> Trade` | 585 |  |
| method | `close_position_at_stop(self, candle: Candle) -> Trade` | 689 |  |
| method | `process_closed_candle(self, candle: Candle) -> Trade \| None` | 725 |  |
| method | `position_stop_was_hit(self, candle: Candle) -> bool` | 741 |  |
| method | `position_stop_exit_price(self, candle: Candle) -> float` | 759 |  |
| method | `update_trailing_stop(self, close_price: float) -> bool` | 781 |  |
| method | `_validate_candle(candle: Candle) -> None` | 843 |  |
### [`app/paper_state.py`](../app/paper_state.py)

Строк: **314**

Связанные тесты: [`tests/test_paper_state.py`](../tests/test_paper_state.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `PaperSessionState` | 18 |  |
| method | `__post_init__(self) -> None` | 24 |  |
| class | `PaperStateStore` | 76 |  |
| method | `__init__(self, file_path: str \| Path) -> None` | 77 |  |
| method | `load(self, *, default_balance: float = 1000.0) -> PaperSessionState` | 83 |  |
| method | `save(self, state: PaperSessionState) -> None` | 120 |  |
| method | `_from_payload(cls, payload: dict[str, Any]) -> PaperSessionState` | 147 |  |
| method | `_snapshot_from_payload(payload: Any) -> PaperSessionSnapshot` | 199 |  |
| method | `_position_from_payload(payload: Any) -> PaperPosition` | 259 |  |
### [`app/paper_statistics.py`](../app/paper_statistics.py)

Строк: **91**

Связанные тесты: [`tests/test_paper_statistics.py`](../tests/test_paper_statistics.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `calculate_statistics(*, start_balance: float, trades: Sequence[Trade]) -> PaperStatistics` | 7 |  |
### [`app/paper_strategy_router.py`](../app/paper_strategy_router.py)

Строк: **175**

Связанные тесты: [`tests/test_paper_strategy_router.py`](../tests/test_paper_strategy_router.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| protocol | `RegimeDetector` | 20 |  |
| method | `detect(self, candles: Sequence[Candle]) -> MarketRegime` | 21 |  |
| dataclass | `DetectorDiagnostics` | 26 |  |
| dataclass | `PaperStrategyDecision` | 33 |  |
| class | `PaperStrategyRouter` | 46 | Route one paper signal without owning trading state. |
| method | `__init__(self, config: PaperStrategyConfig, *, fast_ema_period: int = 20, slow_ema_period: int = 50, detector: RegimeDetector \| None = None, trading_filter: TradingFilter \| None = None) -> None` | 49 |  |
| method | `route(self, signal: Signal \| TradeSignal \| TradeAction, candles: Sequence[Candle]) -> PaperStrategyDecision` | 96 |  |
### [`app/paper_trader.py`](../app/paper_trader.py)

Строк: **200**

Связанные тесты: [`tests/test_paper_trader.py`](../tests/test_paper_trader.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| protocol | `TradeRecorder` | 15 |  |
| method | `record_trade(self, trade: Trade) -> bool` | 16 |  |
| dataclass | `PaperTraderConfig` | 24 |  |
| class | `PaperTrader` | 28 |  |
| method | `__init__(self, config: PaperTraderConfig \| None = None) -> None` | 43 |  |
| method | `trade_key(trade: Trade) -> tuple[int, int, str, float, float]` | 55 |  |
| method | `record_trade(self, trade: Trade) -> bool` | 66 |  |
| method | `record_trades(self, trades: Sequence[Trade]) -> int` | 106 |  |
| method | `run_session(self, *, feed: MarketDataFeed, strategy: Strategy, engine: BacktestEngine \| None = None) -> BacktestResult` | 118 |  |
| method | `count_recorded_trades(self) -> int` | 143 |  |
| method | `_read_existing_keys(self) -> set[tuple[int, int, str, float, float]]` | 146 |  |
### [`app/performance_analyzer.py`](../app/performance_analyzer.py)

Строк: **217**

Связанные тесты: [`tests/test_performance_analyzer.py`](../tests/test_performance_analyzer.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `SidePerformance` | 10 |  |
| dataclass | `PerformanceAnalysisResult` | 21 |  |
| class | `PerformanceAnalyzer` | 44 |  |
| method | `analyze(self, trades: Sequence[Trade]) -> PerformanceAnalysisResult` | 45 |  |
| method | `_maximum_streak(*, trades: Sequence[Trade], profitable: bool) -> int` | 146 |  |
| method | `_analyze_side(trades: Sequence[Trade]) -> SidePerformance` | 170 |  |
### [`app/process_lock.py`](../app/process_lock.py)

Строк: **136**

Связанные тесты: [`tests/test_process_lock.py`](../tests/test_process_lock.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `ProcessLockError` | 13 | Base error raised while managing a process lock. |
| class | `ProcessAlreadyRunningError` | 17 | Raised when another process holds the requested lock. |
| class | `ProcessLock` | 21 | A non-blocking, Linux advisory process lock. |
| method | `__init__(self, path: str \| os.PathLike[str]) -> None` | 24 |  |
| method | `__enter__(self) -> ProcessLock` | 28 |  |
| method | `__exit__(self, exc_type, exc_value, traceback) -> None` | 108 |  |
| method | `_read_details(lock_file: IO[str]) -> str` | 124 |  |
| method | `_release_file(lock_file: IO[str]) -> None` | 132 |  |
### [`app/regime_filter_research.py`](../app/regime_filter_research.py)

Строк: **791**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| protocol | `SignalStrategy` | 43 |  |
| method | `generate_signal(self, candles: Sequence[Candle], index: int) -> StrategySignal` | 44 |  |
| dataclass | `ResearchConfig` | 53 |  |
| method | `validate(self) -> None` | 69 |  |
| dataclass | `WalkForwardWindow` | 87 |  |
| dataclass | `WindowResult` | 96 |  |
| class | `WarmupStrategy` | 126 | Warm strategy state while suppressing all pre-test trading. |
| method | `__init__(self, strategy: SignalStrategy, trade_start_index: int) -> None` | 129 |  |
| method | `generate_signal(self, candles: Sequence[Candle], index: int) -> StrategySignal` | 137 |  |
| class | `CausalRegimeCache` | 148 | Index cache scoped to one immutable candle sequence. |
| method | `__init__(self, detector: MarketRegimeDetector, *, window_id: str = 'standalone') -> None` | 151 |  |
| method | `detect(self, candles: Sequence[Candle]) -> MarketRegime` | 162 |  |
| method | `detect_at(self, candles: Sequence[Candle], index: int) -> MarketRegime` | 166 |  |
| method | `seed(self, candles: Sequence[Candle], regimes: Mapping[int, MarketRegime]) -> None` | 180 |  |
| method | `snapshot(self) -> dict[int, MarketRegime]` | 189 |  |
| function | `fingerprint_candles(candles: Sequence[Candle]) -> str` | 193 |  |
| function | `make_detector(config: ResearchConfig) -> MarketRegimeDetector` | 210 |  |
| function | `build_windows(data: pd.DataFrame, config: ResearchConfig) -> list[WalkForwardWindow]` | 222 |  |
| function | `_run_variant(history: list[Candle], *, trade_start_index: int, window: WalkForwardWindow, variant: str, config: ResearchConfig, cache: CausalRegimeCache \| None, train_candles: int \| None = None, test_candles: int \| None = None, block_policy: EntryBlockPolicy \| None = None) -> tuple[WindowResult, BacktestResult]` | 271 |  |
| function | `run_walk_forward(data: pd.DataFrame, config: ResearchConfig) -> list[WindowResult]` | 374 |  |
| function | `run_policy_walk_forward(data: pd.DataFrame, config: ResearchConfig, policies: Mapping[str, EntryBlockPolicy \| None]) -> list[WindowResult]` | 389 |  |
| function | `summarize(results: list[WindowResult], variant: str) -> dict[str, float \| int]` | 484 |  |
| function | `compare_variants(results: list[WindowResult]) -> dict[str, int \| float]` | 538 |  |
| function | `compounded_diagnostics(results: list[WindowResult], initial_balance: float) -> dict[str, float]` | 588 |  |
| function | `compound_variant(results: list[WindowResult], variant: str, initial_balance: float) -> tuple[float, float]` | 605 |  |
| function | `compare_variant_to_baseline(results: list[WindowResult], variant: str, initial_balance: float) -> dict[str, int \| float]` | 617 |  |
| function | `build_component_analysis(results: list[WindowResult], variants: Sequence[str], initial_balance: float) -> dict[str, object]` | 676 |  |
| function | `research_verdict(baseline: dict[str, float \| int], filtered: dict[str, float \| int], comparison: dict[str, int]) -> str` | 705 |  |
| function | `build_analysis(results: list[WindowResult], initial_balance: float) -> dict[str, object]` | 736 |  |
| function | `atomic_write(path: Path, content: str) -> None` | 772 |  |
| function | `config_dict(config: ResearchConfig) -> dict[str, object]` | 790 |  |
### [`app/regime_filtered_strategy.py`](../app/regime_filtered_strategy.py)

Строк: **201**

Связанные тесты: [`tests/test_regime_filtered_strategy.py`](../tests/test_regime_filtered_strategy.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| protocol | `Strategy` | 26 |  |
| method | `generate_signal(self, candles: Sequence[Candle], index: int) -> StrategySignal` | 27 |  |
| protocol | `IndexedRegimeDetector` | 35 |  |
| method | `detect_at(self, candles: Sequence[Candle], index: int) -> MarketRegime` | 36 |  |
| enum | `EntryBlockReason` | 44 |  |
| dataclass | `EntryBlockPolicy` | 53 | Immutable set of primary regime reasons that block new entries. |
| method | `__post_init__(self) -> None` | 58 |  |
| method | `blocks(self, reason: EntryBlockReason) -> bool` | 70 |  |
| method | `full(cls) -> EntryBlockPolicy` | 74 |  |
| method | `empty(cls) -> EntryBlockPolicy` | 78 |  |
| dataclass | `EntryFilterStatistics` | 83 |  |
| function | `classify_entry_block_reason(regime: MarketRegime) -> EntryBlockReason` | 89 |  |
| class | `RegimeFilteredStrategy` | 106 | Apply a market-regime filter only to new position entries. |
| method | `__init__(self, base_strategy: Strategy, regime_detector: MarketRegimeDetector, trading_filter: TradingFilter, *, apply_filter: bool = True, block_policy: EntryBlockPolicy \| None = None) -> None` | 109 |  |
| method | `statistics(self) -> EntryFilterStatistics` | 133 |  |
| method | `generate_signal(self, candles: Sequence[Candle], index: int) -> StrategySignal` | 145 |  |
| method | `_register_exit(self, action: TradeAction) -> None` | 193 |  |
### [`app/risk.py`](../app/risk.py)

Строк: **152**

Связанные тесты: [`tests/test_risk.py`](../tests/test_risk.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `RiskConfig` | 7 | Настройки управления риском. |
| method | `__post_init__(self) -> None` | 29 |  |
| dataclass | `PositionSize` | 49 |  |
| class | `RiskManager` | 58 |  |
| method | `__init__(self, config: RiskConfig \| None = None) -> None` | 59 |  |
| method | `calculate_position_size(self, *, balance: float, entry_price: float, stop_loss: float, side: PositionSide) -> PositionSize` | 65 |  |
| method | `_validate_inputs(*, balance: float, entry_price: float, stop_loss: float, side: PositionSide) -> None` | 117 |  |
### [`app/runtime.py`](../app/runtime.py)

Строк: **35**

Связанные тесты: [`tests/test_runtime.py`](../tests/test_runtime.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `Runtime` | 15 |  |
| function | `build_runtime(settings: Settings \| None = None) -> Runtime` | 21 |  |
### [`app/runtime_health.py`](../app/runtime_health.py)

Строк: **208**

Связанные тесты: [`tests/test_runtime_health.py`](../tests/test_runtime_health.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| enum | `HealthStatus` | 16 |  |
| dataclass | `HealthCheckResult` | 23 |  |
| method | `to_dict(self) -> dict[str, Any]` | 30 |  |
| function | `utc_now() -> datetime` | 36 |  |
| function | `read_timestamp(path: Path) -> int` | 40 |  |
| function | `read_jsonl_safely(path: Path, *, parser: Callable[[object], Any] \| None = None) -> tuple[list[Any], bool]` | 47 | Read JSONL without modifying it; ignore only an incomplete final line. |
| function | `check_lock(path: Path, *, now: datetime \| None = None) -> HealthCheckResult` | 72 |  |
| function | `_result(name: str, status: HealthStatus, message: str, details: dict[str, Any], now: datetime) -> HealthCheckResult` | 114 |  |
| function | `run_health_checks(*, state_path: Path, candle_path: Path, journal_path: Path, shadow_path: Path, lock_path: Path, symbol: str = 'ETHUSDT', timeframe: str = '60', max_candle_age_minutes: int = 90, max_market_lag_candles: int = 1, no_network: bool = False, now: datetime \| None = None, market_fetcher: Callable[[], int] \| None = None) -> tuple[list[HealthCheckResult], dict[str, Any]]` | 118 |  |
| function | `overall_status(checks: list[HealthCheckResult]) -> HealthStatus` | 207 |  |
### [`app/settings.py`](../app/settings.py)

Строк: **66**

Связанные тесты: [`tests/test_settings.py`](../tests/test_settings.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `Settings` | 10 |  |
| function | `_parse_bool(value: str \| None) -> bool` | 19 |  |
| function | `_optional_text(value: str \| None) -> str \| None` | 31 |  |
| function | `load_settings() -> Settings` | 43 |  |
### [`app/shadow_decision_journal.py`](../app/shadow_decision_journal.py)

Строк: **169**

Связанные тесты: [`tests/test_shadow_decision_journal.py`](../tests/test_shadow_decision_journal.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `ShadowDecisionRecord` | 11 |  |
| method | `deduplication_key(self) -> str` | 33 |  |
| class | `ShadowDecisionJournal` | 45 | Append-only JSONL with restart-safe last-key deduplication. |
| method | `__init__(self, path: str \| Path, *, state_path: str \| Path \| None = None) -> None` | 48 |  |
| method | `append(self, record: ShadowDecisionRecord) -> bool` | 62 |  |
| method | `read_all(self) -> list[ShadowDecisionRecord]` | 86 |  |
| method | `_load_last_key(self) -> str \| None` | 116 |  |
| method | `_save_state(self, key: str) -> None` | 135 |  |
| method | `_truncate(self, size: int) -> None` | 160 |  |
### [`app/signal_generator.py`](../app/signal_generator.py)

Строк: **35**

Связанные тесты: [`tests/test_signal_generator.py`](../tests/test_signal_generator.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| enum | `TradeSignal` | 11 |  |
| class | `SignalGenerator` | 17 |  |
| method | `__init__(self, trading_filter: TradingFilter \| None = None) -> None` | 18 |  |
| method | `market_ready(self, regime: MarketRegime) -> bool` | 21 |  |
| method | `generate(self, regime: MarketRegime) -> TradeSignal` | 24 |  |
### [`app/signal_normalizer.py`](../app/signal_normalizer.py)

Строк: **49**

Связанные тесты: [`tests/test_signal_normalizer.py`](../tests/test_signal_normalizer.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `normalize_signal(signal: Signal \| TradeSignal \| TradeAction) -> TradeSignal` | 6 |  |
### [`app/stop_manager.py`](../app/stop_manager.py)

Строк: **87**

Связанные тесты: [`tests/test_stop_manager.py`](../tests/test_stop_manager.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `stop_was_hit(*, side: PositionSide, candle: Candle, stop_loss: float) -> bool` | 5 |  |
| function | `stop_exit_price(*, side: PositionSide, candle: Candle, stop_loss: float) -> float` | 22 |  |
| function | `trail_stop(*, side: PositionSide, current_stop: float, close_price: float, trailing_stop_percent: float) -> float` | 45 |  |
### [`app/strategies.py`](../app/strategies.py)

Строк: **89**

Связанные тесты: [`tests/test_strategies.py`](../tests/test_strategies.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| enum | `Signal` | 8 |  |
| function | `ma_cross_signals(data: pd.DataFrame, fast_period: int, slow_period: int) -> pd.Series` | 14 |  |
| function | `rsi_signals(data: pd.DataFrame, period: int = 14, buy_level: float = 30.0, sell_level: float = 70.0) -> pd.Series` | 55 |  |
### [`app/trade_accounting.py`](../app/trade_accounting.py)

Строк: **61**

Связанные тесты: [`tests/test_trade_accounting.py`](../tests/test_trade_accounting.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `ClosedTradeAccounting` | 6 |  |
| function | `calculate_long_trade_accounting(entry_price: Decimal, exit_price: Decimal, quantity: Decimal, fee_rate: Decimal) -> ClosedTradeAccounting` | 18 |  |
### [`app/trade_analyzer.py`](../app/trade_analyzer.py)

Строк: **198**

Связанные тесты: [`tests/test_trade_analyzer.py`](../tests/test_trade_analyzer.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `TradeExcursion` | 10 |  |
| dataclass | `TradeAnalysisResult` | 18 |  |
| class | `TradeAnalyzer` | 28 |  |
| method | `analyze(self, candles: Sequence[Candle], trades: Sequence[Trade]) -> TradeAnalysisResult` | 29 |  |
| method | `_analyze_trade(self, *, candles: Sequence[Candle], trade: Trade, timestamp_to_index: dict[int, int]) -> TradeExcursion` | 91 |  |
| method | `_build_timestamp_index(candles: Sequence[Candle]) -> dict[int, int]` | 185 |  |
### [`app/trade_journal.py`](../app/trade_journal.py)

Строк: **147**

Связанные тесты: [`tests/test_trade_journal.py`](../tests/test_trade_journal.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `TradeJournalEntry` | 29 |  |
| method | `to_dict(self) -> dict[str, str \| int]` | 51 |  |
| method | `from_dict(cls, payload: object) -> TradeJournalEntry` | 58 |  |
| protocol | `TradeJournalProtocol` | 94 |  |
| method | `append(self, entry: TradeJournalEntry) -> None` | 95 |  |
| class | `JsonlTradeJournal` | 99 |  |
| method | `__init__(self, path: str \| Path) -> None` | 100 |  |
| method | `append(self, entry: TradeJournalEntry) -> None` | 103 |  |
| method | `read_all(self) -> list[TradeJournalEntry]` | 119 |  |
### [`app/trade_reporting.py`](../app/trade_reporting.py)

Строк: **336**

Связанные тесты: [`tests/test_trade_reporting.py`](../tests/test_trade_reporting.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `TradeReportResult` | 24 |  |
| class | `TradeReportError` | 29 | Raised when a trade report cannot be created. |
| function | `_format_optional(value: object \| None, *, missing: str) -> str` | 33 |  |
| function | `format_trade_statistics(statistics: TradeStatistics) -> list[str]` | 37 |  |
| function | `_format_trade(entry: TradeJournalEntry \| None) -> str` | 78 |  |
| function | `format_trade_report(entries: Sequence[TradeJournalEntry], statistics: TradeStatistics) -> str` | 84 |  |
| function | `_plot_statistics_text(statistics: TradeStatistics) -> str` | 114 |  |
| function | `render_trade_statistics_figure(statistics: TradeStatistics, *, title: str, width: float, height: float)` | 128 |  |
| function | `_temporary_path(output: Path, *, suffix: str) -> Path` | 225 |  |
| function | `save_text_report(report: str, output: str \| Path) -> None` | 235 |  |
| function | `save_trade_statistics_plot(statistics: TradeStatistics, output: str \| Path, *, title: str = 'Trade Statistics', dpi: int = 150, width: float = 12.0, height: float = 9.0) -> None` | 252 |  |
| function | `generate_trade_reports(journal_path: str \| Path, text_report_path: str \| Path, png_report_path: str \| Path, *, title: str = 'Trade Statistics', dpi: int = 150, width: float = 12.0, height: float = 9.0) -> TradeReportResult` | 286 |  |
### [`app/trade_signal.py`](../app/trade_signal.py)

Строк: **44**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `TradeSignal` | 8 |  |
| method | `__post_init__(self) -> None` | 14 |  |
### [`app/trade_statistics.py`](../app/trade_statistics.py)

Строк: **265**

Связанные тесты: [`tests/test_trade_statistics.py`](../tests/test_trade_statistics.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `TradeStatistics` | 16 | Aggregated statistics for closed trade-journal records. |
| function | `_holding_seconds(entry: TradeJournalEntry) -> Decimal` | 62 |  |
| function | `calculate_drawdown_curve(starting_balance: Decimal, equity_curve: Sequence[Decimal]) -> tuple[Decimal, ...]` | 92 | Return absolute drawdown for the starting point and each equity value. |
| function | `_calculate_drawdown(*, starting_balance: Decimal, equity_curve: Sequence[Decimal]) -> tuple[Decimal, Decimal]` | 113 |  |
| function | `calculate_trade_statistics(entries: Sequence[TradeJournalEntry]) -> TradeStatistics` | 137 | Calculate statistics, treating every journal record as one trade. |
### [`app/trading_controller.py`](../app/trading_controller.py)

Строк: **465**

Связанные тесты: [`tests/test_trading_controller.py`](../tests/test_trading_controller.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `TradingControllerState` | 32 |  |
| method | `__post_init__(self) -> None` | 43 |  |
| method | `has_open_position(self) -> bool` | 109 |  |
| protocol | `TradingControllerStateStoreProtocol` | 113 |  |
| method | `load(self) -> TradingControllerState` | 114 |  |
| method | `save(self, state: TradingControllerState) -> None` | 117 |  |
| dataclass | `TradingControllerResult` | 125 |  |
| class | `TradingController` | 134 | Управляет состоянием одной LONG-позиции. |
| method | `__init__(self, runtime: TradingRuntime, *, state: TradingControllerState \| None = None, state_store: TradingControllerStateStoreProtocol \| None = None, fee_rate: Decimal = Decimal('0.001'), trade_journal: TradeJournalProtocol \| None = None, clock: Callable[[], datetime] \| None = None) -> None` | 144 |  |
| method | `state(self) -> TradingControllerState` | 181 |  |
| method | `process_signal(self, *, symbol: str, signal: Signal \| TradeSignal \| TradeAction, entry_quantity: Decimal, price: Decimal, client_order_id: str \| None = None, exit_reason: str = 'signal') -> TradingControllerResult` | 184 |  |
| method | `_apply_execution(self, *, action: TradeAction, execution: ExecutionResult \| None, stop_loss: Decimal \| None, symbol: str, exit_reason: str) -> tuple[bool, ClosedTradeAccounting \| None, TradeJournalEntry \| None]` | 309 |  |
| method | `_iso_timestamp(self) -> str` | 461 |  |
### [`app/trading_controller_store.py`](../app/trading_controller_store.py)

Строк: **205**

Связанные тесты: [`tests/test_trading_controller_store.py`](../tests/test_trading_controller_store.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `TradingControllerStateStore` | 10 | Хранит состояние торгового контроллера в JSON. |
| method | `__init__(self, path: str \| Path) -> None` | 19 |  |
| method | `load(self) -> TradingControllerState` | 22 |  |
| method | `save(self, state: TradingControllerState) -> None` | 100 |  |
| method | `_parse_decimal(value, *, field_name: str, allow_none: bool) -> Decimal \| None` | 162 |  |
| method | `_parse_int(value, *, field_name: str) -> int` | 180 |  |
### [`app/trading_filter.py`](../app/trading_filter.py)

Строк: **27**

Связанные тесты: [`tests/test_trading_filter.py`](../tests/test_trading_filter.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `TradingFilter` | 8 |  |
| method | `__init__(self, minimum_confidence: float = 0.0) -> None` | 9 |  |
| method | `allow_entry(self, regime: MarketRegime) -> bool` | 17 |  |
### [`app/trading_runtime.py`](../app/trading_runtime.py)

Строк: **65**

Связанные тесты: [`tests/test_trading_runtime.py`](../tests/test_trading_runtime.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `RuntimeRequest` | 18 |  |
| class | `TradingRuntime` | 26 | Соединяет сигнал торговой стратегии с ExecutionRunner. |
| method | `__init__(self, runner: ExecutionRunner) -> None` | 36 |  |
| method | `process_signal(self, request: RuntimeRequest) -> ExecutionResult \| None` | 42 |  |
### [`app/trading_types.py`](../app/trading_types.py)

Строк: **23**

Связанные тесты: [`tests/test_trading_types.py`](../tests/test_trading_types.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| enum | `PositionSide` | 4 |  |
| enum | `TradeAction` | 9 |  |
| enum | `ExitReason` | 18 |  |
### [`app/trend_detector.py`](../app/trend_detector.py)

Строк: **192**

Связанные тесты: [`tests/test_trend_detector.py`](../tests/test_trend_detector.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| enum | `TrendState` | 7 |  |
| class | `TrendDetector` | 13 |  |
| method | `__init__(self, fast_period: int = 50, slow_period: int = 200, slope_lookback: int = 5, min_separation_percent: float = 0.1) -> None` | 14 |  |
| method | `detect(self, candles: Sequence[Candle], index: int) -> TrendState` | 68 |  |
| method | `_update(self, close: float) -> None` | 156 |  |
| method | `_reset(self) -> None` | 187 |  |
### [`app/trend_pullback_strategy.py`](../app/trend_pullback_strategy.py)

Строк: **237**

Связанные тесты: [`tests/test_trend_pullback_strategy.py`](../tests/test_trend_pullback_strategy.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `TrendPullbackStrategy` | 14 |  |
| method | `__init__(self, pullback_ema_period: int = 20, trend_fast_period: int = 50, trend_slow_period: int = 200, trend_slope_lookback: int = 5, trend_min_separation_percent: float = 0.1, adx_period: int = 14, minimum_adx: float = 25.0, allow_short: bool = True) -> None` | 15 |  |
| method | `generate_signal(self, candles: Sequence[Candle], index: int) -> TradeAction` | 71 |  |
| method | `_ensure_adx_cache(self, candles: Sequence[Candle]) -> None` | 168 |  |
| method | `_update_ema(self, close: float) -> None` | 206 |  |
| method | `_reset_runtime_state(self) -> None` | 231 |  |

## `scripts/`

### [`scripts/analyze_trends.py`](../scripts/analyze_trends.py)

Строк: **105**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `main() -> None` | 13 |  |
### [`scripts/backtest.py`](../scripts/backtest.py)

Строк: **116**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `main() -> None` | 14 |  |
### [`scripts/build_project_index.py`](../scripts/build_project_index.py)

Строк: **578**

Создаёт docs/PROJECT_MAP.md — автоматическую карту Python-проекта.

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `Definition` | 51 |  |
| dataclass | `ModuleInfo` | 60 |  |
| function | `short_docstring(node: ast.AST, *, maximum_length: int = 120) -> str \| None` | 67 |  |
| function | `expression_text(node: ast.AST \| None) -> str` | 86 |  |
| function | `function_signature(node: ast.FunctionDef \| ast.AsyncFunctionDef) -> str` | 96 |  |
| function | `class_kind(node: ast.ClassDef) -> str` | 175 |  |
| function | `collect_class_definitions(node: ast.ClassDef) -> list[Definition]` | 204 |  |
| function | `parse_module(project_root: Path, path: Path) -> ModuleInfo` | 244 |  |
| function | `iter_python_files(project_root: Path, source_dirs: Iterable[str]) -> Iterable[Path]` | 292 |  |
| function | `related_test_paths(module: ModuleInfo, modules: tuple[ModuleInfo, ...]) -> tuple[Path, ...]` | 312 |  |
| function | `render_index(modules: tuple[ModuleInfo, ...]) -> str` | 336 |  |
| function | `main() -> None` | 490 |  |
### [`scripts/check_runtime.py`](../scripts/check_runtime.py)

Строк: **74**

Связанные тесты: [`tests/test_check_runtime.py`](../tests/test_check_runtime.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `RuntimeSummary` | 10 |  |
| function | `summarize_runtime(runtime: Runtime) -> RuntimeSummary` | 19 |  |
| function | `main() -> None` | 36 |  |
### [`scripts/check_runtime_alerts.py`](../scripts/check_runtime_alerts.py)

Строк: **64**

Связанные тесты: [`tests/test_check_runtime_alerts.py`](../tests/test_check_runtime_alerts.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `parser() -> argparse.ArgumentParser` | 15 |  |
| function | `main(argv: list[str] \| None = None) -> int` | 25 |  |
### [`scripts/compare_regime_filter_components.py`](../scripts/compare_regime_filter_components.py)

Строк: **282**

Связанные тесты: [`tests/test_compare_regime_filter_components.py`](../tests/test_compare_regime_filter_components.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `policy(*names: str) -> EntryBlockPolicy` | 40 |  |
| function | `positive_int(value: str) -> int` | 63 |  |
| function | `non_negative_float(value: str) -> float` | 70 |  |
| function | `build_parser() -> argparse.ArgumentParser` | 77 |  |
| function | `config_from_args(args: argparse.Namespace) -> ResearchConfig` | 123 |  |
| function | `json_safe(value)` | 135 |  |
| function | `build_report(data, data_path: Path, config: ResearchConfig, results)` | 145 |  |
| function | `save_json(path: Path, report: dict[str, object]) -> None` | 175 |  |
| function | `save_csv(path: Path, results) -> None` | 185 |  |
| function | `print_report(report: dict[str, object]) -> None` | 194 |  |
| function | `main(argv: list[str] \| None = None) -> int` | 258 |  |
### [`scripts/compare_regime_filters.py`](../scripts/compare_regime_filters.py)

Строк: **559**

Связанные тесты: [`tests/test_compare_regime_filters.py`](../tests/test_compare_regime_filters.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `CachingRegimeDetector` | 50 | Cache causal results by index for one immutable candle sequence. |
| method | `__init__(self, detector: MarketRegimeDetector) -> None` | 59 |  |
| method | `detect_at(self, candles: Sequence[Candle], index: int) -> MarketRegime` | 64 |  |
| method | `detect(self, candles: Sequence[Candle]) -> MarketRegime` | 78 |  |
| class | `WarmupStrategy` | 84 | Warm indicator state while suppressing all pre-period trading. |
| method | `__init__(self, strategy, trade_start_index: int) -> None` | 87 |  |
| method | `generate_signal(self, candles, index)` | 91 |  |
| dataclass | `ComparisonResult` | 99 |  |
| function | `positive_int(value: str) -> int` | 118 |  |
| function | `non_negative_float(value: str) -> float` | 127 |  |
| function | `confidence(value: str) -> float` | 136 |  |
| function | `build_parser() -> argparse.ArgumentParser` | 145 |  |
| function | `validate_arguments(args: argparse.Namespace) -> None` | 214 |  |
| function | `make_detector(args: argparse.Namespace) -> MarketRegimeDetector` | 239 |  |
| function | `run_variant(data: pd.DataFrame, *, period: str, variant: str, args: argparse.Namespace, regime_detector: CachingRegimeDetector \| None = None) -> ComparisonResult` | 255 |  |
| function | `_execute_variant(data: pd.DataFrame, *, period: str, variant: str, args: argparse.Namespace, regime_detector: CachingRegimeDetector \| None = None, trade_start_index: int = 0, candles: list[Candle] \| None = None) -> tuple[ComparisonResult, BacktestResult]` | 273 |  |
| function | `build_result(*, period: str, variant: str, result: BacktestResult, allowed_entries: int, blocked_entries: int, reasons: dict[str, int]) -> ComparisonResult` | 345 |  |
| function | `run_comparison(data: pd.DataFrame, args: argparse.Namespace) -> list[ComparisonResult]` | 386 |  |
| function | `split_train_test(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]` | 433 |  |
| function | `sorted_results(results: list[ComparisonResult]) -> list[ComparisonResult]` | 447 |  |
| function | `print_results(results: list[ComparisonResult]) -> None` | 460 |  |
| function | `save_report(path: Path, results: list[ComparisonResult], args: argparse.Namespace) -> None` | 499 |  |
| function | `main(argv: list[str] \| None = None) -> int` | 541 |  |
### [`scripts/compare_strategies.py`](../scripts/compare_strategies.py)

Строк: **192**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `print_header() -> None` | 16 |  |
| function | `print_result(name: str, result: BacktestResult) -> None` | 33 |  |
| function | `calculate_buy_and_hold(first_price: float, last_price: float) -> tuple[float, float]` | 60 |  |
| function | `print_buy_and_hold(first_price: float, last_price: float) -> None` | 79 |  |
| function | `main() -> None` | 101 |  |
### [`scripts/download_eth_5m.py`](../scripts/download_eth_5m.py)

Строк: **195**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `to_milliseconds(value: str) -> int` | 20 |  |
| function | `format_datetime(timestamp_ms: int) -> str` | 29 |  |
| function | `request_klines(session: requests.Session, start_time: int, end_time: int) -> list[list]` | 36 |  |
| function | `main() -> None` | 65 |  |
### [`scripts/download_full_history.py`](../scripts/download_full_history.py)

Строк: **138**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `main() -> None` | 17 |  |
### [`scripts/download_history.py`](../scripts/download_history.py)

Строк: **81**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `fetch_history() -> pd.DataFrame` | 14 |  |
| function | `main() -> None` | 63 |  |
### [`scripts/optimize_ema.py`](../scripts/optimize_ema.py)

Строк: **168**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `OptimizationResult` | 38 |  |
| function | `main() -> None` | 49 |  |
### [`scripts/optimize_ma.py`](../scripts/optimize_ma.py)

Строк: **212**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `calculate_max_drawdown(equity_values: list[float]) -> float` | 15 |  |
| function | `run_backtest(source_df: pd.DataFrame, fast_period: int, slow_period: int) -> dict` | 22 |  |
| function | `calculate_buy_and_hold(df: pd.DataFrame) -> float` | 137 |  |
| function | `main() -> None` | 151 |  |
### [`scripts/plot_trade_statistics.py`](../scripts/plot_trade_statistics.py)

Строк: **84**

Связанные тесты: [`tests/test_plot_trade_statistics.py`](../tests/test_plot_trade_statistics.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `positive_int(value: str) -> int` | 23 |  |
| function | `positive_float(value: str) -> float` | 30 |  |
| function | `build_parser() -> argparse.ArgumentParser` | 37 |  |
| function | `main(argv: list[str] \| None = None) -> int` | 64 |  |
### [`scripts/report_paper_daily.py`](../scripts/report_paper_daily.py)

Строк: **74**

Связанные тесты: [`tests/test_report_paper_daily.py`](../tests/test_report_paper_daily.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `parser() -> argparse.ArgumentParser` | 18 |  |
| function | `create_report(args: argparse.Namespace) -> dict` | 30 |  |
| function | `main(argv: list[str] \| None = None) -> int` | 62 |  |
### [`scripts/report_paper_weekly.py`](../scripts/report_paper_weekly.py)

Строк: **77**

Связанные тесты: [`tests/test_report_paper_weekly.py`](../tests/test_report_paper_weekly.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `parser() -> argparse.ArgumentParser` | 19 |  |
| function | `create_report(args: argparse.Namespace) -> dict` | 31 |  |
| function | `main(argv: list[str] \| None = None) -> int` | 65 |  |
### [`scripts/report_shadow_decisions.py`](../scripts/report_shadow_decisions.py)

Строк: **133**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `build_parser() -> argparse.ArgumentParser` | 27 |  |
| function | `parse_time(value: str) -> int` | 40 |  |
| function | `build_summary(records) -> dict[str, object]` | 49 |  |
| function | `atomic_write(path: Path, content: str) -> None` | 91 |  |
| function | `main(argv: list[str] \| None = None) -> int` | 109 |  |
### [`scripts/report_trade_journal.py`](../scripts/report_trade_journal.py)

Строк: **57**

Связанные тесты: [`tests/test_report_trade_journal.py`](../tests/test_report_trade_journal.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `build_parser() -> argparse.ArgumentParser` | 25 |  |
| function | `format_statistics(statistics: TradeStatistics) -> list[str]` | 38 |  |
| function | `render_report(entries: list[TradeJournalEntry]) -> str` | 42 |  |
| function | `main(argv: list[str] \| None = None) -> int` | 49 |  |
### [`scripts/run_bybit_controller.py`](../scripts/run_bybit_controller.py)

Строк: **624**

Связанные тесты: [`tests/test_run_bybit_controller.py`](../tests/test_run_bybit_controller.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `build_parser() -> argparse.ArgumentParser` | 88 |  |
| function | `generate_trade_reports(*args, **kwargs)` | 122 |  |
| function | `generate_reports(*, text_report: Path, png_report: Path) -> int` | 128 |  |
| function | `load_last_candle_timestamp() -> int \| None` | 150 |  |
| function | `save_last_candle_timestamp(timestamp: int) -> None` | 177 |  |
| function | `calculate_latest_signal(candles: tuple) -> tuple[Signal, float, float]` | 197 |  |
| function | `signal_name(signal: Signal) -> str` | 249 |  |
| function | `build_execution_signal(*, strategy_signal: Signal, price: Decimal, state: TradingControllerState) -> tuple[Signal \| TradeSignal, bool]` | 257 | Добавляет защитный стоп к новой LONG-позиции и принудительно закрывает позицию при его достижении. |
| function | `run_controller(args: argparse.Namespace) -> int` | 304 |  |
| function | `build_shadow_record(*, decision: PaperStrategyDecision, latest_candle, state: TradingControllerState, controller_run_identifier: str) -> ShadowDecisionRecord` | 560 |  |
| function | `main(argv: list[str] \| None = None) -> int` | 598 |  |
### [`scripts/run_bybit_paper.py`](../scripts/run_bybit_paper.py)

Строк: **208**

Связанные тесты: [`tests/test_run_bybit_paper.py`](../tests/test_run_bybit_paper.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `PaperRunResult` | 38 |  |
| function | `run_once(*, feed: MarketDataFeed, strategy: Strategy, state_file: str \| Path = STATE_FILE, log_file: str \| Path = LOG_FILE, initial_balance: float = INITIAL_BALANCE, commission_rate: float = COMMISSION_RATE, risk_config: RiskConfig \| None = None) -> PaperRunResult` | 48 |  |
| function | `main() -> None` | 141 |  |
### [`scripts/run_engine_ema.py`](../scripts/run_engine_ema.py)

Строк: **128**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `dataframe_to_candles(data: pd.DataFrame) -> list[Candle]` | 18 |  |
| function | `main() -> None` | 38 |  |
### [`scripts/run_periodic_reports.py`](../scripts/run_periodic_reports.py)

Строк: **51**

Связанные тесты: [`tests/test_run_periodic_reports.py`](../tests/test_run_periodic_reports.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `parser() -> argparse.ArgumentParser` | 17 |  |
| function | `main(argv: list[str] \| None = None) -> int` | 27 |  |
### [`scripts/run_strategy_comparison.py`](../scripts/run_strategy_comparison.py)

Строк: **102**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `print_result(name: str, result) -> None` | 15 |  |
| function | `calculate_buy_and_hold(data: pd.DataFrame, start_balance: float, fee_rate: float) -> float` | 31 |  |
| function | `main() -> None` | 50 |  |
### [`scripts/run_trend_pullback.py`](../scripts/run_trend_pullback.py)

Строк: **115**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `print_result(result) -> None` | 14 |  |
| function | `main() -> None` | 78 |  |
### [`scripts/run_trend_pullback_5m.py`](../scripts/run_trend_pullback_5m.py)

Строк: **176**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `print_result(result) -> None` | 14 |  |
| function | `main() -> None` | 136 |  |
### [`scripts/runtime_status.py`](../scripts/runtime_status.py)

Строк: **96**

Связанные тесты: [`tests/test_runtime_status.py`](../tests/test_runtime_status.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `parser() -> argparse.ArgumentParser` | 21 |  |
| function | `build_status(args: argparse.Namespace) -> tuple[dict, HealthStatus]` | 32 |  |
| function | `main(argv: list[str] \| None = None) -> int` | 77 |  |
### [`scripts/validate_ema_out_of_sample.py`](../scripts/validate_ema_out_of_sample.py)

Строк: **169**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `Result` | 25 |  |
| function | `run_strategy(data: pd.DataFrame, short_period: int, long_period: int) -> Result` | 34 |  |
| function | `calculate_buy_and_hold(data: pd.DataFrame) -> float` | 66 |  |
| function | `main() -> None` | 82 |  |
### [`scripts/walk_forward_ema.py`](../scripts/walk_forward_ema.py)

Строк: **427**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| dataclass | `StrategyResult` | 44 |  |
| dataclass | `WalkForwardWindow` | 55 |  |
| function | `run_strategy(data: pd.DataFrame, short_period: int, long_period: int, initial_balance: float = START_BALANCE) -> StrategyResult` | 74 |  |
| function | `find_best_parameters(train_data: pd.DataFrame) -> StrategyResult` | 115 |  |
| function | `build_windows(data: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]` | 151 |  |
| function | `calculate_buy_and_hold(data: pd.DataFrame) -> float` | 206 |  |
| function | `main() -> None` | 228 |  |
### [`scripts/walk_forward_regime_filter.py`](../scripts/walk_forward_regime_filter.py)

Строк: **270**

Связанные тесты: [`tests/test_walk_forward_regime_filter.py`](../tests/test_walk_forward_regime_filter.py)

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `positive_int(value: str) -> int` | 31 |  |
| function | `non_negative_float(value: str) -> float` | 38 |  |
| function | `confidence(value: str) -> float` | 45 |  |
| function | `build_parser() -> argparse.ArgumentParser` | 52 |  |
| function | `config_from_args(args: argparse.Namespace) -> ResearchConfig` | 143 |  |
| function | `_json_safe(value)` | 162 |  |
| function | `build_report(data, data_path: Path, config: ResearchConfig, results)` | 172 |  |
| function | `save_json(path: Path, report: dict[str, object]) -> None` | 197 |  |
| function | `save_csv(path: Path, results) -> None` | 207 |  |
| function | `print_report(report: dict[str, object]) -> None` | 216 |  |
| function | `main(argv: list[str] \| None = None) -> int` | 250 |  |

## `tests/`

### [`tests/__init__.py`](../tests/__init__.py)

Строк: **0**

_Публичных классов и функций не найдено._
### [`tests/test_backtester.py`](../tests/test_backtester.py)

Строк: **164**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_data(opens: list[float], closes: list[float] \| None = None) -> pd.DataFrame` | 9 |  |
| function | `test_profitable_trade() -> None` | 30 |  |
| function | `test_losing_trade() -> None` | 58 |  |
| function | `test_signal_executes_on_next_candle_open() -> None` | 82 |  |
| function | `test_open_position_is_closed_at_end() -> None` | 105 |  |
| function | `test_signal_length_must_match_data() -> None` | 125 |  |
| function | `test_missing_columns() -> None` | 135 |  |
| function | `test_invalid_balance() -> None` | 145 |  |
| function | `test_unknown_signal() -> None` | 156 |  |
### [`tests/test_bybit_account.py`](../tests/test_bybit_account.py)

Строк: **338**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_bybit_account_config_normalizes_credentials() -> None` | 12 |  |
| function | `test_bybit_account_config_rejects_empty_credentials(api_key: str, api_secret: str) -> None` | 35 |  |
| function | `test_bybit_account_config_rejects_invalid_recv_window() -> None` | 49 |  |
| function | `test_bybit_account_config_rejects_invalid_timeout() -> None` | 61 |  |
| function | `test_wallet_balance_normalizes_coin_name() -> None` | 78 |  |
| function | `test_wallet_balance_rejects_empty_coin() -> None` | 90 |  |
| function | `test_wallet_balance_rejects_negative_values(wallet_balance: Decimal, available_balance: Decimal) -> None` | 106 |  |
| function | `test_wallet_balance_rejects_available_above_wallet_balance() -> None` | 121 |  |
| function | `test_bybit_account_client_uses_testnet_base_url() -> None` | 133 |  |
| function | `test_bybit_account_client_uses_custom_base_url() -> None` | 145 |  |
| function | `test_bybit_account_client_gets_wallet_balance() -> None` | 157 |  |
| function | `test_bybit_account_client_reports_missing_usdt() -> None` | 203 |  |
| function | `test_bybit_account_client_rejects_unexpected_wallet_response() -> None` | 230 |  |
| function | `test_bybit_account_client_gets_api_key_info() -> None` | 246 |  |
| function | `test_bybit_account_client_raises_safe_api_error() -> None` | 283 |  |
| function | `test_wallet_balance_parses_empty_available_balance_as_zero() -> None` | 305 |  |
### [`tests/test_bybit_account_check.py`](../tests/test_bybit_account_check.py)

Строк: **234**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `FakeClient` | 18 |  |
| method | `__init__(self, *, key_info = None, balance = None, error = None, testnet = False, base_url = None) -> None` | 19 |  |
| method | `get_api_key_info(self)` | 40 |  |
| method | `get_wallet_balance(self, *, account_type = 'UNIFIED', coin = 'USDT')` | 46 |  |
| function | `make_key_info(*, read_only = False)` | 53 |  |
| function | `make_balance(wallet = '25.5', available = '20')` | 61 |  |
| function | `test_account_checker_returns_ok_result() -> None` | 69 |  |
| function | `test_account_checker_disables_trading_for_read_only_key() -> None` | 93 |  |
| function | `test_account_checker_detects_empty_balance() -> None` | 108 |  |
| function | `test_account_checker_detects_missing_usdt() -> None` | 124 |  |
| function | `test_account_checker_detects_invalid_credentials() -> None` | 141 |  |
| function | `test_account_checker_detects_generic_api_error() -> None` | 159 |  |
| function | `test_account_checker_detects_timeout() -> None` | 175 |  |
| function | `test_account_checker_detects_url_timeout() -> None` | 187 |  |
| function | `test_account_checker_detects_network_error() -> None` | 199 |  |
| function | `test_account_checker_detects_unexpected_response() -> None` | 211 |  |
| function | `test_account_checker_detects_mainnet_from_custom_url() -> None` | 223 |  |
### [`tests/test_bybit_executor.py`](../tests/test_bybit_executor.py)

Строк: **378**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `FakeBybitOrderClient` | 20 |  |
| method | `__init__(self) -> None` | 21 |  |
| method | `create_limit_order(self, order, *, order_link_id = None, dry_run = True)` | 44 |  |
| method | `get_order(self, *, symbol, order_id = None, order_link_id = None)` | 69 |  |
| method | `cancel_order(self, *, symbol, order_id = None, order_link_id = None, dry_run = True)` | 85 |  |
| function | `make_request(*, side: PositionSide = PositionSide.LONG, client_order_id: str \| None = 'client-123') -> ExecutionRequest` | 109 |  |
| function | `test_bybit_executor_implements_trade_executor() -> None` | 123 |  |
| function | `test_dry_run_executor_has_dry_run_mode() -> None` | 133 |  |
| function | `test_open_position_creates_buy_order() -> None` | 142 |  |
| function | `test_close_position_creates_sell_order() -> None` | 163 |  |
| function | `test_dry_run_order_is_not_submitted() -> None` | 178 |  |
| function | `test_short_position_is_rejected() -> None` | 192 |  |
| function | `test_create_order_failure_returns_failed_result() -> None` | 207 |  |
| function | `test_get_order_status_maps_bybit_status(bybit_status: str, expected_status: ExecutionStatus) -> None` | 244 |  |
| function | `test_filled_order_contains_execution_data() -> None` | 281 |  |
| function | `test_cancel_order_returns_cancelled_result() -> None` | 306 |  |
| function | `test_dry_run_rejects_remote_order_operations(method_name: str) -> None` | 335 |  |
| function | `test_unknown_bybit_status_becomes_failed() -> None` | 354 |  |
### [`tests/test_bybit_instruments.py`](../tests/test_bybit_instruments.py)

Строк: **118**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_instrument_info_normalizes_values() -> None` | 12 |  |
| function | `test_client_gets_spot_instrument_info() -> None` | 28 |  |
| function | `test_client_reports_missing_instrument() -> None` | 81 |  |
| function | `test_client_rejects_api_error() -> None` | 103 |  |
### [`tests/test_bybit_market_data.py`](../tests/test_bybit_market_data.py)

Строк: **310**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_payload(rows: list[list[str]]) -> dict` | 14 |  |
| function | `make_row(start_ms: int, *, open_price: str = '100', high_price: str = '110', low_price: str = '90', close_price: str = '105', volume: str = '12.5') -> list[str]` | 28 |  |
| function | `test_requests_public_bybit_kline_endpoint() -> None` | 48 |  |
| function | `test_converts_and_sorts_bybit_candles() -> None` | 92 |  |
| function | `test_excludes_current_unclosed_candle() -> None` | 146 |  |
| function | `test_can_include_current_candle() -> None` | 168 |  |
| function | `test_latest_candle_returns_newest_closed() -> None` | 184 |  |
| function | `test_rejects_bybit_api_error() -> None` | 203 |  |
| function | `test_rejects_invalid_kline_values() -> None` | 221 |  |
| function | `test_rejects_invalid_configuration(field: str, value) -> None` | 253 |  |
| function | `test_retries_after_connection_error() -> None` | 263 |  |
| function | `test_fails_after_all_retry_attempts() -> None` | 292 |  |
### [`tests/test_bybit_orders.py`](../tests/test_bybit_orders.py)

Строк: **476**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `order() -> SpotLimitOrder` | 18 |  |
| function | `test_create_limit_order_dry_run_does_not_send_request(order: SpotLimitOrder) -> None` | 27 |  |
| function | `test_create_limit_order_sends_signed_request(order: SpotLimitOrder) -> None` | 65 |  |
| function | `test_create_limit_order_raises_safe_api_error(order: SpotLimitOrder) -> None` | 127 |  |
| function | `test_create_limit_order_rejects_unexpected_response(order: SpotLimitOrder) -> None` | 154 |  |
| function | `test_create_limit_order_rejects_empty_order_link_id(order: SpotLimitOrder, order_link_id: str) -> None` | 186 |  |
| function | `test_order_client_uses_testnet_url() -> None` | 207 |  |
| function | `test_get_order_returns_parsed_status() -> None` | 225 |  |
| function | `test_get_order_reports_missing_order() -> None` | 292 |  |
| function | `test_get_order_accepts_order_link_id() -> None` | 316 |  |
| function | `test_cancel_order_dry_run_does_not_send_request() -> None` | 360 |  |
| function | `test_cancel_order_sends_signed_request() -> None` | 392 |  |
| function | `test_order_operations_require_identifier(order_id, order_link_id) -> None` | 453 |  |
### [`tests/test_candle_mapper.py`](../tests/test_candle_mapper.py)

Строк: **75**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_data() -> pd.DataFrame` | 7 |  |
| function | `test_dataframe_to_candles() -> None` | 25 |  |
| function | `test_empty_dataframe_returns_empty_list() -> None` | 45 |  |
| function | `test_missing_columns_raise_error() -> None` | 51 |  |
| function | `test_accepts_string_datetime() -> None` | 68 |  |
### [`tests/test_check_runtime.py`](../tests/test_check_runtime.py)

Строк: **45**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_paper_settings() -> Settings` | 7 |  |
| function | `test_summarizes_paper_runtime() -> None` | 18 |  |
| function | `test_summary_does_not_contain_credentials() -> None` | 31 |  |
| function | `test_summary_mode_matches_executor() -> None` | 40 |  |
### [`tests/test_check_runtime_alerts.py`](../tests/test_check_runtime_alerts.py)

Строк: **9**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_runtime_alerts_exit_code_is_defined()` | 6 |  |
### [`tests/test_compare_regime_filter_components.py`](../tests/test_compare_regime_filter_components.py)

Строк: **458**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `market_data(start: str = '2020-01-01', periods: int = 500) -> pd.DataFrame` | 35 |  |
| function | `small_config() -> ResearchConfig` | 56 |  |
| class | `OneSignalStrategy` | 67 |  |
| method | `__init__(self, signal) -> None` | 68 |  |
| method | `generate_signal(self, candles, index)` | 71 |  |
| function | `wrapped(signal, regime, policy)` | 75 |  |
| function | `detected(trend: MarketTrend, volatility: MarketVolatility = MarketVolatility.NORMAL) -> MarketRegime` | 86 |  |
| function | `candle() -> list[Candle]` | 93 |  |
| function | `test_policy_is_immutable_and_validates_names() -> None` | 97 |  |
| function | `test_range_only_blocks_range() -> None` | 109 |  |
| function | `test_range_only_does_not_block_high_volatility() -> None` | 120 |  |
| function | `test_high_volatility_only_does_not_block_range() -> None` | 131 |  |
| function | `test_primary_reason_priority_controls_policy() -> None` | 142 |  |
| function | `test_full_policy_matches_default_filter() -> None` | 155 |  |
| function | `test_empty_policy_matches_detector_only() -> None` | 170 |  |
| function | `test_non_entries_are_never_blocked(signal) -> None` | 190 |  |
| function | `test_trade_signal_is_not_mutated() -> None` | 201 |  |
| function | `component_results()` | 221 |  |
| function | `test_all_variants_have_independent_results_and_invariants(component_results) -> None` | 229 |  |
| function | `test_component_reasons_match_each_policy(component_results) -> None` | 262 |  |
| function | `test_no_lookahead() -> None` | 286 |  |
| function | `test_full_filtered_reproduces_committed_five_windows() -> None` | 309 |  |
| function | `test_component_aggregates_and_compounding(component_results) -> None` | 324 |  |
| function | `test_mixed_compounding_is_multiplicative(component_results) -> None` | 345 |  |
| function | `test_json_csv_are_atomic_and_deterministic(tmp_path) -> None` | 362 |  |
| function | `test_cli_works_from_any_cwd_without_default_reports(tmp_path) -> None` | 397 |  |
| function | `test_invalid_arguments(arguments, capsys) -> None` | 437 |  |
| function | `test_empty_and_short_datasets_are_rejected() -> None` | 445 |  |
### [`tests/test_compare_regime_filters.py`](../tests/test_compare_regime_filters.py)

Строк: **451**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `write_market_data(path: Path, *, periods: int = 320) -> None` | 20 |  |
| function | `test_run_comparison_contains_all_periods_and_variants(tmp_path) -> None` | 44 |  |
| function | `test_detector_only_financial_results_equal_baseline(tmp_path) -> None` | 70 |  |
| function | `test_detector_cache_does_not_mix_equal_timestamp_ohlc() -> None` | 102 |  |
| function | `test_train_test_boundary_is_complete_and_disjoint() -> None` | 127 |  |
| function | `test_period_runs_use_independent_instances(tmp_path, monkeypatch) -> None` | 144 |  |
| function | `test_cached_and_uncached_runs_are_exactly_equivalent(tmp_path) -> None` | 216 |  |
| function | `test_test_period_warms_indicators_without_carrying_account(tmp_path) -> None` | 251 |  |
| function | `test_default_baseline_matches_historical_ema_backtest() -> None` | 280 |  |
| function | `test_results_sort_by_return_drawdown_and_profit_factor() -> None` | 297 |  |
| function | `test_json_report_is_saved_atomically(tmp_path) -> None` | 355 |  |
| function | `test_atomic_write_failure_preserves_report_and_cleans_temp(tmp_path, monkeypatch) -> None` | 377 |  |
| function | `test_cli_works_from_any_cwd_without_project_writes(tmp_path) -> None` | 397 |  |
| function | `test_invalid_periods_and_thresholds_are_clear(arguments, message, capsys) -> None` | 442 |  |
### [`tests/test_config.py`](../tests/test_config.py)

Строк: **123**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_default_config() -> None` | 11 |  |
| function | `test_custom_config() -> None` | 18 |  |
| function | `test_invalid_start_balance(start_balance: float) -> None` | 35 |  |
| function | `test_invalid_fee_rate(fee_rate: float) -> None` | 46 |  |
| function | `test_empty_symbol() -> None` | 53 |  |
| function | `test_empty_timeframe() -> None` | 58 |  |
| function | `test_default_paper_strategy_mode_is_baseline(monkeypatch) -> None` | 63 |  |
| function | `test_cli_mode_override_has_priority(monkeypatch) -> None` | 73 |  |
| function | `test_invalid_paper_strategy_mode_is_rejected(monkeypatch) -> None` | 83 |  |
| function | `test_invalid_direct_paper_strategy_mode_is_rejected() -> None` | 92 |  |
| function | `test_invalid_regime_environment_is_rejected(monkeypatch, name, value) -> None` | 107 |  |
| function | `test_shadow_path_required_when_enabled(monkeypatch) -> None` | 118 |  |
### [`tests/test_data_loader.py`](../tests/test_data_loader.py)

Строк: **107**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_valid_frame() -> pd.DataFrame` | 12 |  |
| function | `write_csv(tmp_path: Path, frame: pd.DataFrame, filename: str = 'market.csv') -> Path` | 30 |  |
| function | `test_load_valid_market_data(tmp_path: Path) -> None` | 40 |  |
| function | `test_missing_file() -> None` | 56 |  |
| function | `test_missing_required_column(tmp_path: Path) -> None` | 61 |  |
| function | `test_duplicate_datetime(tmp_path: Path) -> None` | 69 |  |
| function | `test_invalid_ohlc(tmp_path: Path) -> None` | 79 |  |
| function | `test_find_missing_hour() -> None` | 89 |  |
| function | `test_no_missing_hours() -> None` | 101 |  |
### [`tests/test_ema_cross_stop_strategy.py`](../tests/test_ema_cross_stop_strategy.py)

Строк: **86**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_candles(*prices: float) -> list[Candle]` | 8 |  |
| function | `test_generates_long_entry_with_stop_loss() -> None` | 24 |  |
| function | `test_generates_close_long_signal() -> None` | 49 |  |
| function | `test_rejects_invalid_stop_loss_percent(stop_loss_percent: float) -> None` | 78 |  |
### [`tests/test_ema_cross_strategy.py`](../tests/test_ema_cross_strategy.py)

Строк: **160**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_candles(*prices: float) -> list[Candle]` | 7 |  |
| function | `test_strategy_returns_hold_before_enough_data()` | 21 |  |
| function | `test_strategy_generates_buy_signal_on_upward_cross()` | 45 |  |
| function | `test_strategy_generates_sell_signal_on_downward_cross()` | 67 |  |
| function | `test_strategy_returns_hold_without_cross()` | 89 |  |
| function | `test_calculate_ema_for_constant_prices()` | 111 |  |
| function | `test_calculate_ema_for_rising_prices()` | 120 |  |
| function | `test_strategy_rejects_invalid_periods(short_period, long_period)` | 140 |  |
| function | `test_calculate_ema_rejects_empty_values()` | 151 |  |
### [`tests/test_ema_trend_strategy.py`](../tests/test_ema_trend_strategy.py)

Строк: **79**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_candles(prices: list[float]) -> list[Candle]` | 8 |  |
| function | `test_returns_hold_during_warmup() -> None` | 24 |  |
| function | `test_rejects_invalid_periods() -> None` | 42 |  |
| function | `test_rejects_invalid_index() -> None` | 63 |  |
### [`tests/test_engine.py`](../tests/test_engine.py)

Строк: **850**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `BuyAndSellStrategy` | 7 |  |
| method | `generate_signal(self, candles, index)` | 8 |  |
| class | `BuyOnlyStrategy` | 18 |  |
| method | `generate_signal(self, candles, index)` | 19 |  |
| class | `HoldStrategy` | 26 |  |
| method | `generate_signal(self, candles, index)` | 27 |  |
| function | `make_candles(*prices: float) -> list[Candle]` | 31 |  |
| function | `test_engine_makes_profitable_trade()` | 45 |  |
| function | `test_engine_makes_losing_trade()` | 65 |  |
| function | `test_engine_accounts_for_commission()` | 84 |  |
| function | `test_engine_closes_open_position_on_last_candle()` | 110 |  |
| function | `test_hold_strategy_makes_no_trades()` | 128 |  |
| function | `test_engine_calculates_drawdown()` | 145 |  |
| function | `test_engine_rejects_empty_candles()` | 159 |  |
| function | `test_engine_rejects_invalid_configuration(initial_balance, commission_rate)` | 178 |  |
| function | `test_engine_rejects_invalid_close_price()` | 189 |  |
| function | `test_signal_executes_at_next_candle_open()` | 211 |  |
| function | `test_engine_calculates_trade_quality_metrics()` | 257 |  |
| function | `test_engine_metrics_for_no_trades()` | 283 |  |
| class | `ProfitableShortStrategy` | 306 |  |
| method | `generate_signal(self, candles, index)` | 307 |  |
| class | `LosingShortStrategy` | 317 |  |
| method | `generate_signal(self, candles, index)` | 318 |  |
| function | `test_engine_makes_profitable_short_trade()` | 328 |  |
| function | `test_engine_makes_losing_short_trade()` | 350 |  |
| function | `test_short_position_is_closed_at_end()` | 370 |  |
| function | `test_legacy_buy_sell_signals_still_open_long()` | 394 |  |
| class | `LongWithStopStrategy` | 410 |  |
| method | `generate_signal(self, candles, index)` | 411 |  |
| class | `ShortWithStopStrategy` | 421 |  |
| method | `generate_signal(self, candles, index)` | 422 |  |
| class | `InvalidLongStopStrategy` | 432 |  |
| method | `generate_signal(self, candles, index)` | 433 |  |
| function | `test_long_stop_loss_is_triggered_inside_candle() -> None` | 443 |  |
| function | `test_long_stop_uses_open_price_after_gap() -> None` | 464 |  |
| function | `test_short_stop_loss_is_triggered_inside_candle() -> None` | 481 |  |
| function | `test_rejects_long_stop_above_entry_price() -> None` | 502 |  |
| class | `RiskSizedLongStrategy` | 521 |  |
| method | `generate_signal(self, candles, index)` | 522 |  |
| class | `RiskSizedShortStrategy` | 532 |  |
| method | `generate_signal(self, candles, index)` | 533 |  |
| function | `test_engine_sizes_long_position_by_risk() -> None` | 543 |  |
| function | `test_engine_sizes_short_position_by_risk() -> None` | 566 |  |
| class | `LongTrailingStopStrategy` | 587 |  |
| method | `generate_signal(self, candles, index)` | 588 |  |
| class | `ShortTrailingStopStrategy` | 599 |  |
| method | `generate_signal(self, candles, index)` | 600 |  |
| function | `test_rejects_trailing_stop_without_initial_stop() -> None` | 611 |  |
| function | `test_rejects_invalid_trailing_stop_percent(trailing_stop_percent: float) -> None` | 626 |  |
| function | `test_long_trailing_stop_protects_profit() -> None` | 640 |  |
| function | `test_short_trailing_stop_protects_profit() -> None` | 666 |  |
| function | `test_long_trailing_stop_never_moves_down() -> None` | 692 |  |
| function | `test_short_trailing_stop_never_moves_up() -> None` | 701 |  |
| function | `test_rejects_break_even_without_stop_loss() -> None` | 710 |  |
| function | `test_rejects_invalid_break_even(break_even_r_multiple) -> None` | 725 |  |
| function | `test_accepts_break_even_configuration() -> None` | 739 |  |
| function | `test_trade_default_exit_reason_is_signal() -> None` | 749 |  |
| function | `test_signal_close_has_signal_exit_reason() -> None` | 768 |  |
| function | `test_initial_stop_has_stop_loss_exit_reason() -> None` | 793 |  |
| function | `test_trailed_stop_has_trailing_stop_exit_reason() -> None` | 813 |  |
| function | `test_end_of_data_has_end_of_data_exit_reason() -> None` | 836 |  |
### [`tests/test_execution.py`](../tests/test_execution.py)

Строк: **220**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_request() -> ExecutionRequest` | 15 |  |
| function | `test_execution_request_normalizes_values() -> None` | 25 |  |
| function | `test_execution_request_rejects_invalid_values(field: str, value: object, message: str) -> None` | 53 |  |
| function | `test_execution_result_reports_success_and_completion() -> None` | 71 |  |
| function | `test_failed_execution_is_not_successful() -> None` | 90 |  |
| function | `test_open_execution_is_successful_but_incomplete() -> None` | 105 |  |
| function | `test_execution_result_requires_average_price_for_fill() -> None` | 119 |  |
| function | `test_execution_result_rejects_overfill() -> None` | 138 |  |
| function | `test_trade_executor_protocol_accepts_implementation() -> None` | 158 |  |
### [`tests/test_execution_config.py`](../tests/test_execution_config.py)

Строк: **145**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_settings(*, mode: ExecutionMode, api_key: str \| None = 'key', api_secret: str \| None = 'secret', testnet: bool = True, confirmed: bool = False, allow_mainnet: bool = False) -> Settings` | 11 |  |
| function | `test_paper_mode_does_not_require_credentials() -> None` | 30 |  |
| function | `test_dry_run_builds_testnet_account() -> None` | 46 |  |
| function | `test_exchange_modes_require_both_credentials(api_key: str \| None, api_secret: str \| None) -> None` | 72 |  |
| function | `test_live_requires_explicit_confirmation() -> None` | 89 |  |
| function | `test_live_testnet_is_allowed_after_confirmation() -> None` | 102 |  |
| function | `test_live_mainnet_requires_separate_permission() -> None` | 118 |  |
| function | `test_live_mainnet_requires_two_confirmations() -> None` | 133 |  |
### [`tests/test_execution_runner.py`](../tests/test_execution_runner.py)

Строк: **179**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `FakeLiveExecutor` | 22 |  |
| method | `__init__(self) -> None` | 23 |  |
| method | `mode(self) -> ExecutionMode` | 28 |  |
| method | `open_position(self, request: ExecutionRequest) -> ExecutionResult` | 31 |  |
| method | `close_position(self, request: ExecutionRequest) -> ExecutionResult` | 40 |  |
| method | `cancel_order(self, *, symbol: str, order_id: str \| None = None, client_order_id: str \| None = None) -> ExecutionResult` | 49 |  |
| method | `get_order_status(self, *, symbol: str, order_id: str \| None = None, client_order_id: str \| None = None) -> ExecutionResult` | 58 |  |
| function | `build_command(action: TradeAction) -> ExecutionCommand` | 68 |  |
| function | `test_execution_command_normalizes_symbol() -> None` | 80 |  |
| function | `test_runner_returns_none_for_hold() -> None` | 88 |  |
| function | `test_runner_opens_long_position() -> None` | 98 |  |
| function | `test_runner_closes_long_position() -> None` | 112 |  |
| function | `test_runner_rejects_short_actions(action: TradeAction) -> None` | 132 |  |
| function | `test_runner_blocks_live_execution_by_default() -> None` | 144 |  |
| function | `test_execution_command_rejects_invalid_values(quantity: Decimal, price: Decimal) -> None` | 169 |  |
### [`tests/test_executor_factory.py`](../tests/test_executor_factory.py)

Строк: **156**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `FakeBybitOrderClient` | 11 |  |
| method | `__init__(self, account: BybitAccountConfig) -> None` | 12 |  |
| function | `make_account(*, testnet: bool = True) -> BybitAccountConfig` | 19 |  |
| function | `test_builds_paper_executor() -> None` | 30 |  |
| function | `test_builds_dry_run_bybit_executor() -> None` | 44 |  |
| function | `test_builds_live_bybit_executor() -> None` | 71 |  |
| function | `test_paper_mode_rejects_exchange_account() -> None` | 90 |  |
| function | `test_exchange_modes_require_account(mode: ExecutionMode) -> None` | 111 |  |
| function | `test_dry_run_mode_requires_dry_run_flag() -> None` | 129 |  |
| function | `test_live_mode_rejects_dry_run_flag() -> None` | 144 |  |
### [`tests/test_indicators.py`](../tests/test_indicators.py)

Строк: **368**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_sma() -> None` | 6 |  |
| function | `test_ema_returns_values() -> None` | 17 |  |
| function | `test_rsi_for_rising_prices() -> None` | 27 |  |
| function | `test_rsi_for_flat_prices() -> None` | 37 |  |
| function | `test_period_must_be_positive(function) -> None` | 49 |  |
| function | `test_true_range_without_price_gap() -> None` | 55 |  |
| function | `test_true_range_accounts_for_upward_gap() -> None` | 71 |  |
| function | `test_true_range_accounts_for_downward_gap() -> None` | 86 |  |
| function | `test_atr_for_constant_ranges() -> None` | 101 |  |
| function | `test_atr_reacts_to_larger_range() -> None` | 116 |  |
| function | `test_true_range_requires_ohlc_columns() -> None` | 130 |  |
| function | `test_atr_period_must_be_positive() -> None` | 145 |  |
| function | `test_adx_for_strong_uptrend() -> None` | 159 |  |
| function | `test_adx_for_strong_downtrend() -> None` | 185 |  |
| function | `test_adx_for_flat_market_is_low() -> None` | 217 |  |
| function | `test_adx_requires_ohlc_columns() -> None` | 234 |  |
| function | `test_adx_period_must_be_positive() -> None` | 249 |  |
| function | `test_adx_for_strong_uptrend() -> None` | 265 |  |
| function | `test_adx_for_strong_downtrend() -> None` | 291 |  |
| function | `test_adx_for_flat_market_is_low() -> None` | 323 |  |
| function | `test_adx_requires_ohlc_columns() -> None` | 340 |  |
| function | `test_adx_period_must_be_positive() -> None` | 355 |  |
### [`tests/test_market_data.py`](../tests/test_market_data.py)

Строк: **182**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `write_market_csv(tmp_path: Path, *, rows: int = 4) -> Path` | 13 |  |
| function | `test_csv_feed_implements_market_data_protocol(tmp_path: Path) -> None` | 55 |  |
| function | `test_csv_feed_returns_candles(tmp_path: Path) -> None` | 67 |  |
| function | `test_csv_feed_preserves_chronological_order(tmp_path: Path) -> None` | 82 |  |
| function | `test_csv_feed_limit_returns_latest_candles(tmp_path: Path) -> None` | 113 |  |
| function | `test_csv_feed_returns_latest_candle(tmp_path: Path) -> None` | 128 |  |
| function | `test_csv_feed_rejects_invalid_limit(tmp_path: Path, limit: int) -> None` | 145 |  |
| function | `test_csv_feed_reuses_loader_validation(tmp_path: Path) -> None` | 159 |  |
### [`tests/test_market_regime.py`](../tests/test_market_regime.py)

Строк: **238**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_market_regime_creation() -> None` | 10 |  |
| function | `test_market_regime_rejects_invalid_confidence() -> None` | 21 |  |
| function | `test_detector_returns_default_regime() -> None` | 29 |  |
| function | `test_detector_returns_unknown_for_single_candle() -> None` | 38 |  |
| function | `test_detector_detects_uptrend() -> None` | 58 |  |
| function | `test_detector_detects_downtrend() -> None` | 84 |  |
| function | `test_detector_detects_range() -> None` | 111 |  |
| function | `test_detector_uses_adx_to_detect_range() -> None` | 138 |  |
| function | `test_detector_uses_ema_direction_when_adx_is_strong() -> None` | 163 |  |
| function | `test_detector_detects_high_volatility_with_atr() -> None` | 188 |  |
| function | `test_detector_detects_low_volatility_with_atr() -> None` | 214 |  |
### [`tests/test_metrics.py`](../tests/test_metrics.py)

Строк: **34**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_calculate_positive_return()` | 9 |  |
| function | `test_calculate_negative_return()` | 13 |  |
| function | `test_start_balance_error()` | 17 |  |
| function | `test_drawdown()` | 22 |  |
| function | `test_drawdown_zero()` | 27 |  |
| function | `test_drawdown_empty()` | 32 |  |
### [`tests/test_models.py`](../tests/test_models.py)

Строк: **27**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_create_paper_statistics() -> None` | 4 |  |
### [`tests/test_order_builder.py`](../tests/test_order_builder.py)

Строк: **151**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `instrument() -> InstrumentInfo` | 14 |  |
| function | `test_limit_order_normalizes_symbol_and_side() -> None` | 26 |  |
| function | `test_builder_rounds_price_and_quantity_down(instrument: InstrumentInfo) -> None` | 38 |  |
| function | `test_order_value_is_calculated(instrument: InstrumentInfo) -> None` | 53 |  |
| function | `test_order_builds_bybit_payload(instrument: InstrumentInfo) -> None` | 67 |  |
| function | `test_builder_rejects_order_below_minimum_value(instrument: InstrumentInfo) -> None` | 88 |  |
| function | `test_builder_rejects_quantity_above_maximum(instrument: InstrumentInfo) -> None` | 104 |  |
| function | `test_builder_rejects_non_trading_instrument() -> None` | 120 |  |
| function | `test_order_rejects_invalid_side(side: str) -> None` | 144 |  |
### [`tests/test_paper_engine.py`](../tests/test_paper_engine.py)

Строк: **232**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `BuyThenSellStrategy` | 16 |  |
| method | `generate_signal(self, candles, index)` | 17 |  |
| class | `HoldStrategy` | 27 |  |
| method | `generate_signal(self, candles, index)` | 28 |  |
| function | `make_candles() -> tuple[Candle, ...]` | 32 |  |
| function | `test_processes_only_new_candles() -> None` | 40 |  |
| function | `test_executes_signal_on_next_candle_open() -> None` | 64 |  |
| function | `test_keeps_pending_signal_after_last_candle() -> None` | 90 |  |
| function | `test_ignores_duplicate_iteration() -> None` | 114 |  |
| function | `make_long_position(*, active_stop_loss: float = 95, trailing_stop_percent: float \| None = None) -> PaperPosition` | 140 |  |
| function | `test_closes_position_when_stop_is_hit() -> None` | 159 |  |
| function | `test_updates_trailing_stop_during_iteration() -> None` | 195 |  |
### [`tests/test_paper_executor.py`](../tests/test_paper_executor.py)

Строк: **167**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_request(*, side: PositionSide = PositionSide.LONG, client_order_id: str \| None = 'client-001') -> ExecutionRequest` | 15 |  |
| function | `test_paper_executor_implements_trade_executor() -> None` | 29 |  |
| function | `test_open_position_returns_filled_result() -> None` | 36 |  |
| function | `test_close_position_returns_filled_result() -> None` | 53 |  |
| function | `test_order_ids_are_sequential() -> None` | 69 |  |
| function | `test_get_order_status_by_order_id() -> None` | 83 |  |
| function | `test_get_order_status_by_client_order_id() -> None` | 95 |  |
| function | `test_cancel_order_returns_cancelled_result() -> None` | 107 |  |
| function | `test_unknown_order_raises_error(method_name: str, kwargs: dict[str, str]) -> None` | 147 |  |
| function | `test_order_lookup_rejects_wrong_symbol() -> None` | 158 |  |
### [`tests/test_paper_session.py`](../tests/test_paper_session.py)

Строк: **936**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_candle(timestamp: int) -> Candle` | 17 |  |
| function | `test_default_session_snapshot() -> None` | 30 |  |
| function | `test_accepts_new_closed_candle() -> None` | 47 |  |
| function | `test_ignores_duplicate_candle() -> None` | 60 |  |
| function | `test_ignores_older_candle() -> None` | 72 |  |
| function | `test_preserves_existing_position() -> None` | 89 |  |
| function | `test_rejects_invalid_position_values(field: str, value) -> None` | 130 |  |
| function | `test_rejects_long_stop_above_entry() -> None` | 148 |  |
| function | `test_rejects_short_stop_below_entry() -> None` | 166 |  |
| function | `test_pending_open_requires_reference_price() -> None` | 184 |  |
| function | `test_pending_stop_requires_open_action() -> None` | 194 |  |
| function | `test_rejects_invalid_candle() -> None` | 205 |  |
| function | `make_long_position(*, stop_loss: float = 95, trailing_stop_percent: float \| None = None) -> PaperPosition` | 224 |  |
| function | `test_session_detects_position_stop() -> None` | 243 |  |
| function | `test_session_returns_stop_exit_price_after_gap() -> None` | 256 |  |
| function | `test_session_updates_long_trailing_stop() -> None` | 271 |  |
| function | `test_session_does_not_move_trailing_stop_back() -> None` | 296 |  |
| function | `test_session_without_position_has_no_stop() -> None` | 318 |  |
| function | `test_closes_profitable_long_position() -> None` | 326 |  |
| function | `test_closes_losing_long_position() -> None` | 351 |  |
| function | `test_closes_profitable_short_position() -> None` | 372 |  |
| function | `test_close_position_accounts_for_commission() -> None` | 406 |  |
| function | `test_closes_position_at_initial_stop() -> None` | 438 |  |
| function | `test_closes_position_at_trailing_stop() -> None` | 457 |  |
| function | `test_close_position_rejects_missing_position() -> None` | 494 |  |
| function | `test_close_at_stop_rejects_unhit_stop() -> None` | 508 |  |
| function | `test_session_rejects_invalid_commission(commission_rate: float) -> None` | 529 |  |
| function | `test_process_closed_candle_ignores_duplicate() -> None` | 541 |  |
| function | `test_process_closed_candle_closes_position_at_stop() -> None` | 558 |  |
| function | `test_process_closed_candle_updates_trailing_stop() -> None` | 582 |  |
| function | `test_process_closed_candle_checks_stop_before_trailing() -> None` | 609 |  |
| function | `test_process_closed_candle_without_position() -> None` | 630 |  |
| function | `test_opens_long_position_without_stop() -> None` | 644 |  |
| function | `test_opens_position_using_risk_manager() -> None` | 672 |  |
| function | `test_rejects_opening_second_position() -> None` | 712 |  |
| function | `test_queues_open_long_action() -> None` | 730 |  |
| function | `test_ignores_close_action_without_position() -> None` | 758 |  |
| function | `test_queues_close_for_matching_position() -> None` | 772 |  |
| function | `test_executes_pending_open_on_candle_open() -> None` | 791 |  |
| function | `test_executes_pending_close_on_candle_open() -> None` | 821 |  |
| function | `test_pending_close_does_not_close_wrong_side() -> None` | 844 |  |
| function | `test_process_closed_candle_ignores_duplicate() -> None` | 878 |  |
| function | `test_process_closed_candle_closes_at_stop() -> None` | 893 |  |
| function | `test_process_closed_candle_updates_trailing_stop() -> None` | 913 |  |
### [`tests/test_paper_state.py`](../tests/test_paper_state.py)

Строк: **213**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_loads_default_state_when_file_missing(tmp_path: Path) -> None` | 21 |  |
| function | `test_saves_and_loads_state(tmp_path: Path) -> None` | 39 |  |
| function | `test_rejects_invalid_state_file(tmp_path: Path) -> None` | 57 |  |
| function | `test_rejects_invalid_state_values(field: str, value) -> None` | 81 |  |
| function | `test_saves_and_loads_full_session_snapshot(tmp_path: Path) -> None` | 91 |  |
| function | `test_saves_pending_open_action(tmp_path: Path) -> None` | 134 |  |
| function | `test_legacy_state_creates_snapshot() -> None` | 176 |  |
| function | `test_allows_zero_free_balance_with_open_position() -> None` | 193 |  |
### [`tests/test_paper_statistics.py`](../tests/test_paper_statistics.py)

Строк: **95**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_trade(profit: float) -> Trade` | 8 |  |
| function | `test_returns_empty_statistics() -> None` | 23 |  |
| function | `test_calculates_basic_statistics() -> None` | 39 |  |
| function | `test_calculates_profit_factor_and_averages() -> None` | 61 |  |
| function | `test_profit_factor_is_zero_without_losses() -> None` | 82 |  |
### [`tests/test_paper_strategy_router.py`](../tests/test_paper_strategy_router.py)

Строк: **214**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `candles() -> list[Candle]` | 23 |  |
| function | `regime(trend = MarketTrend.TREND_UP, volatility = MarketVolatility.NORMAL)` | 30 |  |
| function | `router(mode, detected = None)` | 37 |  |
| function | `test_baseline_preserves_signal_without_detector() -> None` | 49 |  |
| function | `test_filtered_allows_valid_entry() -> None` | 60 |  |
| function | `test_filtered_blocks_invalid_entry(detected, reason) -> None` | 84 |  |
| function | `test_filtered_never_blocks_exit(signal) -> None` | 103 |  |
| function | `test_shadow_executes_baseline_and_records_filtered_view() -> None` | 119 |  |
| function | `test_detector_error_filtered_fails_closed_only_for_entry() -> None` | 133 |  |
| function | `test_detector_error_shadow_keeps_baseline_entry() -> None` | 147 |  |
| function | `test_shadow_and_baseline_have_identical_accounting() -> None` | 157 |  |
| function | `test_filtered_can_differ_only_by_suppressing_entry() -> None` | 196 |  |
### [`tests/test_paper_trader.py`](../tests/test_paper_trader.py)

Строк: **339**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `StaticFeed` | 22 |  |
| method | `__init__(self, candles: tuple[Candle, ...]) -> None` | 23 |  |
| method | `get_candles(self) -> tuple[Candle, ...]` | 29 |  |
| class | `BuyOnlyStrategy` | 33 |  |
| method | `generate_signal(self, candles, index)` | 34 |  |
| class | `HoldStrategy` | 41 |  |
| method | `generate_signal(self, candles, index)` | 42 |  |
| function | `make_trade(*, entry_timestamp: int = 1, exit_timestamp: int = 2, profit: float = 10) -> Trade` | 46 |  |
| function | `make_candles() -> tuple[Candle, ...]` | 67 |  |
| function | `test_records_trade_to_csv(tmp_path: Path) -> None` | 75 |  |
| function | `test_records_header_only_once(tmp_path: Path) -> None` | 113 |  |
| function | `test_records_multiple_trades(tmp_path: Path) -> None` | 150 |  |
| function | `test_run_session_executes_engine_and_logs_trade(tmp_path: Path) -> None` | 183 |  |
| function | `test_run_session_with_no_trades_writes_no_file(tmp_path: Path) -> None` | 220 |  |
| function | `test_run_session_rejects_empty_feed(tmp_path: Path) -> None` | 244 |  |
| function | `test_does_not_record_same_trade_twice(tmp_path: Path) -> None` | 263 |  |
| function | `test_record_trades_returns_number_of_new_rows(tmp_path: Path) -> None` | 288 |  |
| function | `test_counts_recorded_trades(tmp_path: Path) -> None` | 315 |  |
### [`tests/test_performance_analyzer.py`](../tests/test_performance_analyzer.py)

Строк: **136**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_trade(*, profit: float, profit_percent: float, side: PositionSide = PositionSide.LONG) -> Trade` | 8 |  |
| function | `test_returns_empty_analysis() -> None` | 28 |  |
| function | `test_calculates_general_statistics() -> None` | 39 |  |
| function | `test_calculates_winning_and_losing_streaks() -> None` | 77 |  |
| function | `test_calculates_long_and_short_statistics() -> None` | 93 |  |
| function | `test_break_even_trade_breaks_streak() -> None` | 127 |  |
### [`tests/test_plot_trade_statistics.py`](../tests/test_plot_trade_statistics.py)

Строк: **154**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `assert_png(path: Path) -> None` | 21 |  |
| function | `test_uses_headless_backend() -> None` | 27 |  |
| function | `test_custom_journal_output_and_parent_creation(tmp_path) -> None` | 31 |  |
| function | `test_empty_journal_creates_png(tmp_path) -> None` | 65 |  |
| function | `test_corrupt_journal_returns_nonzero_without_png(tmp_path, capsys) -> None` | 80 |  |
| function | `test_cli_runs_from_project_root_and_creates_png(tmp_path) -> None` | 103 |  |
| function | `test_cli_uses_shared_library_plot_writer(tmp_path, monkeypatch) -> None` | 132 |  |
### [`tests/test_process_lock.py`](../tests/test_process_lock.py)

Строк: **178**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `start_holder(path: Path) -> subprocess.Popen` | 27 |  |
| function | `stop_holder(process: subprocess.Popen) -> None` | 42 |  |
| function | `test_lock_is_acquired_and_released(tmp_path) -> None` | 53 |  |
| function | `test_independent_process_cannot_acquire_held_lock(tmp_path) -> None` | 69 |  |
| function | `test_lock_can_be_reacquired_after_process_exits(tmp_path) -> None` | 80 |  |
| function | `test_existing_unlocked_file_does_not_block(tmp_path) -> None` | 89 |  |
| function | `test_parent_directory_is_created(tmp_path) -> None` | 97 |  |
| function | `test_metadata_contains_pid_and_utc_timestamp(tmp_path) -> None` | 104 |  |
| function | `test_descriptor_is_closed_after_body_exception(tmp_path) -> None` | 114 |  |
| function | `test_metadata_write_error_releases_lock(tmp_path, monkeypatch) -> None` | 125 |  |
| function | `test_open_error_is_wrapped_and_contains_path(tmp_path) -> None` | 148 |  |
| function | `test_control_flow_exceptions_are_not_wrapped(tmp_path, exception_type) -> None` | 159 |  |
| function | `test_same_object_cannot_be_entered_twice(tmp_path) -> None` | 173 |  |
### [`tests/test_regime_filtered_strategy.py`](../tests/test_regime_filtered_strategy.py)

Строк: **279**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_candles(count: int = 3) -> list[Candle]` | 18 |  |
| function | `regime(trend: MarketTrend, volatility: MarketVolatility = MarketVolatility.NORMAL, confidence: float = 1.0) -> MarketRegime` | 32 |  |
| class | `SequenceStrategy` | 40 |  |
| method | `__init__(self, *signals) -> None` | 41 |  |
| method | `generate_signal(self, candles, index)` | 44 |  |
| class | `SequenceDetector` | 48 |  |
| method | `__init__(self, *regimes: MarketRegime) -> None` | 49 |  |
| method | `detect(self, candles)` | 53 |  |
| function | `wrap(signal, detected_regime, *, confidence = 0.0)` | 58 |  |
| function | `test_allows_entry_in_uptrend(volatility) -> None` | 70 |  |
| function | `test_blocks_entry_and_counts_reason(detected_regime, reason) -> None` | 102 |  |
| function | `test_exit_is_never_blocked_and_preserves_parameters() -> None` | 122 |  |
| function | `test_hold_remains_hold_without_regime_detection() -> None` | 149 |  |
| function | `test_allowed_entry_preserves_stop_loss() -> None` | 161 |  |
| function | `test_detector_never_receives_future_candles() -> None` | 177 |  |
| dataclass | `ImmutableStrategy` | 194 |  |
| method | `generate_signal(self, candles, index)` | 197 |  |
| function | `test_base_strategy_is_not_reconfigured_or_replaced() -> None` | 201 |  |
| function | `test_allowed_and_blocked_counters_accumulate() -> None` | 215 |  |
| function | `test_block_reason_priority_is_exclusive(detected_regime, reason) -> None` | 261 |  |
### [`tests/test_report_paper_daily.py`](../tests/test_report_paper_daily.py)

Строк: **33**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `files(tmp_path: Path, trade: dict \| None = None, shadow: dict \| None = None)` | 8 |  |
| function | `trade()` | 17 |  |
| function | `test_daily_without_trades_is_valid_and_atomic(tmp_path)` | 21 |  |
| function | `test_daily_trade_fees_pnl_and_shadow(tmp_path)` | 28 |  |
### [`tests/test_report_paper_weekly.py`](../tests/test_report_paper_weekly.py)

Строк: **12**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_weekly_aggregation_and_daily_breakdown(tmp_path)` | 6 |  |
### [`tests/test_report_trade_journal.py`](../tests/test_report_trade_journal.py)

Строк: **82**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_successful_report_uses_custom_journal_path(tmp_path, capsys) -> None` | 11 |  |
| function | `test_empty_journal_report(tmp_path, capsys) -> None` | 41 |  |
| function | `test_corrupt_custom_journal_is_reported(tmp_path) -> None` | 56 |  |
| function | `test_cli_uses_library_formatting(tmp_path, capsys, monkeypatch) -> None` | 67 |  |
### [`tests/test_risk.py`](../tests/test_risk.py)

Строк: **272**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_default_risk_config() -> None` | 11 |  |
| function | `test_rejects_invalid_risk_per_trade(risk_per_trade: float) -> None` | 23 |  |
| function | `test_rejects_invalid_max_position_fraction(max_position_fraction: float) -> None` | 37 |  |
| function | `test_rejects_invalid_leverage(leverage: float) -> None` | 53 |  |
| function | `test_calculates_long_position_by_risk() -> None` | 63 |  |
| function | `test_calculates_short_position_by_risk() -> None` | 90 |  |
| function | `test_position_is_limited_by_available_capital() -> None` | 111 |  |
| function | `test_leverage_increases_maximum_position_value() -> None` | 133 |  |
| function | `test_position_by_risk_can_use_less_than_maximum() -> None` | 155 |  |
| function | `test_rejects_non_positive_values(field_name: str, kwargs: dict[str, float]) -> None` | 207 |  |
| function | `test_rejects_invalid_long_stop_loss(stop_loss: float) -> None` | 224 |  |
| function | `test_rejects_invalid_short_stop_loss(stop_loss: float) -> None` | 245 |  |
| function | `test_accepts_full_risk_and_full_position_fraction() -> None` | 262 |  |
### [`tests/test_run_bybit_controller.py`](../tests/test_run_bybit_controller.py)

Строк: **798**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `start_lock_holder(path)` | 34 |  |
| function | `stop_lock_holder(process)` | 49 |  |
| function | `test_stop_loss_percent_is_two_percent() -> None` | 60 |  |
| function | `test_buy_signal_receives_stop_loss() -> None` | 64 |  |
| function | `test_stop_loss_closes_open_position() -> None` | 77 |  |
| function | `test_stop_loss_triggers_at_exact_price() -> None` | 95 |  |
| function | `test_hold_above_stop_does_not_close() -> None` | 113 |  |
| function | `test_strategy_sell_is_preserved() -> None` | 130 |  |
| function | `test_buy_does_not_replace_existing_stop() -> None` | 147 |  |
| function | `install_successful_run(monkeypatch, *, journal_entry) -> None` | 164 |  |
| function | `test_reports_are_created_after_successful_journal_change(tmp_path, monkeypatch) -> None` | 219 |  |
| function | `test_reports_are_not_created_before_successful_processing(tmp_path, monkeypatch) -> None` | 251 |  |
| function | `test_no_new_candle_does_not_overwrite_reports(tmp_path, monkeypatch) -> None` | 285 |  |
| function | `test_second_run_recovers_reports_without_duplicate_trade(tmp_path, monkeypatch) -> None` | 319 |  |
| function | `test_reporting_error_returns_nonzero(tmp_path, monkeypatch, capsys) -> None` | 448 |  |
| function | `test_custom_report_paths_are_forwarded(tmp_path, monkeypatch) -> None` | 475 |  |
| function | `test_unchanged_journal_skips_report_generation(monkeypatch) -> None` | 511 |  |
| function | `test_default_report_paths_are_project_relative() -> None` | 526 |  |
| function | `test_default_report_paths_do_not_depend_on_cwd(tmp_path, monkeypatch) -> None` | 537 |  |
| function | `test_successful_run_with_free_custom_lock(tmp_path, monkeypatch) -> None` | 567 |  |
| function | `test_occupied_lock_returns_two_without_side_effects(tmp_path, monkeypatch, capsys) -> None` | 578 |  |
| function | `test_run_succeeds_after_occupied_lock_is_released(tmp_path, monkeypatch) -> None` | 645 |  |
| function | `test_custom_lock_path_is_used(tmp_path, monkeypatch) -> None` | 664 |  |
| function | `test_default_lock_path_is_project_relative() -> None` | 674 |  |
| function | `test_default_lock_path_does_not_depend_on_cwd(tmp_path, monkeypatch) -> None` | 681 |  |
| function | `test_lock_creation_error_returns_one_with_path(tmp_path, capsys) -> None` | 709 |  |
| function | `test_lock_is_held_during_report_generation(tmp_path, monkeypatch) -> None` | 723 |  |
| function | `test_help_does_not_import_matplotlib_or_create_files(tmp_path) -> None` | 759 |  |
### [`tests/test_run_bybit_paper.py`](../tests/test_run_bybit_paper.py)

Строк: **122**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `StaticFeed` | 13 |  |
| method | `__init__(self, candles: tuple[Candle, ...]) -> None` | 14 |  |
| method | `get_candles(self) -> tuple[Candle, ...]` | 20 |  |
| class | `BuyThenHoldStrategy` | 24 |  |
| method | `generate_signal(self, candles, index)` | 25 |  |
| function | `test_run_once_processes_new_candles_and_saves_state(tmp_path: Path) -> None` | 32 |  |
| function | `test_run_once_executes_saved_pending_open(tmp_path: Path) -> None` | 77 |  |
### [`tests/test_run_periodic_reports.py`](../tests/test_run_periodic_reports.py)

Строк: **40**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| class | `Clock` | 7 |  |
| method | `now(zone)` | 9 |  |
| function | `test_periodic_does_not_overwrite_without_force(monkeypatch, tmp_path)` | 15 |  |
| function | `test_force_overwrites(monkeypatch, tmp_path)` | 26 |  |
| function | `test_templates_use_absolute_paths_and_shadow()` | 35 |  |
### [`tests/test_runtime.py`](../tests/test_runtime.py)

Строк: **41**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_settings() -> Settings` | 10 |  |
| function | `test_build_runtime_returns_runtime() -> None` | 21 |  |
| function | `test_runtime_uses_same_settings_instance() -> None` | 30 |  |
| function | `test_runtime_executor_mode_matches_execution_mode() -> None` | 38 |  |
### [`tests/test_runtime_health.py`](../tests/test_runtime_health.py)

Строк: **69**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_runtime(tmp_path: Path, *, candle: int \| None = None) -> dict` | 11 |  |
| function | `test_valid_state_is_ok_without_network(tmp_path)` | 27 |  |
| function | `test_missing_and_damaged_state_are_critical(tmp_path)` | 32 |  |
| function | `test_stale_candle_and_aggregation(tmp_path)` | 42 |  |
| function | `test_bybit_unavailable_is_captured(tmp_path)` | 48 |  |
| function | `test_incomplete_final_jsonl_is_safe(tmp_path)` | 55 |  |
| function | `test_invalid_balance_and_position_are_critical(tmp_path)` | 63 |  |
### [`tests/test_runtime_status.py`](../tests/test_runtime_status.py)

Строк: **20**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_cli_works_from_another_cwd_and_hides_secrets(tmp_path)` | 10 |  |
### [`tests/test_settings.py`](../tests/test_settings.py)

Строк: **66**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `clear_environment()` | 10 |  |
| function | `test_defaults()` | 36 |  |
| function | `test_environment_loading()` | 46 |  |
| function | `test_invalid_execution_mode()` | 62 |  |
### [`tests/test_shadow_decision_journal.py`](../tests/test_shadow_decision_journal.py)

Строк: **112**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `record(timestamp = 1, **changes)` | 12 |  |
| function | `test_append_and_read_jsonl(tmp_path) -> None` | 38 |  |
| function | `test_same_candle_is_not_appended_twice(tmp_path) -> None` | 46 |  |
| function | `test_deduplication_survives_restart(tmp_path) -> None` | 54 |  |
| function | `test_stale_or_corrupt_optional_state_recovers_from_jsonl(tmp_path) -> None` | 63 |  |
| function | `test_partial_last_line_is_ignored(tmp_path) -> None` | 76 |  |
| function | `test_corrupt_middle_line_is_rejected(tmp_path) -> None` | 91 |  |
| function | `test_invalid_utf8_last_line_is_repaired(tmp_path) -> None` | 102 |  |
### [`tests/test_shadow_report.py`](../tests/test_shadow_report.py)

Строк: **66**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_report_counts_decisions_and_reasons(tmp_path) -> None` | 8 |  |
| function | `test_blocked_reasons_sum_matches_blocked_entries(tmp_path) -> None` | 34 |  |
| function | `test_report_filters_and_saves_json(tmp_path) -> None` | 48 |  |
### [`tests/test_signal_generator.py`](../tests/test_signal_generator.py)

Строк: **138**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_market_ready_when_filter_allows() -> None` | 10 |  |
| function | `test_market_not_ready_when_filter_rejects() -> None` | 22 |  |
| class | `RejectAllFilter` | 34 |  |
| method | `allow_entry(self, regime: MarketRegime) -> bool` | 35 |  |
| function | `test_market_ready_uses_injected_filter() -> None` | 39 |  |
| function | `test_generate_returns_buy_when_market_is_ready() -> None` | 51 |  |
| function | `test_generate_returns_hold_when_market_is_not_ready() -> None` | 63 |  |
| function | `test_generate_returns_trade_signal_enum() -> None` | 75 |  |
| function | `test_generate_returns_sell_for_downtrend() -> None` | 89 |  |
| function | `test_generate_returns_hold_for_downtrend_with_high_volatility() -> None` | 101 |  |
| function | `test_generate_returns_hold_for_downtrend_with_low_confidence() -> None` | 113 |  |
| function | `test_generate_returns_sell_when_confidence_equals_minimum() -> None` | 127 |  |
### [`tests/test_signal_normalizer.py`](../tests/test_signal_normalizer.py)

Строк: **74**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_normalizes_legacy_signal(signal: Signal, expected_action: TradeAction) -> None` | 17 |  |
| function | `test_normalizes_trade_action(action: TradeAction) -> None` | 30 |  |
| function | `test_preserves_trade_signal_with_trade_action() -> None` | 38 |  |
| function | `test_preserves_trade_signal_settings() -> None` | 49 |  |
| function | `test_rejects_unknown_signal_type() -> None` | 69 |  |
### [`tests/test_stop_manager.py`](../tests/test_stop_manager.py)

Строк: **155**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_candle(*, open_price: float = 100, high: float = 110, low: float = 90, close: float = 105) -> Candle` | 12 |  |
| function | `test_long_stop_is_hit() -> None` | 29 |  |
| function | `test_long_stop_is_not_hit() -> None` | 37 |  |
| function | `test_short_stop_is_hit() -> None` | 45 |  |
| function | `test_short_stop_is_not_hit() -> None` | 53 |  |
| function | `test_long_stop_exit_uses_stop_price() -> None` | 61 |  |
| function | `test_long_gap_uses_open_price() -> None` | 69 |  |
| function | `test_short_stop_exit_uses_stop_price() -> None` | 82 |  |
| function | `test_short_gap_uses_open_price() -> None` | 90 |  |
| function | `test_long_trailing_stop_moves_up() -> None` | 103 |  |
| function | `test_long_trailing_stop_never_moves_down() -> None` | 112 |  |
| function | `test_short_trailing_stop_moves_down() -> None` | 121 |  |
| function | `test_short_trailing_stop_never_moves_up() -> None` | 130 |  |
| function | `test_rejects_invalid_trailing_percent(trailing_stop_percent: float) -> None` | 143 |  |
### [`tests/test_strategies.py`](../tests/test_strategies.py)

Строк: **90**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_data(prices: list[float]) -> pd.DataFrame` | 11 |  |
| function | `test_ma_cross_returns_valid_signals() -> None` | 15 |  |
| function | `test_ma_cross_invalid_periods() -> None` | 37 |  |
| function | `test_rsi_returns_valid_signals() -> None` | 48 |  |
| function | `test_rsi_invalid_levels() -> None` | 70 |  |
| function | `test_missing_close_column() -> None` | 81 |  |
### [`tests/test_trade_accounting.py`](../tests/test_trade_accounting.py)

Строк: **74**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_calculates_profitable_long_trade() -> None` | 10 |  |
| function | `test_calculates_losing_long_trade() -> None` | 26 |  |
| function | `test_calculates_trade_without_fees() -> None` | 38 |  |
| function | `test_rejects_invalid_values(field: str, value: Decimal, message: str) -> None` | 60 |  |
### [`tests/test_trade_analyzer.py`](../tests/test_trade_analyzer.py)

Строк: **282**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_candle(timestamp: int, *, open_price: float, high: float, low: float, close: float) -> Candle` | 8 |  |
| function | `make_trade(*, side: PositionSide, entry_timestamp: int, exit_timestamp: int, entry_price: float, exit_price: float) -> Trade` | 26 |  |
| function | `test_analyzes_long_trade_excursions() -> None` | 52 |  |
| function | `test_analyzes_short_trade_excursions() -> None` | 99 |  |
| function | `test_calculates_summary_for_multiple_trades() -> None` | 144 |  |
| function | `test_returns_empty_result_without_trades() -> None` | 205 |  |
| function | `test_rejects_missing_entry_timestamp() -> None` | 220 |  |
| function | `test_rejects_duplicate_candle_timestamps() -> None` | 249 |  |
### [`tests/test_trade_journal.py`](../tests/test_trade_journal.py)

Строк: **88**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_entry(*, record_id: str = 'record-1', net_pnl: Decimal = Decimal('9.79')) -> TradeJournalEntry` | 12 |  |
| function | `test_missing_journal_returns_empty_list(tmp_path) -> None` | 41 |  |
| function | `test_append_creates_parent_and_preserves_decimal_strings(tmp_path) -> None` | 47 |  |
| function | `test_two_entries_are_appended_without_overwrite(tmp_path) -> None` | 62 |  |
| function | `test_corrupt_jsonl_line_has_clear_line_number(tmp_path) -> None` | 80 |  |
### [`tests/test_trade_reporting.py`](../tests/test_trade_reporting.py)

Строк: **314**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `assert_png(path: Path) -> None` | 18 |  |
| function | `test_generates_text_and_png_from_nonempty_journal(tmp_path) -> None` | 24 |  |
| function | `test_empty_missing_journal_creates_reports_and_directories(tmp_path) -> None` | 41 |  |
| function | `test_existing_empty_journal_creates_nonempty_reports(tmp_path) -> None` | 62 |  |
| function | `test_custom_paths_are_returned_and_safely_overwritten(tmp_path) -> None` | 79 |  |
| function | `test_corrupt_journal_has_clear_error(tmp_path) -> None` | 107 |  |
| function | `test_text_write_error_identifies_text_report(tmp_path) -> None` | 122 |  |
| function | `test_png_write_error_identifies_png_report(tmp_path) -> None` | 138 |  |
| function | `test_uses_headless_backend() -> None` | 154 |  |
| function | `test_figure_is_closed_when_rendering_fails(tmp_path, monkeypatch) -> None` | 158 |  |
| function | `test_runtime_error_during_png_save_is_wrapped_and_cleans_temporary(tmp_path, monkeypatch) -> None` | 185 |  |
| function | `test_text_write_failure_after_temporary_creation_cleans_file(tmp_path, monkeypatch) -> None` | 207 |  |
| function | `test_replace_failure_preserves_target_and_cleans_temporary(tmp_path, monkeypatch) -> None` | 232 |  |
| function | `test_statistics_error_is_wrapped_with_journal_path(tmp_path, monkeypatch) -> None` | 257 |  |
| function | `test_statistics_are_calculated_once_and_remain_decimal(tmp_path, monkeypatch) -> None` | 282 |  |
### [`tests/test_trade_statistics.py`](../tests/test_trade_statistics.py)

Строк: **258**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_calculate_drawdown_curve(starting_balance: str, equity_curve: list[str], expected: tuple[str, ...]) -> None` | 32 |  |
| function | `entry(net_pnl: str, balance: str, *, record_id: str = 'trade', gross_pnl: str \| None = None, fee: str = '0', opened_at: str = '2026-07-27T10:00:00+00:00', closed_at: str = '2026-07-27T11:00:00+00:00')` | 43 |  |
| function | `test_empty_statistics_have_consistent_zero_values() -> None` | 64 |  |
| function | `test_classifies_single_trade(net_pnl: str, winning: int, losing: int, breakeven: int) -> None` | 99 |  |
| function | `test_calculates_mixed_pnl_fees_averages_and_factors() -> None` | 112 |  |
| function | `test_profit_factor_without_losses_is_undefined() -> None` | 138 |  |
| function | `test_no_winning_trades_has_zero_profit_factor() -> None` | 147 |  |
| function | `test_equity_drawdown_and_recovery_use_journal_order() -> None` | 157 |  |
| function | `test_no_drawdown_has_undefined_recovery_factor() -> None` | 181 |  |
| function | `test_zero_peak_skips_percentage_until_positive_peak() -> None` | 191 |  |
| function | `test_streaks_and_breakeven_reset() -> None` | 201 |  |
| function | `test_holding_time_statistics() -> None` | 219 |  |
| function | `test_invalid_timestamp_has_clear_field_name(field_name: str) -> None` | 241 |  |
| function | `test_partial_closes_are_separate_records() -> None` | 248 |  |
### [`tests/test_trading_controller.py`](../tests/test_trading_controller.py)

Строк: **702**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `build_controller(state: TradingControllerState \| None = None) -> TradingController` | 23 |  |
| function | `test_opens_long_position() -> None` | 38 |  |
| function | `test_does_not_open_second_long_position() -> None` | 54 |  |
| function | `test_closes_entire_long_position() -> None` | 75 |  |
| function | `test_does_not_close_missing_position() -> None` | 98 |  |
| function | `test_hold_does_not_execute_order() -> None` | 114 |  |
| function | `test_rejects_invalid_request(entry_quantity: Decimal, price: Decimal, message: str) -> None` | 150 |  |
| function | `test_rejects_negative_state_quantity() -> None` | 166 |  |
| function | `test_rejects_negative_fee_rate() -> None` | 176 |  |
| class | `FakeStateStore` | 187 |  |
| method | `__init__(self, state: TradingControllerState) -> None` | 188 |  |
| method | `load(self) -> TradingControllerState` | 197 |  |
| method | `save(self, state: TradingControllerState) -> None` | 200 |  |
| function | `test_loads_state_from_store() -> None` | 207 |  |
| function | `test_saves_state_after_opening_position() -> None` | 229 |  |
| function | `test_saves_state_after_closing_position() -> None` | 257 |  |
| function | `test_does_not_save_state_for_hold() -> None` | 287 |  |
| function | `test_rejects_state_and_store_together() -> None` | 311 |  |
| function | `test_open_position_saves_entry_price() -> None` | 334 |  |
| function | `test_open_position_saves_stop_loss() -> None` | 348 |  |
| function | `test_close_position_clears_entry_data() -> None` | 368 |  |
| function | `test_profitable_close_updates_accounting() -> None` | 389 |  |
| function | `test_losing_close_updates_accounting() -> None` | 416 |  |
| function | `test_does_not_open_with_insufficient_balance() -> None` | 438 |  |
| class | `FixedRuntime` | 455 |  |
| method | `__init__(self, result: ExecutionResult) -> None` | 456 |  |
| method | `process_signal(self, request)` | 459 |  |
| class | `MemoryJournal` | 463 |  |
| method | `__init__(self) -> None` | 464 |  |
| method | `append(self, entry: TradeJournalEntry) -> None` | 467 |  |
| function | `test_partial_close_keeps_position_and_entry_fee() -> None` | 471 |  |
| function | `test_profitable_close_is_written_to_journal() -> None` | 508 |  |
| function | `test_losing_close_is_written_to_journal() -> None` | 548 |  |
| function | `test_partial_close_writes_remaining_quantity() -> None` | 570 |  |
| function | `test_hold_does_not_write_journal() -> None` | 610 |  |
| function | `test_rejected_close_does_not_write_journal() -> None` | 627 |  |
| function | `test_rejected_execution_does_not_change_state() -> None` | 658 |  |
| function | `test_rejects_long_stop_above_entry_price() -> None` | 685 |  |
### [`tests/test_trading_controller_store.py`](../tests/test_trading_controller_store.py)

Строк: **254**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_missing_file_returns_empty_state(tmp_path) -> None` | 12 |  |
| function | `test_saves_and_loads_state(tmp_path) -> None` | 25 |  |
| function | `test_decimal_is_saved_as_string(tmp_path) -> None` | 46 |  |
| function | `test_creates_parent_directory(tmp_path) -> None` | 74 |  |
| function | `test_rejects_invalid_json(tmp_path) -> None` | 90 |  |
| function | `test_rejects_non_object_json(tmp_path) -> None` | 108 |  |
| function | `test_rejects_invalid_position_quantity(tmp_path, value) -> None` | 137 |  |
| function | `test_rejects_negative_position_quantity(tmp_path) -> None` | 158 |  |
| function | `test_overwrites_previous_state(tmp_path) -> None` | 181 |  |
| function | `test_saves_and_loads_entry_price_and_stop_loss(tmp_path) -> None` | 205 |  |
| function | `test_loads_legacy_state_without_entry_data(tmp_path) -> None` | 236 |  |
### [`tests/test_trading_filter.py`](../tests/test_trading_filter.py)

Строк: **98**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_allow_uptrend_low_volatility() -> None` | 9 |  |
| function | `test_allow_uptrend_normal_volatility() -> None` | 19 |  |
| function | `test_reject_high_volatility() -> None` | 29 |  |
| function | `test_reject_range_market() -> None` | 39 |  |
| function | `test_reject_downtrend() -> None` | 49 |  |
| function | `test_reject_low_confidence() -> None` | 59 |  |
| function | `test_allow_confidence_equal_to_minimum() -> None` | 73 |  |
| function | `test_reject_negative_minimum_confidence() -> None` | 87 |  |
| function | `test_reject_minimum_confidence_above_one() -> None` | 94 |  |
### [`tests/test_trading_runtime.py`](../tests/test_trading_runtime.py)

Строк: **96**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `build_request(signal: Signal \| TradeSignal \| TradeAction) -> RuntimeRequest` | 15 |  |
| function | `test_runtime_executes_buy_signal() -> None` | 27 |  |
| function | `test_runtime_executes_sell_signal() -> None` | 42 |  |
| function | `test_runtime_returns_none_for_hold_signal() -> None` | 56 |  |
| function | `test_runtime_accepts_trade_action() -> None` | 68 |  |
| function | `test_runtime_accepts_trade_signal() -> None` | 81 |  |
### [`tests/test_trading_types.py`](../tests/test_trading_types.py)

Строк: **22**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `test_position_side_values() -> None` | 7 |  |
| function | `test_trade_action_values() -> None` | 12 |  |
| function | `test_enum_values_can_be_serialized() -> None` | 20 |  |
### [`tests/test_trend_detector.py`](../tests/test_trend_detector.py)

Строк: **245**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_candles(*prices: float) -> list[Candle]` | 10 |  |
| function | `test_detects_uptrend() -> None` | 26 |  |
| function | `test_detects_downtrend() -> None` | 53 |  |
| function | `test_detects_sideways_market() -> None` | 80 |  |
| function | `test_returns_sideways_before_warmup() -> None` | 106 |  |
| function | `test_small_ema_separation_is_sideways() -> None` | 129 |  |
| function | `test_detector_can_be_reused_from_start() -> None` | 154 |  |
| function | `test_rejects_invalid_configuration(fast_period, slow_period, slope_lookback, min_separation_percent) -> None` | 213 |  |
| function | `test_rejects_invalid_index() -> None` | 230 |  |
### [`tests/test_trend_pullback_strategy.py`](../tests/test_trend_pullback_strategy.py)

Строк: **290**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `make_candles(*prices: float) -> list[Candle]` | 10 |  |
| function | `make_strategy() -> TrendPullbackStrategy` | 26 |  |
| function | `test_returns_hold_during_warmup() -> None` | 38 |  |
| function | `test_opens_long_after_pullback_in_uptrend() -> None` | 53 |  |
| function | `test_opens_short_after_rebound_in_downtrend() -> None` | 74 |  |
| function | `test_does_not_open_long_in_downtrend() -> None` | 95 |  |
| function | `test_does_not_open_short_in_uptrend() -> None` | 116 |  |
| function | `test_returns_hold_without_pullback_cross() -> None` | 137 |  |
| function | `test_strategy_can_be_reused() -> None` | 158 |  |
| function | `test_rejects_invalid_pullback_period() -> None` | 197 |  |
| function | `test_rejects_invalid_index() -> None` | 204 |  |
| function | `test_adx_filter_blocks_entry_when_threshold_is_too_high() -> None` | 215 |  |
| function | `test_rejects_invalid_adx_configuration(adx_period, minimum_adx) -> None` | 252 |  |
| function | `test_short_entry_can_be_disabled() -> None` | 263 |  |
### [`tests/test_walk_forward_regime_filter.py`](../tests/test_walk_forward_regime_filter.py)

Строк: **774**

| Тип | Определение | Строка | Описание |
|---|---|---:|---|
| function | `market_data(start: str = '2020-01-01', periods: int = 1100, freq: str = 'D') -> pd.DataFrame` | 43 |  |
| function | `small_config(**changes) -> ResearchConfig` | 65 |  |
| function | `test_build_windows_has_half_open_boundaries_and_exact_step() -> None` | 78 |  |
| function | `test_windows_preserve_timezone_and_drop_incomplete_tail() -> None` | 107 |  |
| function | `test_warmup_updates_strategy_but_suppresses_train_signals() -> None` | 129 |  |
| function | `test_train_never_trades_or_transfers_position() -> None` | 150 |  |
| function | `test_every_window_has_independent_balance_and_state() -> None` | 183 |  |
| function | `test_every_window_builds_fresh_research_objects(monkeypatch) -> None` | 194 |  |
| function | `test_fingerprint_and_cache_distinguish_ohlc_and_windows() -> None` | 254 |  |
| function | `test_detector_only_equals_baseline_and_never_blocks() -> None` | 280 |  |
| function | `test_detector_only_full_backtest_result_equals_baseline() -> None` | 304 |  |
| function | `test_filtered_preserves_exit_and_stop_loss() -> None` | 340 |  |
| function | `test_future_change_cannot_change_past_decisions_or_trades() -> None` | 368 |  |
| function | `test_blocked_reason_sum_is_exact() -> None` | 414 |  |
| function | `test_cached_and_plain_detector_are_equivalent() -> None` | 438 |  |
| function | `test_invalid_configuration_is_rejected(config) -> None` | 490 |  |
| function | `test_insufficient_data_is_clear() -> None` | 495 |  |
| function | `test_json_and_csv_are_atomic_and_deterministic(tmp_path) -> None` | 500 |  |
| function | `test_atomic_output_failure_preserves_existing_file(tmp_path, monkeypatch, writer) -> None` | 540 |  |
| function | `test_cli_works_from_another_cwd(tmp_path) -> None` | 566 |  |
| function | `test_cli_rejects_invalid_arguments(arguments, message, capsys) -> None` | 606 |  |
| function | `test_verdict_uses_fixed_criteria_and_few_windows_inconclusive() -> None` | 614 |  |
| function | `test_analysis_contains_summary_comparison_compounding_and_verdict() -> None` | 634 |  |
| function | `test_compounding_multiplies_mixed_window_returns() -> None` | 668 |  |
| function | `test_summary_calculates_all_required_aggregates() -> None` | 716 |  |
| function | `test_profit_factor_zero_and_infinity_are_preserved() -> None` | 758 |  |

## Правила использования

Перед добавлением нового класса или модуля:

1. Найти похожую функциональность в этой карте.
2. Выполнить поиск по репозиторию.
3. Расширять существующий модуль, если он уже решает ту же задачу.
4. После изменений обновить карту.
