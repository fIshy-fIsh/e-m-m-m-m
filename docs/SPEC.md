# CS2 BUFF Trade-up Opportunity Scanner — Technical Specification

## 1. Project Goal

This project is a backend-first, **read-only** CS2 trade-up opportunity scanner. It discovers trade-up opportunities from BUFF marketplace listings, evaluates each opportunity against the canonical trade-up rules and a SteamDT-based output valuation, and surfaces only opportunities that satisfy explicit quality thresholds.

The system performs the following closed loop:

1. Fetch candidate BUFF material listings through the anonymous read-only sell-order path.
2. Resolve listing identity through a pinned offline community catalog using exact fail-closed matching.
3. Pin and normalize canonical CS2 metadata (collection, rarity, min/max float, paint-seed bounds) from the local metadata snapshot. No runtime metadata network I/O.
4. Construct the bounded automatic universe of goods IDs (BREADTH default; COHORT_DEPTH opt-in).
5. Enrich listings into the trade-up `InputItem` pool.
6. Run the bounded multi-recipe enumeration (default 2 candidates / 256 states) with deterministic baseline + radius-one substitutions.
7. Compute output pool, output probability, output float, output wear, and per-recipe geometry.
8. Value every output through the strict SteamDT-BUFF aggregate sell price path. No fallback valuation.
9. Calculate EV, ROI, worst-case loss, and profit probability per candidate.
10. Filter weak opportunities using configurable risk rules.
11. Emit structured opportunity reports for human review.

V1 is **notification-only**. It does not place purchases, automate account actions, or bypass BUFF risk controls.

## 2. Non-Goals

V1 explicitly does **not**:

- implement automatic purchasing / auto-buy
- implement automatic trading
- implement automatic login
- extract cookies
- bypass CAPTCHA
- bypass BUFF risk control
- use browser automation for purchases
- use non-official anti-detection or evasion techniques
- use invented BUFF endpoints, signatures, request parameters, or response field mappings
- use fallback valuation (no second-platform substitute, no bid substitution, no metadata-zero reuse)
- renormalize solver-computed probabilities
- implement Telegram or multi-channel alerting
- implement multi-source automatic switching
- implement capital management, automated position allocation, or portfolio-level backtesting

## 3. Tech Stack

- Python 3.12
- FastAPI
- PostgreSQL
- Redis
- SQLAlchemy 2.0
- Alembic
- Pydantic
- httpx
- APScheduler
- pytest
- ruff
- mypy
- Docker Compose

Stack principles:

- modular monolith with clear boundaries
- external dependencies are isolated behind client / provider abstractions
- core formulas, filter rules, and configuration are separated
- all secrets are read from `.env`; nothing is hardcoded

## 4. System Architecture

The project uses the following logical layering. The current production scanner exercises a subset of this layering end-to-end; the rest is implemented as offline cores, opt-in factory wiring, or unit-tested seams.

### 4.1 API / Ops Layer

Responsibilities:

- FastAPI health check (`/health`)
- (Future) recent-scan status, recent opportunities, recent alerts, manual trigger endpoint

### 4.2 Scheduler Layer

Responsibilities:

- APScheduler for periodic scan, enrich, compute, and alert workflows
- re-entrance protection, failure recording, heartbeat management

Current state: APScheduler mock exists for unit tests only; not wired to the live scanner.

### 4.3 Client / Provider Layer

Responsibilities:

- `BuffClient`: anonymous read-only BUFF sell-order transport (research-validated field shape; no official OpenAPI integration)
- `MetadataClient` / `MetadataProvider`: pinned local ByMykel-derived snapshot
- `DiscordWebhookClient`: Webhook delivery
- `SteamDTHttpClient`: Bearer-token aggregate market data; typed errors; endpoint-specific rate limiter
- `RedisPriceCache`: persistent Redis-backed price cache (opt-in)

### 4.4 Service Layer

Responsibilities:

- `scan_service`: scanning, parsing, listing snapshots
- `metadata_service`: provider -> internal normalized metadata
- `opportunity_service`: composition, calculation, filtering, persistence, alerting
- `alert_service`: alert formatting, deduplication, sending, failure retry

