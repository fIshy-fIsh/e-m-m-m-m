# Architecture Overview

## Goal

This repository contains a backend-first, **read-only** CS2 BUFF trade-up opportunity scanner. The current production capability is a bounded multi-recipe one-shot scanner exposed as a manual CLI. The scanner performs no purchases, no account actions, no cookie capture, no CAPTCHA bypass, no BUFF risk-control bypass, and no browser automation.

## Current Production Data Flow

```text
BUFF anonymous sell-order listings
  -> identity binding                       BuffCommunityIdentityResolver (pinned offline
                                            community catalog, exact fail-closed)
  -> intrinsic flag binding                 CanonicalNameIntrinsicFlagResolver
                                            (three-state StatTrak / Souvenir facts)
  -> candidate adapter                      convert_buff_listing_to_candidate
  -> TradeUpInputCandidate pool
  -> enrichment                             TradeUpInputEnrichment
                                            (pinned metadata + Decimal -> float)
  -> bounded automatic universe             BREADTH (default) or COHORT_DEPTH (opt-in)
  -> enumerate_scanner_recipe_selections    Phase 13T-2 composition adapter
                                            (per-bucket fair-share aggregate allocation,
                                             exact InputItem rehydration after temporary
                                             souvenir=False solver projection)
  -> enumerate_recipe_selections            Phase 13T-1 bounded solver enumerator
                                            (default 2 / 256)
  -> calculate_tradeup_results              existing trade-up engine
  -> ValuationService.value_tradeup_results
  -> SteamDTBuffPriceProvider               strict exact case-sensitive BUFF aggregate
                                            sell price; source "steamdt:buff"
  -> calculate_opportunity_metrics          EV / ROI / worst-case loss / profit
                                            probability
  -> evaluate_opportunity                   RiskFilterConfig policy
  -> ScannerRunResult
```

The production `run_once()` path is the chain above. The legacy `construct_scanner_recipe_selections` / `construct_recipe_selections` APIs remain available for compatibility but are **not** the production run path.

## Bounded Multi-Recipe Enumeration

The current production recipe enumeration is bounded.

```text
default candidates per run:           2
default explored states per run:      256
hard bound candidates:                1 .. 6
hard bound explored states:           1 .. 1024
hard bound invariant:                 states >= candidates
```

The bounded search explores the exact baseline recipe first, then deterministic radius-one substitutions ordered by `(r-d, r, d, RecipeSelectionKey)`. No exhaustive combinations, no beam search, no financial ranking inside the solver.

Cross-candidate exact listing reuse is allowed: the same `(source, goods_id, listing_id)` offer may appear across multiple candidate selections. Duplicate canonical offer identity fails closed before sort / collection cap / output-pool construction / search.

Per-bucket fair-share aggregate allocation distributes the candidate and state budgets across the active `(rarity, StatTrak)` buckets without redistribution and without a second pass. Projected inputs are rehydrated to the exact original `InputItem` before any valuation / EV / risk evaluation.

## Souvenir Compatibility Seam

Per D-TRADEUP-001 (May 21, 2026 contract), normal and Souvenir inputs may coexist in the standard Trade Up Contract path. The selected Souvenir inputs keep their true provenance facts but the resulting output is canonical non-Souvenir (`souvenir=False`). The current scanner enforces this without rewriting caller state:

```text
candidate-owned InputItem (with original souvenir fact)
  -> temporary souvenir=False solver projection
  -> solver geometry, output pool, output probability, output float
  -> exact original InputItem rehydration
  -> valuation / EV / risk / opportunity
```

Projected inputs never escape into valuation, EV, risk, or opportunity.

## Layered Modules

```text
api/                FastAPI routes and schemas (current surface: /health only)
jobs/               scheduler entrypoints (current surface: APScheduler mock only)
clients/            BUFF, SteamDT, Discord HTTP clients + typed errors
services/           domain services (orchestration, recipe solver, valuation,
                     risk, metadata, listing contract, Phase 12D cache stack)
repositories/       persistence access abstractions (current surface: skeleton)
models/ ORM and domain entities
utils/ shared helper utilities
```

## Existing Cache / Refresh Infrastructure

The Phase 12D cache and refresh stack is **implemented and unit-tested**. It is **not** currently wired into the live scanner valuation path. The two concepts are kept separate.

### Persistent / cache snapshot infrastructure

