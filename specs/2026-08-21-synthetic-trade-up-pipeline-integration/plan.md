# Phase 13H-0 — Synthetic Trade-up Pipeline Integration — Plan

1. Document a synthetic-only pipeline boundary in a new spec trilogy.
2. Add a minimal domain adapter that converts `TradeUpInputCandidate` to existing engine `InputItem` via a synthetic metadata store.
3. Add thin synthetic resolver implementation used only for offline tests.
4. Add deterministic unit tests that prove the full pipeline (candidates → InputItem → trade-up engine → EV → risk) runs with synthetic data.
5. Record the integration in the AI context handoff.
6. No live provider, no identity resolver, no BUFF endpoint, no SteamApis, no solver/valuation/risk modification.
