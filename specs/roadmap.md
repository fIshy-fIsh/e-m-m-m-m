# CS2 BUFF Trade-up Opportunity Scanner — Roadmap

## Current Position

```text
Current phase:                            PHASE_13T_COMPLETE

Current capability:                       read-only bounded multi-recipe one-shot scanner

Active development line:                  feature/steamdt-cache-rate-limit

Latest production / test checkpoint:      9288794
                                        add bounded multi-recipe scale validation
                                        (full SHA 92887947e0e1808f1bc23258cf53adb10a0036ee)

Post-Phase-13T documentation /
handoff baseline:                         bb09068
                                        sync AI context after Phase 13T
                                        (full SHA bb090686407032b915172eaed2424bf2dd41a9a3)

Default recipe enumeration:               2 candidates / 256 states

Repository normalization:                  NOT YET COMPLETE (origin/main is on a separate
                                        initial history; merge requires manual reconciliation)

Live repository HEAD / branch / tree:     MUST be verified from Git at task entry;
                                        do not infer current HEAD from this document
```

## Development History

Concise chronological milestone grouping. Detailed commit-level evidence, decision-level rationale, and step-by-step handoff live in `docs/ai-context/DEVELOPMENT_HANDOFF.md`, `docs/ai-context/DECISION_LOG.md`, and `docs/ai-context/ARCHITECTURE_STATE.md`; this roadmap does not duplicate them.

### Original Skeleton / Planning Baseline

`Phase 1..8` MVP skeleton (initial planning: specification / foundation / market ingestion / metadata enrichment / trade-up engine / risk filtering / alerting and operations / hardening). Classification: **historical planning baseline, later superseded** by the actual implementation sequence recorded in Git history and the Phase 12–13T specifications. Retained only as historical planning context; not restored as the active roadmap.

### V1 Dry-run Foundation

Anchored by `feature/buff-tradeup-scanner` (local-only branch) and tag `v1-dry-run-baseline -> 32ab47c5`. Branch and tag are independent refs; the tag independently preserves the baseline commit regardless of any future branch cleanup.

```text
trade-up domain model
CS2 metadata / wear / float handling
trade-up output computation
EV / ROI / worst-case loss / profit probability foundations
risk filter foundations
dry-run / mock opportunity pipeline
mock APScheduler pipeline
FastAPI /health skeleton
configuration / service boundaries
```

### SteamDT Data-source Foundation

`specs/2026-06-28-steamdt-data-source/` documents the initial SteamDT design. Notable commits:

```text
5261d81 Add SteamDT phase 1 design docs
b5b4fec add steamdt client abstraction
2dd6ba9 Add SteamDT valuation abstractions
2dbff19 wire mock valuation into pipeline
95526bd Add SteamDT parser skeleton
f5d1bb8 Add SteamDT official price smoke test
3cc5522 Refine SteamDT price selection
```

```text
SteamDT HTTP client
response parser
selection policy (lowest_positive_sell_price, then liquidity-aware)
provider / composition wiring
smoke harnesses
SteamDT documentation matrix (docs/STEAMDT_API_NOTES.md)
```

End of `feature/steamdt-data-source`: `912fec5f — Support direct SteamDT smoke script execution`. The entire branch history is a strict subset of `feature/steamdt-cache-rate-limit`.

### Phase 12A — SteamDT Typed Errors and Retry Classification

Source of truth: `docs/STEAMDT_API_NOTES.md`. Typed error classification (transport / HTTP status / API wrapper / rate-limit / response-parse). Retry only transport and HTTP 5xx; no retry on HTTP 4xx, `errorCode=4005`, or parser/Decimal failures. Redacted error text.

### Phase 12B — SteamDT Endpoint-specific In-memory Rate Limiter

Source of truth: `docs/STEAMDT_API_NOTES.md`. Endpoint policy: `price_single` 60/min (official), `price_batch` 1/min + 5s buffer (official + project buffer), `price_avg` 10/min (internal cap, not official), `base` 1/day, `kline` 120/min, `wear` 36000/hour. Process-local monotonic-clock sliding windows; fail-fast `SteamDTRateLimitError`; HTTP 429 + `errorCode=4005` record server cooldown.

### Phase 12C — SteamDT Redis Shared Limiter

