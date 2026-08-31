# Phase 16A — Recipe-first Pre-screen Architecture Plan

## 1. Scope

Phase 16A is a DESIGN-FREEZE ONLY phase. No production code
change. No new live request / refresh / scheduler path. No
test change. No CI / workflow / dependency / configuration
change.

This plan records the staged implementation sequence for the
NEW production path that Phase 16A freezes, plus the
re-validation of Phase 15C-3 under that new path.

## 2. Stage 16B — RecipeFamily domain + deterministic generator + structural geometry

Status: NOT STARTED / awaiting separate authorization.

Scope:

- Introduce `RecipeFamily` dataclass, frozen DTO, canonical
  serialization, deterministic SHA-256 `family_hash` /
  `family_key` derivation.
- Introduce `RecipeFamilyGenerator`:
  - inputs: pinned CS2 metadata snapshot + pinned BUFF community
    identity snapshot + `StatTrakMode` + `SouvenirInclusion`;
  - output: deterministic ordered tuple of `RecipeFamily`.
- Hard bound `MAX_DISTINCT_COLLECTIONS_PER_FAMILY = 3`.
- Reuse `app.services.metadata_service.get_next_rarity` for
  `output_rarity`.
- Reuse `app.services.scanner_recipe_composition.is_current_standard_trade_up_output_eligible`
  for canonical output non-Souvenir eligibility.
- Reuse existing probability authority; do not fork.
- OFFLINE ONLY. No I/O. No network. Pure functions.

Validation:

- `tests/test_recipe_family_domain.py`:
  - structural invariants (sum == 10; distinct collections bound;
    canonical non-Souvenir output rule),
  - canonical serialization roundtrip / hashing determinism,
  - duplicate suppression,
  - deterministic enumeration order,
  - hash chain stability across reruns.

Gate: full offline suite, ruff, mypy app, git diff --check
against the protected-core boundary.

## 3. Stage 16C — Static float feasibility + SteamDT batch pre-screen adapter / resolver

Status: NOT STARTED / awaiting separate authorization.

Scope:

- `StaticFloatFeasibilityAnalyzer` (offline; no listing float):
  - inputs: RecipeFamily + per-output `(output_min,
    output_max)` + threshold `T`,
  - output: `StaticFloatFeasibilityResult`.
- `SteamDTBatchPreScreenAdapter`:
  - inputs: batch of exact wear-qualified `market_hash_name`s,
  - mocked transport for tests; NO live BUFF.
  - strict BUFF selector reusing
    `select_buff_output_price` semantics (case-sensitive
    platform = "BUFF", positive finite sellPrice, one BUFF
    record per name, missing or unusable BUFF record ->
    FAIL_CLOSED).
  - batch size hard cap `10` per request (PROJECT bound; not a
    confirmed SteamDT external limit).
- `RecipeFamilyPreScreenResult` DTO bundling feasibility +
  batch pre-screen outcome.

Validation:

- `tests/test_static_float_feasibility.py`:
  - `required_max_avg_adjusted` correctness against canonical
    float math,
  - structurally_feasible boundary cases,
  - reason codes.
- `tests/test_steamdt_batch_pre_screen_adapter.py`:
  - strict selector parity with `select_buff_output_price`,
  - missing / unusable BUFF record -> FAIL_CLOSED,
  - duplicate BUFF records -> FAIL_CLOSED,
  - batch-size cap,
  - never uses `biddingPrice`, never substitutes a second
    platform, never picks lowest across platforms,
  - mock-transport asserts NO live HTTP.

Gate: full offline suite, ruff, mypy app, git diff --check
against the protected-core boundary.

## 4. Stage 16D — Coarse economics + ranking + TargetedBuffScanPlan

Status: NOT STARTED / awaiting separate authorization.

Scope:

- `RecipeFamilyEconomicsCalculator`:
  - outputs `RecipeFamilyPreScreenEconomics` for optimistic,
    base, conservative scenarios;
  - DOES NOT reuse `OpportunityMetrics` for approximate values.
- `RecipeFamilyRanker`:
  - gates (structurally_feasible, batch-completed, no missing
    penalty, supporting wear band, request-count bound),
  - static lexicographic ranking keys,
  - exclusion reason codes,
  - Top-N bound `TOP_RANKED_FAMILIES = 2`.
- `TargetedBuffScanPlanner`:
  - inputs: ranked RecipeFamily tuple,
  - outputs `TargetedBuffScanPlan` per family,
  - `MAX_EXACT_GOODS_IDS_PER_PRESCREEN = 10`,
  - reuse `MarketUniverseBuilder` only for goods_id mapping /
    eligibility / hard-request bounds / diagnostics.
