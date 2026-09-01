# Phase 16A — Recipe-first Pre-screen Architecture Design

## 1. Current authority map

Production authority (read-only reuse; no rewrite):

- `app/services/market_universe_builder.py`
  - `build_universe_goods_ids`, `MarketUniverseSpec`,
    `StatTrakMode`, `SouvenirInclusion` (planner-level input only;
    NOT a `RecipeFamily` structural identity axis),
    `UniverseAllocationStrategy`, `MarketUniverseDiagnostics`.
  - Diagnostic counts `catalog_capacity`,
    `canonical_output_count`, `selected_cohort_count` are
    structural (catalog eligibility), not liquidity or
    profitability.
  - Retained as a fallback exact-eligibility / hard-request /
    goods_id mapping utility. NOT the new discovery brain.
- `app/clients/buff_anonymous_listing_client.py`,
  `app/services/buff_listing_provider.py`
  - Anonymous page-1/default-sort read-only listing path.
  - `get_listings(goods_id) -> list[BuffListing]`.
- `app/services/buff_community_identity_resolver.py`
  - Pinned offline community identity catalog; exact fail-closed
    `market_hash_name <-> goods_id`; no fuzzy / casefold / alias.
- `app/services/buff_intrinsic_flag_resolver.py`,
  `app/services/buff_listing_intrinsic_flags.py`
  - Three-state StatTrak / Souvenir; candidate owns the bits.
- `app/services/skin_metadata_resolver.py`
  - `PinnedSkinMetadataResolver.skins` (immutable full catalog).
- `app/services/scanner_recipe_composition.py`,
  `app/services/recipe_solver.py`
  - Bounded enumeration `RecipeEnumerationConfig`
    (defaults `2 / 256`, hard max `6 / 1024`, invariant
    `states >= candidates`).
  - `is_current_standard_trade_up_output_eligible`
    (`skin.souvenir is False and skin.stattrak == result_stattrak`).
- `app/services/tradeup_engine.py`, `app/utils/float_math.py`
  - Canonical trade-up math; no fork.
  - **Production math currently operates on wear-qualified
    `market_hash_name` rows as separate probability buckets.**
    Phase 16B MUST NOT silently reuse this wear-row cardinality
    for structural output geometry. The future recipe-first
    structural probability primitive MUST count unique eligible
    output finishes (not wear rows). Production refactor of
    `tradeup_engine.py` is separately gated under
    `D-TRADEUP-WEAR-ROW-MIGRATION-001`.
- `app/services/scanner_orchestrator.py`
  - `LiveScannerOrchestrator.HARD_MAX_GOODS_IDS = 10`,
    `HARD_MAX_VALUATION_REQUESTS_PER_RUN = 60`. Default 5.
- `app/services/steamdt_buff_price_provider.py`,
  `app/services/steamdt_buff_price_policy.py`
  - Strict exact BUFF sell-price authority. No second platform,
    no biddingPrice, no metadata-zero fallback.
- `app/services/scanner_valuation_session.py`
  - Run-scoped exact-name reuse + atomic NEW-LIVE cap admission.
- `app/services/scanner_cached_buff_price_resolver.py`
  - Phase 14C optional FRESH_ONLY scanner cache read.
- `app/services/ev_service.py`, `app/services/risk_filter.py`
  - `OpportunityMetrics` and `evaluate_opportunity`.

Out-of-scope historical compatibility (do NOT revive):
- `app/services/steamapis_*`
- `app/services/live_metadata_catalog.py`
- `app/services/live_pool_recipe_construction.py`
- `app/services/steamapis_offer_session.py`
- `app/clients/steamapis_websocket_client.py`

## 2. Target architecture diagram

```text
[pinned CS2 metadata snapshot]
  + [pinned BUFF community identity snapshot]
    -> RecipeFamilyGenerator                 (16B, offline)
    -> static structural / output geometry   (16B, offline)
    -> static float feasibility              (16C, offline)
    -> SteamDT batch pre-screen              (16C, mocked transport,
                                              offline tests; no live BUFF)
    -> RecipeFamilyPreScreenEconomics        (16D, offline)
    -> deterministic ranking / Top-N         (16D, offline)
    -> TargetedBuffScanPlanner               (16D, offline)
    -> existing BUFF anonymous listing       (16E, integrated; offline
                                              validation; production gated)
    -> existing identity / intrinsic /       (16E, reused as-is)
       enrichment
    -> family-constrained concrete search    (16E, reuses 2 / 256 solver)
    -> existing strict final SteamDT-BUFF    (16E)
       valuation
    -> existing EV / risk                    (16E)
    -> opportunity report (LiveOpportunity)  (16E)
```