```text
PriceCache                       async cache protocol (Phase 12D1)
InMemoryPriceCache               concurrency-safe in-memory core (Phase 12D1)
RedisPriceCache                  Redis hash codec + atomic Lua core (Phase 12D2A)
                                 opt-in real Redis integration harness (Phase 12D2B)
PriceCacheFactory                inmemory | redis composition (Phase 12D3A)
SteamDTPlatformPrice ->          selector-after adapter (Phase 12D3B)
  NormalizedPriceCandidate
SteamDTCachedPriceResolver       read-only resolver; one get() + selector rerun
                                 (Phase 12D3B)
SteamDTPriceSnapshotSource       narrow async source port (Phase 12D4A)
SteamDTSinglePriceSnapshotSource concrete read-only snapshot source (Phase 12D4B)
SteamDTPriceRefreshService       single-item write service (Phase 12D4A)
SteamDTRefreshPlanner            dedup + chunk planner (Phase 12D5A)
SteamDTRefreshExecutor           sequential chunk executor (Phase 12D5B)
                                 (max_concurrency bound; chunk 0 completes
                                  before chunk 1 starts)
steamdt_refresh_integration      manual end-to-end refresh integration command
                                 (Phase 12D5C)
```

Status: implemented, unit-tested, opt-in via `STEAMDT_PRICE_CACHE_BACKEND`. Existing SteamDT client retry, typed errors, endpoint limiter, and server cooldown semantics are preserved unchanged.

### Live scanner cache integration

The live scanner valuation path (`scripts/run_live_scan_once.py` -> `LiveScannerOrchestrator` -> `ValuationService` -> `SteamDTBuffPriceProvider`) currently calls `SteamDTBuffPriceProvider.get_price()` / `get_prices()` directly. None of the four files import any Phase 12D cache module.

Status: **NOT IMPLEMENTED**.

### Run-level cross-recipe exact-price reuse

The same exact output market name in separate recipe valuation calls is currently a separate logical request. A per-run "already valued" memoization keyed by output market hash name does not exist.

Status: **NOT IMPLEMENTED** (D-CACHE-001). Future implementation requires separate authorization and must preserve exact-price / fail-closed semantics, the atomic valuation budget, and bounded multi-recipe ordering.

## SteamDT Endpoint Inventory

```text
GET  /open/cs2/v1/price/single     60 requests / minute      (confirmed official quota)
POST /open/cs2/v1/price/batch      1 request / minute + 5s   (confirmed official +
                                   project safety buffer       project buffer)
GET  /open/cs2/v1/price/avg        10 requests / minute      (internal safety cap;
                                                              NOT confirmed official)
GET  /open/cs2/v1/base             1 request / day           (confirmed official quota)
POST /open/cs2/item/v1/kline       120 requests / minute     (confirmed official quota)
POST /open/cs2/v1/wear             36000 requests / hour     (confirmed official quota)
```

Production uses only `GET /open/cs2/v1/price/single` (aggregate, then exact BUFF selection). All other endpoints are documented and unit-tested but not currently exercised by the production scanner.

## BUFF Source Inventory

```text
anonymous sell-order path          used (read-only, one-request, fail-closed research probe)
official product / search API      not integrated (TODO; see docs/BUFF_API_NOTES.md)
official identity resolution API   not integrated (TODO; see docs/BUFF_API_NOTES.md)
```

## Operational Surfaces

```text
production CLI                     scripts/run_live_scan_once.py
FastAPI                             /health only (no operational endpoints)
scheduler                           APScheduler mock only (not wired to live scanner)
DB persistence                      none (no opportunity, alert, scan-run, or listing
                                         history is written)
Discord Webhook                     not wired (pipeline_alert_service mock exists
                                         for unit tests only)
```

## Safety Constraints

```text
no auto-buy
no auto-trade
no automatic login
no cookie extraction
no captcha bypass
no BUFF risk-control bypass
no browser-simulated purchasing
no non-official anti-detection or evasion techniques
no invented BUFF endpoints, signatures, parameters, or field mappings
no fallback valuation (no second-platform substitute, no bid substitution,
                       no metadata-zero reuse)
no probability renormalization
no hardcoded secrets
```

Unknown BUFF API details remain tracked in `docs/BUFF_API_NOTES.md`. Unknown SteamDT API details remain tracked in `docs/STEAMDT_API_NOTES.md`.