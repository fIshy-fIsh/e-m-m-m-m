# CS2 BUFF Trade-up Opportunity Scanner — Roadmap

## Current Position

```text
Current phase:                            PHASE_15A_MEASUREMENT_COMPLETE

Current capability:                       read-only bounded multi-recipe one-shot scanner
                                          plus offline exact-output-name calibration
                                          evidence; production budget unchanged

Active development line:                  feature/valuation-budget-calibration
                                          (offline research/tests/docs only)

Latest Phase 15A checkpoint:              measure scanner valuation output cardinality
                                          (verify exact SHA from Git after commit)
                                          192 deterministic replay observations /
                                          439 structural census records
                                          artifacts under
                                          research/valuation_budget_calibration/

Post-Phase-13T documentation /
handoff baseline:                         bb09068
                                        sync AI context after Phase 13T
                                        (full SHA bb090686407032b915172eaed2424bf2dd41a9a3)

Default recipe enumeration:               2 candidates / 256 states

Repository normalization:                  COMPLETE
                                        canonical main = P3 =
                                          24c95c029f583d5cc0b0a67986e48c06d0ef7957
                                        parents: {328269112f229faf3fce4cf0be4b9c7875582b65,
                                                   6964cc4ff25cd4ad72fe65f92f40a5ce70a4a268}
                                        tree:   608d3e473072afb0d97aadf46ea0be8b1f55ca26
                                        CI workflow blob 02d0ce81... preserved
                                        (R0-A / R0-B / R0-C / R0-C docs checkpoint /
                                         R0-D all complete; canonical main advanced
                                         to P3 by the R0-D completion documentation
                                         checkpoint PR #3)

Branch / repository cleanup (R0-D):       COMPLETE
                                        (R0-D1 audit, R0-D2 / R0-D2-BIS / R0-D2-TER
                                         cleanup all complete; R0-D completion
                                         documentation checkpoint PR #3 merged;
                                         final-main push CI green at run 33240760167
                                         SUCCESS)

Phase 14A / R1 design authority:          COMPLETE
                                        e98cd97 / bb056e5
                                        specs/2026-08-29-scanner-valuation-integration-design-freeze/

Phase 14B — Run-scoped exact-name
valuation reuse:                          COMPLETE
                                        fresh session per run_once
                                        async memo-only prepare (zero provider calls)
                                        atomic NEW-LIVE exact-name admission
                                        execute NEW exact names only
                                        success + terminal-failure reuse
                                        no same-name retry / no cross-run reuse
                                        existing ValuationService formula reused
                                        legacy logical counters preserved
                                        additive run_reuse/live/cache counters
                                        deep-pool: 20 logical / 10 provider /
                                          10 reuse; cap 10 pass; cap 9 zero-provider block
                                        no Phase12D cache use on resolver-None path

Phase 14C — Phase12D FRESH_ONLY
cache READ integration:                  COMPLETE
                                        optional scanner-owned resolver wrapper
                                          over injected cache-reader boundary
                                        raw resolver structurally fixed to strict selector
                                        memo -> cache -> live Stage A order
                                        sequential explicit FRESH_ONLY reads
                                        strict-BUFF adapter delegates to
                                          select_buff_output_price
                                        fresh selection success/failure memoized
                                        MISS / EXPIRED / POLICY_BLOCKED become NEW LIVE
                                        backend/codec/adapter errors propagate
                                        no stale values / no persistent writeback
                                        snapshot PriceCachePolicy writer-owned;
                                          no scanner numeric TTL config
                                        default CLI composition remains pending

Phase 14D — CLI composition + scale /
bounded-live validation:                COMPLETE

Phase 15A — Valuation Budget
Calibration offline measurement:        COMPLETE
                                        no production budget change
                                        Phase 15B NOT STARTED / NOT AUTHORIZED

Live repository HEAD / branch / tree:     MUST be verified from Git at task entry;
                                        do not infer current HEAD from this document
```

## Development History

Concise chronological milestone grouping. Detailed commit-level evidence, decision-level rationale, and step-by-step handoff live in `docs/ai-context/DEVELOPMENT_HANDOFF.md`, `docs/ai-context/DECISION_LOG.md`, and `docs/ai-context/ARCHITECTURE_STATE.md`; this roadmap does not duplicate them.

### Original Skeleton / Planning Baseline

`Phase 1..8` MVP skeleton (initial planning: specification / foundation / market ingestion / metadata enrichment / trade-up engine / risk filtering / alerting and operations / hardening). Classification: **historical planning baseline, later superseded** by the actual implementation sequence recorded in Git history and the Phase 12–13T specifications. Retained only as historical planning context; not restored as the active roadmap.

### V1 Dry-run Foundation

