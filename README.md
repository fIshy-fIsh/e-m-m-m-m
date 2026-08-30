# CS2 BUFF Trade-up Opportunity Scanner

## What is this project?

A backend-first, **read-only** scanner that discovers CS2 (Counter-Strike 2) trade-up opportunities from BUFF marketplace listings, evaluates each opportunity against the canonical trade-up rules and a SteamDT-based output valuation, and exposes the result for human review.

The project performs **no** purchase, login, cookie capture, CAPTCHA bypass, BUFF risk-control bypass, or browser-automation actions. Every external API it touches is consulted anonymously or via an official Bearer token. The scanner outputs structured opportunity reports and never acts on them.

## Current status

```text
Phase:                                PHASE_14C_COMPLETE

Production scanner:                   bounded multi-recipe one-shot scanner
                                      with run-scoped exact-name reuse and
                                      optional FRESH_ONLY persistent cache reads

Default enumeration:                  2 candidates / 256 states

Active development line:              feature/scanner-valuation-integration

Latest production / test checkpoint:  Phase 14C branch commit
                                      (add scanner fresh-only price cache reads;
                                       verify exact SHA from Git)

Phase 14A design freeze:              e98cd97
Phase 14A-R1 coherence correction:    bb056e5

Pre-R0-C DEV tip:                     4c2f1ef
                                      (sync docs after minimum CI validation)

Post-R0-C main (historical ancestor): 9cfaf36
                                      (sync docs after R0-C repository consolidation)
                                      parents: {24ece858..., 3aa44e93...}
                                      tree: 7a39d28...

Post-R0-C docs checkpoint:            b13201b
                                      (sync docs after R0-C docs checkpoint, PR #2)

Canonical main after R0-D:            P3 = 24c95c029f583d5cc0b0a67986e48c06d0ef7957
                                      parents: {328269112..., 6964cc4...}
                                      tree:   608d3e473072afb0d97aadf46ea0be8b1f55ca26

Repository HEAD / branch / tree:      MUST be verified from Git at task entry;
                                      do not infer current HEAD from this file
```

The scanner is a **manual one-shot CLI**, not a 24/7 service. Continuous scheduling, Discord opportunity delivery, database persistence, and FastAPI operational endpoints are **not** part of this milestone.

## What works now

- **Live BUFF anonymous sell-order listing ingestion** through the documented anonymous read-only `sell_order` endpoint (research-validated field shape).
- **Pinned offline identity resolution** using the project-versioned community catalog (`market_hash_name ↔ BUFF goods_id`), wired in by `D-IDENTITY-007`. Identity binding is exact and fail-closed.
- **Pinned metadata enrichment** from the ByMykel-derived local snapshot (`data/metadata/skin_metadata_v1.json`); collection, rarity, min/max float ranges, paint-seed bounds. No runtime metadata network I/O.
- **StatTrak / Souvenir intrinsic classification** as a three-state input fact (`D-INTRINSIC-001` / `D-INTRINSIC-002` / `D-TRADEUP-001`). May 21, 2026 contract: normal and Souvenir inputs may coexist in the standard Trade Up Contract path; the resulting output is canonical non-Souvenir. StatTrak is independent and homogeneous/mode-matched.
- **BREADTH** market-universe allocation (default): round-robin across collections up to the hard cap of 10 goods IDs.
- **COHORT_DEPTH** market-universe allocation (opt-in): collection-local cohorts `(collection_name, input rarity, StatTrak)` ranked by eligible catalog capacity; default target of 3 cohorts.
- **Bounded multi-recipe enumeration** (`enumerate_recipe_selections` / `enumerate_scanner_recipe_selections`). Defaults to 2 candidates × 256 states. Hard bounds `1..6` candidates, `1..1024` states with `states >= candidates`.
- **Bounded search semantics**: baseline recipe first, then deterministic radius-one substitutions ordered by `(r-d, r, d, RecipeSelectionKey)`. No exhaustive combinations, no beam search, no financial ranking inside the solver.
- **Cross-candidate listing reuse**: the same `(source, goods_id, listing_id)` offer may appear across multiple candidate selections. Duplicate canonical offer identity fails closed before sort / cap / search.
- **Strict SteamDT BUFF valuation path** (`SteamDTBuffPriceProvider`): exact, case-sensitive `BUFF` aggregate sell price under the project-approved CNY/RMB interpretation. No fallback platform, no bid substitution, no fee/EV inside the price provider.
- **EV / ROI / worst-case loss / profit probability** from the existing `calculate_opportunity_metrics` authority.
- **Risk evaluation** under the configured `RiskFilterConfig` (default `min_roi=0.05`, `min_expected_profit_cny=20`, `max_worst_case_loss_pct=0.25`, `min_profit_probability=0.35`, `max_input_total_cost_cny=1000`).
- **Atomic NEW-LIVE valuation budget**: per-run hard cap `max_valuation_requests_per_run ∈ [1, 60]`, default 5. It counts NEW LIVE exact output names only. Stage A memo preparation performs zero provider calls; if NEW LIVE demand exceeds the remaining cap, the whole recipe is blocked before any provider work. Exact boundary is allowed; no partial execution.
- **Run-scoped exact-name valuation reuse and optional FRESH_ONLY cache reads** (`app/services/scanner_valuation_session.py`): every `run_once()` creates a fresh session. Stage A resolves in exact memo → optional Phase12D cache → live-demand order. The public scanner API accepts only a scanner-owned resolver wrapper whose internal raw `SteamDTCachedPriceResolver` is structurally fixed to `select_scanner_cached_buff_price`; generic cross-platform resolver composition is rejected. Fresh strict-BUFF successes and reason-preserving terminal selection failures enter the run memo; MISS, EXPIRED, and POLICY_BLOCKED become NEW LIVE demand. Selected outcomes independently require FRESH lookup state. Nothing in the run memo persists across runs.
- **Strict cached BUFF selection** (`app/services/scanner_cached_buff_price_selector.py`): cached candidates are re-evaluated through `select_buff_output_price`; the generic cross-platform selector is not scanner valuation authority. No bid, second-platform, or lowest-positive fallback.
- **One-shot live scanner CLI** (`scripts/run_live_scan_once.py`).