The new brain is structural recipe families + offline SteamDT
batch pre-screen + family-targeted BUFF. The mature downstream
calculation/safety stack stays unchanged.

## 3. RecipeFamily domain model (frozen)

```python
@dataclass(frozen=True, kw_only=True)
class RecipeFamily:
    family_key: str                          # first 24 hex of family_hash
    family_spec_version: Literal[1]
    input_rarity: str                        # 5 productive rarities
    stattrak_mode: StatTrakMode              # normal / stattrak
    collection_counts: tuple[tuple[str, int], ...]
    #   sorted by collection_name ascending
    #   each count > 0
    #   sum == 10
    #   distinct collections <= MAX_DISTINCT_COLLECTIONS_PER_FAMILY = 3
    represented_output_finishes: tuple[StructuralOutputFinish, ...]
    #   unique FINISH identities (one per structural outcome)
    #   NOT per wear-qualified market_hash_name
    output_rarity: str                       # next(input_rarity)
    output_stattrak: bool                    # == stattrak_mode
    structural_probability_denominator: int  # > 0
    family_hash: str                         # SHA-256 of canonical bytes
```

Invariants:

- `input_rarity in {"Consumer Grade","Industrial Grade",
  "Mil-Spec Grade","Restricted","Classified"}`.
- `stattrak_mode in {normal, stattrak}`. StatTrak IS a material
  structural family dimension.
- `output_stattrak == (stattrak_mode == stattrak)`.
- Canonical non-Souvenir output rule unchanged.
- **Souvenir is NOT a RecipeFamily structural identity axis.**
  Normal and Souvenir inputs may coexist under the current
  standard contract; concrete selected inputs retain true Souvenir
  provenance through the existing temporary `souvenir=False`
  solver projection + exact rehydration seam. Souvenir policy, if
  needed by a future targeted scan, lives as a separate
  planner/runtime acquisition-policy field, not as family
  identity.
- `sum(counts) == 10` exactly.
- `1 <= distinct_collections <= 3`.
- `family_hash = SHA-256(canonical_sorted_utf8_bytes)`;
  `family_key = first 24 lowercase hex chars`.
- Deterministic enumeration order:
  `(input_rarity, stattrak_mode, tuple(collection_counts),
  family_hash)`.
- Duplicate suppression: identical `(input_rarity,
  stattrak_mode, collection_counts)` yields one family.
- Canonical serialization: keys sorted, no whitespace, exactly
  one trailing newline; `canonicalize(bytes) is its own inverse`.
- RecipeFamily enumeration MUST support lazy deterministic
  iteration that yields one family at a time; theoretical
  family-space counts are analytic evidence, not eager-
  materialization authorization.

## 3.1 StructuralOutputFinish (frozen)

```python
@dataclass(frozen=True, kw_only=True)
class StructuralOutputFinish:
    finish_key: str                                  # canonical SHA-256 hex
    collection_name: str
    rarity: str
    stattrak: bool
    base_name: str                                  # skin.name
    weapon: str | None
    paint_index: int | None
    min_float: float
    max_float: float
    wear_market_names: tuple[tuple[str, str], ...]
    #   ordered (wear_name, exact_market_hash_name)
    #   canonical non-Souvenir wear rows only
```

### 3.1.1 Finish-key uniqueness (offline evidence)

Pinned snapshot:
`data/metadata/skin_metadata_v1.json` (sha256
`55e4d446...`, accepted 16868). Candidate 6-tuple key

```text
(collection_name, rarity, stattrak, name, weapon, paint_index)
```

is sufficient and collision-free: it maps the 16868 wear-qualified
rows to **2148 distinct finish keys**. The 2148 finishes break
down as:

- 3 finishes with a single canonical non-Souvenir wear row,
- 2145 finishes with multiple canonical non-Souvenir wear rows
  (1791 have all 5 wear bands; the remaining 357 have 1, 2, 3,
  or 4 wear bands).

`min_float` and `max_float` are consistent across all wear
variants of the same finish (no inconsistency observed in the
pinned snapshot).

The exact `(wear_name, exact_market_hash_name)` map per finish
is well-defined for canonical non-Souvenir wear bands only. The
Souvenir wear bands share `wear_name` labels with the
non-Souvenir wear bands but carry a different
`market_hash_name` prefix (`"Souvenir " ...`); they MUST NOT
contribute to `wear_market_names` for the canonical non-Souvenir
output pool.

### 3.1.2 Wear-row vs unique-finish counts (offline)

Aggregate per `(input_rarity, output rarity, statrak)`):

```text
Consumer Grade / normal -> wear_rows=1962 unique_finishes=200
Industrial Grade / normal -> wear_rows=1900 unique_finishes=204
Mil-Spec  / normal -> wear_rows=4154 unique_finishes=446
Mil-Spec  / stattrak -> wear_rows=1318 unique_finishes=279
Restricted / normal -> wear_rows=2884 unique_finishes=311
Restricted / stattrak -> wear_rows= 957 unique_finishes=205
Classified / normal -> wear_rows=1696 unique_finishes=183
Classified / stattrak -> wear_rows= 602 unique_finishes=130
```

For every productive stratum, the number of wear-qualified rows
is greater than the number of unique output finishes (typically
roughly 4x to 9x). Structural probability MUST count unique
finishes, not wear rows.

## 3.2 Output identity boundaries

Two distinct output identities are frozen:

A. **Structural output identity** (`StructuralOutputFinish`).
   Used for:
   - collection output pool membership,
   - trade-up structural probability,
   - family geometry,
   - duplicate suppression at the finish level.

B. **Exact market valuation identity** (the canonical
   non-Souvenir `market_hash_name` for a finish + concrete
   output_float). Used only when a specific output wear is known.

Future chain:

```text
RecipeFamily
  -> represented_output_finishes (unique finish identities)
  -> StaticFloatFeasibility / scenario avg_adjusted_float
  -> output_float for each structural finish
  -> wear band from output_float
  -> exact wear-qualified canonical non-Souvenir market_hash_name
  -> SteamDT pre-screen scenario price
```

For a CONCRETE live recipe:

```text
10 exact InputItems
  -> canonical average adjusted float
  -> each structural output finish
  -> exact output_float
  -> exact wear
  -> exact pinned canonical non-Souvenir market_hash_name
  -> strict final SteamDT-BUFF valuation
```

Resolution semantics:

- zero wear-qualified `market_hash_name` mappings for the
  finish+wear combination -> FAIL_CLOSED `unresolved_output_wear`;
- multiple `market_hash_name` mappings for the same finish+wear
  combination -> FAIL_CLOSED `output_wear_collision`;
- no fuzzy / hand-constructed names if the pinned catalog can
  provide the exact name;
- no guessing of missing wear variants;
- canonical non-Souvenir rows only; Souvenir rows are concrete-
  input provenance and never appear in
  `wear_market_names` for the canonical non-Souvenir output pool.

## 4. Family enumeration / bounds analysis

### 4.1 Offline evidence

Pinned snapshots used:

- `data/metadata/skin_metadata_v1.json`
  - sha256 `55e4d446a5343e1932f24b9069090431f87b0c750d2cb4c091947ec2411dc421`
  - `accepted = 16868`, `rejected = 671`, `source = 2126`
  - schema version `1`
- `data/identity/buff_identity_v1.json`
  - sha256 `e3aab46d570869e0b6866eac44b26bca7492ea7c2c54669e74b2b4feeec506ac`
  - `accepted = 34402`, `rejected = 15`, `source = 34417`

Authoritative Phase 16B eligibility (exact pinned input identity + at
least one unique canonical non-Souvenir next-rarity output finish):

