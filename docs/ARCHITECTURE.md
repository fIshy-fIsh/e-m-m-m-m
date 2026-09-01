# Architecture Overview

## Goal

This repository contains a backend-first, **read-only** CS2 BUFF trade-up opportunity scanner. The current production capability is a bounded multi-recipe one-shot scanner exposed as a manual CLI. The scanner performs no purchases, no account actions, no cookie capture, no CAPTCHA bypass, no BUFF risk-control bypass, and no browser automation.

## Current Production Data Flow

The production scanner is invoked through `LiveScannerOrchestrator.run_once(goods_ids)`. The goods IDs are decided **before** any BUFF listing fetch — `MarketUniverseBuilder` is a CLI-side planner, not a runtime post-fetch step. The full execution therefore has two clearly separated layers.

### CLI auto-universe planning

```text
MarketUniverseBuilder
  -> goods_ids                                 (CLI planner; BREADTH default,
                                                COHORT_DEPTH opt-in;
                                                cap 10; offline preview mode)
  -> LiveScannerOrchestrator.run_once(goods_ids)
```

### Scanner data path

```text
BUFF anonymous sell-order listings (for each goods_id)
  -> identity binding                       BuffCommunityIdentityResolver (pinned offline
                                            community catalog, exact fail-closed)
  -> intrinsic flag binding                 CanonicalNameIntrinsicFlagResolver
                                            (three-state StatTrak / Souvenir facts)
  -> candidate adapter                      convert_buff_listing_to_candidate
  -> TradeUpInputCandidate pool
  -> enrichment                             TradeUpInputEnrichment
                                            (pinned metadata + Decimal -> float)
  -> InputItem pool
  -> bounded scanner composition            enumerate_scanner_recipe_selections
                                            (Phase 13T-2; per-bucket fair-share
                                             aggregate allocation, exact InputItem
                                             rehydration after temporary
                                             souvenir=False solver projection)
  -> bounded protected multi-recipe solver  enumerate_recipe_selections
                                            (Phase 13T-1; default 2 / 256)
  -> calculate_tradeup_results              existing trade-up engine
  -> ValuationService.value_tradeup_results
  -> SteamDTBuffPriceProvider               strict exact case-sensitive BUFF aggregate
                                            sell price; source "steamdt:buff"
  -> calculate_opportunity_metrics          EV / ROI / worst-case loss / profit
                                            probability
  -> evaluate_opportunity                   RiskFilterConfig policy
  -> ScannerRunResult
```

The production `run_once(goods_ids)` path is the chain above. The legacy `construct_scanner_recipe_selections` / `construct_recipe_selections` APIs remain available for compatibility but are **not** the production run path.

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

The Phase 12D cache and refresh stack is **implemented and unit-tested**. It remains **unwired** from the live scanner valuation path. Phase 14B adds a separate scanner-owned run memo; it is not a persistent cache and imports no Phase 12D module.

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

### Live scanner persistent-cache READ integration

The Phase 14C scanner service/session path is:

```text
LiveScannerOrchestrator.run_once
  -> fresh RunScopedValuationSession (one run only; optional resolver injected)
  -> async prepare_output_prices
       -> exact-name run memo first
       -> scanner-owned resolver wrapper fixes the raw resolver to
          select_scanner_cached_buff_price
       -> sequential cache reads with explicit FRESH_ONLY
       -> scanner strict-BUFF adapter delegates to select_buff_output_price
       -> selected outcomes independently require FRESH lookup state
       -> fresh SELECTED / SELECTION_FAILURE enter the run memo
          (selection failures retain the stable strict-BUFF reason)
       -> MISS / EXPIRED / POLICY_BLOCKED become ordered NEW LIVE demand
  -> atomic NEW-LIVE exact-name admission
  -> resolve_prepared (live provider for NEW exact names only; no cache work)
  -> full logical PriceLookupResult (memo + cache + live)
  -> existing ValuationService field application
  -> existing metrics / risk / opportunity path
```

The orchestrator never constructs an InMemory/Redis runtime. With no resolver injection, the exact Phase 14B behavior remains. Cache backend/codec/adapter/resolver errors propagate and are not live candidates. Stage B never reads or writes cache and never calls refresh services.

Status: **IMPLEMENTED end-to-end** (Phase 14C reads + Phase 14D default one-shot CLI cache composition). Default `scripts/run_live_scan_once.py` now composes `create_steamdt_price_cache_runtime` and injects `ScannerCachedBuffPriceResolver(runtime.cache)` into `LiveScannerOrchestrator`. Default backend is process-local in-memory; Redis remains optional through the existing three-field settings seam. Scanner write-after-live is not implemented. Stored snapshot `PriceCachePolicy` is writer-owned; no scanner read-time numeric TTL exists.

