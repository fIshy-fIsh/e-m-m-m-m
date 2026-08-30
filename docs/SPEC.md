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

The session is not persistent and nothing in its memo is reused across runs. The scanner never writes cache after live success. Stored snapshot `PriceCachePolicy` is writer-owned; no scanner read-time numeric TTL config exists. `scripts/run_live_scan_once.py` does not yet construct/inject the resolver (Phase 14D), so `D-CACHE-001` remains Active until default runtime composition lands.

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