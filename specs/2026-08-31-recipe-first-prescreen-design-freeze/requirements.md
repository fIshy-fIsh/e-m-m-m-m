# Phase 16A — Recipe-first Pre-screen Architecture Design Freeze

## Requirements

## 1. Problem statement

The current production scanner is a goods-first discovery brain.
`MarketUniverseBuilder` chooses a bounded set of BUFF `goods_id`s
(`BREADTH` / `COHORT_DEPTH`, cap 10) CLI-side. Only then does
`LiveScannerOrchestrator.run_once` fetch BUFF anonymous listings,
bind identity/intrinsics, enrich metadata, run bounded multi-recipe
enumeration (`2 / 256`), apply strict SteamDT-BUFF final valuation,
and run existing EV / risk.

Phase 15A measured that under default COHORT_DEPTH / `2 / 256` the
per-run `run_unique_output_names` reaches `max = 95`. That confirmed
the goods-first brain can spend almost a full hard max of 60
NEW LIVE exact-name demands on a single run. Phase 15B froze:
default 5, hard max 60, no production change, no policy claim from
designed replay quantiles.

The remaining inefficiency: the scanner fetches BUFF listings before
it knows whether the resulting structural recipe is even ranked
promising. We need to invert the discovery order:

```text
OLD: structural goods selection -> BUFF first -> recipes later
NEW: structural recipes first
       -> SteamDT batch market-data pre-screen
       -> rank
       -> BUFF only for promising families
       -> exact concrete recipe
       -> strict final valuation
```

The pre-screen may be approximate. The final opportunity path may
not. The mature downstream calculation/safety stack stays
unchanged.

## 2. Goals

- Freeze the next discovery architecture in a docs-only checkpoint.
- Reuse the existing mature downstream calculation/safety stack
  (trade-up engine, float math, strict SteamDT-BUFF valuation,
  Phase 14B run-scoped exact-name reuse, Phase 14C FRESH_ONLY
  cache reads, EV / risk, `RiskFilterConfig`).
- Replace the current goods-first discovery brain with a
  recipe-first structural family model.
- Add an offline SteamDT batch pre-screen that produces
  approximate ranking / pruning evidence only.
- Make BUFF acquisition family-targeted, bounded, and exact-pinned.
- Preserve all existing safety contracts:
  - read-only market interaction in V1;
  - exact pinned identity only, no fuzzy / casefold / alias;
  - no invented BUFF endpoints, signatures, parameters, mappings;
  - no auto-buy / no auto-login / no cookie scraping / no CAPTCHA
    bypass / no BUFF risk-control bypass / no browser automation;
  - no second-platform fallback / no biddingPrice substitution /
    no metadata-zero reuse / no probability renormalization;
  - `MemoryError` propagation verbatim per `D-MEMORY-001`;
  - production default `5`, hard max `60` unchanged.

## 3. Non-goals (this phase)

- No implementation of the new production path.
- No production code change of any kind.
- No new live request / refresh / scheduler / background task.
- No test code change.
- No CI / workflow / dependency / configuration change.
- No Phase 15C-3 representative campaign execution.
- No promotion of historical `steamapis_*` paths into production.
- No invented BUFF / SteamDT details that are not already
  documented in `docs/BUFF_API_NOTES.md` /
  `docs/STEAMDT_API_NOTES.md` /
  `docs/BUFF_LISTING_NOTES.md`.
- No change to `MarketUniverseBuilder`'s structural / eligibility /
  hard-request / goods_id mapping role (kept as a fallback utility).

## 4. Current vs target data flow

```text
CURRENT (production):
  MarketUniverseBuilder
    -> bounded goods_ids (cap 10; BREADTH default / COHORT_DEPTH opt-in)
    -> BUFF anonymous page-1/default-sort listings (one goods_id per request)
    -> BuffCommunityIdentityResolver (pinned offline community catalog)
    -> CanonicalNameIntrinsicFlagResolver (three-state StatTrak / Souvenir)
    -> convert_buff_listing_to_candidate
    -> TradeUpInputCandidate pool
    -> TradeUpInputEnrichment (pinned metadata + Decimal -> float)
    -> enumerate_scanner_recipe_selections (Phase 13T-2)
    -> enumerate_recipe_selections (Phase 13T-1; default 2 / 256)
    -> calculate_tradeup_results
    -> ValuationService.value_tradeup_results
    -> SteamDTBuffPriceProvider (strict exact BUFF sell-price)
    -> calculate_opportunity_metrics
    -> evaluate_opportunity
    -> ScannerRunResult / LiveOpportunity

TARGET (frozen next architecture):
  pinned CS2 metadata + pinned BUFF identity
    -> RecipeFamilyGenerator
    -> static structural / output geometry
    -> static float feasibility
    -> SteamDT batch pre-screen (POST /open/cs2/v1/price/batch)
    -> RecipeFamilyPreScreenEconomics (optimistic / base / conservative)
    -> deterministic ranking / Top-N (TOP_RANKED_FAMILIES = 2)
    -> TargetedBuffScanPlanner (MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10; one active family per run)
    -> existing BUFF anonymous listing ingestion (page-1/default-sort only)
    -> existing identity / intrinsic / enrichment (reused)
    -> family-constrained concrete recipe search (reuses 2 / 256 solver)
    -> existing strict final SteamDT-BUFF valuation
    -> existing EV / risk
    -> opportunity report (LiveOpportunity)
```