## What is not implemented

- **No production scheduler.** The historical APScheduler mock has not been wired against the live scanner.
- **No DB persistence path.** No opportunity, alert, scan-run, or listing history is written to PostgreSQL.
- **No real Discord opportunity delivery.** The `pipeline_alert_service` mock exists for unit tests; no Webhook integration is enabled.
- **No FastAPI operational surface** beyond the bare `/health` skeleton endpoint.
- **Default one-shot CLI cache composition is wired.** `scripts/run_live_scan_once.py` now constructs the existing Phase 12D cache runtime through `create_steamdt_price_cache_runtime`, hands `runtime.cache` to `ScannerCachedBuffPriceResolver`, and injects it into `LiveScannerOrchestrator`. Default backend is in-memory; Redis remains optional through the existing factory seam.
- **Scanner write-after-live is not implemented.** The scanner never calls cache `put` or `SteamDTPriceRefreshService`; the existing manual refresh stack remains the writer. Stored snapshot `PriceCachePolicy` is writer-owned, and the scanner adds no read-time numeric TTL setting.
- **No auto-universe live refresh / no listing history database.** Auto-universe planning is offline and offline-only by default (`--universe-preview` mode performs zero network calls).

## How is the scanner structured?

```text
BUFF anonymous listings
  -> identity binding                 (BuffCommunityIdentityResolver, pinned snapshot)
  -> intrinsic flag binding           (CanonicalNameIntrinsicFlagResolver, three-state facts)
  -> candidate adapter                (convert_buff_listing_to_candidate)
  -> TradeUpInputCandidate pool
  -> enrichment                       (TradeUpInputEnrichment, metadata + Decimal -> float)
  -> bounded automatic universe       (BREADTH or COHORT_DEPTH allocation; cap 10)
  -> enumerate_scanner_recipe_selections  (Phase 13T-2 composition adapter)
  -> enumerate_recipe_selections      (Phase 13T-1 bounded solver enumerator)
  -> calculate_tradeup_results        (existing trade-up engine)
  -> scanner valuation session prepare     (run memo -> optional FRESH_ONLY cache)
  -> strict cached BUFF selector            (select_buff_output_price authority)
  -> atomic NEW-LIVE demand admission
  -> scanner valuation session execute     (live provider for NEW exact names only)
  -> ValuationService.value_tradeup_results (existing valuation formula authority)
  -> SteamDTBuffPriceProvider              (live exact BUFF aggregate sell price)
  -> calculate_opportunity_metrics    (EV / ROI)
  -> evaluate_opportunity             (RiskFilterConfig policy)
  -> ScannerRunResult
```

The legacy `construct_scanner_recipe_selections` / `construct_recipe_selections` APIs remain available for compatibility but are **not** the production `run_once()` path.

## BUFF source — accurate wording