Source of truth: `docs/STEAMDT_API_NOTES.md`. `12C1`: Redis Lua-atomic acquire using Redis server TIME; per-endpoint sorted set; UUID request members; server cooldown with max semantics; `SteamDTRateLimitBackendError` fails closed. `12C2`: opt-in real-Redis integration harness (`STEAMDT_RUN_REDIS_INTEGRATION_TESTS=true`); test-only URL/namespace; paged SCAN cleanup. `12C3`: `STEAMDT_RATE_LIMIT_BACKEND` selects `inmemory | redis`; runtime `aclose()`; factory-owned Redis clients.

### Phase 12D — Price Cache & Refresh Infrastructure

```text
12D1   PriceCache domain + InMemoryPriceCache
12D2A  RedisPriceCache with Lua-atomic codec
12D2B  opt-in real-Redis price cache integration harness
12D3A  PriceCacheFactory / SteamDTPriceCacheRuntime composition
12D3B  SteamDTPlatformPrice <-> NormalizedPriceCandidate adapter;
       SteamDTCachedPriceResolver (read-only; one get() + selector rerun)
12D4A  SteamDTPriceSnapshotSource + SteamDTPriceRefreshService
12D4B  SteamDTSinglePriceSnapshotSource concrete read-only source
12D5A  SteamDTRefreshPlanner dedup + chunk planner
12D5B  SteamDTRefreshExecutor controlled sequential executor
12D5C  scripts/steamdt_refresh_integration.py manual end-to-end command
```

Status: **COMPLETE** (implemented and unit-tested).

Current caveat:

```text
Phase 12D persistent / cache infrastructure:  IMPLEMENTED + UNIT TESTED
Live scanner cache integration:                NOT IMPLEMENTED
Run-level cross-recipe exact-price reuse:      NOT IMPLEMENTED
```

### Phase 12E — BUFF Listing / Adapter Foundation

BUFF listing domain contract; project-owned v1/v2 listing fixtures; listing eligibility evaluator (facts-driven; default policy); offline listing facts provider; listing qualification service; qualified-listing-to-solver-candidate adapter; manual offline qualification + adapter integration commands; canonical `goods_id` propagation through normalization; `TradeUpInputCandidate` boundary on the solver-input side. Phase 12E established the offline BUFF listing / adapter contract; live runtime identity binding was added later in Phase 13N through the pinned community identity catalog and the separate runtime identity-binding stage.

### Phase 13A — Valuation Source Evolution

```text
SteamApis exploration (paused / historical; not a current runtime source)
SteamDT pivot to primary aggregate market data source (Step 2L-PIVOT-R1)
BUFF-platform aggregate valuation selection  (Step 2M-A1)
BUFF-only SteamDTPriceProvider               (Step 2M-A2)
offline BUFF live recipe valuation composition (Step 2M-A3)
opt-in live BUFF provider smoke             (Step 2M-A4)
deterministic one-output recipe fixture      (Step 2M-A5-PRE1)
verified output identity freeze              (Step 2M-A5-PRE2)
opt-in full live recipe valuation smoke      (Step 2M-A5)
```

Historical outcome: **SteamDT became the active valuation source**.

### Phase 13C / 13D — BUFF Anonymous Research & Identity Boundary

`Phase 13C`: anonymous BUFF sell-order research (one-request, read-only); verified sell-order field shape (id, price, paintwear, assetid; paintseed absent). `Phase 13D-0`: canonical identity DTO and resolver protocol boundary; no mappings; explicit no-invented-endpoint policy.

Current distinction preserved:

```text
live anonymous BUFF sell-order listing path:                YES
official authoritative BUFF product / search / identity API: NO
```

### Phase 13I / 13M / 13N — Enrichment, Orchestration & Identity Binding

```text
Phase 13I-3     TradeUpInputCandidate boundary;
                TradeUpInputEnrichment boundary
                (metadata + Decimal -> float actual_float exactly once)
Phase 13M-0     production orchestration architecture review
Phase 13L-0     identity-bridge architecture review
Phase 13N-3A    pinned community BUFF identity catalog
Phase 13N-3B    BuffCommunityIdentityResolver composition
Phase 13N-3C    identity binding between BuffListingProvider and
                BuffListingCandidateAdapter (identity-only)
D-IDENTITY-007  resolver wired into the runtime
```

Ownership rule preserved: `adapter does NOT resolve identity; identity binding is a separate stage`.

### Phase 13O — Intrinsic Flags

StatTrak / Souvenir canonical-name classification; three-state intrinsic facts (stattrak / souvenir); adapter hardcoded-false semantics removed; intrinsic binding as a separate provider stage.

