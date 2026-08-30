# Phase 14A — Scanner Valuation Integration Design Freeze — Requirements

## Status and authority

- **Date:** 2026-08-29 (initial design freeze); revised 2026-08-29 under Phase 14A-R1 design coherence correction.
- **Branch:** `feature/scanner-valuation-integration`.
- **Verified baseline:** `24c95c029f583d5cc0b0a67986e48c06d0ef7957` (post-R0-D; PR #3 merge on `main`; canonical main tip after the R0-D completion documentation checkpoint). Upstream and local both at this SHA, `ahead/behind = 0 0`.
- **Phase type:** design freeze and repository / boundary audit only.
- **Implementation status:** no scanner, valuation, engine, EV/risk, SteamDT, BUFF, metadata, identity, intrinsic, or cache code is being modified in Phase 14A or in Phase 14A-R1.
- **Protected Core status:** unchanged. Phase 14A-R1 freezes the design for any future implementation that touches `app/services/valuation_service.py`, `app/services/live_recipe_valuation.py`, `app/services/scanner_orchestrator.py`, `app/services/scanner_recipe_composition.py`, or any Phase 12D cache module. Any such future implementation requires an explicit reviewed migration authorization.
- **Frozen contracts:** `D-ENUM-001..004`, `D-CACHE-001..004`, `D-BUDGET-001`, `D-ACCOUNTING-001`, `D-SCANNER-001`, `D-VALIDATION-001`, `D-MEMORY-001`, `D-ADAPTER-003`, `D-ADAPTER-004` are preserved unchanged. `D-CACHE-001` remains **`Active`** after Phase 14A-R1; the runtime cache is still not implemented. `D-PHASE14A-R1-COHERENCE` records the design coherence corrections.
- **Safety:** no scheduler, no daemon, no market execution, no login, no Cookie, no browser automation, no risk-control bypass, no invented BUFF endpoint / signature / field mapping, no fallback valuation, no probability renormalization.

This document follows `specs/mission.md`, `specs/tech-stack.md`, the current authoritative AI-context set, the current `docs/ARCHITECTURE.md`, and the exact current code. It is a design freeze; it does not authorize runtime change.

## Goal

Freeze the exact semantics, audit boundaries, and implementation sequence for integrating the existing Phase 12D cache stack (`PriceCache`, `InMemoryPriceCache`, `RedisPriceCache`, `SteamDTCachedPriceResolver`, `SteamDTPriceRefreshService`, `SteamDTRefreshPlanner`, `SteamDTRefreshExecutor`, `scripts/steamdt_refresh_integration.py`) into the live scanner valuation path, **and** for closing `D-CACHE-001` (run-level cross-recipe exact-price reuse), in a way that:

- preserves the existing strict SteamDT-BUFF output valuation contract (positive finite sell price, exact case-sensitive `BUFF` platform, exactly one BUFF record, no bid fallback, no second-platform fallback, no metadata-zero reuse, no probability renormalization, no risk-threshold weakening);
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
       atomic preflight: if valuation_requests_used + len(requested_names) > max_valuation_requests_per_run:
                     build_blocked_evaluation(VALUATION_REQUEST_CAP_EXCEEDED); valuation_requests_blocked += requested_count; recipes_valuation_failed += 1; recipes_rejected += 1; continue
       valuation_requests_used += requested_count
       valuation_requests_attempted += requested_count   (only for admitted recipes)
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
- `valuation_requests_attempted` is incremented at `app/services/scanner_orchestrator.py:442-444` for ADMITTED recipes only.
- `_evaluate_selection` calls `ValuationService.value_tradeup_results` at `app/services/scanner_orchestrator.py:544-546`.
- `ValuationService.value_tradeup_results` calls `self.price_provider.get_prices(output_names)` directly at `app/services/valuation_service.py:71-78` with **no cache lookup, no run-scope memoization, and no cache writeback**.
- `SteamDTBuffPriceProvider.get_prices` (`app/services/steamdt_buff_price_provider.py:39-73`) deduplicates only within ONE `get_prices` call (via `_clean_market_hash_names` at `:77-88`); it has no cross-call memo.
- A grep across `scripts/run_live_scan_once.py`, `app/services/scanner_orchestrator.py`, `app/services/valuation_service.py`, `app/services/steamdt_buff_price_provider.py`, `app/services/steamdt_buff_price_policy.py`, `app/services/steamdt_market_data.py`, `app/services/price_provider.py`, `app/services/recipe_solver.py`, `app/services/scanner_recipe_composition.py` returns ZERO matches for `price_cache`, `InMemoryPriceCache`, `RedisPriceCache`, `SteamDTCachedPriceResolver`, `PriceCacheKey`, `PriceCacheRuntime`. None of the four files in the scanner-to-price chain import any Phase 12D cache module.
- `scripts/steamdt_refresh_integration.py` is the only existing consumer of the Phase 12D stack and it is a manual CLI only.

### Current `SteamDTBuffPriceProvider` failure handling (verified)

- Catches `SteamDTBuffPriceSelectionError` per-name and records `missing` + `errors=["STEAMDT_BUFF_PRICE_SELECTION_FAILED: item_index=…, reason=…"]` (`app/services/steamdt_buff_price_provider.py:54-58`).
- Catches all other `Exception` per-name and records `missing` + `errors=["STEAMDT_BUFF_PRICE_LOOKUP_FAILED: item_index=…"]` (`:60-64`).
- Bare `raise` on `MemoryError` — propagates by identity (`:52-53`).
- Wider `BaseException` subclasses (`asyncio.CancelledError`, `KeyboardInterrupt`, `SystemExit`, `GeneratorExit`) propagate because the catch chain stops at `except Exception`.
- Item name is never leaked into `errors`; only `item_index` is.
- Identity guard at `:66-71`: if `quote.market_hash_name != market_hash_name`, the item is recorded as missing.

### Current `PriceLookupResult` shape (verified)

```python
@dataclass(frozen=True)
class PriceLookupResult:
    quotes: dict[str, PriceQuote]
    missing: list[str]
    errors: list[str] = field(default_factory=list)
```
(`app/services/price_provider.py:32-38`)

### Current `ValuationService.value_tradeup_results` (verified)

`app/services/valuation_service.py:57-152`. Dedupes `output_names` via `dict.fromkeys` (`:72`). Empty input short-circuits without touching the provider (`:63-69`). Catches `MemoryError` and re-raises; catches all other `Exception` and converts to a `ValuationResult` with `warnings`, `missing_market_hash_names`, and a populated `PriceLookupResult`. Default `ValuationMissingPriceStrategy` is `KEEP_ORIGINAL`; `require_all_prices` defaults to `False` and only appends a warning.

## Current Phase 12D cache stack (verified)

- `app/services/price_cache.py` — schema-versioned `PriceCacheKey(market_hash_name, game="cs2", currency="CNY", source="steamdt", snapshot_type="platform_prices", schema_version=1)`; deterministic sha256 key digest; `CachedPriceSnapshot(candidates: tuple[NormalizedPriceCandidate, ...], observed_at, stored_at, policy)`; `PriceCacheReadPolicy = {FRESH_ONLY, ALLOW_STALE, ALLOW_STALE_GRACE}`; `PriceCache` Protocol; `InMemoryPriceCache` (default backend, no Redis required).
- `app/services/price_cache_codec.py` — strict deterministic version-1 Redis hash codec; `PriceCacheCodecError(ValueError)`.
- `app/services/redis_price_cache.py` — Redis backend; fail-closed `PriceCacheBackendError(RuntimeError)`; namespace-scoped keys; Lua-atomic PUT/GET/PURGE.
- `app/services/price_cache_factory.py` — `create_steamdt_price_cache_runtime`; explicit backend selection `inmemory | redis`; rejects unsupported backend strings.
- `app/services/steamdt_price_cache_adapter.py` — `SteamDTPlatformPrice ↔ NormalizedPriceCandidate / CachedPriceSnapshot`; typed `SteamDTPriceCacheAdapterError`; no I/O.
- `app/services/steamdt_cached_price_resolver.py` — read-only; one `cache.get()` + caller-supplied selector rerun against stored candidates. **No `try` / `except` anywhere in this file**: `PriceCacheBackendError` and `PriceCacheCodecError` propagate by identity. The default selector is `select_steamdt_price_quote` (`app/services/steamdt_cached_price_resolver.py:143`), which is a **generic cross-platform** selector — NOT the strict BUFF selector.
- `app/services/steamdt_price_snapshot_source.py` — typed single-item fetch contract.
- `app/services/steamdt_price_refresh_service.py` — fetch-once + write-once; propagates `PriceCacheBackendError` / `PriceCacheCodecError` / `SteamDTPriceCacheAdapterError` by identity.
- `app/services/steamdt_refresh_planner.py` — pure CPU dedup + chunk planner.
- `app/services/steamdt_refresh_executor.py` — bounded-concurrency executor.
- `scripts/steamdt_refresh_integration.py` — manual one-shot end-to-end CLI; default `InMemoryPriceCache`; live mode requires `STEAMDT_RUN_REFRESH_INTEGRATION=true` plus `STEAMDT_API_KEY`. Existing script uses `INTEGRATION_POLICY = PriceCachePolicy(fresh_ttl=timedelta(minutes=5))` with `stale_ttl=0` and `stale_grace_ttl=0` (`scripts/steamdt_refresh_integration.py:59`); this is **historical manual-script precedent only**, NOT a frozen scanner default.

### Strict BUFF vs generic selector (verified)

**`select_buff_output_price`** (`app/services/steamdt_buff_price_policy.py:73-77`) is the strict BUFF selector:
- exact platform `== "BUFF"` (case-sensitive, exact equality against `_BUFF_PLATFORM = "BUFF"` at `:12`);
- exactly one BUFF record (`DUPLICATE_BUFF_RECORDS` otherwise);
- `sell_price_cny` must be a `Decimal`, finite, and strictly positive;
- never reads `bidding_price_cny` / `bidding_count`;
- never falls back to another platform;
- raises `SteamDTBuffPriceSelectionError` on any failure — never returns a "no quote" result.

**`select_steamdt_price_quote`** (`app/clients/steamdt_price_selection.py:81-89`) is a **generic cross-platform selector**:
- accepts candidates from any platform; `SteamDTPriceSelectionConfig` has **no platform field**;
- considers bid data (`require_bidding_price`, `min_bidding_count`, `max_sell_bid_spread_pct`);
- default strategy is `LIQUIDITY_AWARE_SELL_PRICE` with `fallback_to_lowest_positive=True`;
- **CANNOT be configured to be strict BUFF-only** — strict BUFF behavior exists solely in the separate `select_buff_output_price`.

### `SteamDTCachedPriceResolutionStatus` enum (verified)

`app/services/steamdt_cached_price_resolver.py:24-31`. **Exactly five values**: `SELECTED`, `MISS`, `POLICY_BLOCKED`, `EXPIRED`, `SELECTION_FAILURE`. **No `BACKEND_ERROR` and no `CODEC_ERROR`** — those propagate as typed exceptions (`PriceCacheBackendError`, `PriceCacheCodecError`) by identity from the resolver.

### `PriceCacheLookup` fields (verified)

`app/services/price_cache.py:239-250`. **Eight fields**, not five: `key`, `hit`, `state`, `snapshot`, `age`, `needs_refresh`, `policy_blocked`, `expired`. Note `expired` is a separate boolean from `policy_blocked`; expiry sets `hit=False, snapshot=None, policy_blocked=False, expired=True` while policy-blocking sets `hit=False, snapshot=None, policy_blocked=True, expired=False`.

### `MISS` representation (verified)

`MISS` is **not** a `PriceCacheState` value. A miss is represented as `state=None` with `hit=False` via `PriceCacheLookup.missing(key)` (`app/services/price_cache.py:252-263`).

### `PriceCachePolicy` shape (verified)

`app/services/price_cache.py:128-142`. `fresh_ttl` is **required** (`> timedelta(0)`); `stale_ttl` and `stale_grace_ttl` default to `timedelta(0)` and must be `>= 0`. So a policy with `fresh_ttl=5min, stale_ttl=0, stale_grace_ttl=0` jumps straight from FRESH to EXPIRED at the 5-minute mark; `ALLOW_STALE` and `ALLOW_STALE_GRACE` are unreachable under it.

## Confirmed missing seam

The single seam Phase 14 must integrate is the call to `self.price_provider.get_prices(output_names)` inside `ValuationService.value_tradeup_results` at `app/services/valuation_service.py:71-78`. No Phase 12D cache lookup, no run-scope memoization, and no cache writeback currently exists in that path.

## Non-goals

- No live SteamDT, BUFF, Redis, or Discord integration behavior change.
- No invented BUFF endpoint, signature, parameter, or field mapping.
- No fallback valuation, no bid substitution, no metadata-zero reuse, no probability renormalization.
- No risk-threshold change, no EV / ROI / worst-case loss / profit-probability formula change.
- No scheduler, no daemon, no background refresh worker, no periodic cron, no Discord webhook.
- No production Redis requirement; default one-shot CLI must continue to work with `STEAMDT_PRICE_CACHE_BACKEND=inmemory`.
- No migration of `D-CACHE-001` status. `D-CACHE-001` remains `Active` after Phase 14A-R1. Phase 14B (run-scope reuse) and Phase 14C (Phase 12D scanner cache integration) are the phases that, when they land and are verified, reclassify `D-CACHE-001` from `Active` to `Implemented`.
- No automatic expansion of `max_valuation_requests_per_run`. The cap remains a separately configurable parameter.
- No renaming, retagging, deleting, force-updating, or pushing the local-only `v1-dry-run-baseline` tag.
- No change of canonical `main`, no PR, no merge.

## In-scope design freeze (summary; full detail in `plan.md`)

1. **Scanner-owned run-scoped valuation session** boundary (a new seam type), wrapping the current per-recipe valuation call. The seam is the only place where run-scope exact-name reuse, Phase12D cache preflight, and NEW LIVE SteamDT demand accounting live. The session exposes a **two-stage contract**: a Stage A `prepare_output_prices(names)` that performs memo + cache preflight WITHOUT issuing any live SteamDT call, and a Stage B `resolve_prepared(plan)` that is only called after the orchestrator's atomic-cap admission succeeds.
2. **Exact-name reuse key** = the canonical `output_market_hash_name` string itself. No fuzzy matching, no case folding, no aliases, no `goods_id` substitution, no `platformItemId` substitution, no hidden normalization layer. The current canonicalization is the Steam community market canonical name used by `TradeUpResult.estimated_market_hash_name` / `OutputCandidate.market_hash_name` throughout the engine path.
3. **Run-scoped memo** of exact-name outcomes within a single `run_once()` call. Successes and terminal failures are reused. The memo dies at end of `run_once`. Successful quote-name pairs from `PriceLookupResult.quotes` are memoed as success; names in `PriceLookupResult.missing` are memoed as terminal failure; the next recipe demanding the same exact name reuses the memo entry without re-issuing any provider or cache call.
4. **Initial persistent-cache policy** is `PriceCacheReadPolicy.FRESH_ONLY` (only `FRESH + SELECTED` is a usable cache hit; all other cache states fall through to live). Stale, stale-grace, expired, and policy-blocked under FRESH_ONLY are live-refresh candidates if budget allows. **Cache backend / codec / adapter exceptions are NOT live candidates**: they propagate by identity from the resolver and are NEVER reinterpreted as `MISS`. No persistent negative caching in Phase 14B or 14C.
5. **Strict BUFF cache selection (Phase 14C)**. The scanner-side session MUST inject a strict BUFF cache-selection adapter behaviorally equivalent to `select_buff_output_price` (exact `BUFF` platform, exactly one BUFF record, positive finite sell price, no bid, never another platform, never a generic lowest-positive cross-platform fallback). The resolver's default selector `select_steamdt_price_quote` is **cross-platform and CANNOT be configured to be strict BUFF-only** (`SteamDTPriceSelectionConfig` has no platform field). The strict BUFF behavior lives in `select_buff_output_price`; the scanner must reuse or adapt it rather than reimplement the rules. The `SteamDTCachedPriceResolver` itself is NOT modified in R1.
6. **No partial valuation**. Any missing, failed, blocked, or invalid exact-name resolution yields `valuation_completed=False`, no metrics, no risk, no opportunity. Never drop outputs, renormalize probabilities, substitute another platform, or zero-fill.
7. **`max_valuation_requests_per_run` redefined** as the count of NEW LIVE SteamDT provider demand / attempts within the run, exclusive of run-reuse hits and `FRESH + SELECTED` cache hits. Atomic preflight: count NEW LIVE demand BEFORE any provider call; if demand exceeds remaining live budget, the entire recipe is blocked and zero live calls are issued for it.
8. **Counters**: Option A is finalized. Legacy `valuation_requests_attempted / succeeded / failed / blocked` semantics are preserved exactly. The new discriminators (`run_reuse_hits`, `run_reuse_successes`, `run_reuse_failures`, `cache_hits_fresh_selected`, `cache_misses`, `cache_policy_blocked`, `cache_expired`, `cache_selection_failures`, `live_demand`, `live_attempted`, `live_succeeded`, `live_failed`, `live_atomically_blocked`) are added additively. Counter invariants (only for COMPLETED runs) are recorded in `plan.md` task group 7. No arithmetic equality is defined between the legacy `valuation_requests_attempted` counter and the new Phase 14 counters.
9. **TTL / config ownership**: Phase 14C adds no scanner `fresh_ttl` numeric config. Backends evaluate freshness from each stored `CachedPriceSnapshot.policy`, which remains owned by the authorized writer. The 5-minute value in `scripts/steamdt_refresh_integration.py:59` is historical manual-writer precedent only. A future scanner writeback phase, if authorized, must choose write-side TTL separately.
10. **Backend composition**: Phase 14B and 14C must both work with `InMemoryPriceCache` without Redis; Redis is an opt-in explicit backend; no Redis is required for the default one-shot CLI.
11. **Write-after-live OUT of initial 14C**: initial Phase 14C is scanner cache READ integration only. Automatic scanner write-after-live is OFF / OUT OF SCOPE. The existing manual refresh stack (`scripts/steamdt_refresh_integration.py` + `SteamDTPriceRefreshService`) remains the writer. No write-failure runtime test is required for initial 14C because scanner writeback does not occur. A future separately authorized phase may add scanner writeback and must then define opt-in config, write-failure semantics, write counters, and whether live success survives write failure.
12. **14B / 14C / 14D split** — see `plan.md` and `validation.md`.

## Acceptance criteria

Phase 14A is **complete** when, and only when, all of the following hold simultaneously:

- The three spec files (`requirements.md`, `plan.md`, `validation.md`) exist under `specs/2026-08-29-scanner-valuation-integration-design-freeze/` and pass `git diff --check`.
- `git diff --name-only` shows that **no production `.py` file has been modified**.
- The default pytest suite (offline-safe), `ruff check .`, and `mypy app` all pass locally with no weakening of any pre-existing test.
- The full byte-identity list in `validation.md` Gate 3 holds.
- The design freeze has been documented in `docs/ai-context/DECISION_LOG.md` (including the new `D-PHASE14A-R1-COHERENCE` decision), `docs/ai-context/PROJECT_CONTEXT.md`, `docs/ai-context/DEVELOPMENT_HANDOFF.md`, `docs/ai-context/ARCHITECTURE_STATE.md`, `specs/roadmap.md`, and `CLAUDE.md` per the existing pointer convention.
- All six public surfaces that currently say "run-level cross-recipe exact-price reuse = NOT IMPLEMENTED" still say so (the design freeze does not promote the feature).
- `D-CACHE-001` is **Active** (the cache is still not implemented at runtime); Phase 14A-R1 only freezes the design.
- The feature branch `feature/scanner-valuation-integration` has been pushed to `origin`. `main` is unchanged. The local-only `v1-dry-run-baseline` tag is preserved at `32ab47c5b66a0f331457e69f1515e5e9bb2a37e1`. The two excluded research JSONs remain untouched.