```text
stratum                    | eligible collections | K<=3 families
Consumer Grade / normal    |                   38 |       310,061
Industrial Grade / normal  |                   44 |       485,342
Mil-Spec Grade / normal    |                   86 |     3,717,221
Mil-Spec Grade / stattrak  |                   44 |       485,342
Restricted / normal        |                   76 |     2,556,526
Restricted / stattrak      |                   44 |       485,342
Classified / normal        |                   63 |     1,447,236
Classified / stattrak      |                   44 |       485,342
TOTAL                      |                      |     9,972,412
```

Eligibility gates:

1. productive input rarity;
2. at least one exact input `market_hash_name` resolvable by the
   pinned BUFF identity catalog;
3. mode-compatible input row (normal mode admits normal and
   Souvenir non-StatTrak rows without splitting family identity;
   StatTrak mode admits StatTrak rows);
4. at least one unique canonical non-Souvenir next-rarity
   structural output finish matching StatTrak mode.

Superseded historical Phase 16A metadata-only evidence (preserved
for traceability): C values `38/46/91/44/91/45/78/44` and their
listed family counts. Those line items sum to 13,943,034, not the
written 13,947,034 (a separate 4,000 arithmetic error). Neither old
total is authoritative for Phase 16B.

- `MAX_DISTINCT_COLLECTIONS_PER_FAMILY = 3` (PROJECT bound, NOT
  external API limit).
- Justification:
  - The current production `COHORT_DEPTH` strategy already uses
    `target_cohort_count = 3` from
    `MarketUniverseSpec.target_cohort_count = 3`. The current
    scanner structurally spans <= 3 collection-local cohorts in
    10 picks.
  - K=1 collapses to single-collection families and loses
    cross-collection structure the production already supports.
  - Under the corrected Phase 16B eligibility gates, total
    theoretical counts are K=1: 439, K<=2: 116,944, and K<=3:
    9,972,412.
  - K=3’s 9,972,412 states are a theoretical deterministic
    structural state space; they are NOT a per-run or per-stratum
    eager-materialization requirement. The generator MUST support
    lazy deterministic iteration by stratum and analytic counting
    without materializing the full family space.
- `TOP_RANKED_FAMILIES = 2` (PROJECT bound).
  - Reason: under the existing `HARD_MAX_GOODS_IDS = 10` and
    `HARD_MAX_VALUATION_REQUESTS_PER_RUN = 60`, two families
    preserve one fallback family; Top-2 is a ranking / fallback
    signal and does NOT multiply the live BUFF request budget.
- `MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10` (PROJECT bound,
  NOT a BUFF external limit).
  - Exactly ONE family is active for one live targeted BUFF scan
    per run. Family #2 is allowed only as a fallback BEFORE any
    BUFF request starts. Once any BUFF page request starts,
    family switching in that run is forbidden. Total BUFF page
    requests per run is `<= MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN`.
  - Preserves `LiveScannerOrchestrator.HARD_MAX_GOODS_IDS = 10`.
- `PRESCREEN_BATCH_CHUNK_SIZE = 10` (internal project transport
  chunk, NEVER a confirmed SteamDT provider limit; do not exceed
  in any pre-screen call until provider documentation confirms
  a larger limit).

## 5. Structural output geometry (offline, no live listings)

For one RecipeFamily:

- `output_rarity = next(input_rarity)` (from
  `app.services.metadata_service.get_next_rarity`).
- `represented_output_finishes` is the **finish-level** set of
  canonical non-Souvenir output finishes whose
  `(collection_name, rarity)` matches one of the family
  collections and the next input rarity, and whose
  `stattrak == (stattrak_mode == stattrak)`. Source: pinned
  metadata snapshot only. The set contains unique FINISH
  identities, NOT per wear-qualified `market_hash_name`.
  (Concrete output wear is NOT known at RecipeFamily generation
  time; it is resolved only after a wear scenario or a concrete
  output float is supplied.)
- `output_stattrak = (stattrak_mode == stattrak)`.
- Structural probability denominator for one collection c with
  `collection_counts[c] = n` inputs and `unique_finish_count_in_c`
  eligible unique finishes (canonical non-Souvenir output):

  ```text
  per-input weight              = 1 / 10
  per-input weight on output c  = n / 10
  per-finish probability on c   = (n / 10) / unique_finish_count_in_c
  ```

  The family-level denominator equals the LCM (or exact rational
  common denominator) across all per-collection finish
  probabilities; the probability sum over all
  `represented_output_finishes` MUST equal exactly 1.