Ownership rule preserved: `TradeUpInputCandidate: stattrak / souvenir; metadata: collection_name / rarity / min_float / max_float`.

### Phase 13P — Live One-shot Scanner

BUFF anonymous listings; identity binding (separate stage); intrinsic binding (separate stage); candidate adaptation; metadata enrichment; `InputItem` construction; recipe construction; SteamDT valuation; opportunity metrics; risk evaluation; one-shot live scanner CLI (`scripts/run_live_scan_once.py`).

`Phase 13P` is a major architectural milestone: real live end-to-end evidence was obtained against the documented anonymous BUFF sell-order path and the SteamDT single-price endpoint. Operational mode is **manual one-shot CLI**; no scheduler exists.

### Phase 13R — Automatic Market Universe

Automatic bounded goods-id universe; exact pinned identity/metadata intersection; `BREADTH` allocation (collection round-robin); hard goods cap (10); preview mode (no network). Status: **COMPLETE**.

### Phase 13S — Structural Cohort Depth

`COHORT_DEPTH` strategy; cohort key = `(collection_name, rarity, stattrak)`; normal and Souvenir share structural cohort; target cohort count = 3; 10-slot structural allocation = `4 / 3 / 3`; capacity-aware fair rounds within cohort; deterministic interleaving of normal / Souvenir identities.

Caveat: `catalog capacity is structural capacity, not live liquidity or financial ranking`.

### Phase 13T — Bounded Multi-Recipe Migration

Most recent major migration. Detailed validation evidence lives in `docs/ai-context/DEVELOPMENT_HANDOFF.md` and the commit messages themselves; this roadmap records provenance only.

```text
Design Freeze:  bounded additive radius-one enumeration;
                no exhaustive combinations / no beam search;
                candidate offer identity = (source, goods_id, listing_id);
                cross-candidate exact listing reuse allowed;
                duplicate canonical offer identity fails closed

13T-1:          enumerate_recipe_selections;
                RecipeEnumerationConfig (defaults 2 / 256);
                hard limits candidates 1..6, states 1..1024;
                invariant states >= candidates;
                legacy construct_recipe_selections preserved unchanged

13T-2:          enumerate_scanner_recipe_selections (composition adapter);
                per-bucket fair-share aggregate candidate / state budget;
                no redistribution; no second pass;
                temporary souvenir=False solver projection;
                exact InputItem rehydration;
                projected inputs never escape

13T-3A:         LiveScannerOrchestrator integration;
                atomic cumulative valuation-request cap
                (required == remaining cap allowed;
                 required > remaining cap blocks whole recipe
                  before any SteamDT HTTP / provider request)

13T-3B:         CLI enumeration flags
                  --max-recipe-candidates-returned
                  --max-candidate-states-explored

13T-4A:         bounded deep-pool validation (offline);
                real composition -> real engine -> real ValuationService
                  -> real metrics -> real risk;
                exact rehydration;
                atomic exact-cap / one-below behavior;
                two-bucket aggregate allocation;
                1 / 1 legacy compatibility;
                determinism

13T-4B:         live-only validation; no commit; no repository artifact;
                real BUFF run; 10 / 10 goods requests succeeded;
                95 listings / InputItems;
                2 real recipe candidates;
                valuation demands 10 and 20;
                cap 5 atomically blocked both before SteamDT provider work;
                SteamDT live mode configured; SteamDT HTTP requests = 0;
                LIVE_VALIDATION_PASSED_NO_COMPLETE_VALUATION

final status:   PHASE_13T_COMPLETE.
                Phase 13T-1 through Phase 13T-4A were committed and pushed,
                culminating in the Phase 13T-4A checkpoint 9288794.
                Phase 13T-4B was live-only validation and produced no
                commit and no repository artifact.
                SteamDT live mode configured: YES.
                SteamDT HTTP / provider requests issued during 13T-4B: 0.
                Frozen contracts held.
```

### Post-13T Documentation Synchronization

`bb09068 — sync AI context after Phase 13T` — documentation / handoff synchronization only. `PROJECT_CONTEXT.md` / `ARCHITECTURE_STATE.md` / `DECISION_LOG.md` / `DEVELOPMENT_HANDOFF.md` / `CLAUDE.md` pointer. Six new decision IDs appended: `D-ENUM-001..004`, `D-CACHE-001`, `D-PHASE13T-COMPLETE`. This is a documentation milestone, **not** a production feature.

