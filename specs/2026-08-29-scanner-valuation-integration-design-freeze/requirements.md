# Phase 14A — Scanner Valuation Integration Design Freeze — Requirements

## Status and authority

- **Date:** 2026-08-29.
- **Branch:** `feature/scanner-valuation-integration`.
- **Verified baseline:** `24c95c029f583d5cc0b0a67986e48c06d0ef7957` (post-R0-D; PR #3 merge on `main`; canonical main tip after the R0-D completion documentation checkpoint). Upstream and local both at this SHA, `ahead/behind = 0 0`.
- **Phase type:** design freeze and repository / boundary audit only.
- **Implementation status:** no scanner, valuation, engine, EV/risk, SteamDT, BUFF, metadata, identity, intrinsic, or cache code is being modified in Phase 14A.
- **Protected Core status:** unchanged. Phase 14A freezes the design for any future implementation that touches `app/services/valuation_service.py`, `app/services/live_recipe_valuation.py`, `app/services/scanner_orchestrator.py`, `app/services/scanner_recipe_composition.py`, or any Phase 12D cache module. Any such future implementation requires an explicit reviewed migration authorization.
- **Frozen contracts:** `D-ENUM-001..004`, `D-CACHE-001`, `D-SCANNER-001`, `D-VALIDATION-001`, `D-MEMORY-001`, `D-ADAPTER-003`, `D-ADAPTER-004` are preserved unchanged. `D-CACHE-001` itself remains **Active** (the cache is still not implemented at runtime); Phase 14A only freezes the design that any future implementation must satisfy.
- **Safety:** no scheduler, no daemon, no market execution, no login, no Cookie, no browser automation, no risk-control bypass, no invented BUFF endpoint / signature / field mapping, no fallback valuation, no probability renormalization.

This document follows `specs/mission.md`, `specs/tech-stack.md`, the current authoritative AI-context set, the current `docs/ARCHITECTURE.md`, and the exact current code. It is a design freeze; it does not authorize runtime change.

## Goal

Freeze the exact semantics, audit boundaries, and implementation sequence for integrating the existing Phase 12D cache stack (`PriceCache`, `InMemoryPriceCache`, `RedisPriceCache`, `SteamDTCachedPriceResolver`, `SteamDTPriceRefreshService`, `SteamDTRefreshPlanner`, `SteamDTRefreshExecutor`, `scripts/steamdt_refresh_integration.py`) into the live scanner valuation path, **and** for closing `D-CACHE-001` (run-level cross-recipe exact-price reuse), in a way that:

- preserves the existing strict SteamDT-BUFF output valuation contract (positive finite sell price, exact case-sensitive `BUFF` platform, no bid fallback, no second-platform fallback, no metadata-zero reuse, no probability renormalization, no risk-threshold weakening);
- preserves the existing atomic cumulative valuation-request cap (`max_valuation_requests_per_run ∈ [1, 60]`, default CLI 5) under a clearly redefined accounting model that distinguishes **NEW LIVE SteamDT demand** from **run-reuse hits** and **persistent-cache hits**;
- preserves bounded multi-recipe enumeration order (`P0..P9` baseline first, deterministic radius-one substitutions, cross-candidate listing reuse allowed) and structural recipe processing order;
- keeps the cache seam scanner-owned (a run-scoped valuation session), keeps the trade-up engine, EV, and risk unaware of cache mechanics, and does not turn `ValuationService` into a generic global cache manager;
- preserves every existing fail-closed invariant (`PriceCacheBackendError`, `PriceCacheCodecError`, `MemoryError`, valuation-missing price, secondary platform fallback refused);
- introduces no scheduler, no background work, no Redis requirement for the default one-shot CLI, and no fund-side, browser-automation, login, cookie, or risk-control change.

## Current scanner valuation path (verified)

The production scanner valuation chain is:

```text
LiveScannerOrchestrator.run_once
  -> for each returned recipe in structural composition order:
       _unique_output_names(selection) -> requested_names
       preflight: if valuation_requests_used + len(requested_names) > max_valuation_requests_per_run:
                     build_blocked_evaluation(VALUATION_REQUEST_CAP_EXCEEDED); increment blocked counter; continue
       valuation_requests_used += len(requested_names)
       _evaluate_selection
         -> ValuationService.value_tradeup_results(recipe.tradeup_results)
              -> price_provider.get_prices(output_names)
                   -> SteamDTBuffPriceProvider.get_prices  (per-call dedupe only)
                        -> get_steamdt_market_data(client, name)
                             -> client.get_price_single_candidates(name)
```

Verified file locations (2026-08-29 audit):

- Atomic preflight block at `app/services/scanner_orchestrator.py:417-439` — the ONLY place `valuation_requests_used` is mutated.
- `valuation_requests_blocked` records the full logical demand of a blocked recipe (`valuation_requests_used` is NOT incremented).
- `_evaluate_selection` calls `ValuationService.value_tradeup_results` at `app/services/scanner_orchestrator.py:544-546`.
- `ValuationService.value_tradeup_results` calls `self.price_provider.get_prices(output_names)` directly at `app/services/valuation_service.py:78` with **no cache lookup, no run-scope memoization, and no cache writeback**.
- `SteamDTBuffPriceProvider.get_prices` (`app/services/steamdt_buff_price_provider.py:39-73`) deduplicates only within ONE `get_prices` call (via `_clean_market_hash_names` at `:77-88`); it has no cross-call memo.
- A grep across `scripts/run_live_scan_once.py`, `app/services/scanner_orchestrator.py`, `app/services/valuation_service.py`, `app/services/steamdt_buff_price_provider.py`, `app/services/steamdt_buff_price_policy.py`, `app/services/steamdt_market_data.py`, `app/services/price_provider.py`, `app/services/recipe_solver.py`, `app/services/scanner_recipe_composition.py` returns ZERO matches for `price_cache`, `InMemoryPriceCache`, `RedisPriceCache`, `SteamDTCachedPriceResolver`, `PriceCacheKey`, `PriceCacheRuntime`. None of the four files in the scanner-to-price chain import any Phase 12D cache module.
- `scripts/steamdt_refresh_integration.py` is the only existing consumer of the Phase 12D stack and it is a manual CLI only.

## Current Phase 12D cache stack (verified)

- `app/services/price_cache.py` — schema-versioned `PriceCacheKey(market_hash_name, game="cs2", currency="CNY", source="steamdt", snapshot_type="platform_prices", schema_version=1)`; deterministic sha256 key digest; `CachedPriceSnapshot(candidates: tuple[NormalizedPriceCandidate, ...], observed_at, stored_at, policy)`; `PriceCacheReadPolicy = {FRESH_ONLY, ALLOW_STALE, ALLOW_STALE_GRACE}`; `PriceCache` Protocol; `InMemoryPriceCache` (default backend, no Redis required).
- `app/services/price_cache_codec.py` — strict deterministic version-1 Redis hash codec; `PriceCacheCodecError`.
- `app/services/redis_price_cache.py` — Redis backend; fail-closed `PriceCacheBackendError`; namespace-scoped keys; Lua-atomic PUT/GET/PURGE.
- `app/services/price_cache_factory.py` — `create_steamdt_price_cache_runtime`; explicit backend selection `inmemory | redis`; rejects unsupported backend strings.
- `app/services/steamdt_price_cache_adapter.py` — `SteamDTPlatformPrice ↔ NormalizedPriceCandidate / CachedPriceSnapshot`; typed `SteamDTPriceCacheAdapterError`; no I/O.
- `app/services/steamdt_cached_price_resolver.py` — read-only; one `cache.get()` + caller-supplied selector rerun against stored candidates; re-raises `PriceCacheBackendError` and `PriceCacheCodecError` by identity.
- `app/services/steamdt_price_snapshot_source.py` — typed single-item fetch contract.
- `app/services/steamdt_price_refresh_service.py` — fetch-once + write-once; propagates `PriceCacheBackendError` / `PriceCacheCodecError` / `SteamDTPriceCacheAdapterError` by identity.
- `app/services/steamdt_refresh_planner.py` — pure CPU dedup + chunk planner.
- `app/services/steamdt_refresh_executor.py` — bounded-concurrency executor.
- `scripts/steamdt_refresh_integration.py` — manual one-shot end-to-end CLI; default `InMemoryPriceCache`; live mode requires `STEAMDT_RUN_REFRESH_INTEGRATION=true` plus `STEAMDT_API_KEY`.

Cache states and `FRESH_ONLY` semantics:

```text
FRESH              hit=True, snapshot=StoredSnapshot, policy_blocked=False, needs_refresh=False
STALE              hit=False, snapshot=None,    policy_blocked=True,  needs_refresh=True   (under FRESH_ONLY)
STALE_GRACE        hit=False, snapshot=None,    policy_blocked=True,  needs_refresh=True   (under FRESH_ONLY)
EXPIRED            hit=False, snapshot=None,    policy_blocked=False, needs_refresh=True   (any policy)
MISS               hit=False, snapshot=None,    policy_blocked=False, needs_refresh=True
SELECTED           a hit whose selector rerun produced a strict quote (the only "usable" outcome)
SELECTION_FAILURE  a hit whose selector rerun produced no strict quote (no fallback; terminal)
```

BUFF-vs-other selection is applied at **read** time via `select_steamdt_price_quote` against the stored candidates; the cache stores the full ordered candidate list, not a pre-selected record. The cached value's `source` is `"steamdt"`; the BUFF preference and "positive finite sell price" guarantee are properties of the selector at read time, not of the stored value.

There is no env-driven TTL today. TTL is a per-call `PriceCachePolicy(fresh_ttl=...)` constructed at each call site. Default script value: `fresh_ttl=timedelta(minutes=5)`. `STEAMDT_PRICE_CACHE_BACKEND` and `STEAMDT_PRICE_CACHE_REDIS_NAMESPACE` are defined in `app/config.py:77-78`; `inmemory` is the explicit default.

## Confirmed missing seam

The single seam Phase 14 must integrate is the call to `self.price_provider.get_prices(output_names)` inside `ValuationService.value_tradeup_results` at `app/services/valuation_service.py:78`. No Phase 12D cache lookup, no run-scope memoization, and no cache writeback currently exists in that path.

## Non-goals

- No live SteamDT, BUFF, Redis, or Discord integration behavior change.
- No invented BUFF endpoint, signature, parameter, or field mapping.
- No fallback valuation, no bid substitution, no metadata-zero reuse, no probability renormalization.
- No risk-threshold change, no EV / ROI / worst-case loss / profit-probability formula change.
- No scheduler, no daemon, no background refresh worker, no periodic cron, no Discord webhook.
- No production Redis requirement; default one-shot CLI must continue to work with `STEAMDT_PRICE_CACHE_BACKEND=inmemory`.
- No migration of `D-CACHE-001` semantics. Phase 14A only freezes the design that any future implementation must satisfy.
- No automatic expansion of `max_valuation_requests_per_run`. The cap remains a separately configurable parameter.
- No renaming, retagging, deleting, force-updating, or pushing the local-only `v1-dry-run-baseline` tag.
- No change of canonical `main`, no PR, no merge.

## In-scope design freeze (summary; full detail in `plan.md`)

1. **Scanner-owned run-scoped valuation session** boundary (a new seam type), wrapping the current per-recipe valuation call. The seam is the only place where run-scope exact-name reuse, Phase12D cache preflight, and NEW LIVE SteamDT demand accounting live.
2. **Exact-name reuse key** = the canonical `output_market_hash_name` string itself. No fuzzy matching, no case folding, no aliases, no `goods_id` substitution, no `platformItemId` substitution, no hidden normalization layer. The current canonicalization is the Steam community market canonical name used by `TradeUpResult.estimated_market_hash_name` / `OutputCandidate.market_hash_name` throughout the engine path.
3. **Run-scoped memo** of exact-name outcomes within a single `run_once()` call. Successes and terminal failures are reused. The memo dies at end of `run_once`.
4. **Initial persistent-cache policy** is `PriceCacheReadPolicy.FRESH_ONLY` (only `FRESH + SELECTED` is a usable cache hit; all other states fall through to live). Stale, stale-grace, expired, and policy-blocked under FRESH_ONLY are not usable; only `FRESH + SELECTED` consumes zero live-provider budget. Cache backend / codec exceptions are explicit fail-closed. No persistent negative caching in Phase 14B or 14C.
5. **No partial valuation**. Any missing, failed, blocked, or invalid exact-name resolution yields `valuation_completed=False`, no metrics, no risk, no opportunity. Never drop outputs, renormalize probabilities, substitute another platform, or zero-fill.
6. **`max_valuation_requests_per_run` redefined** as the count of NEW LIVE SteamDT provider demand / attempts within the run, exclusive of run-reuse hits and `FRESH + SELECTED` cache hits. Atomic preflight: count NEW LIVE demand BEFORE any provider call; if demand exceeds remaining live budget, the entire recipe is blocked and zero live calls are issued for it.
7. **Counters**: prefer additive migration (Option A) — preserve legacy `valuation_requests_attempted / succeeded / failed / blocked` semantics and add the new discriminators (`cache_hits_fresh_selected`, `cache_misses`, `cache_policy_blocked`, `cache_expired`, `cache_selection_failures`, `live_demand`, `live_attempted`, `live_succeeded`, `live_failed`, `live_atomically_blocked`, `run_reuse_hits`, `run_reuse_failures`). Option B (explicit semantics migration with full test/doc migration) is the fallback if Option A surfaces ambiguity.
8. **TTL / config ownership**: no env-driven TTL is invented in Phase 14A. Future scanner-side `PriceCachePolicy` config must live in a new `PriceCachePolicyConfig` Pydantic DTO next to `LiveScanSettings`, exposed in `.env.example`, with identical semantics for `InMemoryPriceCache` and `RedisPriceCache`. No TTL number is invented in 14A.
9. **Backend composition**: Phase 14B and 14C must both work with `InMemoryPriceCache` without Redis; Redis is an opt-in explicit backend; no Redis is required for the default one-shot CLI.
10. **14B / 14C / 14D split** — see `plan.md` and `validation.md`.

## Acceptance criteria

Phase 14A is **complete** when, and only when, all of the following hold simultaneously:

- The three spec files (`requirements.md`, `plan.md`, `validation.md`) exist under `specs/2026-08-29-scanner-valuation-integration-design-freeze/` and pass `git diff --check`.
- `git diff --name-only` shows that **no production `.py` file has been modified**.
- The default pytest suite (offline-safe), `ruff check .`, and `mypy app` all pass locally with no weakening of any pre-existing test.
- `ScannerRunStageCounters` semantics, `valuation_service.py`, `live_recipe_valuation.py`, `steamdt_buff_price_provider.py`, `recipe_solver.py`, `scanner_recipe_composition.py`, `price_cache.py`, `redis_price_cache.py`, `steamdt_cached_price_resolver.py`, and every other Phase 12D cache module are **byte-identical** to `24c95c029f583d5cc0b0a67986e48c06d0ef7957`.
- The design freeze has been documented in `docs/ai-context/DECISION_LOG.md`, `docs/ai-context/PROJECT_CONTEXT.md`, `docs/ai-context/DEVELOPMENT_HANDOFF.md`, `docs/ai-context/ARCHITECTURE_STATE.md`, `specs/roadmap.md`, and `CLAUDE.md` per the existing pointer convention.
- All six public surfaces that currently say "run-level cross-recipe exact-price reuse = NOT IMPLEMENTED" still say so (the design freeze does not promote the feature).
- `D-CACHE-001` is **Active** (the cache is still not implemented at runtime); Phase 14A only freezes the design.
- The feature branch `feature/scanner-valuation-integration` has been pushed to `origin`. `main` is unchanged. The local-only `v1-dry-run-baseline` tag is preserved at `32ab47c5b66a0f331457e69f1515e5e9bb2a37e1`. The two excluded research JSONs remain untouched.