### 4.5 Engine Layer

Responsibilities:

- `tradeup_engine`: output pool, output probability, output float, output wear
- `ev_service`: EV, ROI, worst-case loss, profit probability
- `risk_filter`: conservative opportunity filtering
- `recipe_solver`: bounded multi-recipe enumeration (`enumerate_recipe_selections` / `enumerate_recipe_selections` / `enumerate_scanner_recipe_selections`) plus legacy compatibility (`construct_recipe_selections` / `construct_scanner_recipe_selections`)

### 4.6 Data Layer

PostgreSQL: durable storage of listings, item metadata mappings, scan runs, computed opportunities, alerts, audit trails. Redis: cache, locks, alert deduplication, short-lived state.

Current state: PostgreSQL and Redis are provisioned in `.env.example`; they are not yet wired into the live scanner path.

## 5. Data Sources

### 5.1 BUFF Market Data

Current target data:

- materials listings (anonymous sell-order)
- price
- goods_id
- float if available
- listing metadata (canonical market hash name + listing identity)

Notes:

- BUFF endpoint, signing, response field mapping still have unconfirmed items
- unconfirmed items must be tracked in `docs/BUFF_API_NOTES.md`
- official BUFF product / search / identity API is **not** integrated

### 5.2 CS2 Metadata Data

V1 uses a unified metadata interface:

- the engine depends only on a unified `MetadataProvider` / `MetadataClient`
- the default source is the pinned local ByMykel-derived snapshot
- `metadata_service` is responsible for normalization; raw provider fields are never written directly into business logic

### 5.3 Valuation and Alerting Data

- Output result price comes from the strict SteamDT-BUFF aggregate sell price path (no fallback, no bid substitution)
- Discord Webhook is the V1 alerting channel (current production does not yet send to Discord)

## 6. Core Modules

1. **BUFF Anonymous Listing Module**
   - fetch candidate materials through the anonymous sell-order path
   - normalize into the strict listing observation -> tradable candidate contract
   - resolve identity through the pinned offline community catalog (exact fail-closed)
   - classify StatTrak / Souvenir via the canonical-name intrinsic flag resolver

2. **Metadata Normalize Module**
   - provider abstraction
   - collection / rarity / float range normalize
   - result-pool-required metadata assembly

3. **Trade-up Engine Module**
   - input validation
   - output pool construction
   - output probability calculation
   - output float calculation

4. **Economics Module**
   - cost aggregation
   - conservative output valuation (strict SteamDT-BUFF aggregate sell price)
   - EV / ROI / worst-case loss / profit probability

5. **Risk Filter Module**
   - threshold filtering
   - liquidity filtering
   - anomaly price filtering
   - quantity / executability filtering

6. **Alert Module**
   - Discord payload formatting (current production: not wired)
   - deduplication / cooldown
   - retry / failure logging

7. **Scheduler and Ops Module**
   - 24-hour recurring jobs (current production: not wired)
   - health checks
   - observability / run history

## 7. Bounded Multi-Recipe Enumeration (current production)

```text
default candidates per run:           2
default explored states per run:      256
hard bound candidates:                1 .. 6
hard bound explored states:           1 .. 1024
hard bound invariant:                 states >= candidates
```

Search semantics:

- baseline recipe first
- then deterministic radius-one substitutions ordered by `(r-d, r, d, RecipeSelectionKey)`
- no exhaustive combinations
- no beam search
- no financial ranking inside the solver

Identity:

- canonical offer identity is `(source, goods_id, listing_id)`
- cross-candidate exact listing reuse is allowed
- duplicate canonical offer identity fails closed before sort / cap / output / search

Atomic valuation budget:

- per-run hard cap `max_valuation_requests_per_run ∈ [1, 60]`, default 5
- budget counts NEW LIVE exact output names not present in the run memo
- Stage A preparation performs zero provider calls
- NEW LIVE demand strictly greater than the remaining cap blocks the whole recipe before Stage B / provider work; exact boundary is allowed
- blocked NEW names are not memoized; no partial provider execution