### Broad evolution chronology

```text
Original skeleton / planning baseline
  -> V1 dry-run foundation
  -> SteamDT data-source foundation
  -> Phase 12A typed errors and retry classification
  -> Phase 12B endpoint-specific in-memory rate limiter
  -> Phase 12C Redis shared limiter (12C1 / 12C2 / 12C3)
  -> Phase 12D price cache and refresh infrastructure
  -> Phase 12E BUFF listing / adapter foundation
  -> Phase 13A valuation source evolution (SteamApis -> SteamDT pivot)
  -> Phase 13C / 13D BUFF anonymous research + identity boundary
  -> Phase 13I / 13M / 13N enrichment + identity binding
  -> Phase 13O intrinsic flags
  -> Phase 13P live one-shot scanner
  -> Phase 13R automatic market universe
  -> Phase 13S cohort depth
  -> Phase 13T bounded multi-recipe migration
  -> bb09068 AI-context synchronization
  -> R0 public-document synchronization
  -> proposed scanner valuation integration (next, not authorized)
```

## Current Capabilities

Each capability carries an explicit status. Independent of chronology.

```text
Trade-up engine                                       COMPLETE
SteamDT strict BUFF valuation path                    COMPLETE
Phase 12A typed errors and retry classification       COMPLETE
Phase 12B endpoint-specific in-memory limiter         COMPLETE
Phase 12C Redis shared limiter                        COMPLETE
Phase 12D price-cache infrastructure                  COMPLETE
Live scanner cache integration                        NOT IMPLEMENTED
Run-level cross-recipe exact-price reuse              NOT IMPLEMENTED
BUFF anonymous listing ingestion                      COMPLETE
Live BUFF product / search / identity API             NOT INTEGRATED
Pinned offline identity catalog                       COMPLETE
Identity binding (separate stage)                     COMPLETE
Intrinsic flag binding (separate stage)               COMPLETE
Three-state StatTrak / Souvenir intrinsic facts       COMPLETE
Automatic market universe                             COMPLETE
BREADTH allocation                                    COMPLETE
COHORT_DEPTH allocation                               COMPLETE
Bounded multi-recipe enumeration                      COMPLETE
Offline multi-recipe scale validation                 COMPLETE
Bounded live validation (no commit)                   COMPLETE
One-shot live scanner CLI                             COMPLETE
AI-context synchronization                            COMPLETE
Production scheduler / continuous operation            NOT IMPLEMENTED
DB persistence                                        NOT IMPLEMENTED
Real Discord opportunity delivery                     NOT IMPLEMENTED
FastAPI operational surface                           /health only
```

Two structural invariants preserved across all phases: (1) `candidate-owned stattrak / souvenir facts -> temporary souvenir=False solver projection -> exact InputItem rehydration -> valuation / EV / risk / opportunity`; (2) `canonical SteamDT-BUFF aggregate sell price -> no second-platform fallback / no bid substitution / no metadata-zero reuse / no probability renormalization`.

## Repository Consolidation

Immediate current maintenance track. No branch operation is authorized.

Current branch facts:

```text
origin/main:
  separate unrelated initial history (no shared commit with the
  active branch); cannot fast-forward from the active branch

feature/steamdt-cache-rate-limit:
  active development line;
  production / test checkpoint = 9288794;
  documentation / handoff baseline = bb09068;
  live HEAD / branch / tree state must be verified from Git

feature/steamdt-data-source:
  strict ancestor / superseded (all of its commits are also on
  feature/steamdt-cache-rate-limit);
  safe to delete after the active branch is merged into main

feature/buff-tradeup-scanner:
  historical local ancestor
  (independently preserved by tag v1-dry-run-baseline -> 32ab47c5;
   branch and tag are separate refs; branch cleanup may be
   considered after repository consolidation)
```

Consolidation status:

```text
R0-A — Public Documentation Synchronization

```text
scope:
  README / roadmap / architecture / spec / mission / metadata
  synchronization

status authority:
  Git history / repository checkpoint

status:
  documentation synchronization workstream
  (transient staged / committed / pushed state is recorded in the
   checkpoint report, not in this durable roadmap)
