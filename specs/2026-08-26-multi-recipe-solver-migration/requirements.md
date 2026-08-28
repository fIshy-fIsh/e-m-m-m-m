# Phase 13T — Multi-Recipe Solver Migration Design / Protected-Core Audit Requirements

## Status and authority

- **Date:** 2026-08-26.
- **Branch:** `feature/steamdt-cache-rate-limit`.
- **Verified baseline:** `d161ec43d47644751f874e85f796889506f0051a`, synchronized with its upstream (`0 0`).
- **Phase type:** design and repository audit only.
- **Implementation status:** no multi-recipe implementation has begun.
- **Protected Core status:** unchanged. A future implementation requires an approved Protected Core migration in `app/services/recipe_solver.py`.
- **Safety:** read-only scanner design only; no scheduler, market execution, login, Cookie, browser automation, risk-control bypass, or external request.

This specification follows `specs/mission.md`, `specs/tech-stack.md`, the current architecture records, and the exact current code. It supersedes no existing runtime contract in Phase 13T itself.

## Goal

Design the smallest safe migration from:

```text
one homogeneous solver invocation
→ zero or one greedy recipe selection
```

to:

```text
one homogeneous solver invocation
→ bounded deterministic sequence of alternative recipe candidates
```

without exhaustive `C(n, 10)` enumeration, without price/EV/risk-driven search, and without changing trade-up, float, probability, valuation, EV, ROI, or risk mathematics.

## Current protected solver contract

The authoritative current path is in `app/services/recipe_solver.py`:

1. `construct_recipes(...) -> list[ConstructedRecipe]` projects the recipes from `construct_recipe_selections(...)` ([recipe_solver.py:127-141](../../app/services/recipe_solver.py#L127-L141)).
2. `construct_recipe_selections(...) -> list[ConstructedRecipeSelection]` is the authoritative selection path ([recipe_solver.py:144-199](../../app/services/recipe_solver.py#L144-L199)).
3. `solve_recipes(...) -> list[RecipeCandidate]` calls construction once, then calculates metrics and risk once per construction ([recipe_solver.py:202-241](../../app/services/recipe_solver.py#L202-L241)).

### Inputs and outputs

```python
def construct_recipe_selections(
    candidates: list[CandidateListing],
    skins: list[SkinMetadata],
    solver_config: RecipeSolverConfig,
) -> list[ConstructedRecipeSelection]:
    ...
```

- `CandidateListing` carries `source`, `goods_id`, `listing_id`, exact/optional market identity, listing price and float, paint seed, and observation facts ([market_scan_service.py:9-34](../../app/services/market_scan_service.py#L9-L34)).
- `SkinMetadata` carries canonical name, rarity, collection, float bounds, StatTrak, and Souvenir catalog facts ([metadata_models.py:7-30](../../app/services/metadata_models.py#L7-L30)).
- `RecipeSolverConfig` fixes the recipe input count at exactly ten and provides rarity, fee, optional retained-input cap per collection, and optional intrinsic filters; it has no recipe-count or search-state limit ([recipe_solver.py:15-40](../../app/services/recipe_solver.py#L15-L40)).
- `ConstructedRecipe` contains exactly ten ordered `InputItem` values, nonempty ordered engine results, and compact ordered non-null paint seeds ([recipe_solver.py:42-76](../../app/services/recipe_solver.py#L42-L76)).
- `ConstructedRecipeSelection` adds listing IDs aligned one-to-one with the selected inputs; the DTO itself does not prove listing-ID uniqueness ([recipe_solver.py:78-103](../../app/services/recipe_solver.py#L78-L103)).

### Eligibility, sort, and greedy selection

The solver:

1. Builds an exact-name metadata dictionary; duplicate metadata names are last-wins for the legacy input lookup.
2. Skips candidates with unresolved identity, missing metadata/collection, wrong rarity, missing float, intrinsic mismatch, or invalid adjusted float.
3. Constructs `InputItem` from listing facts plus metadata facts ([recipe_solver.py:275-337](../../app/services/recipe_solver.py#L275-L337)).
4. Sorts ascending by `(adjusted_float, price_cny, market_hash_name, listing_id)` ([recipe_solver.py:341-352](../../app/services/recipe_solver.py#L341-L352)).
5. Applies `max_candidates_per_collection`, when configured, after the global sort ([recipe_solver.py:356-376](../../app/services/recipe_solver.py#L356-L376)).
6. Selects `eligible_pairs[:10]` once.
7. Builds the output pool once and invokes `calculate_tradeup_results(...)` once.
8. Returns a literal empty list or one-element list ([recipe_solver.py:151-199](../../app/services/recipe_solver.py#L151-L199)).

### Exact reason for the current ceiling

The ceiling is a combination of **A and E**, plus ordinary control-flow termination:

- **A — YES:** it greedily takes exactly the first ten retained pairs once.
- **B — NO:** it does not optimize or compare ten-item subsets; the first-ten slice is a deterministic heuristic, not an optimal-subset search.
- **C — NO explicit first-valid break:** there is no candidate loop to break. Control simply reaches the singleton return after one engine call.
- **D — NO:** it does not consume or mutate a working pool and rerun.
- **E — YES in implementation cardinality:** one invocation structurally returns at most one selection, although the public return type is plural.

The scanner composition calls this path once per sufficiently large StatTrak bucket, normal first and StatTrak second ([scanner_recipe_composition.py:50-111](../../app/services/scanner_recipe_composition.py#L50-L111)). Therefore each such homogeneous invocation currently yields at most one selection.

## Legal compatibility versus current heuristic

These categories MUST remain separate.

### Current game/domain legality at the scanner boundary

For a current standard Trade Up Contract candidate emitted by the scanner:

1. **Input count:** exactly ten.
2. **Rarity:** all ten have the same input rarity.
3. **StatTrak:** all ten share one StatTrak mode; normal and StatTrak never mix.
4. **Collections:** inputs from different collections may coexist. Collection is not a legal solver bucket.
5. **Souvenir:** normal and Souvenir inputs may coexist under the current May 21, 2026 rule. Candidate-owned Souvenir facts remain original facts.
6. **Outputs:** outputs are canonical non-Souvenir records matching the homogeneous StatTrak mode.
7. **Float:** each listing must have a valid actual float within its metadata input range; every emitted candidate is passed through the existing engine float/probability calculation.
8. **Identity:** one scanner run fails closed on duplicate listing IDs before solver composition; one recipe therefore contains ten exact, distinct current listing identities.

The current-rule Souvenir projection and exact rehydration are implemented in [scanner_recipe_composition.py:218-251](../../app/services/scanner_recipe_composition.py#L218-L251) and [scanner_recipe_composition.py:275-312](../../app/services/scanner_recipe_composition.py#L275-L312). Duplicate input identities fail closed at [scanner_recipe_composition.py:133-157](../../app/services/scanner_recipe_composition.py#L133-L157) and across acquired pages at [scanner_orchestrator.py:378-382](../../app/services/scanner_orchestrator.py#L378-L382).

### Historical Protected Core compatibility

The unchanged engine itself validates exactly ten inputs, one rarity, one StatTrak value, one Souvenir value, and an output pool for every represented collection ([tradeup_engine.py:107-134](../../app/services/tradeup_engine.py#L107-L134)). Scanner composition supplies a temporary `souvenir=False` view solely to cross that historical compatibility boundary, then rehydrates every selected original input.

The protected historical Souvenir-homogeneity check is not the current game-domain rule and MUST NOT be copied into a new enumeration policy.

### Current greedy heuristic, not legality

The following are selection heuristics only:

- adjusted float before price;
- lower input price before market name and listing ID;
- optional retained-input cap per collection;
- selecting only the first ten;
- returning only one selection.

No future requirement may mislabel those properties as legal compatibility.

## Candidate identity and canonical key

### Case decisions

| Case | Candidate identity decision | Reason |
|---|---|---|
| A — same ten exact listings, different order | **Same candidate** | Recipe identity is permutation invariant; solver order remains separately observable. |
| B — same market identities, different listing IDs | **Different candidates** | Exact listings can carry different prices, actual floats, total cost, and output-float geometry. Market name is not listing identity. |
| C — nine exact listings equal, one listing changed | **Different candidates** | The selected exact-listing multiset changed. |
| D — different collection composition | **Different candidates** | In practice the exact selected listing multiset changes; collection alone is not used as the key. |
| E — same exact ten listings under a temporary Souvenir projection | **Same candidate** | Projection is solver-only and must not alter original identity. |

### Frozen proposed `RecipeSelectionKey`

Within the current scanner, `listing_id` alone is unique because duplicate IDs fail closed. It is not a sufficiently source-agnostic public identity for the protected solver, because another source may reuse the same textual listing ID.

The minimum stable listing tuple already available on legacy `CandidateListing` is:

```python
RecipeListingKey = tuple[str, str, str]
# (source, goods_id, listing_id)

RecipeSelectionKey = tuple[RecipeListingKey, ...]
# exactly ten RecipeListingKey values in lexical sorted order
```

Properties:

- permutation invariant;
- independent of solver selection order;
- independent of temporary Souvenir metadata projection;
- deterministic and cheap (`10 ×` tuple construction plus sorting);
- collision resistant within one run under existing source/goods/listing contracts;
- based on original listing facts preserved by `_to_legacy_candidates(...)` ([scanner_recipe_composition.py:255-273](../../app/services/scanner_recipe_composition.py#L255-L273)).

The new enumerator applies a stronger public-boundary invariant before search: after existing eligibility has produced `_EligiblePair` values, but before sorting, collection limiting, output-pool construction, or state exploration, every eligible pair's `RecipeListingKey` must be unique. A duplicate raises exact `ValueError("duplicate recipe offer identity")`. Checking before the collection cap prevents that cap from hiding two copies of one physical offer. Candidates skipped by the unchanged eligibility rules never enter this new enumerator pool.

The enumerator MUST NOT silently deduplicate duplicate offers, treat them as separate physical inputs, or permit one returned key to contain the same exact offer twice. The existing legacy `construct_recipe_selections(...)` path deliberately does not acquire this stronger invariant; its behavior remains unchanged. Both public APIs may share private eligibility/construction helpers, but the legacy path must bypass the new duplicate-offer boundary check.

`asset_id` is not part of the minimum solver key because it is not present on `CandidateListing`; the marketplace offer (`source`, `goods_id`, `listing_id`) is the scanner candidate identity. If a future source proves listing IDs can mutate while retaining one offer identity, that source contract must be reviewed separately rather than adding mutable price/float/metadata facts to this key.

The existing `build_recipe_hash(...)` MUST NOT be reused as the candidate key. It omits source, goods ID, listing ID, and asset ID, and its ordering is not a complete canonical ordering over every serialized field ([recipe_solver.py:255-271](../../app/services/recipe_solver.py#L255-L271)).

## Input reuse contract

**Alternative candidates MAY reuse listings.**

Examples such as:

```text
A = L1 ... L10
B = L1 ... L9 + L11
```

represent counterfactual alternatives for human evaluation. The scanner does not buy, reserve, allocate, or consume inventory. Requiring disjointness would turn candidate search into inventory partitioning and would discard useful near-neighbor comparisons.

Invariants:

- no exact listing appears twice within one valid scanner recipe;
- the same listing may appear in multiple different returned candidates;
- reuse does not imply simultaneous executability;
- future presentation must label candidates as alternatives, not a purchasable batch.

The older SteamApis `LiveRecipeConstructionResult` and `LiveRecipeValuationResult` reject source-ID reuse across recipes ([live_recipe_construction.py:71-101](../../app/services/live_recipe_construction.py#L71-L101), [live_recipe_valuation.py:133-165](../../app/services/live_recipe_valuation.py#L133-L165)). They MUST remain on the legacy single-selection API unless a separate migration changes their disjoint-allocation semantics. Phase 13T’s recommended integration target is the current scanner path.

## Combination explosion

For one homogeneous pool of `n` distinct eligible listings:

```text
C(10,10)   = 1
C(20,10)   = 184,756
C(30,10)   = 30,045,015
C(50,10)   = 10,272,278,170
C(94,10)   = 9,041,256,841,903
C(100,10)  = 17,310,309,456,440
```

The observed Phase 13S pool of 94 inputs therefore makes exhaustive combination generation, sorting, or materialization unacceptable. “Generate all then truncate” is forbidden.

## Recommended bounded enumeration contract

### Limits

Use two independent exact-integer limits:

```text
proposed default max_recipe_candidates_returned: 2
proposed absolute hard maximum:                   6

proposed default max_candidate_states_explored:  256
proposed absolute hard maximum:                   1,024
```

Rationale:

- two candidates permit up to two successful unique states—for the common one-mode run, ordinarily a valid baseline candidate plus one alternative, while a rejected baseline state consumes exploration but not candidate quota;
- six candidates × the observed ten-name output universe equals the existing hard maximum of 60 logical valuation lookups, while the valuation guard remains authoritative because output count is not universally ten;
- a radius-one neighborhood contains `1 + 10 × (n - 10)` states, so 94 inputs produce 841 states and 100 inputs produce 901 states, both below the hard state maximum;
- default 256 prevents large searches by default while allowing rejected/duplicate states without making candidate count and exploration count synonymous.

Validation MUST reject `bool`, non-integers, values outside each range, and:

```text
max_candidate_states_explored >= max_recipe_candidates_returned
```

is a required configuration invariant. The aggregate scanner quota split in turn guarantees:

```text
state_quota[i] >= candidate_quota[i]
```

for every participating bucket.

### Aggregate scanner budget allocation

Let active buckets be those current StatTrak-mode buckets that have at least `solver_config.input_count` filtered eligible inputs and a nonempty current-rule projection. Active buckets retain existing order: non-StatTrak, then StatTrak. No financial, valuation, or later search result participates in deciding activity or quota.

Given aggregate candidate budget `C`, aggregate explored-state budget `S`, and `B` active buckets:

1. If `B == 0`, make no core enumeration call and leave both budgets unused.
2. Let `P = min(B, C)`. Only the first `P` active buckets participate; later active buckets receive candidate quota `0`, state quota `0`, and no enumeration call.
3. Candidate quota for participating bucket index `i` (zero-based) is:

   ```text
   candidate_base = C // P
   candidate_remainder = C % P
   candidate_quota[i] = candidate_base + (1 if i < candidate_remainder else 0)
   ```

4. Reserve one explored state for each participating bucket's baseline state. Split the remaining state budget `S - P` fairly in the same order:

   ```text
   state_extra_base = (S - P) // P
   state_extra_remainder = (S - P) % P
   state_quota[i] = 1 + state_extra_base + (
       1 if i < state_extra_remainder else 0
   )
   ```

Because global configuration requires `S >= C >= P`, every participating bucket receives at least one explored state and also satisfies `state_quota[i] >= candidate_quota[i]`. Quota sums are exactly `C` and `S` across participating calls. Actual usage may be lower when a bucket exhausts its bounded neighborhood or reaches its candidate quota early.

Candidate examples with two active buckets:

```text
C=6 → P=2 → 3 / 3
C=5 → P=2 → 3 / 2
C=2 → P=2 → 1 / 1
C=1 → P=1 → normal 1 / StatTrak 0
```

State examples:

```text
C=6, S=256, P=2 → 128 / 128
C=5, S=255, P=2 → 128 / 127
C=2, S=3,   P=2 → 2 / 1
C=1, S=256, P=1 → normal 256 / StatTrak 0
```

No second pass, quota stealing, or dynamic redistribution occurs in V1. A participating bucket that uses less than its quota leaves the difference unused. Total returned selections never exceed `C`; total actual states explored never exceed `S`.

### Exploration is bounded at generation time

The implementation MUST lazily emit at most the configured number of state descriptors. It MUST NOT construct, count by iteration, sort, or materialize all ten-item combinations before applying either limit.

## Preferred V1 search

Use **greedy-first plus deterministic radius-one substitutions**.

Let `P` be the retained eligible pairs after the exact current eligibility, sort, and per-collection-cap steps. If `len(P) < 10`, return no candidates.

### Baseline state

```text
indices: (0,1,2,3,4,5,6,7,8,9)
```

The baseline state is always the first explored state. It becomes a baseline candidate only after the existing engine successfully validates and constructs it. A successful baseline candidate MUST be exactly equal to the current greedy selection: same listing IDs, selected input order, compact paint seeds, output order, probabilities, floats, and wear.

Compatibility behavior is exact:

- `construct_recipe_selections(...)` remains unchanged and returns `[]` when its legacy baseline fails.
- New enumeration with strict `1/1` limits explores only the baseline state, so a valid baseline returns the exact legacy selection and an invalid baseline returns no selection.
- New enumeration with a larger state budget records an engine-rejected baseline state and continues through deterministic radius-one states. A later valid alternative may become the first returned candidate.

Rejected states never occupy returned-candidate quota. No alternative is called “candidate 1” until it has successfully produced the first returned selection.

### Alternative states

For every baseline drop index `d ∈ [0, 9]` and reserve index `r ∈ [10, len(P)-1]`, define one state replacing `P[d]` with `P[r]`. Enumerate lazily by the total deterministic key:

```text
(r - d, r, d, RecipeSelectionKey)
```

This visits the smallest loss in existing solver rank first. The first alternative is therefore:

```text
P0, P1, ..., P8, P10
```

Each candidate’s ten selected pairs remain in existing solver-priority order. Key order is only a final state tie-break and deduplication mechanism, not presentation order.

V1 does not perform radius-two or deeper substitutions, expand alternatives recursively, use sliding windows, beam search, best-first search, or any financial score.

### Candidate validation

For each explored state:

1. select exactly ten retained pairs;
2. compute its canonical `RecipeSelectionKey` from original facts;
3. if that key was already seen, increment `duplicates_suppressed` and continue without an engine call;
4. otherwise record the key and invoke existing `calculate_tradeup_results(...)` exactly once;
5. let existing float and probability code validate and construct results;
6. treat engine `ValueError` as a rejected state: increment `engine_rejected_states`, set `baseline_state_rejected=True` when this was the first baseline state, and continue if exploration budget remains;
7. propagate every unexpected exception and every `MemoryError`;
8. on success, increment `raw_candidates_found`, append exactly one unique selection, and stop immediately when either configured limit is reached.

The output pool is built once per core enumeration invocation. No float or probability formula is duplicated.

## Strategy comparison

### Exhaustive combinations

Rejected: its cost is `C(n,10)`, reaching trillions at current pool sizes. Even a lazy exhaustive iterator has unacceptable worst-case exploration when invalid/duplicate states precede enough valid candidates.

### Sliding windows

Rejected: it is bounded and deterministic but has severe adjacency bias. Window two removes the best-ranked item and changes a different structural neighborhood than the smallest single substitution; later windows change many inputs simultaneously and miss obvious near-neighbor candidates.

### Greedy-first plus deterministic neighborhood substitutions

Accepted for V1: explores the exact legacy baseline state first, yields explainable one-listing alternatives, requires at most `1 + 10(n-10)` radius-one states, needs no financial ranking, and allows strict state/candidate bounds. A rejected baseline state does not terminate a larger-budget search.

### Beam search

Rejected for V1: requires beam width, depth, and a score. A price/EV/ROI score would violate the domain/valuation boundary; an unproven structural score would create hidden policy and complicate compatibility.

### Best-first bounded structural search

Rejected for V1: requires a priority heuristic and retained frontier. Radius-one rank-loss ordering achieves the needed bounded local search without a general heap/frontier or an invented objective.

## Deterministic ordering contract

1. Every participating bucket explores its baseline state first.
2. If a baseline state is valid, its selection is the first returned selection for that bucket; if rejected, it occupies one explored state but no candidate slot, and later valid alternatives retain their structural state order.
3. Core radius-one states use `(rank_loss, reserve_rank, dropped_rank, canonical_key)`.
4. Rejected and duplicate states do not occupy returned-candidate slots.
5. Returned selections preserve successful unique state-exploration order within each bucket.
6. Inputs inside a candidate remain in current solver-priority order.
7. Engine results retain the existing exact market-name ordering ([tradeup_engine.py:98-103](../../app/services/tradeup_engine.py#L98-L103)).
8. Scanner composition uses structural result depth rather than raw state index or undifferentiated selection index:

   ```text
   depth 0:
     normal successful baseline candidate, if present
     StatTrak successful baseline candidate, if present

   depth 1:
     normal first successful alternative, if present
     StatTrak first successful alternative, if present

   depth 2:
     normal second successful alternative, if present
     StatTrak second successful alternative, if present
   ...
   ```

   `baseline_state_rejected` tells composition whether a bucket's first returned selection is an alternative. Rejected baseline/alternative states are absent from global output; they do not occupy a returned depth and do not reorder later successful alternatives within that bucket.
9. Only participating buckets from the frozen fair split contribute. The total returned count never exceeds aggregate `C`, and the sum of actual explored states never exceeds aggregate `S`.
10. The orchestrator values candidates in this global composition order. Passed opportunities may still be sorted by the existing expected-profit/ROI display rule ([scanner_orchestrator.py:488-493](../../app/services/scanner_orchestrator.py#L488-L493)).

Input price remains part of ordering only because the legacy greedy sort already uses it. V1 MUST NOT add total candidate cost, output price, expected profit, EV, ROI, or risk score as an enumeration ranking input.

## Legacy compatibility

For valid inputs whose eligible offer identities are unique:

```text
new bounded enumerator with:
max_recipe_candidates_returned = 1
max_candidate_states_explored = 1

→ exactly current construct_recipe_selections(...) result
```

**Required answer: YES.**

The existing legacy public function and exact signature remain unchanged and preserve their current direct implementation semantics. For eligible unique-offer inputs, its output is also the strict `1/1` enumeration compatibility projection. It MUST NOT simply call the new public enumerator in a way that applies the new duplicate-offer preflight, because that would change malformed duplicate-input behavior. Shared private helpers may be used only if the legacy path explicitly bypasses the stronger new-API invariant. `construct_recipes(...)` and `solve_recipes(...)` therefore retain zero-or-one behavior, and existing callers do not silently opt into multiplicity.

This equivalence is a future migration acceptance requirement, not an implemented Phase 13T fact.

## Proposed backward-compatible Python API

```python
DEFAULT_MAX_RECIPE_CANDIDATES_RETURNED = 2
HARD_MAX_RECIPE_CANDIDATES_RETURNED = 6
DEFAULT_MAX_CANDIDATE_STATES_EXPLORED = 256
HARD_MAX_CANDIDATE_STATES_EXPLORED = 1_024


@dataclass(frozen=True, kw_only=True)
class RecipeEnumerationConfig:
    max_recipe_candidates_returned: int = (
        DEFAULT_MAX_RECIPE_CANDIDATES_RETURNED
    )
    max_candidate_states_explored: int = (
        DEFAULT_MAX_CANDIDATE_STATES_EXPLORED
    )


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeEnumerationDiagnostics:
    eligible_input_count: int
    retained_input_count: int
    theoretical_radius_one_states: int
    states_explored: int
    raw_candidates_found: int
    unique_candidates_returned: int
    duplicates_suppressed: int
    engine_rejected_states: int
    baseline_state_rejected: bool
    candidate_limit_reached: bool
    exploration_limit_reached: bool


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeEnumerationResult:
    selections: tuple[ConstructedRecipeSelection, ...]
    diagnostics: RecipeEnumerationDiagnostics


def enumerate_recipe_selections(
    candidates: list[CandidateListing],
    skins: list[SkinMetadata],
    solver_config: RecipeSolverConfig,
    *,
    enumeration_config: RecipeEnumerationConfig,
) -> RecipeEnumerationResult:
    ...


def construct_recipe_selections(
    candidates: list[CandidateListing],
    skins: list[SkinMetadata],
    solver_config: RecipeSolverConfig,
) -> list[ConstructedRecipeSelection]:
    # Exact legacy path. It is value-equivalent to enumeration 1/1 for
    # eligible unique-offer inputs, but bypasses the new duplicate preflight.
    ...
```

Search policy remains outside `RecipeSolverConfig`; that existing DTO describes recipe geometry, fee, and retained-input policy rather than enumeration work limits.

## Diagnostics semantics

All diagnostic fields must be measurable exactly:

- `eligible_input_count`: pairs after existing eligibility.
- `retained_input_count`: pairs after existing sort and per-collection cap.
- `theoretical_radius_one_states`: `0` when retained count is below ten, otherwise `1 + 10 × (retained - 10)`.
- `states_explored`: state descriptors consumed, including duplicate and engine-invalid states.
- `raw_candidates_found`: explored unique states whose existing engine call successfully produced a `ConstructedRecipeSelection`; with pre-engine key suppression this equals `unique_candidates_returned`.
- `unique_candidates_returned`: exact length of `selections`.
- `duplicates_suppressed`: explored states skipped before the engine call because their canonical key had already been seen.
- `engine_rejected_states`: explored unique states whose existing engine call raised `ValueError`.
- `baseline_state_rejected`: true exactly when the first explored baseline state raised that engine `ValueError`; this is not redundant with the aggregate rejection count because it explains why the first returned candidate may be an alternative and lets composition assign structural depth correctly. When true, every returned selection is an alternative; when false and a selection exists, `selections[0]` is the baseline candidate.
- `candidate_limit_reached`: true only when the returned-candidate bound stops search while at least one state is known to remain. The bounded neighborhood exposes remaining-state cardinality arithmetically; do not pull or evaluate an extra state merely to set this flag.
- `exploration_limit_reached`: true only when the explored-state bound stops search while at least one state is known to remain.

No candidate key, listing ID, price, float, or projected DTO is required in routine diagnostics.

## Failure and completion semantics

### Normal bounded completion

- no eligible input;
- fewer than ten retained inputs;
- baseline state rejected and no later valid state found within the configured exploration budget;
- radius-one search exhausted;
- candidate limit reached;
- exploration limit reached;
- duplicate suppression;
- alternative engine `ValueError`.

These return a result plus truthful diagnostics. Hitting a bound is not an error and is not a recipe rejection.

### Errors

- invalid enumeration config: `ValueError` with a fixed configuration message;
- duplicate eligible `RecipeListingKey` in new enumerator input: exact `ValueError("duplicate recipe offer identity")` before search;
- output-pool construction error: propagate as today;
- unexpected engine or internal invariant error: propagate; do not convert to an empty business result;
- scanner-boundary ordinary error: retain the existing fixed `ScannerRecipeCompositionError` behavior unless separately migrated;
- `MemoryError`: propagate the same instance verbatim through enumerator, composition, and orchestrator.

## Float and probability correctness

Every emitted candidate MUST use the existing Protected Core validation/math:

- adjusted input float from `calculate_adjusted_float(...)`;
- average adjusted float and output projection from existing float helpers;
- exactly ten/range/mode/output-pool checks in `calculate_tradeup_results(...)`;
- exact `Fraction` probability contributions and merging across represented collections;
- existing deterministic output ordering.

The enumerator may only choose ten existing eligible pairs. It MUST NOT implement a duplicate float formula, infer wear, precompute output probabilities, or declare a same-rarity set valid without the engine call.

Mixed collections remain legal. The enumeration algorithm MUST NOT group or partition by collection merely because Phase 13S allocation cohorts used collection-local depth.

## Souvenir projection impact

Future scanner integration MUST keep this sequence for every returned candidate:

```text
original enriched inputs
→ temporary souvenir=False solver projection
→ bounded core enumeration
→ canonical-key dedupe based on original source/goods/listing identity
→ exact original InputItem rehydration for every selection
```

Requirements:

- projected objects never escape composition;
- every selected listing ID maps back to exactly one original enriched input;
- the projected recipe differs from originals only at the temporary Souvenir bit;
- normal and Souvenir inputs remain mixable;
- outputs remain canonical non-Souvenir and match StatTrak mode;
- every returned selection, not only index zero, is rehydrated and validated.

`scanner_recipe_composition.py` therefore requires migration in Phase 13T-2 after the core API exists. Phase 13T itself changes nothing.

## StatTrak behavior

- Non-StatTrak inputs produce only non-StatTrak outputs.
- StatTrak inputs produce only StatTrak outputs.
- Modes never mix within one candidate.
- Core limits are per explicit enumeration call; scanner aggregate limits are invocation-wide across its active mode buckets.
- Scanner global ordering uses depth-interleaving of each participating bucket's successful returned sequence in normal-then-StatTrak order; rejected states are absent and do not reorder later successes within a bucket.

## Valuation-budget interaction

Current scanner accounting is:

```text
sum over candidates of:
  count(unique exact output names within that candidate)
```

not the size of the run-wide output-name union. The cap check, charging, and sequential valuation are at [scanner_orchestrator.py:393-460](../../app/services/scanner_orchestrator.py#L393-L460); exact first-seen per-recipe name deduplication is at [scanner_orchestrator.py:596-605](../../app/services/scanner_orchestrator.py#L596-L605).

Architectural rule:

```text
recipe generation: domain/structural and offline
valuation scheduling: network-budget aware
```

The core enumerator MUST NOT import or inspect SteamDT settings, request budget, quote availability, live price, EV, ROI, profit, or risk. The candidate hard maximum is informed by existing scale, but the existing valuation cap remains the authoritative network-work guard.

No additional structural output-count rejection belongs in the core V1 enumerator. A candidate whose output universe exceeds the remaining valuation budget may be constructed and then blocked atomically before any partial lookup, preserving the current domain/network boundary.

## Run-level exact-name price-cache audit

**Exists: NO.**

- Scanner deduplication is within one recipe only.
- `ValuationService` deduplicates exact names within one service call, not across calls ([valuation_service.py:70-78](../../app/services/valuation_service.py#L70-L78)).
- Every candidate is valued by a separate service call, so shared output names are looked up again.
- Existing integration coverage explicitly expects the same exact output name to be requested again across two recipes ([test_steamdt_buff_live_recipe_valuation.py:513-541](../../tests/test_steamdt_buff_live_recipe_valuation.py#L513-L541)).
- The current CLI does not wire the existing cache abstraction into this path, as recorded in architecture context.

A run-scoped exact-name cache is a separate possible optimization with separate freshness, failure-caching, counter, and request-budget semantics. It is not part of multi-recipe enumeration and MUST NOT be smuggled into Phase 13T-1 through 13T-3.

## API migration options

### Option A — extend `construct_recipe_selections(...)`

Pros:

- smallest visible API surface;
- default `max=1` could preserve common callers.

Cons:

- breaks exact signature tests and the established zero-or-one semantic contract;
- combines legacy construction with explicit search policy;
- risks silently changing all direct callers;
- tempts putting search limits into broadly copied `RecipeSolverConfig`.

**Decision: reject.**

### Option B — new bounded enumeration API plus legacy wrapper

Pros:

- explicit opt-in to multiplicity;
- exact legacy signature and caller behavior remain, including malformed duplicate-input behavior;
- new-API duplicate-offer failure is explicit rather than silently inherited by legacy callers;
- eligibility, ordering, output construction, and engine validation stay in one Protected Core owner;
- bounded diagnostics are first-class and testable;
- scanner migration can be staged independently.

Cons:

- requires an explicit, reviewed Protected Core change;
- requires additive config/result/diagnostic DTOs and shared internals.

**Decision: recommend.**

### Option C — non-Protected wrapper repeatedly calling the greedy solver

Pros:

- avoids editing Protected Core initially;
- first call naturally yields the legacy baseline.

Cons:

- repeats eligibility, sorting, output-pool, and engine work;
- candidate omission is order-dependent and easily becomes disjoint inventory allocation;
- coverage is incomplete unless the wrapper recreates core ranking/search semantics;
- duplicate suppression and state accounting become indirect;
- Souvenir projection and rehydration code acquires search ownership;
- proving bounded exploration and exact candidate ordering is harder.

**Decision: reject.**

## Recommended migration seam

```text
app/services/scanner_recipe_composition.py
    → app/services/recipe_solver.py::enumerate_recipe_selections
    → app/services/tradeup_engine.py::calculate_tradeup_results
```

**Protected Core migration required: YES.**

Expected future implementation files:

```text
13T-1:
  app/services/recipe_solver.py
  tests/test_recipe_solver.py

13T-2:
  app/services/scanner_recipe_composition.py
  tests/test_scanner_recipe_composition.py

13T-3:
  app/services/scanner_orchestrator.py
  scripts/run_live_scan_once.py
  tests/test_scanner_orchestrator.py
  tests/test_run_live_scan_once.py

13T-4:
  focused bounded-scale/integration tests and documentation only;
  then exactly one separately authorized bounded live validation using
  the reviewed configuration, with no retry/tuning/second scan
```

`tradeup_engine.py`, float helpers, metadata output mathematics, valuation, EV, and risk modules are reused unchanged.

## Explicit non-goals

Phase 13T and its proposed migration do not include:

- scheduler or continuous scanning;
- database or persistence;
- Discord or alerts;
- auto-buy, orders, trades, reservation, or inventory allocation;
- automatic login, Cookie extraction, browser automation, CAPTCHA/risk-control bypass, proxy/UA rotation, or evasion;
- price-based, EV-driven, ROI-driven, profit-driven, or risk-driven recipe search;
- changes to valuation, EV, probability, float, ROI, or risk mathematics;
- dynamic risk thresholds;
- increased goods-ID cap;
- full-catalog brute force or exhaustive ten-item combinations;
- unbounded SteamDT calls;
- run-level price caching;
- implementation in this design-only phase.

## Phase 13T repository scope

Create only:

```text
specs/2026-08-26-multi-recipe-solver-migration/requirements.md
specs/2026-08-26-multi-recipe-solver-migration/plan.md
specs/2026-08-26-multi-recipe-solver-migration/validation.md
```

No `app/**/*.py`, `scripts/**/*.py`, `tests/**/*.py`, AI-context, roadmap, configuration, snapshot, or research artifact may change. Do not stage, commit, or push.