### Run-level cross-recipe exact-name valuation reuse

A fresh scanner-owned session is constructed inside every `run_once()` call. The exact key is `output_market_hash_name`; no normalization, case folding, aliasing, `goods_id`, or `platformItemId` substitution is used. Successes and terminal failures are reused across later recipes in the same run; blocked NEW names are not memoized; nothing survives across runs.

`max_valuation_requests_per_run` counts NEW LIVE exact-name demand after memo/cache classification. The orchestrator prepares demand before any provider call and atomically blocks the whole recipe if demand exceeds the remaining cap. Legacy logical valuation counters remain recipe-facing; additive run-reuse/cache/live-demand counters expose resolution work.

Status: **IMPLEMENTED end-to-end** (Phase 14B reuse + Phase 14C FRESH_ONLY reads + Phase 14D default CLI cache composition). `D-CACHE-001` is superseded for the originally tracked run-reuse + CLI composition gap. Scanner write-after-live remains unimplemented; deferred write/refresh concerns remain separate future work.

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

## Frozen Next Architecture — Phase 16A Recipe-first Pre-screen

Phase 16A freezes a new recipe-first discovery architecture that
reuses the mature downstream calculation/safety stack but replaces
the current goods-first discovery brain. Implementation of the new
production path is staged under Phases 16B / 16C / 16D / 16E / 16F
and is separately gated. The current goods-first path stays in
place; the recipe-first path is OFF by default until production
opt-in.

```text
pinned CS2 metadata snapshot + pinned BUFF community identity snapshot
  -> RecipeFamilyGenerator                          (16B, offline; lazy iteration)
       input_rarity ∈ {Consumer, Industrial, Mil-Spec, Restricted, Classified}
       stattrak_mode ∈ {normal, stattrak}            (StatTrak IS structural family dimension)
       Souvenir is NOT a RecipeFamily identity axis  (concrete input provenance only)
       MAX_DISTINCT_COLLECTIONS_PER_FAMILY = 3       (PROJECT bound)
  -> static structural / output geometry            (16B, offline)
       next_rarity, represented collections, eligible exact outputs,
       per-output probability contribution, output StatTrak mode
  -> static float feasibility                       (16C, offline)
       exact interval-union / Minkowski reachability;
       reachable finish/wear evidence; possibility != executability
  -> SteamDT batch pre-screen                       (16C, mocked transport)
       POST /open/cs2/v1/price/batch; strict BUFF selector;
       case-sensitive platform == "BUFF"; positive finite sellPrice;
       one BUFF record per name; missing/unusable BUFF -> FAIL_CLOSED;
       never biddingPrice; never second-platform; never lowest-across;
       sellCount / updateTime retained as diagnostics only;
       PRE: dedupe exact market_hash_names across active run batch;
       PRESCREEN_BATCH_CHUNK_SIZE = 10 per batch call (NOT a confirmed limit)
  -> RecipeFamilyPreScreenEconomics                 (16D, offline)
       optimistic / base / conservative scenarios;
       separate DTO from OpportunityMetrics;
       never claims executability; never passes RiskFilterConfig
  -> deterministic ranking / Top-N                  (16D, offline)
       gates + lexicographic ranking keys
       TOP_RANKED_FAMILIES = 2                       (PROJECT bound; ranking signal only)
  -> TargetedBuffScanPlanner                        (16D, offline)
       per-family exact input market_hash_names,
       mapped goods_ids via pinned identity,
       MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10    (PROJECT safety bound; one active family per run)
       MarketUniverseBuilder retained as fallback
       structural / eligibility / goods_id mapping utility
  -> existing BUFF anonymous listing ingestion      (16E, page-1/default-sort)
  -> existing identity / intrinsic / enrichment     (16E, reused)
  -> family-constrained concrete recipe search      (16E)
       reuses enumerate_scanner_recipe_selections
       with RecipeEnumerationConfig(2, 256)
       proves collection_counts match, StatTrak homogeneity,
       normal/Souvenir projection seam, exact InputItem
       rehydration, output identity membership;
       duplicate listing identity fails closed
  -> existing strict final SteamDT-BUFF valuation   (16E)
       via RunScopedValuationSession + ScannerCachedBuffPriceResolver
       Phase 14B run-scoped exact-name reuse and
       Phase 14C FRESH_ONLY cache reads unchanged
  -> existing EV / risk                             (16E)
       calculate_opportunity_metrics, evaluate_opportunity
  -> opportunity report (LiveOpportunity)           (16E)
```