- All structural probabilities MUST come from a future
  finish-level structural probability primitive that operates
  on `(input collection counts, unique output finish counts)`.
  No duplicate probability math.
- The current production `tradeup_engine.calculate_tradeup_results`
  operates on `OutputCandidate.market_hash_name` (per wear-qualified
  row). This is the wear-row cardinality bug documented under
  `D-TRADEUP-WEAR-ROW-MIGRATION-001`. Phase 16B MUST NOT silently
  reuse the wear-row cardinality. A future narrow protected-core
  refactor under that decision MUST add the finish-level primitive
  AND keep `calculate_tradeup_results` semantically identical for
  legacy callers; production math remains unchanged in 16B.

What is structural (independent of concrete input identity /
float / price):

- next rarity,
- represented collections,
- eligible unique output finishes (canonical non-Souvenir
  finish identities, NOT wear-qualified market rows),
- per-finish structural probability contribution
  (`collection_count / 10 / unique_finish_count_in_collection`),
- output StatTrak mode.

What is NOT structural:

- actual float distribution (depends on concrete input floats),
- concrete output wear (depends on concrete output float,
  resolved later from the finish wear map),
- exact wear-qualified output `market_hash_name` (depends on
  concrete output float; resolved later fail-closed),
- actual listing prices (depends on concrete live BUFF sell
  orders).

## 6. Static float feasibility (offline math; no listing float)

For one RecipeFamily with output `(output_min, output_max)` and
desired output float threshold `T`:

```text
adjusted_i     = (actual_float_i - input_min_i) / (input_max_i - input_min_i)
avg_adjusted   = mean(adjusted_i)
output_float   = avg_adjusted * (output_max - output_min) + output_min
```

Inverse reasoning for `output_float <= T`:

```text
required_max_avg_adjusted = (T - output_min) / (output_max - output_min)
```

Frozen pre-screen result DTO:

```python
@dataclass(frozen=True, kw_only=True)
class StaticFloatFeasibilityResult:
    family_hash: str
    structurally_feasible: bool
    required_max_avg_adjusted: Fraction | None
    threshold: Decimal
    output_min: Decimal
    output_max: Decimal
    supporting_input_wear_bands: tuple[tuple[str, Decimal, Decimal], ...]
    reason_codes: tuple[str, ...]
```

Critical caveat: range feasibility != proof BUFF has executable
listings. No fabricated listing-float distribution.

## 7. SteamDT batch pre-screen boundary

Transport: `POST /open/cs2/v1/price/batch` (confirmed endpoint
per `docs/STEAMDT_API_NOTES.md`).

Strict selector (no fallback):

- exact `platform == "BUFF"` (case-sensitive),
- `sell_price_cny > 0`, finite,
- exactly one BUFF record per name (duplicate BUFF records fail
  closed),
- missing or unusable BUFF record -> family pre-screen outcome
  `FAIL_CLOSED`,
- NEVER `biddingPrice`,
- NEVER second-platform substitute,
- NEVER lowest-price-across-platforms,
- `sellCount` / `updateTime` retained as diagnostics only.

Must NOT be assumed (no fabrication):

- exact batch-size hard limit (current observations used `<= 10`;
  Phase 16C must not exceed 10 in any pre-screen call until
  provider documentation confirms a larger limit),
- currency field guarantee,
- freshness guarantee.

Quota boundary: current `price_batch` policy is 1 request /
minute + 5-second project safety buffer (process-local; Redis
shared limiter optional via Phase 12C2 / 12C3 settings).
The pre-screen must respect this rate; offline tests must mock
transport and assert zero HTTP. The pre-screen transport MUST
deduplicate exact `market_hash_name`s before issuing any batch
call, and may chunk the deduped set into batches of at most
`PRESCREEN_BATCH_CHUNK_SIZE = 10` names each. The pre-screen
MUST NOT issue one batch call per family; the dedupe and chunk
plan operate over the union of names across the active run
batch.

## 8. Coarse economics DTO (frozen, NOT implemented in 16A)