## 8. SteamDT Valuation Boundary (current production)

- The current production valuation path uses only `SteamDTBuffPriceProvider` over `GET /open/cs2/v1/price/single`.
- The exact case-sensitive `BUFF` aggregate record is the only eligible record.
- The price uses the project-approved CNY / RMB interpretation; this is **not** an explicit current provider currency guarantee.
- `biddingPrice` and `biddingCount` are not read and do not substitute for a missing or unusable sell price.
- The selected aggregate sell price is not an executable listing price or a guaranteed realized proceeds.

## 9. Phase 12D Cache / Refresh Infrastructure and Scanner Reads

Persistent cache snapshot infrastructure is unit-tested and opt-in behind `STEAMDT_PRICE_CACHE_BACKEND`:

- `PriceCache` (async cache protocol)
- `InMemoryPriceCache`
- `RedisPriceCache`
- `PriceCacheFactory` (composition / runtime ownership)
- `SteamDTCachedPriceResolver` (read-only; one `get()` plus selector rerun)
- `SteamDTPriceSnapshotSource` and `SteamDTSinglePriceSnapshotSource`
- `SteamDTPriceRefreshService` (single-item write)
- `SteamDTRefreshPlanner` (dedup + chunk)
- `SteamDTRefreshExecutor` (sequential chunks; `max_concurrency` is only a work bound, not a rate limit)

Phase 14B implements scanner-owned run-scoped exact-name success/failure reuse with a fresh session inside every `run_once()` call. Phase 14C adds optional scanner service/session persistent cache reads through `ScannerCachedBuffPriceResolver`: the scanner-owned wrapper accepts the existing cache-reader boundary and internally constructs `SteamDTCachedPriceResolver` with the fixed `select_scanner_cached_buff_price` selector, so an arbitrary generic-selector resolver cannot enter the public scanner API. Stage A consults run memo first, then reads sequentially with `PriceCacheReadPolicy.FRESH_ONLY`; cached candidates are selected only by the adapter delegating to `select_buff_output_price`. Selected success independently requires `lookup.state == FRESH`; strict selection failures retain their stable reason across same-run memo reuse. MISS, EXPIRED, and POLICY_BLOCKED outcomes become NEW LIVE demand. Cache backend/codec/adapter/resolver errors propagate; Stage B performs no cache read, write, or refresh call.

The session is not persistent and nothing in its memo is reused across runs. The scanner never writes cache after live success. Stored snapshot `PriceCachePolicy` is writer-owned; no scanner read-time numeric TTL config exists. `scripts/run_live_scan_once.py` constructs the existing Phase 12D cache runtime and injects the strict-BUFF FRESH_ONLY reader; default backend is in-memory and Redis is optional. `D-CACHE-001` is superseded for the originally tracked run-reuse + CLI composition gap.

## 10. Data Model (current production, in-memory)

The current production scanner operates entirely in memory. The entities below describe the active DTOs; no PostgreSQL schema is provisioned in this milestone.

### 10.1 TradeUpInputCandidate

Source-agnostic normalized candidate from BUFF listing normalization.

### 10.2 TradeUpEnrichedInput

Pinned-metadata-enriched candidate with collection, rarity, min/max float, paint-seed bounds.

### 10.3 ConstructedRecipe / ConstructedRecipeSelection

The ten ordered `InputItem` values, the ordered `TradeupResult` outputs, and the selected non-null paint seeds. No metrics, risk decision, hash, or timestamp stored.

### 10.4 RecipeEnumerationConfig

```text
max_candidates_returned:           int (default 2; range 1..6)
max_candidate_states_explored:     int (default 256; range 1..1024)
invariant:                         max_candidate_states_explored
                                   >= max_candidates_returned
```

### 10.5 LiveOpportunity / ScannerRunResult

Per-recipe EV, ROI, expected profit, worst-case loss, profit probability, source IDs, and risk decision.

## 11. Risk Filter

The default `RiskFilterConfig` is:

```text
min_roi:                          0.05
min_expected_profit_cny:          20
max_worst_case_loss_pct:          0.25
min_profit_probability:           0.35
max_input_total_cost_cny:         1000
```

Default policy targets conservative high-quality opportunities: low false positive rate, high liquidity, reproducible, executable.

Required filter behavior:

- low-liquidity result skins are rejected
- insufficient material quantity is rejected
- BUFF price anomalies are rejected
- isolated listings are rejected
- clearly low-volume opportunities are rejected
- single-anomalous-price-driven inflated EV is rejected

The filter must output an explicit reason code and reason text. Thresholds must be configurable.

## 12. Discord Webhook Alert (current production: not wired)

Per alert, when wired in a future phase:

- opportunity identifier
- input materials summary
- total cost
- output pool summary
- EV
- ROI
- worst-case loss
- profit probability
- key risk notes
- fee / slippage / price timestamp core assumptions

Engineering requirements:

- Webhook URL must be read from `.env`
- formatter and sender are separate
- deduplication / cooldown support
- retry on failure
- failure must not crash the main scan loop

## 13. Scheduler (current production: not wired)

When wired in a future phase:

- market scan job
- metadata refresh job
- opportunity evaluation job
- alert dispatch job
- cleanup / housekeeping job

Operational requirements:

- 24h unattended operation
- configurable scheduling frequency
- re-entrance protection
- single-job failure does not block subsequent cycles
- per-cycle run state and error counts are recorded

Redis uses:

- distributed lock or mutex control
- cooldown and deduplication key
- short-lived cache
- ephemeral state

## 14. Quality Gates

The project's quality baseline is:

```text
ruff check .
mypy app
pytest
```

Core calculation tests are mandatory. Mock external API tests cover timeout, 429, 5xx, missing fields, and shape changes.

## 15. Validation and Acceptance Criteria

### 15.1 Production behavior

The current scanner is acceptable for production usage in its manual one-shot form when:

- `scripts/run_live_scan_once.py --help` succeeds
- one bounded one-shot scan returns a structured `ScannerRunResult` with exact ingredient / output / EV / risk fields
- the scanner never claims auto-buy, auto-trade, login, cookie capture, CAPTCHA bypass, BUFF risk-control bypass, or browser-automation behavior
- the scanner never invents BUFF endpoints, signatures, parameters, or response field mappings
- the scanner never falls back to a second-platform price, a bid substitution, or a metadata-zero reuse
- the scanner never renormalizes solver-computed probabilities
- all secrets are read from `.env` and are never printed

### 15.2 Roadmap alignment

This specification is the durable functional contract. The current position in the roadmap and the proposed next functional directions are documented in `specs/roadmap.md`.

## 16. Unconfirmed BUFF API Assumptions

Still unconfirmed items remain tracked in `docs/BUFF_API_NOTES.md`. The scanner must continue to operate without resolving them; if an unconfirmed item becomes necessary for a future phase, the project must record the TODO rather than invent the implementation.

## 17. Phase 16A — Recipe-first Pre-screen Architecture Design Freeze

Phase 16A freezes a new recipe-first discovery architecture that
reuses the mature downstream calculation/safety stack but replaces
the current goods-first discovery brain. The current production
path stays in place; the recipe-first path is OFF by default
until production opt-in.

### 17.1 Target data flow

```
pinned CS2 metadata snapshot + pinned BUFF community identity snapshot
  -> RecipeFamilyGenerator
  -> static structural / output geometry
  -> static float feasibility
  -> SteamDT batch pre-screen (POST /open/cs2/v1/price/batch)
  -> RecipeFamilyPreScreenEconomics (optimistic / base / conservative)
  -> deterministic ranking / Top-N
  -> TargetedBuffScanPlanner
  -> existing BUFF anonymous listing ingestion (page-1/default-sort)
  -> existing identity / intrinsic / enrichment (reused)
  -> family-constrained concrete recipe search (reuses 2 / 256 solver)
  -> existing strict final SteamDT-BUFF valuation
  -> existing EV / risk
  -> opportunity report (LiveOpportunity)
```

