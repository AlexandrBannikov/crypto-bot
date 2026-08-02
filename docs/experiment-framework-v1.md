# Experiment Framework v1

All contours are isolated paper research consumers of one closed-candle snapshot. Production, Candidate, scored shadow and threshold-60 paths are never referenced. Runtime defaults to disabled.

Active rollout order: `control_baseline_v1`, then `relaxed_signal_v1`. `scored_allocation_v1` is registered but disabled pending execution validation. Future slots: lifecycle, adaptive pullback, regime-aware, ML, multi-asset and optimizers; none is implemented or active.

Relaxed's only change is the entry gate: a bullish EMA20/EMA50 alignment may enter instead of requiring the crossover event. Exit, 2% stop, 1% risk, 100% capital cap, 0.1% commission and no leverage are unchanged.

Review after 50 closed trades or 60 days, with at least 30 market episodes. No result promotes anything automatically.