```

R0-B Minimum CI                     NOT STARTED
                                    Python 3.12 / ruff / mypy / pytest on push and PR
                                    against main (no CI workflow files exist yet)

R0-C Main History Consolidation     NOT STARTED
                                    merge feature/steamdt-cache-rate-limit into main
                                    via a manual reconciliation commit (fast-forward
                                    is not possible because origin/main has no shared
                                    commit with the active branch)

R0-D Branch / Repository Cleanup    NOT STARTED
                                    delete origin/feature/steamdt-data-source AFTER
                                    the active branch is merged into main;
                                    consider local-only feature/buff-tradeup-scanner
                                    (tag anchor v1-dry-run-baseline is independent);
                                    prune stale worktree-agent-* references;
                                    apply branch protection to main;
                                    refresh repository description / topics;
                                    establish tag discipline (PHASE_13T_COMPLETE on main);
                                    prune worktree-agent-* references
```

## Next Proposed Functional Work

**Proposed, not yet authorized.** No new functional phase is currently in progress.

### Primary — Scanner Valuation Integration

```text
scope:
  integrate the EXISTING Phase 12D cache stack
    (InMemoryPriceCache / RedisPriceCache / SteamDTCachedPriceResolver /
     refresh service / planner / executor)
    into the live scanner valuation path
  add run-level exact-price reuse keyed by output market_hash_name
  add cache-hit / cache-miss / provider-demand accounting
  preserve exact-price / fail-closed semantics
  preserve bounded multi-recipe ordering
  preserve atomic fail-closed valuation budget behavior

constraints:
  no invented endpoints, signatures, or field mappings
  no fallback valuation
  no probability renormalization
  no scheduler or background work introduced by this phase
  no real BUFF / SteamDT request behavior change

closure of D-CACHE-001:
  run-level cross-recipe exact-price reuse lives here, NOT in Deferred
```

### Secondary — Valuation Budget Calibration

```text
scope:
  offline measurement of unique output-name cardinality distribution
    (min / P25 / median / P75 / P90 / P95 / max)
    under the current cohort-depth allocation and the default
    bounded enumeration (2 / 256)
  evidence-based max_valuation_requests_per_run policy

constraints:
  no future numeric cap is hardcoded; the cap remains a separately
  configurable parameter
  CLI flag semantics unchanged
  atomic budget semantics unchanged
```

## Deferred

Not part of any current or proposed functional phase. Each requires its own future authorization.

```text
production scheduler / continuous operation
real Discord opportunity delivery
DB persistence / operational state
FastAPI operational surface (admin / run inspection / opportunity query / control)
advanced recipe search
larger structural search budgets (beyond hard bounds 1..6 / 1..1024)
```

## Permanent Non-Goals

Listed separately from Deferred. Not roadmap items.

```text
auto-buy
auto-trade
automatic BUFF login
cookie scraping
CAPTCHA bypass
BUFF risk-control bypass
browser automation for purchasing
non-official anti-detection / evasion techniques
invented BUFF endpoints, signatures, parameters, or field mappings
fallback valuation (second-platform substitute, bid substitution, metadata-zero reuse)
probability renormalization
```

## Detailed History / Authority

This roadmap is the project-level navigation document. Detailed micro-phase / commit / validation / decision evidence lives elsewhere and is intentionally not duplicated here.

```text
docs/ai-context/DEVELOPMENT_HANDOFF.md    commit-level handoff and current-phase state
docs/ai-context/DECISION_LOG.md           decision-level rationale (appended per phase)
docs/ai-context/ARCHITECTURE_STATE.md     authoritative module structure
docs/ai-context/PROJECT_CONTEXT.md        authoritative project context
docs/ai-context/README.md  AI-context entry point
docs/BUFF_API_NOTES.md     BUFF API TODO matrix
docs/BUFF_LISTING_NOTES.md BUFF listing contract notes
docs/STEAMDT_API_NOTES.md  SteamDT API confirmed / TODO matrix
                            (also the source of truth for Phase 12A / 12B / 12C)
specs/mission.md           mission statement and V1 non-goals
specs/tech-stack.md        Python 3.12, FastAPI, Redis, PostgreSQL,
                           SQLAlchemy 2.0, httpx, APScheduler,
                           ruff, mypy, pytest
docs/ARCHITECTURE.md       current production architecture
docs/SPEC.md               current functional requirements and non-goals
specs/                     per-phase plan / requirements / validation documents
git log feature/buff-tradeup-scanner
git log origin/feature/steamdt-data-source
git log origin/feature/steamdt-cache-rate-limit
```