Historically anchored by `feature/buff-tradeup-scanner` (local-only branch; removed during R0-D cleanup) and tag `v1-dry-run-baseline -> 32ab47c5`. The tag independently preserves the baseline commit. Branch and tag were separate refs; the branch was safely deletable in R0-D because its tip exactly equaled the retained tag target and it had 0 unique commits vs canonical main.

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
Scanner service/session cache READ support:    IMPLEMENTED (PHASE 14C)
Run-level cross-recipe exact-name reuse:        IMPLEMENTED (PHASE 14B)
FRESH_ONLY scanner service cache reads:         IMPLEMENTED (PHASE 14C)
Default run_live_scan_once cache composition:   NOT IMPLEMENTED (PHASE 14D)
Scanner write-after-live:                       NOT IMPLEMENTED / OUT OF SCOPE
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
  -> R0-A public-document synchronization
  -> R0-B minimum CI
  -> R0-C main history consolidation
  -> b13201b post-R0-C docs checkpoint
  -> R0-D branch / repository cleanup (complete)
  -> Phase 14A/R1 scanner valuation design
  -> Phase 14B run-scoped exact-name reuse
  -> Phase 14C optional FRESH_ONLY scanner cache reads
  -> Phase 14D default CLI composition (next, not authorized)
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
Scanner service/session persistent-cache READ seam    COMPLETE (PHASE 14C)
Run-level cross-recipe exact-name valuation reuse     COMPLETE (PHASE 14B)
FRESH_ONLY scanner cache reads                        COMPLETE (PHASE 14C)
Default one-shot CLI cache composition                 NOT IMPLEMENTED (PHASE 14D)
Scanner write-after-live                               NOT IMPLEMENTED / OUT OF SCOPE
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

R0-A / R0-B / R0-C / R0-C docs checkpoint / R0-D are all complete. Canonical `main` advanced to P3 (`24c95c0…`) by the R0-D completion documentation checkpoint PR #3.

Current branch state (after R0-D cleanup):

```text
canonical main (local + remote):   ONLY branch
  remote SHA: 328269112f229faf3fce4cf0be4b9c7875582b65 (P2)
  local SHA:   328269112f229faf3fce4cf0be4b9c7875582b65 (tracks origin/main at 0 0)
  parents:     {9cfaf36..., b13201b...}
  tree:        b7648ad185aaf9ae4f4ca1057294e4b84010ab8d

linked worktrees:                  ONLY D:/CS root
```

Historical branches removed during R0-D cleanup (all retained as historical
references; their commits remain reachable through canonical main and/or the
preserved `v1-dry-run-baseline` tag):

```text
docs/r0c-completion-checkpoint    (removed; was b13201b;
                                   commits remain reachable as ancestor of P2)
repo/main-consolidation           (removed; was 3aa44e9;
                                   commits remain reachable as ancestor of P2)
feature/steamdt-cache-rate-limit  (removed; was 4c2f1ef (historical DEV tip);
                                   commits remain reachable as ancestor of P2)
feature/steamdt-data-source       (removed; was 912fec5;
                                   strict ancestor of feature/steamdt-cache-rate-limit
                                   and therefore of main)
feature/buff-tradeup-scanner      (removed; was 32ab47c5;
                                   historical local anchor preserved independently
                                   by retained tag v1-dry-run-baseline -> 32ab47c5;
                                   tag and branch were exact-tip duplicates;
                                   0 unique commits lost)
worktree-agent-a*                 (removed; 305 generated local branches at OLD_MAIN
                                   24ece858; all were ancestors of P2 with 0 unique
                                   commits; their linked Claude agent worktrees under
                                   D:/CS/.claude/worktrees/agent-* were removed first)
```

Mandatory preserved local-only tag:

```text
v1-dry-run-baseline -> 32ab47c5b66a0f331457e69f1515e5e9bb2a37e1
  status:        local-only (was never pushed)
  retains:       the V1 dry-run foundation commit
  relation:      branch feature/buff-tradeup-scanner (now removed) pointed
                 at the same commit before R0-D cleanup
```

Cleanup method:

```text
`git worktree remove <path>` (no --force)  for 305 linked agent worktrees
`git branch -d <name>`          (no -D)   for 305 worktree-agent local branches
`git branch -d <name>`          (no -D)   for 5 named local branches
`git push origin --delete <b>`            for 4 named remote branches
0 force pushes; 0 -D deletions; 0 history rewrites; 0 tracked file changes;
 0 commits; 0 main pushes; 0 `git fetch --prune` / `git remote prune` /
 `git worktree prune`; 0 settings changes.
session-local `.claude/settings.local.json` (305, one per agent worktree)
  was deleted before worktree removal as a separately authorized file
  removal; no other files were touched inside any worktree.
```

Unique unpreserved history lost: **NO**.

Consolidation status:

### R0-A — Public Documentation Synchronization

