# Phase 13T — Multi-Recipe Solver Migration Design / Protected-Core Audit Plan

## Status

- **Design and audit only.** No application implementation, test implementation, Protected Core edit, live request, commit, or push.
- **Date:** 2026-08-26.
- **Branch:** `feature/steamdt-cache-rate-limit`.
- **Baseline:** `d161ec43d47644751f874e85f796889506f0051a`, synchronized upstream.
- **Recommendation:** Option B — additive bounded enumerator in Protected Core with the exact existing API retained as a strict legacy `1 candidate / 1 state` projection.
- **Future search:** exact legacy baseline state explored first, followed—when budget remains—by bounded deterministic radius-one substitutions. A rejected baseline state does not terminate a larger-budget search.
- **Future input model:** alternative candidates may reuse listings; one recipe cannot duplicate a listing.
- **Limits:** default `2 / 256`; hard maximum `6 / 1,024` for returned candidates / explored states.

## Numbered task groups

### 1. Freeze and characterize the current protected contract

1. Record the exact public signatures and DTOs in `recipe_solver.py`.
2. Pin the existing eligibility, adjusted-float calculation, global ordering, per-collection retained-input cap, first-ten slice, output-pool construction, engine call, and exception behavior.
3. Preserve direct protected-engine legality separately from current scanner-domain legality.
4. Treat the existing first-ten tuple as the normative legacy baseline **state**. It becomes a baseline candidate only after successful existing-engine validation; preserve source listing IDs and item/result ordering on success.
5. Keep the existing `MemoryError` identity-propagation contract.

Deliverable: the current contract and one-selection ceiling in `requirements.md`, with exact code/test citations.

### 2. Freeze candidate identity and alternative-search semantics

1. Define canonical listing identity as `(source, goods_id, listing_id)` from original facts.
2. Define `RecipeSelectionKey` as the sorted ten-element multiset of canonical listing identities.
3. Keep solver input order separate from deduplication identity.
4. Reject market name, collection, price, float, and current `recipe_hash` as sufficient candidate identity.
5. Define new-enumerator duplicate-offer handling: after existing eligibility but before sort/cap/search, duplicate exact `(source, goods_id, listing_id)` raises the single explicit `ValueError("duplicate recipe offer identity")`; do not alter legacy API behavior.
6. Define same-listing permutations and temporary projection variants as duplicate candidates.
7. Define different listing IDs, one-listing changes, and different exact collection compositions as distinct candidates.
8. Permit overlap between alternative candidates because this is read-only counterfactual search, not inventory allocation.
9. Keep the disjoint older SteamApis construction/valuation path on the legacy API until a separately approved migration.

Deliverable: a stable identity and reuse contract before any enumerator implementation.

### 3. Design the bounded V1 search and API

1. Add, in a future implementation, an explicit `RecipeEnumerationConfig`, diagnostics DTO, result DTO, and `enumerate_recipe_selections(...)` API in `recipe_solver.py`.
2. Retain the exact existing `construct_recipe_selections(...)` signature, zero-or-one behavior, and malformed duplicate-input behavior. For eligible unique-offer inputs it must be value-equivalent to new enumeration under `max_recipe_candidates_returned=1` and `max_candidate_states_explored=1`, but it bypasses the stronger new-API duplicate-offer preflight.
3. Explore the exact existing first-ten baseline state first. A valid baseline becomes the first candidate; a rejected baseline consumes one state and larger-budget enumeration continues to alternatives.
4. Lazily enumerate radius-one states: replace one baseline input with one reserve input, ordered by `(rank_loss, reserve_rank, dropped_rank, RecipeSelectionKey)`.
5. Build the output pool once per enumeration invocation; call the existing engine once per explored unique candidate state.
6. Stop state generation immediately when either bound is reached; never generate all combinations and truncate later.
7. Return limit exhaustion as normal bounded completion with exact diagnostics.
8. Keep every price, EV, ROI, expected-profit, and risk fact out of core search.

Deliverable: proposed signatures, exact ordering, limits, diagnostics, and failure semantics in `requirements.md`.

### 4. Stage future Phase 13T-1 — Protected Core bounded enumerator

Future implementation scope:

```text
app/services/recipe_solver.py
tests/test_recipe_solver.py
```

Tasks:

1. Refactor existing eligibility/sort/cap/output-pool work into shared internal authority without changing its observable legacy result.
2. Implement lazy greedy-first radius-one enumeration and canonical-key deduplication.
3. Validate exact-integer limits and absolute hard maxima.
4. Implement the new API's fail-closed duplicate-offer preflight after eligibility and before sort/cap/search; raise exact `ValueError("duplicate recipe offer identity")` without changing the legacy path.
5. Preserve the legacy function as an exact behavior path. For eligible unique-offer inputs, prove it equals the new enumerator under `1/1`; for duplicate eligible offers, prove only the new API raises while the legacy behavior is unchanged.
6. Preserve `construct_recipes(...)` and `solve_recipes(...)` as zero-or-one legacy APIs.
7. Prove exact baseline-state/result compatibility over all historical fixtures, including baseline engine rejection under strict `1/1`.
8. Add a larger-budget case where a rejected baseline is followed by a valid alternative.
9. Add limit, state accounting, duplicate suppression, invalid-alternative, deterministic ordering, and `MemoryError` tests.
10. Do not integrate scanner composition yet.

Exit criterion:

For every existing characterization fixture with eligible unique offer identities:

```text
construct_recipe_selections(...)
== list(
    enumerate_recipe_selections(
        ...,
        enumeration_config=RecipeEnumerationConfig(
            max_recipe_candidates_returned=1,
            max_candidate_states_explored=1,
        ),
    ).selections
)
```

A separate duplicate-offer characterization proves the new API fails closed while the legacy API retains its pre-migration result.

### 5. Stage future Phase 13T-2 — Scanner composition adaptation

Future implementation scope:

```text
app/services/scanner_recipe_composition.py
tests/test_scanner_recipe_composition.py
```

Tasks:

1. Add an enumeration-aware scanner composition entry point while preserving the current compatibility function.
2. Allocate one aggregate invocation-wide candidate/state budget across active normal and StatTrak buckets without doubling limits. Freeze the quotient/remainder fair split: `P=min(active_buckets, C)` participating buckets, candidate quotas split from `C`, and state quotas split from `S-P` after reserving one baseline state per participant; earlier buckets receive remainders.
3. Compose successful per-bucket results globally by structural returned depth in current `normal → StatTrak` order: successful baseline candidates at depth 0, then successful alternatives at depth 1 onward. Use `baseline_state_rejected` to avoid misclassifying a bucket's first returned alternative as a baseline. Rejected/absent states do not occupy returned depth or reorder later successful alternatives within a bucket.
4. Reuse the existing temporary Souvenir projection and current canonical output eligibility.
5. Rehydrate and validate exact original `InputItem` facts for **every** returned candidate.
6. Deduplicate on original listing identity, never projected objects.
7. Permit nine-of-ten and other cross-candidate listing reuse while forbidding duplicate input identity within one candidate.
8. Add per-bucket and aggregate structural diagnostics, including truthful baseline-state rejection.
9. Test all required fair-split examples, no quota redistribution, returned-depth global ordering, and aggregate usage bounds.
10. Keep ordinary fixed boundary errors and verbatim `MemoryError` propagation.

Exit criterion: multiple candidates from one bucket are deterministic, projection-safe, and mode-correct; aggregate quotas and global order are exact; the compatibility wrapper remains current scanner zero/one-per-bucket behavior.

### 6. Stage future Phase 13T-3 — Orchestrator and valuation-budget integration

Future implementation scope:

```text
app/services/scanner_orchestrator.py
scripts/run_live_scan_once.py
tests/test_scanner_orchestrator.py
tests/test_run_live_scan_once.py
```

Tasks:

1. Require explicit finite recipe-candidate and search-state limits at the orchestrator boundary; CLI defaults remain `2 / 256` and hard maxima `6 / 1,024`.
2. Validate before any client/provider/network construction.
3. Consume candidates in deterministic enumeration order.
4. Preserve the existing all-or-nothing per-recipe valuation budget check and hard maximum of 60.
5. Keep recipe generation unaware of SteamDT budget, quotes, prices, EV, ROI, and risk.
6. Add exact structural enumeration counters and diagnostics without logging candidate keys or listing details.
7. Preserve complete-valuation gates, metrics, risk, evaluation order, opportunity ordering, failure isolation, and `MemoryError` behavior.
8. Test fake-provider multi-candidate runs, cumulative request blocking, deterministic ordering, and unchanged read-only safety.
9. Do **not** add run-level price caching in this stage; record shared output lookups as a separate optimization phase.

Exit criterion: N bounded candidates can flow through fake-provider valuation without exceeding the existing request guard or changing domain mathematics.

### 7. Stage future Phase 13T-4 — Offline gate, one bounded live validation, and documentation

Future implementation scope:

1. Add explicit solver/composition scale fixtures for retained pools of `10`, `30`, `50`, `94`, `100`, and at least one `100+` case.
2. Add a two-mode case proving independent legal buckets under one aggregate invocation limit.
3. Verify returned candidates and explored states never exceed configured bounds.
4. Verify no exhaustive combination materialization using a guarded lazy state iterator plus an AST supplementary guard.
5. Verify storage is bounded by retained inputs, explored-key bound, and `returned × 10`, not `C(n,10)`.
6. Preserve the existing synthetic candidate/enrichment scale gate; do not weaken or misrepresent it as solver-scale coverage.
7. Run the complete offline regression suite and static gates before any live activity.
8. After separate authorization and only if every offline gate passes, perform exactly one bounded live validation using the reviewed hard goods-ID and valuation-request limits; do not retry, tune, raise a cap, or perform a comparison scan.
9. Record exact enumeration, BUFF, valuation, opportunity, and no-write counters; a recipe/profit gain is evidence, not a correctness condition.
10. Update architecture/decision/handoff documents only from the implemented and observed facts; do not claim run-level caching or scheduler support.

Exit criterion: bounded behavior is proven structurally at and above the Phase 13S observed 94-input size, then one authorized live run confirms the integrated one-shot path without changing safety, domain, or financial policy.

## Future required test matrix

### Legacy and identity

- `max=1/state=1` reproduces the exact legacy selection and engine results.
- Exactly ten eligible listings still produce exactly one candidate.
- Same ten listing identities in any permutation deduplicate.
- Same market names/economics with different listing IDs remain distinct.
- One listing changed yields a distinct candidate.
- Different exact collection composition yields a distinct candidate while mixed collections remain legal.
- Temporary Souvenir projection cannot create a duplicate candidate.
- Existing `recipe_hash` is not used as enumeration identity.
- Duplicate eligible canonical offer identity fails closed in the new enumerator before search; same textual listing ID under a different source/goods identity follows the full canonical key.

### Enumeration and ordering

- Baseline state is always explored first; when valid it produces the exact legacy greedy candidate, and when rejected larger-budget search continues while `1/1` remains exactly empty.
- Candidate 2 after a valid baseline is `P0..P8 + P10` in existing solver order.
- Radius-one alternatives follow exact rank-loss order.
- Alternative candidates may reuse listings.
- No candidate repeats an exact listing internally.
- Candidate hard limit and explored-state hard limit stop generation, not post-materialization truncation.
- Limit exhaustion returns truthful normal diagnostics.
- Same input/config produces value-identical ordered results and diagnostics.

### Domain correctness

- No StatTrak mixing; mode-matched outputs.
- Normal/Souvenir current composition remains legal and output remains canonical non-Souvenir.
- Exact projection rehydration for every emitted candidate.
- Mixed collections remain legal.
- Existing collection probabilities are identical for each selected ten-item set.
- Existing adjusted/input/output float validation and formula are reused.
- Invalid candidate states do not bypass engine validation.
- `MemoryError` propagates by identity through enumerator, composition, and orchestrator.

### Scale and orchestration

- Pool sizes `10`, `30`, `50`, `94`, `100`, `101+`.
- One aggregate limit across normal/StatTrak buckets, with exact quotient/remainder candidate and reserved-baseline state quota splits.
- Global returned order is depth-interleaved over successful bucket sequences; rejected states consume state quota only.
- At most six returned candidates and at most 1,024 explored states under hard configuration.
- No `list/tuple/set/sorted(combinations(...))` or equivalent exhaustive state materialization.
- Fake valuation provider is never called beyond the current request budget.
- A later candidate that cannot fit the remaining budget is blocked before any partial lookup.
- Shared output names remain repeated logical/service requests until a separate cache phase changes that contract.

## Integration impact table