```python
@dataclass(frozen=True, kw_only=True)
class RecipeFamilyPreScreenEconomics:
    family_hash: str
    scenario_label: str              # optimistic | base | conservative
    estimated_input_cost_cny: Decimal | None
    estimated_gross_output_ev_cny: Decimal | None
    estimated_net_ev_after_sell_fee_cny: Decimal | None
    estimated_profit_cny: Decimal | None
    estimated_roi: Fraction | None
    assumptions: tuple[str, ...]
    data_timestamp: datetime | None
    missing_price_count: int
    evidence: tuple[str, ...]
    reason_codes: tuple[str, ...]
```

Scenario rules:

- optimistic: cheapest plausible input cost (lowest observed BUFF
  sellPrice per required identity); highest observed BUFF
  sellPrice for outputs (or base if absent).
- base: most-recent observed BUFF sellPrice for inputs and
  outputs.
- conservative: highest observed BUFF sellPrice for inputs;
  lowest observed BUFF sellPrice for outputs.

Pre-screen MUST NEVER:

- claim executability,
- pass the existing `RiskFilterConfig`,
- reuse `OpportunityMetrics` for approximate values.

## 9. Deterministic ranking

Default = static lexicographic by gates and explicit keys; no
weighted score until evidence justifies weights.

Gates:

1. `structurally_feasible == True`
2. `batch_pre_screen outcome == SUCCESS`
3. no missing-price penalty
4. >= 1 supporting wear band exists
5. `family_request_count <= MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10`

Lexicographic sort key (descending):

1. `estimated_roi_scenario_base`
2. `estimated_profit_scenario_base`
3. `static_float_margin_vs_threshold`
4. batch `sellCount` aggregate evidence (sum over family)
5. `data_timestamp` (newest first)
6. `family_hash` (deterministic tie-break)

Top-N bound: `TOP_RANKED_FAMILIES = 2` (PROJECT bound).

Frozen exclusion reason codes:

- `STRUCTURALLY_INFEASIBLE`
- `BATCH_PRE_SCREEN_FAILED`
- `MISSING_PRICE_PENALTY`
- `NO_SUPPORTING_WEAR_BAND`
- `REQUEST_COUNT_OVER_BUDGET`
- `UNRESOLVED_IDENTITY`

## 10. TargetedBuffScanPlan (frozen contract)

```python
@dataclass(frozen=True, kw_only=True)
class TargetedBuffScanPlan:
    family_hash: str
    requested_input_market_hash_names: tuple[str, ...]
    mapped_goods_ids: tuple[str, ...]
    unresolved_identity_count: int
    collection_role: Mapping[str, str]     # collection_name -> primary|secondary|tertiary
    stattrak_mode: StatTrakMode
    static_float_relevance: StaticFloatFeasibilityResult
    priority: int                          # lexicographic rank position
    hard_request_count: int
    diagnostics: tuple[str, ...]
```

Contract:

- `requested_input_market_hash_names` is the canonical exact-name
  set the family needs; each must resolve via the pinned BUFF
  identity catalog.
- `mapped_goods_ids` is the bounded subset for anonymous
  page-1/default-sort fetch. The total across the active
  `TargetedBuffScanPlan` for ONE run is bounded by
  `MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10`.
- Exactly ONE family is active for one live targeted BUFF scan
  per run. Top-2 ranking does NOT multiply the live BUFF request
  budget.
- Family #2 is fallback only BEFORE live acquisition starts; if
  family #1 fails completely during OFFLINE targeted planning,
  family #2 may become active. Once any BUFF page request starts,
  family switching in that run is forbidden.
- Total BUFF page requests per run is
  `<= MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10`.
- `unresolved_identity_count > 0` -> plan diagnostic; family
  still proceedable but with diagnostic counters raised.
- First-page/default-sort only; no pagination expansion in 16A.
- `MarketUniverseBuilder` retained for fallback structural
  planning, exact eligibility, and goods_id mapping diagnostics.
  NOT the primary discovery brain.

Conceptual `TargetedBuffScanDecision` (NOT implemented in 16A):