```text
status:   COMPLETE
scope:    README / roadmap / architecture / spec / mission / metadata
          synchronization

authority:
  Git history / repository checkpoint
```

### R0-B — Minimum CI

```text
status:       COMPLETE
workflow:     .github/workflows/ci.yml
triggers:     push / pull_request
runner:       ubuntu-latest / Python 3.12
permissions:  contents: read
gates:        ruff check . / mypy app / pytest
validation:   remote quality job completed successfully
safety:       default suite offline-safe; no real secrets or live smokes
```

```text
R0-A Public Documentation Synchronization COMPLETE
                                  public docs / roadmap / mission / metadata / spec
                                  synchronization checkpoint 1dbc6f1

R0-B Minimum CI                 COMPLETE
                                  workflow .github/workflows/ci.yml
                                  push / pull_request, contents: read,
                                  ubuntu-latest, Python 3.12,
                                  ruff check . / mypy app / pytest
                                  remote validation run 33098999757 success
                                  checkpoint 7a6349e

R0-C Main History Consolidation COMPLETE
                                  PR #1 merged with merge-commit semantics
                                  post-R0-C main = 9cfaf36...
                                  parents: {24ece858..., 3aa44e93...}
                                  tree == DEV tree == 7a39d28...
                                  CI workflow blob 02d0ce81... preserved
                                  exact-P push CI run 33173529766 success

R0-C docs checkpoint             MERGED / VERIFIED
                                  PR #2 merged with merge-commit semantics
                                  canonical main P2 = 328269112...
                                  parents: {9cfaf36..., b13201b...}
                                  tree:   b7648ad185aaf9ae4f4ca1057294e4b84010ab8d
                                  CI workflow blob 02d0ce81... preserved
                                  final-main push CI run 33175931060 success

R0-D Branch / Repository Cleanup COMPLETE
                                  R0-D1 audit, R0-D2, R0-D2-BIS, R0-D2-TER complete
                                  305 agent worktrees + 305 generated local branches
                                  + 5 named local branches + 4 named remote branches
                                  removed
                                  completion docs PR #3 merged / verified
                                  canonical main P3 = 24c95c029...
                                  `v1-dry-run-baseline` preserved locally
                                  no unique history lost

Phase 14 Integration                  MERGED / VERIFIED
                                  Phase 14A / 14A-R1 / 14B / 14C / 14D merged
                                  via PR #4 (`Integrate scanner valuation cache
                                  and run-level reuse`) onto canonical main.
                                  canonical main P4 = 26c69bae9e482452f56f380277d8b10fefa29d52
                                  parents: {24c95c029..., 47227b33...}
                                  tree:   39a82914fa53fd414d141fbb87cbf197c1ff2c19
                                  CI workflow blob 02d0ce81... preserved
                                  main push CI run 33320657978 success
                                  feature branch `feature/scanner-valuation-integration`
                                  safely retired locally and on origin
                                  `v1-dry-run-baseline` preserved locally
                                  no unique history lost
```

R0-D completion condition: this checkpoint merged and verified on `main`. CONDITION SATISFIED — PR #3 merged on `main` at P3 = `24c95c029f583d5cc0b0a67986e48c06d0ef7957`; final-main push CI green (run 33240760167 SUCCESS). R0-D = COMPLETE.

Phase 14 integration condition: Phase 14A / 14A-R1 / 14B / 14C / 14D merged on `main`. CONDITION SATISFIED — PR #4 merged on `main` at P4 = `26c69bae9e482452f56f380277d8b10fefa29d52`; main push CI green (run 33320657978 SUCCESS). Phase 14 = COMPLETE.

## Next Functional Work