## 5. Invariants

The frozen architecture MUST preserve, in addition to the existing
contracts above:

- `RecipeFamily.collection_counts` sums exactly to 10.
- `RecipeFamily` distinct collections <= `MAX_DISTINCT_COLLECTIONS_PER_FAMILY = 3` (PROJECT bound, not external API limit).
- `RecipeFamily.output_stattrak` is homogeneous with the input
  `stattrak_mode` (StatTrak mode IS a material family dimension).
- `RecipeFamily` canonical non-Souvenir output rule (May-2026
  standard rule).
- **Output structural identity is finish-level, not
  wear-row-level.** The pinned metadata snapshot expands one
  underlying CS2 finish into multiple wear-qualified
  `market_hash_name` rows (typically 5 normal wear bands per
  finish; some finishes are incomplete). Trade-up structural
  probability is a probability over output FINISHES, not over
  wear-qualified market rows.
- **Concrete output wear is NOT known at RecipeFamily generation
  time.** The exact wear-qualified `market_hash_name` for an
  output is resolved only after a wear scenario or a concrete
  output float is supplied (fail-closed from pinned
  finish + wear metadata). No fuzzy / name guessing.
- **Souvenir is NOT a RecipeFamily structural identity axis.**
  Normal and Souvenir inputs may coexist under the current
  standard contract; concrete selected inputs retain true Souvenir
  provenance through the existing temporary `souvenir=False`
  solver projection + exact rehydration seam. If a future targeted
  scan needs a Souvenir acquisition policy, it lives as a separate
  planner/runtime acquisition-policy field, not as family
  identity.
- Live BUFF acquisition is bounded by
  `MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10` per run (PROJECT
  safety bound, NOT a BUFF external limit).
- Top-N ranking is a ranking / fallback signal, NOT a live request
  multiplier: `TOP_RANKED_FAMILIES = 2`, but at most ONE family is
  active for one live targeted BUFF scan per run, with family #2
  allowed only as a fallback BEFORE any BUFF request starts. Once
  any BUFF page request starts, family switching in that run is
  forbidden. Total BUFF page requests per run is
  `<= MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10`.
- New LIVE exact-name demands remain inside the existing
  `HARD_MAX_VALUATION_REQUESTS_PER_RUN = 60` and existing default
  `5`. Phase 14B run-scoped exact-name reuse and Phase 14C
  FRESH_ONLY cache reads stay valid.
- Pre-screen is approximate; it NEVER produces a
  `LiveOpportunity`; it NEVER passes the existing
  `RiskFilterConfig`.
- Pre-screen uses a new `RecipeFamilyPreScreenEconomics` DTO;
  it does NOT reuse `OpportunityMetrics`.
- SteamDT batch pre-screen uses only the strict BUFF selector
  (case-sensitive platform = "BUFF", positive finite sellPrice,
  one BUFF record per name; duplicate BUFF records fail closed;
  missing or unusable BUFF record fails the family closed).
- Pre-screen NEVER uses `biddingPrice`, NEVER substitutes a
  second platform, NEVER picks the lowest price across platforms.
- SteamDT `sellCount` and `updateTime` are retained as diagnostics only.
  `updateTime` has normalized type `int | str | None`; its timestamp
  format and semantics remain unconfirmed, so it MUST NOT be parsed,
  chronologically compared, called freshness proof, or used as a
  Phase 16D ranking key.
- Phase 16C exact interval-union and reachable finish/wear evidence
  is the static feasibility authority. Phase 16D uses it as a gate
  and structured evidence; it MUST NOT regress to a universal
  `static_float_margin_vs_threshold` scalar.