### 17.2 Frozen V1 project bounds

```text
MAX_DISTINCT_COLLECTIONS_PER_FAMILY = 3       (not an external API limit)
TOP_RANKED_FAMILIES                 = 2       (ranking signal only; not a budget multiplier)
MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10      (PROJECT safety bound; one active family per run)
PRESCREEN_BATCH_CHUNK_SIZE         = 10       (internal project transport chunk; NOT a confirmed SteamDT limit)
```

### 17.3 Live BUFF request budget (run-level)

The Top-N ranking is a ranking / fallback signal, not a live
request multiplier. Exactly ONE family is active for one live
targeted BUFF scan per run. Family #2 is allowed only as a
fallback BEFORE any BUFF request starts. Once any BUFF page
request starts, family switching in that run is forbidden. Total
BUFF page requests per run is
`<= MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10`.

### 17.4 Souvenir identity boundary

Souvenir is NOT a `RecipeFamily` structural identity axis under
the current standard contract. StatTrak mode IS a structural
family dimension. Normal and Souvenir inputs may coexist;
concrete selected inputs retain true Souvenir provenance through
the existing temporary `souvenir=False` solver projection + exact
rehydration seam. Outputs remain canonical non-Souvenir. If a
future targeted scan needs a Souvenir acquisition policy, it
lives as a planner/runtime acquisition-policy field, not as
family identity.

### 17.5 Lazy enumeration

The K=3 theoretical family-state count (9,972,412 across the eight
productive strata) are analytic evidence for the project limit,
NOT an eager-materialization requirement. `RecipeFamilyGenerator`
MUST support lazy deterministic iteration by stratum and analytic
counting without materializing all family objects. Ranking MUST
support streaming / top-K evaluation without retaining all
family DTOs simultaneously.

### 17.6 Pre-screen vs final valuation separation

The SteamDT batch pre-screen uses the strict BUFF selector as
approximate ranking / pruning evidence only:

- case-sensitive `platform == "BUFF"`,
- positive finite `sellPrice`,
- exactly one BUFF record per name; missing / unusable BUFF
  record -> family FAIL_CLOSED,
- never `biddingPrice`, never a second-platform substitute,
  never lowest-across-platforms,
- `sellCount` / `updateTime` retained as diagnostics only.

The pre-screen NEVER produces a `LiveOpportunity`, NEVER passes
the existing `RiskFilterConfig`, and uses a separate
`RecipeFamilyPreScreenEconomics` DTO distinct from
`OpportunityMetrics`. Final executable valuation of concrete
candidates remains the existing strict `SteamDTBuffPriceProvider`
path with Phase 14B run-scoped exact-name reuse and Phase 14C
FRESH_ONLY cache reads unchanged.

### 17.6 Output identity boundary (Phase 16A-R2)

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

### 17.7 Migration concern

`tradeup_engine.calculate_tradeup_results` currently operates on
`OutputCandidate.market_hash_name` (per wear-qualified row).
This is the wear-row cardinality bug documented under
`D-TRADEUP-WEAR-ROW-MIGRATION-001`. Phase 16B MUST NOT silently
reuse the wear-row cardinality. A future narrow protected-core
refactor under that decision MUST add the finish-level primitive
AND keep `calculate_tradeup_results` semantically identical for
legacy callers; production math remains unchanged in 16B.

### 17.8 Implementation stages (NOT in 16A; freeze only)

```text
16B  RecipeFamily + Structural Finish Index + Lazy Generator +
     Finish-Level Geometry (lazy iteration, analytic counts,
     Souvenir NOT on family identity, finish-level probability)
16C  Static float feasibility + SteamDT batch pre-screen adapter / resolver
16D  Coarse economics + ranking + TargetedBuffScanPlan
     (one active family per run; family-switching-after-live forbidden)
16E  Family-constrained concrete solver integration + orchestrator composition
     behind explicit opt-in (production default OFF)
16F  ONE bounded live read-only validation (separately authorized)
```

### 17.9 Phase 15C-3 defer

