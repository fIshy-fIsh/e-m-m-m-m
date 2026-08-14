# Phase 13A Step 2K — Plan

1. Freeze the manual smoke contract: inherited-process opt-in and secret, integer duration, one bounded session, one current snapshot, fixed safe output, and exact exit behavior.
2. Add `scripts/run_live_steamapis_offer_smoke.py` by composing the existing SteamApis WebSocket client, offer-session runner, and in-memory offer pool without changing or duplicating them.
3. Add focused offline tests for CLI guards, secret safety, timeout/cancellation, one-session/one-snapshot behavior, current Added/Updated counts, and a real-client/fake-connector integration.
4. Document the manual command, smoke-only retention settings, deliberate exclusion of Step 2J/metadata, and unchanged SteamDT blocker.
5. Run all focused and full offline validation, static/scope audits, and three existing dry-runs.
6. Only after offline validation, run the real smoke at most once if the current inherited environment already contains the exact opt-in and a nonblank key; otherwise skip without prompting or searching.
7. Stop with all Step 2K changes unstaged, uncommitted, and unpushed. Do not resume Step 2G or begin Step 2L.