- Live anonymous BUFF sell-order listing path: **YES** (read-only, one-request, fail-closed research probe; not an official OpenAPI integration).
- Listing identity resolution: **pinned offline community catalog** (exact-name matching, fail-closed).
- Official authoritative BUFF identity / product / search API integration: **NO**. Endpoint paths, signing, response field mapping, and authoritative goods ID semantics remain tracked as TODOs in `docs/BUFF_API_NOTES.md`.
- No cookies are scraped, no CAPTCHA is bypassed, no BUFF risk control is bypassed, and no browser automation is used.

The system is **not** a "fully official BUFF integration". It is an anonymous-read-only listing ingestion seam over a pinned identity catalog, which is sufficient for the bounded multi-recipe scanner's current needs and matches the project's V1 non-goals.

## SteamDT source — accurate wording

Current production valuation path:

```text
recipe output market hash names
  -> RunScopedValuationSession.prepare_output_prices
       -> exact-name run memo first
       -> optional SteamDTCachedPriceResolver, explicit FRESH_ONLY, strict BUFF
       -> classify unresolved MISS / EXPIRED / POLICY_BLOCKED as NEW LIVE
  -> LiveScannerOrchestrator atomic NEW-LIVE cap admission
  -> RunScopedValuationSession.resolve_prepared
       -> SteamDTBuffPriceProvider.get_prices(NEW exact names only)
       -> aggregate client (GET /open/cs2/v1/price/single, official Bearer token)
       -> strict exact case-sensitive BUFF record selection
       -> full logical PriceLookupResult (memo + cache + live)
       -> existing ValuationService formula application
```

The aggregate SteamDT service is confirmed against the official documentation (base URL `https://open.steamdt.com`, Bearer-token authentication, response wrapper fields, price single / batch / avg / base / kline / wear endpoints). See `docs/STEAMDT_API_NOTES.md` for the full confirmed / TODO matrix.

Existing cache infrastructure and scanner read integration:

```text
PriceCache / InMemoryPriceCache / RedisPriceCache (Phase 12D)
SteamDTCachedPriceResolver (Phase 12D3B, read-only)
RunScopedValuationSession optional FRESH_ONLY resolver injection (Phase 14C)
scanner strict-BUFF cached selector (Phase 14C)
SteamDTPriceRefreshService / planner / executor (manual writer stack only)
```

Run-level cross-recipe exact-name reuse (Phase 14B), scanner service/session persistent cache READ support (Phase 14C), and default one-shot CLI cache composition (Phase 14D) are **implemented**. Scanner write-after-live, refresh, scheduler/background work, and any scanner TTL env/config remain unimplemented. `D-CACHE-001` is superseded for the original run-reuse + CLI composition gap; deferred write/refresh concerns remain separate future work.

The production one-shot CLI does **not** yet inject the cache resolver. Scanner write-after-live is absent. Freshness is evaluated by the backends from each stored snapshot's writer-owned `PriceCachePolicy`; there is no scanner read-time TTL knob, and the manual script's five-minute policy is historical writer precedent only.

## Safety boundaries (V1 hard constraints)

```text
NO automatic purchasing / auto-buy
NO automatic trading
NO automatic BUFF login
NO cookie scraping
NO CAPTCHA bypass
NO BUFF risk-control bypass
NO browser automation for purchasing
NO non-official anti-detection or evasion techniques
NO invented BUFF endpoints, signatures, parameters, or field mappings
NO fallback valuation (no second-platform substitute, no bid substitution, no metadata-zero reuse)
NO probability renormalization (no implicit rebalancing of solver-computed probabilities)
```

All external credentials (BUFF API key/secret, SteamDT API key, Discord Webhook URL) are read from `.env` only. They are never committed, never printed in logs, and never appear in unit-test fixtures.

## How do I run it?

### Prerequisites

```text
Python 3.12
pip install -e .[dev]
```

### Environment

Copy `.env.example` to `.env` and populate only what you need. Live SteamDT valuation requires `STEAMDT_API_KEY` and `STEAMDT_DRY_RUN=false`. BUFF anonymous listing ingestion does not require any credential.

### Help

```text
python -m scripts.run_live_scan_once --help
```

### One bounded one-shot scan (manual goods IDs)

```text
python -m scripts.run_live_scan_once \
    --goods-id <BUFF_GOODS_ID> \
    --goods-id <BUFF_GOODS_ID> \
    --max-valuation-requests 5
```

### One bounded one-shot scan (auto-universe, cohort-depth)

```text
python -m scripts.run_live_scan_once \
    --auto-universe \
    --allocation cohort-depth \
    --target-cohorts 3 \
    --max-goods-ids 10 \
    --rarity Restricted \
    --stattrak-mode normal \
    --souvenir include \
    --max-valuation-requests 5
```

