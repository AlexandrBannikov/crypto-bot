"""Canonical versions shared by live-like and replay execution paths."""

STRATEGY_LOGIC_VERSION = "strategy_logic_v2_causal"
FEATURE_VERSION = "scored_features_v1"
EXECUTION_POLICY_VERSION = "next_candle_open_v1"
LEDGER_SCHEMA_VERSION = "ledger_v2"


def version_fields() -> dict[str, str]:
    return {
        "strategy_logic_version": STRATEGY_LOGIC_VERSION,
        "feature_version": FEATURE_VERSION,
        "execution_policy_version": EXECUTION_POLICY_VERSION,
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
    }