- No pre-screen call may exceed `batch-size = 10` until official
  SteamDT documentation confirms a larger limit.
- RecipeFamily enumeration order is deterministic
  (`input_rarity`, `stattrak_mode`, sorted `collection_counts`,
  `family_hash`).
- Duplicate `(input_rarity, stattrak_mode, collection_counts)`
  families are suppressed.
- `RecipeFamily.family_key = first 24 lowercase hex chars of
  family_hash = SHA-256 of canonical sorted UTF-8 bytes`.
- Canonical serialization: keys sorted, no whitespace, exactly
  one trailing newline; canonicalize(bytes) is its own inverse.

## 6. Functional requirements (16B-16F scope, NOT 16A implementation)

- 16B: `RecipeFamily` domain + deterministic generator +
  structural output geometry, OFFLINE ONLY.
- 16C: static float feasibility + SteamDT batch pre-screen
  adapter/resolver; mocked transport / offline tests; NO live BUF.
- 16D: coarse economics DTO + ranking + `TargetedBuffScanPlan`;
  OFFLINE integration.
- 16E: family-constrained concrete solver integration +
  orchestrator composition behind an explicit opt-in; OFFLINE
  end-to-end validation; preserves Phase 14B / 14C semantics.
- 16F: ONE bounded live read-only validation; only after all
  offline gates pass; fixed campaign identity; fixed stratum;
  fixed window; at most 10 BUFF page requests; zero retries;
  artifact OUTSIDE Git; NO PR/merge.

## 7. Safety

- The new architecture MUST NOT introduce any auto-buy, auto-login,
  cookie extraction, CAPTCHA bypass, BUFF risk-control bypass, or
  browser automation path.
- The new architecture MUST NOT introduce any secret / cookie /
  token / `.env` / webhook URL access or disclosure.
- The new architecture MUST NOT introduce any non-official
  anti-detection / evasion technique.
- The new architecture MUST NOT introduce any invented BUFF
  endpoint, signature, request parameter, or response field
  mapping.
- Pre-screen is approximate and MUST NEVER claim executability.
- Live smoke (Phase 16F) is bounded and requires a separate
  authorization.

## 8. Determinism

- All RecipeFamily enumeration is deterministic for identical
  pinned metadata + pinned identity inputs.
- All pre-screen outputs (feasibility, economics scenarios,
  ranking, scan plans) are deterministic for identical
  inputs and identical SteamDT batch responses.
- All hash / key / canonicalization functions are pure and
  produce stable, testable bytes.
- RecipeFamily enumeration MUST support a lazy deterministic
  iterator/generator that yields families one at a time without
  eagerly materializing the full state space (9,972,412 theoretical
  states across the eight productive strata at K=3 under the
  authoritative Phase 16B eligibility gates). Theoretical
  family-space counts are analytic evidence, not eager-
  materialization authorization.
- Ranking MUST support streaming / top-K evaluation without
  retaining all family DTOs simultaneously.
- SteamDT pre-screen transport MUST deduplicate exact
  `market_hash_name`s before issuing any batch call.

## 9. Failure behavior

- Identity / metadata / external response parse / typed errors
  fail closed.
- Missing or unusable BUFF record in SteamDT batch pre-screen
  fails the affected family closed (`FAIL_CLOSED` reason code).
- Duplicate BUFF records in SteamDT batch response fail closed.
- `MemoryError` propagates verbatim at every layer per
  `D-MEMORY-001`.
- Pre-screen failure for one family never crashes the whole
  pre-screen; failure is isolated with diagnostics and reason codes.
- Hard-cap violations fail closed before any BUFF / SteamDT
  live work.

## 10. Phase 15C-3 defer decision

- Phase 15C-1 protocol remains valid historical / calibration work.
- Phase 15C-2 tooling and Phase 15C-2B smoke remain preserved.
- Phase 15C-3 representative 14-day / 112-attempt campaign is
  DEFERRED until recipe-first production discovery path is
  implemented (16B / 16C / 16D / 16E) and bounded-live validated
  (16F).
- Reason: recipe-first discovery is expected to materially change
  which families reach BUFF and downstream valuation-demand
  distribution; the Phase 15C-3 campaign must run under the new
  production path, not the goods-first one.
- Production default remains `5`; hard max remains `60`.
- No claim that Phase 15A designed / Phase 15C-1 sampled
  distributions represent future recipe-first production workload.
- Phase 15 evidence MUST NOT be deleted or rewritten.