### Phase 16A-R1 frozen V1 project bounds

```text
MAX_DISTINCT_COLLECTIONS_PER_FAMILY = 3       (not an external API limit)
TOP_RANKED_FAMILIES                 = 2       (ranking signal only; not a budget multiplier)
MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10      (PROJECT safety bound; one active family per run)
PRESCREEN_BATCH_CHUNK_SIZE         = 10       (internal project transport chunk; NOT a confirmed SteamDT limit)
```

### Live BUFF request budget (run-level)

The Top-N ranking is a ranking / fallback signal, not a live
request multiplier. Exactly ONE family is active for one live
targeted BUFF scan per run. Family #2 is allowed only as a
fallback BEFORE any BUFF request starts. Once any BUFF page
request starts, family switching in that run is forbidden. Total
BUFF page requests per run is
`<= MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10`. This is a PROJECT
safety bound, NOT a BUFF external limit, and preserves
`LiveScannerOrchestrator.HARD_MAX_GOODS_IDS = 10`.

### Souvenir identity boundary

Souvenir is NOT a `RecipeFamily` structural identity axis under
the current standard contract. StatTrak mode IS a structural
family dimension. Normal and Souvenir inputs may coexist;
concrete selected inputs retain true Souvenir provenance through
the existing temporary `souvenir=False` solver projection + exact
rehydration seam. Outputs remain canonical non-Souvenir. If a
future targeted scan needs a Souvenir acquisition policy, it
lives as a planner/runtime acquisition-policy field, not as
family identity.

### Lazy enumeration

The K=3 theoretical family-state count (9,972,412 across the eight
productive strata) are analytic evidence for the project limit,
NOT an eager-materialization requirement. `RecipeFamilyGenerator`
MUST support lazy deterministic iteration by stratum and analytic
counting without materializing all family objects. Ranking MUST
support streaming / top-K evaluation without retaining all
family DTOs simultaneously.

### Pre-screen vs final valuation separation

- The SteamDT batch pre-screen uses the strict BUFF selector as
  approximate ranking / pruning evidence only.
- It NEVER produces a `LiveOpportunity`.
- It NEVER passes the existing `RiskFilterConfig`.
- It uses a separate `RecipeFamilyPreScreenEconomics` DTO; it does
  not reuse `OpportunityMetrics`.
- Final executable valuation of concrete candidates remains the
  existing strict `SteamDTBuffPriceProvider` path.

### Output identity boundary (Phase 16A-R2)

Two distinct output identities are frozen:

- `StructuralOutputFinish` (finish-level). Used for collection
  output pool membership, trade-up structural probability,
  family geometry, and finish-level duplicate suppression. The
  frozen 6-tuple key
  `(collection_name, rarity, stattrak, name, weapon, paint_index)`
  is collision-free against the pinned snapshot
  (16868 wear rows -> 2148 distinct finish keys). The canonical
  non-Souvenir wear rows form a deterministic
  `(wear_name, exact_market_hash_name)` map per finish. Souvenir
  wear rows are concrete-input provenance and never appear in the
  canonical non-Souvenir output wear map.
- Exact market valuation identity (canonical non-Souvenir
  `market_hash_name` for a finish + concrete output_float).
  Resolved only after wear is known. Resolution is fail-closed:
  zero / multiple mappings for the same finish + wear
  combination -> `FAIL_CLOSED`. No fuzzy / name guessing. No
  guessing of missing wear variants.

Structural probability operates on UNIQUE FINISH COUNTS, not
wear-qualified market rows:
`(collection_count / 10) / unique_finish_count_in_collection`.
The probability sum over `represented_output_finishes` MUST
equal 1.

### Migration concern: production wear-row cardinality

The current production `tradeup_engine.calculate_tradeup_results`
operates on `OutputCandidate.market_hash_name` (per wear-qualified
row). This is the wear-row cardinality bug documented under
`D-TRADEUP-WEAR-ROW-MIGRATION-001`. Phase 16B MUST NOT silently
reuse the wear-row cardinality. A future narrow protected-core
refactor under that decision MUST add the finish-level primitive
AND keep `calculate_tradeup_results` semantically identical for
legacy callers; production math remains unchanged in 16B.

### Phase 15C-3 defer

