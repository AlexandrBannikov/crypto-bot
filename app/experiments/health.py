from __future__ import annotations
from decimal import Decimal
import math
from .framework import CanonicalJsonl
from .registry import ExperimentRegistry

def research_health(registry: ExperimentRegistry) -> dict:
    errors=[]; last=[]; closed=0; running=0
    for spec in registry.all():
        if not spec.enabled: continue
        try:
            decisions=CanonicalJsonl(spec.decision_path,()).rows(); trades=CanonicalJsonl(spec.journal_path,()).rows(); equity=CanonicalJsonl(spec.equity_path,()).rows()
            keys=[(r.get("experiment_id"),r.get("strategy_version"),r.get("candle_close_timestamp")) for r in decisions]
            if len(keys)!=len(set(keys)): raise ValueError("duplicate decisions")
            for row in (*decisions,*trades,*equity):
                if row.get("experiment_id")!=spec.experiment_id: raise ValueError("cross-experiment collision")
            for row in equity:
                values=[Decimal(str(row[k])) for k in ("cash","position_market_value","equity")]
                if any(not v.is_finite() for v in values): raise ValueError("NaN/Infinity")
                if abs(values[0]+values[1]-values[2])>Decimal("0.000001"): raise ValueError("balance/equity inconsistency")
            closed+=len(trades); running+=bool(equity)
            if decisions:last.append(max(int(r["candle_close_timestamp"]) for r in decisions))
        except Exception as exc: errors.append({"experiment_id":spec.experiment_id,"error":type(exc).__name__})
    return {"status":"WARNING" if errors else "OK","configured":len(registry.all()),"enabled":sum(s.enabled for s in registry.all()),"running":running,"errors":errors,"last_cycle":max(last) if last else None,"total_closed_trades":closed}