Phase 15C-1 protocol, Phase 15C-2 tooling, and Phase 15C-2B
smoke remain preserved on `feature/representative-snapshot-calibration`.
Phase 15C-3 representative 14-day / 112-attempt campaign is
DEFERRED until recipe-first production discovery is implemented
and bounded-live validated. Production default remains `5`;
hard max remains `60`.

### 17.10 Safety / contract preservation

The new architecture preserves:

- V1 read-only market interaction;
- exact pinned identity only; no fuzzy / casefold / alias;
- canonical non-Souvenir output rule (May-2026 standard);
- `MemoryError` propagation per `D-MEMORY-001`;
- no auto-buy / auto-login / cookie / captcha bypass /
  risk-control bypass / browser automation;
- no second-platform fallback / no biddingPrice substitution /
  no metadata-zero reuse / no probability renormalization;
- production default `5`, hard max `60` unchanged;
- no invented BUFF / SteamDT details.

### 17.11 Phase 16D implementation checkpoint

Phase 16D implements a pure immutable price-book boundary, exact
per-input pinned identity/adjusted-float evidence, three approximate
economics scenarios, deterministic streaming Top-2 ranking, bounded
targeted plan construction, and a one-active-family offline decision.

The scenario rules are input min/median/max and reachable-output
max/median/min. All money is `Decimal`, structural probability is the
Phase 16B exact `Fraction`, estimated ROI is exact `Fraction`, and
sell fee is explicit. Required component gaps fail closed while
missing alternatives remain diagnostic.

Ranking has no weighted score. It orders base ROI/profit,
conservative ROI/profit, and known sellCount descending, followed by
request count and family hash ascending. SteamDT `update_time` remains
opaque diagnostics because its format/semantics are unconfirmed; it
is not parsed or used for chronology, freshness, or ranking. Exact
Phase 16C reachability is a gate/structured evidence and is not
reduced to `static_float_margin_vs_threshold`.

Targeted planning uses exact identity only, covers every represented
collection, rejects duplicate names/goods IDs, allocates family-count
slots with represented-collection-only shortfall redistribution, and
produces at most 10 requests. Top-2 still means exactly zero or one
active family. Phase 16D performs no network and has no production
scanner/CLI caller. Final valuation and wear-row migration status are
unchanged.

### 17.12 Phase 16E implementation checkpoint

Phase 16E implements a dedicated family-count-preserving bounded concrete search, a correct finish-level concrete output builder, an existing-stage acquisition composition, and an explicit opt-in recipe-first orchestrator.

The search reuses ``RecipeEnumerationConfig`` bounds (default 2/256; hard maximum 6/1024) but not the legacy unconstrained enumerator. It yields the exact family baseline, then deterministic one-for-one same-collection radius-one replacements. Every returned selection proves the exact family collection counts, input rarity, homogeneous StatTrak mode, true Souvenir provenance, unique listing identity, and aligned listing IDs.

Concrete outputs use Phase 16B unique structural finish probabilities, the ten concrete inputs' canonical average adjusted float, per-finish output float mapping, canonical wear resolution, and exact pinned non-Souvenir market names. Missing mappings and collisions fail closed. The recipe-first path never calls the legacy wear-row ``calculate_tradeup_results``. ``D-TRADEUP-WEAR-ROW-MIGRATION-001`` remains deferred for the goods-first path.

``RecipeFirstScannerConfig.enabled`` defaults to ``False``. The new orchestrator is not wired into the current CLI or goods-first scanner. Enabled offline tests consume one active ``TargetedBuffScanDecision``, reverse-prove every exact goods/name identity before page acquisition, acquire at most 10 active plan pages sequentially, never activate fallback, create one fresh ``RunScopedValuationSession``, preserve memo/FRESH_ONLY-cache/atomic-NEW-LIVE behavior, and reuse final ``ValuationService``, ``calculate_opportunity_metrics``, and ``evaluate_opportunity`` unchanged. Phase 16E performs zero live BUFF/SteamDT work.

Full architectural contract and offline evidence: `specs/2026-08-31-recipe-first-prescreen-design-freeze/{requirements,design,plan,validation}.md`.