Phase 15C-1 protocol, Phase 15C-2 tooling, and Phase 15C-2B
smoke remain preserved on `feature/representative-snapshot-calibration`.
Phase 15C-3 representative 14-day / 112-attempt campaign is
DEFERRED until recipe-first production discovery is implemented
and bounded-live validated. Production default remains `5`;
hard max remains `60`.

### Safety / contract preservation

The new architecture preserves:

- V1 read-only market interaction;
- exact pinned identity only; no fuzzy / casefold / alias;
- canonical non-Souvenir output rule (May-2026 standard);
- `MemoryError` propagation per `D-MEMORY-001`;
- no auto-buy / auto-login / cookie / captcha bypass / risk-control
  bypass / browser automation;
- no second-platform fallback / no biddingPrice substitution / no
  metadata-zero reuse / no probability renormalization;
- production default `5`, hard max `60` unchanged;
- no invented BUFF / SteamDT details.
## Phase 16B Offline Structural Core

Implemented isolated modules (zero current production callers):

```text
StructuralOutputFinishIndex
  -> 6-tuple canonical SHA-256 finish identity
  -> strict WEAR_RANGES terminal suffix parser
  -> canonical non-Souvenir exact wear map
  -> fail-closed finish+wear market_hash_name lookup

RecipeFamilyGenerator
  -> exact pinned input identity + valid next-rarity finish eligibility
  -> analytic counts
  -> lazy deterministic k / combination / positive-composition iteration

RecipeFamilyGeometry
  -> unique finish outcomes
  -> exact Fraction P(finish)=(collection_count/10)/N_c
  -> exact sum 1; independent of wear-row count
```

Production remains goods-first and unchanged. `D-TRADEUP-WEAR-ROW-MIGRATION-001` remains deferred.

## Phase 16C Offline Static-Float and Batch Pre-Screen Primitives

```text
RecipeFamily + pinned exact identity/metadata
  -> per-exact-input intrinsic ∩ canonical-wear actual interval
  -> exact adjusted FloatIntervalUnion per collection
  -> n-fold Minkowski sum by collection counts / 10
  -> output finish affine float mapping
  -> canonical wear intersection
  -> fail-closed exact pinned non-Souvenir market_hash_name

exact market_hash_names
  -> first-seen exact dedupe
  -> PRESCREEN_BATCH_CHUNK_SIZE=10 (project chunk, not provider limit)
  -> sequential existing SteamDT batch transport/parser
  -> existing select_buff_output_price strict BUFF selector
  -> isolated pre-screen quote/missing/failure diagnostics
```

## Phase 16D Offline Economics, Ranking, and Targeted Plan

```text
immutable Phase 16C strict-BUFF price book (no transport)
  + exact per-name input identity/adjusted-float evidence
  + RecipeFamilyGeometry exact Fraction probabilities
  + exact StaticFloatFeasibilityResult reachable finish/wear names
    -> optimistic/base/conservative approximate economics
       inputs: min / Decimal median / max by represented collection
       outputs: max / Decimal median / min by reachable names per finish
       explicit Decimal sell fee; estimated ROI is exact Fraction
       required component missing -> fail closed
       alternative quote missing -> complete with diagnostic
       no joint-realizability or executability claim
    -> deterministic lexicographic streaming Top-2
       base ROI, base profit, conservative ROI, conservative profit,
       known sellCount sum descending; request count then hash ascending
       no weighted score; no timestamp key; no static threshold margin
    -> exact targeted input candidates
       price, adjusted lower bound, sellCount, name, goods_id order
    -> deterministic TargetedBuffScanPlan
       family slot targets 10 / 6+4 / 4+3+3;
       shortfall redistribution among represented collections only;
       <=10 unique exact names and goods_ids
    -> TargetedBuffScanDecision
       at most two ranked keys; exactly zero or one active plan;
       fallback only before first future BUFF request
```

SteamDT `update_time: int | str | None` remains opaque diagnostic
evidence. Provider timestamp format/semantics are unconfirmed, so it
is never parsed, chronologically compared, called freshness proof, or
used for ranking (`D-PRESCREEN-TIMESTAMP-NONAUTHORITY-001`).

Phase 16D has zero production scanner callers and performs no BUFF or
SteamDT request. Production remains goods-first. Final valuation,
`OpportunityMetrics`, `RiskFilterConfig`, Phase 14 cache/session/budget
semantics, default 5, hard max 60, enumeration 2/256, and
`D-TRADEUP-WEAR-ROW-MIGRATION-001` remain unchanged.