| File | Symbol | Current assumption | Required future migration | Protected Core |
|---|---|---|---|---|
| `app/services/recipe_solver.py` | `construct_recipe_selections` | One first-ten slice; zero/one result | Add bounded enumeration authority; retain exact legacy behavior and require `1/1` equivalence on eligible unique-offer inputs | YES |
| `app/services/recipe_solver.py` | `construct_recipes`, `solve_recipes` | Legacy zero/one construction | Remain on legacy API; no silent multiplicity | YES |
| `app/services/tradeup_engine.py` | `calculate_tradeup_results` | Validates/calculates one exact ten-item recipe | Reuse once per explored unique state; no formula change | YES |
| `app/services/scanner_recipe_composition.py` | `construct_scanner_recipe_selections` | One legacy solver call per StatTrak bucket; loops over returned list | Add bounded composition API, aggregate mode budget, and rehydrate every selection; retain compatibility wrapper | NO |
| `app/services/scanner_recipe_composition.py` | `_build_solver_projection`, `_rehydrate_selection` | Solver-only Souvenir projection; exact one-selection-safe logic | Reuse for every candidate; key/dedupe on original identities | NO |
| `app/services/scanner_orchestrator.py` | `LiveScannerOrchestrator.run_once` | Already loops over all selections; cumulative logical request cap | Supply explicit enumeration limits/diagnostics; preserve sequential valuation and budget | NO |
| `app/services/scanner_orchestrator.py` | `LiveRecipeEvaluation`, `ScannerRunResult` | Can hold many evaluations but no enumeration diagnostics/key | Add structural counts/diagnostics only as needed; keep exact recipe provenance | NO |
| `app/services/valuation_service.py` | `value_tradeup_results` | Dedupes names within one call only | No enumeration change; no caching in this migration | YES |
| `app/services/live_recipe_valuation.py` | `value_live_recipes`, result DTOs | Supports sequential recipes but requires global source-ID disjointness | Remain on legacy/disjoint path unless separately migrated | YES |
| `app/services/live_recipe_construction.py` | `construct_live_recipes`, result DTO | Iterates returned lists but rejects cross-recipe source-ID reuse | Keep calling legacy API for this scanner-focused migration | NO |
| `app/services/steamdt_buff_live_recipe_fixture.py` | fixture builder/validator | Requires exactly one selection and supplies exactly ten inputs | Keep legacy API and exact fixture contract | NO |
| `app/services/ev_service.py` | `calculate_opportunity_metrics` | Calculates one valued recipe | Invoke unchanged per complete candidate | YES |
| `app/services/risk_filter.py` | `evaluate_opportunity` | Evaluates one complete recipe with original facts | Invoke unchanged after rehydration/valuation | YES |
| `scripts/run_live_scan_once.py` | CLI config/output | No enumeration limits or diagnostics | Future explicit flags/defaults and no-client preflight validation | NO |

## Existing test disposition

### Must remain unchanged

- trade-up legality, mixed-collection probability, float, wear, and probability-sum tests;
- EV and risk primitive tests;
- exact current Souvenir projection and rehydration tests;
- provenance conflict/duplicate/atomicity tests;
- complete valuation and missing-price tests;
- all existing `MemoryError` identity tests;
- exact-ten-input tests expecting one candidate;
- exact public legacy signatures;
- SteamDT deterministic one-recipe fixture.

### Should be generalized or supplemented

- 11-input tests that assert only the first ten survive;
- one-engine-call tests for the new API (legacy call remains one; enumerator becomes once per explored state);
- one-result tests using pools larger than ten;
- live construction tests only if/when that disjoint path is separately migrated;
- composition tests that inspect only selection zero;
- orchestrator one-evaluation counters/indexing;
- Phase 13S language that describes the old ceiling as permanent after implementation lands.

### New migration tests required

Use the full matrix in task group 7. Existing test anchors are cataloged in `requirements.md` and the Phase 13T final audit report.

## Scale strategy

The existing `tests/test_synthetic_scanner_scale_validation.py` is a candidate/enrichment/engine seam test, not a recipe-solver enumeration scale test. Its current fixtures total 50 candidates and the driver calls the engine by collection rather than the recipe solver. It must remain a historical gate, while Phase 13T-4 adds dedicated solver-scale coverage.

Structural scale proof must use:

1. an internal lazy state-stream seam with a deterministic pull counter;
2. a test iterable that raises if consumed past the configured state bound;
3. exact diagnostic assertions;
4. an AST guard against obvious exhaustive combination materialization;
5. a sentinel `MemoryError` raised at a known explored state and checked by identity;
6. no wall-clock threshold as the primary algorithmic proof.

## Rejected alternatives

- **Extend legacy API:** rejected due to exact signature/semantic compatibility.
- **Repeated non-Protected wrapper:** rejected due to repeated work, coverage gaps, order dependence, confused reuse semantics, and projection-boundary ownership.
- **Exhaustive combinations:** rejected by trillions of combinations at observed scale.
- **Sliding windows:** rejected for adjacency/coverage bias.
- **Beam/best-first:** rejected because they require an unproven structural or forbidden financial score.
- **Disjoint candidate allocation:** rejected because the scanner evaluates alternatives rather than reserving inventory.
- **Run-level price cache inside solver migration:** rejected as a separate freshness/accounting concern.

## Phase 13T completion boundary

This design phase is complete when:

1. `requirements.md`, `plan.md`, and `validation.md` agree on Option B, candidate identity, reuse, radius-one search, ordering, limits, diagnostics, failures, scale, and staged ownership.
2. Every code-derived claim has exact repository evidence.
3. No application, script, test, AI-context, roadmap, configuration, snapshot, or research file changed.
4. No external request occurred.
5. Nothing is staged, committed, or pushed.

Do not begin Phase 13T-1 without a separate user-approved implementation phase and Protected Core migration authorization.