```python
@dataclass(frozen=True, kw_only=True)
class TargetedBuffScanDecision:
    ranked_family_keys: tuple[str, ...]   # max 2
    active_family_key: str | None
    active_plan: TargetedBuffScanPlan | None
    fallback_family_key: str | None
    hard_request_cap: int                # exactly 10 in V1
    diagnostics: tuple[str, ...]
```

## 11. Family-constrained concrete search (reuses solver)

After targeted BUFF fetch:

1. Filter / expand the listing pool into a `family`-compatible
   candidate set (matching `input_rarity`, `stattrak_mode`, exact
   pinned identities; no duplicate listing identity).
2. Reuse `enumerate_scanner_recipe_selections` with
   `RecipeEnumerationConfig(max_recipe_candidates_returned = 2,
   max_candidate_states_explored = 256)` (existing default).
3. For each candidate selection, prove:
   - `count(collection_name)` per family collection matches the
     family `collection_counts` exactly;
   - all inputs have homogeneous `stattrak` and the right
     `souvenir` projection;
   - duplicate listing identity fails closed;
   - output `TradeupResult.output_market_hash_name` is among
     `family.represented_output_finishes` (finish-level membership).
4. Reuse `RunScopedValuationSession.prepare_output_prices` and
   `ScannerCachedBuffPriceResolver` (Phase 14C FRESH_ONLY reads)
   inside the same atomic NEW-LIVE cap.
5. Reuse `calculate_opportunity_metrics` and
   `evaluate_opportunity` unchanged.
6. Only selections that pass existing `RiskFilterConfig` produce
   `LiveOpportunity`.

## 12. Final valuation boundary

- Pre-screen is approximate; it NEVER produces a
  `LiveOpportunity`.
- Final valuation of concrete `LiveOpportunity` candidates uses
  the existing strict SteamDT-BUFF selector via
  `SteamDTBuffPriceProvider` and `select_buff_output_price`.
- No second-platform fallback. No biddingPrice substitution.
  No metadata-zero reuse. No probability renormalization.
- The same `RunScopedValuationSession.prepare_output_prices` /
  `resolve_prepared` atomic NEW-LIVE cap admission semantics
  from Phase 14B apply unchanged.
- The same Phase 14C `ScannerCachedBuffPriceResolver` FRESH_ONLY
  read seam is reused unchanged.

## 13. Cache / rate-limit interaction

Preserve unchanged:

- `max_valuation_requests_per_run` default `5`; hard max `60`.
- Phase 14C FRESH_ONLY scanner cache reads (optional resolver).
- Phase 14B run-scoped exact-name reuse.
- `price_batch` 1 / minute + 5-second project buffer; Phase 12C
  Redis shared limiter optional through existing settings.
- No scanner write-after-live, no scheduler/background refresh,
  no scanner TTL env config.

## 14. Observability

The new architecture MUST expose:

- per-family RecipeFamily key / hash / spec version,
- per-stratum family enumeration counters,
- per-family structural output geometry,
- per-family static float feasibility reason codes,
- per-family SteamDT batch pre-screen reason codes,
- per-family coarse economics scenarios with diagnostics,
- per-family ranking gates + lexicographic key,
- per-family `TargetedBuffScanPlan` hard request count and
  unresolved identity count,
- per-run aggregate counters:
  families_generated, families_ranked, families_ranked_to_plan,
  buff_requests_planned, buff_requests_actually_issued,
  steampre_screen_requests, steampre_screen_failures,
  missing_price_penalties.

No secret / cookie / token / webhook URL is exposed.

## 15. Migration compatibility

- `MarketUniverseBuilder` stays as a fallback structural /
  eligibility / goods_id mapping utility.
- The current goods-first path is NOT removed by Phase 16A.
  A separate authorization decides whether the production CLI
  switches to the new recipe-first brain.
- Phase 15C-3 representative campaign remains DEFERRED.

## 16. Deferred work

- Concrete implementation of 16B / 16C / 16D / 16E / 16F.
- A separate re-scope of the Phase 15C-3 representative campaign
  under the new production path.
- Production scheduler / continuous operation under recipe-first.
- Real Discord opportunity delivery under recipe-first.
- DB persistence under recipe-first.
- Weighted ranking (only if offline evidence justifies weights).