**Phase 14A / 14A-R1 / 14B / 14C are COMPLETE.**
**Phase 14D is COMPLETE (PR #4 merged). Valuation Budget Calibration remains NOT STARTED / NOT AUTHORIZED.**

### Completed — Phase 14D One-shot CLI cache composition + final validation

```text
implemented:
  scripts/run_live_scan_once.py
    LiveScanSettings exposes only the three cache-composition fields
      already supported by the factory
    create_steamdt_price_cache_runtime -> runtime.cache ->
      ScannerCachedBuffPriceResolver -> LiveScannerOrchestrator
    invalid cache config fail closed before any BUFF/SteamDT live work
    AsyncExitStack + runtime context for deterministic cleanup
    exactly one run_once; no scheduler; no write-after-live
  app/services/price_cache_factory.py
    narrow SteamDTPriceCacheSettings Protocol
    existing behavior preserved (in-memory default; optional Redis;
      zero-I/O construction; ownership; cleanup)
  tests/test_run_live_scan_once.py
    default in-memory composition injects strict scanner resolver
    redis settings reach existing factory seam
    invalid cache config fails before live work; no secret disclosure
    deterministic cleanup on success / RuntimeError / MemoryError /
      CancelledError / partial HTTP construction
    exactly one orchestrator; exactly one run_once; no write methods;
      no refresh service
    human output prints every Phase 14 counter group
    JSON shape preserves existing ScannerRunResult dataclass keys
    universe preview still forbids cache runtime / live client
  tests/test_price_cache_factory.py
    narrow protocol-backed composition; existing full Settings coverage

not implemented:
  scanner write-after-live
  scheduled / background refresh
  continuous scanner / scheduler
  scanner TTL environment or config setting

validated:
  full offline suite: 3428 passed / 23 skipped / 1 warning
```

### Completed — Phase 14B Run-scoped exact-name valuation reuse

```text
implemented:
  app/services/scanner_valuation_session.py
  reviewed scanner_orchestrator.py migration
  fresh session per run_once
  async prepare: memo-only, zero provider calls
  atomic NEW-LIVE exact-name cap admission
  execute: only NEW exact names
  exact success + terminal-failure reuse
  no same-name retry / no cross-run reuse
  existing ValuationService formula authority retained
  legacy logical counters preserved
  additive run_reuse/live/cache counters
  cache counters zero in 14B

validated:
  deep-pool two same-output recipes:
    20 logical valuation requests
    10 provider exact-name demand
    10 run-reuse hits
    cap 10 -> both fully valued
    cap 9 -> both atomically blocked; zero provider calls
  full offline suite: 3382 passed / 23 skipped / 1 warning

not implemented in 14B:
  persistent Phase12D scanner reads (completed by Phase 14C)
  scanner write-after-live
```

### Completed — Phase 14C Phase12D FRESH_ONLY cache READ integration

```text
implemented:
  optional scanner-owned resolver wrapper over cache-reader dependency
  raw SteamDTCachedPriceResolver structurally bound to strict selector
  generic cross-platform resolver rejected by public scanner API
  deterministic run memo -> sequential cache -> live order
  explicit PriceCacheReadPolicy.FRESH_ONLY
  scanner strict-BUFF adapter delegates to select_buff_output_price
  fresh SELECTED -> memo success
  fresh SELECTION_FAILURE -> memo terminal failure / no live fallback
  MISS / EXPIRED / POLICY_BLOCKED -> unmemoized NEW LIVE
  cache backend / codec / adapter / contract errors propagate
  cache outcome counters active
  cache memo survives atomic block; unresolved misses re-read
  no persistent writeback; no refresh service
  snapshot PriceCachePolicy remains writer-owned; no scanner TTL config

not implemented:
  default run_live_scan_once.py cache runtime/resolver composition (14D)
  scanner write-after-live
```

### Next — Phase 14D CLI composition + scale / bounded-live validation

```text
status:
  COMPLETE — see "Completed — Phase 14D" above
```

### Completed — Phase 15A Valuation Budget Calibration: offline measurement

```text
status:
  COMPLETE on feature/valuation-budget-calibration

measurement:
  primary metric = run_unique_output_names
  exact-name union across ordered default scanner recipe candidates
  empty persistent cache + fresh run memo interpretation
  current COHORT_DEPTH allocation and fixed default enumeration 2 / 256
  R-7 empirical quantiles with exact rational arithmetic

corpus:
  normalized pinned identity + metadata snapshots only
  structural census across eligible input cohorts / next-rarity pools
  deterministic synthetic offer-order replays through the real universe
    builder, scanner composition, recipe solver, and trade-up output engine
  no BUFF / SteamDT / Redis / .env / credentials
  synthetic orderings make no market-frequency claim

artifacts:
  research/valuation_budget_calibration/results.json
  research/valuation_budget_calibration/REPORT.md
  research/valuation_budget_calibration/{corpus,measurement,report}.py
  tests/test_valuation_budget_calibration.py

policy boundary:
  no max_valuation_requests_per_run default/hard-max/CLI change
  no atomic NEW-LIVE semantics change
  no production code change
  Phase 15B policy decision NOT STARTED / NOT AUTHORIZED
```

### Later — Phase 15B Valuation Budget Policy Decision

```text
status:
  NOT STARTED / NOT AUTHORIZED

scope:
  review Phase 15A structural and replay evidence
  obtain/assess the missing representative market-frequency evidence
  make a separate explicit policy decision, if authorized

constraints:
  Phase 15A reference thresholds are analysis only, not defaults
  no future numeric cap is implicitly authorized by Phase 15A
  the cap remains separately configurable
  CLI flag semantics and atomic NEW-LIVE semantics remain unchanged
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
git log main               (canonical main; historical branches
                           feature/buff-tradeup-scanner / feature/steamdt-data-source /
                           feature/steamdt-cache-rate-limit / repo/main-consolidation /
                           docs/r0c-completion-checkpoint were removed in R0-D
                           and are reachable as ancestors of main)
```