- OFFLINE integration. No I/O. No network.

Validation:

- `tests/test_recipe_family_economics.py`:
  - scenario consistency,
  - missing-price penalty path,
  - DTO separation from `OpportunityMetrics`.
- `tests/test_recipe_family_ranking.py`:
  - gate enforcement,
  - lexicographic sort stability,
  - tie-break by `family_hash`,
  - exclusion reason codes.
- `tests/test_targeted_buff_scan_planner.py`:
  - `MAX_EXACT_GOODS_IDS_PER_PRESCREEN` enforcement,
  - unresolved identity diagnostics,
  - goods_id mapping correctness via
    `MarketUniverseBuilder`.

Gate: full offline suite, ruff, mypy app, git diff --check
against the protected-core boundary.

## 5. Stage 16E — Family-constrained concrete solver integration + orchestrator composition behind explicit opt-in

Status: NOT STARTED / awaiting separate authorization.

Scope:

- `FamilyConstrainedConcreteSearch`:
  - filter listings to family-compatible candidate set,
  - reuse `enumerate_scanner_recipe_selections` with
    `RecipeEnumerationConfig(2, 256)`,
  - prove family-`collection_counts` match,
  - prove homogeneous `stattrak` + right `souvenir` projection,
  - duplicate listing identity fail-closed,
  - output `TradeupResult.output_market_hash_name` is among
    `family.represented_outputs`.
- Reuse `RunScopedValuationSession.prepare_output_prices` /
  `resolve_prepared` (Phase 14B) inside the existing atomic
  NEW-LIVE cap.
- Reuse `ScannerCachedBuffPriceResolver` (Phase 14C) FRESH_ONLY
  read seam unchanged.
- Reuse `calculate_opportunity_metrics` /
  `evaluate_opportunity` unchanged.
- New orchestrator composed ONLY behind an explicit opt-in
  flag (production default OFF). The current goods-first
  orchestrator remains the production path.
- OFFLINE end-to-end validation against pinned snapshots +
  synthesized BUFF listing fixtures.

Validation:

- `tests/test_family_constrained_concrete_search.py`:
  - family-counts match enforcement,
  - StatTrak homogeneity,
  - normal/Souvenir projection seam,
  - duplicate listing identity failure,
  - output identity set membership,
  - run-scoped atomic NEW-LIVE cap honored.
- `tests/test_recipe_first_orchestrator_composition.py`:
  - explicit opt-in path,
  - production default remains OFF,
  - offline-only fixtures.

Gate: full offline suite, ruff, mypy app, git diff --check
against the protected-core boundary.

## 6. Stage 16F — ONE bounded live read-only validation

Status: NOT STARTED / awaiting separate authorization.

Scope:

- Exactly ONE observation attempt.
- At most 10 BUFF anonymous page-1/default-sort requests.
- Sequential.
- Minimum 2-second request-start pacing.
- No retry / no polling / no pagination.
- Zero SteamDT / Redis / cache write.
- Zero `.env` / credential / cookie inspection.
- Artifact OUTSIDE Git.
- Fixed campaign identity; fixed stratum; fixed window.
- Commit `validate recipe-first prescreen interface`.
- NO PR / NO merge.

Validation: full offline suite + focused live smoke gating +
SHA-256 + canonical manifest + offline replay + protected
guards. Zero reuse of Phase 15C-2B smoke artifacts.

## 7. Phase 15C-3 re-scope

Status: DEFERRED until 16B / 16C / 16D / 16E are merged AND
16F passes.

Reason: recipe-first discovery is expected to materially
change which families reach BUFF and downstream valuation
demand distribution. Phase 15C-3 sampling must run under the
NEW production path, not the goods-first one.

Production default remains `5`; hard max remains `60`.
No claim Phase 15A / Phase 15C-1 distributions represent
future recipe-first production workload. Phase 15 evidence is
NOT deleted or rewritten.

## 8. Cross-stage invariants

Every stage MUST:

- preserve the V1 read-only / strict BUFF / no-fallback
  contracts;
- preserve `D-MEMORY-001` propagation;
- fail closed on identity / metadata / external response /
  typed errors;
- keep the mature downstream calculation/safety stack
  unchanged;
- keep production defaults unchanged (`5` / hard max `60`);
- keep `v1-dry-run-baseline` preserved;
- keep protected JSONs untouched and untracked;
- keep CI workflow blob `02d0ce81...` preserved.