The `--universe-preview` flag prints the auto-universe plan and exits before any network or client construction. Use it to verify the planned goods IDs offline.

### Validation

```text
ruff check .
mypy app
pytest
```

These three gates are the project's quality baseline. GitHub Actions enforces them on every push and pull request using Python 3.12 (`.github/workflows/ci.yml`). The default `pytest` suite is offline-safe; live and integration paths under `scripts/` remain explicitly opt-in and are not exercised by minimum CI.

## Project status at a glance

```text
What is this project?
  Read-only CS2 BUFF trade-up opportunity scanner with bounded
  multi-recipe enumeration over a pinned identity / metadata catalog
  and a strict SteamDT-BUFF output valuation path.

What works now?
  - live anonymous BUFF sell-order listing ingestion
  - pinned offline identity + metadata enrichment
  - StatTrak / Souvenir three-state intrinsic classification
  - BREADTH or COHORT_DEPTH auto-universe allocation
  - bounded multi-recipe enumeration (default 2 candidates / 256 states)
  - exact SteamDT BUFF aggregate sell valuation
  - EV / ROI / risk evaluation
  - one-shot CLI scanner with atomic NEW-LIVE valuation budget
  - run-scoped exact-name success/failure reuse across recipes
  - Phase 12D cache / refresh infrastructure (offline unit-tested)
  - optional scanner service/session FRESH_ONLY cache READ integration
    with strict-BUFF cached selection

What is not implemented?
  - production scheduler
  - database persistence
  - real Discord opportunity delivery
  - default one-shot CLI cache-resolver composition (Phase 14D)
  - scanner write-after-live

How is the scanner structured?
  See the data flow diagram under "How is the scanner structured?" above.

How do I run it?
  See "How do I run it?" above. One-shot CLI only.

What are the safety boundaries?
  See "Safety boundaries (V1 hard constraints)" above. No auto-buy,
  no login, no cookies, no CAPTCHA bypass, no BUFF risk-control bypass,
  no browser automation, no invented BUFF endpoints, no fallback
  valuation, no probability renormalization.

Where is the project in its roadmap?
  Phase 14C is complete on `feature/scanner-valuation-integration`.
  Phase 14B implemented one-run exact-name success/failure reuse and
  NEW-LIVE accounting; Phase 14C added optional scanner service/session
  FRESH_ONLY reads with strict-BUFF cached selection and no writeback;
  Phase 14D wired the default one-shot CLI cache composition with
  in-memory default and optional Redis through the existing factory.
  R0-A through R0-D are complete; canonical main remains P3 (`24c95c0...`).

What should happen next?
  Valuation Budget Calibration remains next and not authorized.
  Scanner write-after-live, refresh, scheduler/background work, and
  any scanner TTL env/config remain unimplemented and out of scope.
```

## Where to look next

```text
specs/roadmap.md             current roadmap structure (proposed, not authorized)
specs/mission.md             mission statement and V1 non-goals
specs/tech-stack.md          Python 3.12, FastAPI, Redis, PostgreSQL, SQLAlchemy 2.0, httpx, APScheduler, ruff, mypy, pytest
docs/ARCHITECTURE.md         current production architecture
docs/SPEC.md                 current functional requirements and non-goals
docs/BUFF_API_NOTES.md       BUFF API TODO matrix
docs/BUFF_LISTING_NOTES.md   BUFF listing contract notes
docs/STEAMDT_API_NOTES.md    SteamDT API confirmed / TODO matrix
docs/ai-context/README.md    AI-context documentation system entry point
docs/ai-context/PROJECT_CONTEXT.md     authoritative project state
docs/ai-context/ARCHITECTURE_STATE.md  authoritative module structure
docs/ai-context/DECISION_LOG.md        authoritative decision log
docs/ai-context/DEVELOPMENT_HANDOFF.md authoritative handoff
.env.example                 environment variable template
pyproject.toml               project metadata and tooling configuration
```

## Before enabling real BUFF / Discord / SteamDT integration

- Resolve the BUFF API TODOs in `docs/BUFF_API_NOTES.md`.
- Confirm the project is operating with all credentials sourced from `.env` only.
- Confirm the real Discord Webhook URL is a private channel and that alerts are an allowlisted summary only.
- Set `DRY_RUN=false` only after explicit review.
- Never commit `.env`.
- Run `ruff check .`, `mypy app`, and `pytest` against the current `main` branch before promoting to a new integration milestone.