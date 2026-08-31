# Phase 16A — Recipe-first Pre-screen Architecture Design

## 1. Current authority map

Production authority (read-only reuse; no rewrite):

- `app/services/market_universe_builder.py`
  - `build_universe_goods_ids`, `MarketUniverseSpec`,
    `StatTrakMode`, `SouvenirInclusion`,
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
    souvenir_inclusion: SouvenirInclusion    # May-2026 mix allowed
    collection_counts: tuple[tuple[str, int], ...]
    #   sorted by collection_name ascending
    #   each count > 0
    #   sum == 10
    #   distinct collections <= MAX_DISTINCT_COLLECTIONS_PER_FAMILY = 3
    represented_outputs: tuple[str, ...]     # canonical exact output names
    output_rarity: str                       # next(input_rarity)
    output_stattrak: bool                    # == stattrak_mode
    structural_probability_denominator: int  # > 0
    family_hash: str                         # SHA-256 of canonical bytes
```

Invariants:

- `input_rarity in {"Consumer Grade","Industrial Grade",
  "Mil-Spec Grade","Restricted","Classified"}`.
- `stattrak_mode in {normal, stattrak}`.
- `output_stattrak == (stattrak_mode == stattrak)`.
- Canonical non-Souvenir output rule unchanged.
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

Eligible inputs (productive rarities, normal and stattrak, souve
nir excluded; collection_name non-empty):

```text
stratum                  | normal inputs | distinct collections | stattrak inputs | distinct collections
Consumer Grade           |            981 |                   38 |               0 |                   0
Industrial Grade         |            950 |                   46 |               0 |                   0
Mil-Spec Grade           |          2,077 |                   91 |           1,318 |                  44
Restricted               |          1,442 |                   91 |             957 |                  45
Classified               |            848 |                   78 |             602 |                  44
```

### 4.2 State count formula

```text
count_families(C, K) = sum_{k=1..K} C(C, k) * C(9, k-1)
```

State count table by `MAX_DISTINCT_COLLECTIONS_PER_FAMILY = K`:

```text
stratum                  | C |    K=1 |       K=2 |         K=3
Consumer Grade / normal  | 38 |     38 |     6,365 |     310,061
Industrial Grade / normal| 46 |     46 |     9,361 |     555,841
Mil-Spec Grade / normal  | 91 |     91 |    36,946 |   4,410,406
Mil-Spec Grade / stattrak| 44 |     44 |     8,558 |     485,342
Restricted / normal      | 91 |     91 |    36,946 |   4,410,406
Restricted / stattrak    | 45 |     45 |     8,955 |     519,795
Classified / normal      | 78 |     78 |    27,105 |   2,765,841
Classified / stattrak    | 44 |     44 |     8,558 |     485,342
sum                      |   |    477 |   142,794 |  13,947,034
```

### 4.3 V1 bound choice

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
  - K=2 yields ~143k total family states and misses the
    cohort-depth-3 structure.
  - K=3 ~14M total family states is a one-time OFFLINE
    pre-screen enumeration cost; downstream BUFF request budget
    remains tiny (`TOP_RANKED_FAMILIES *
    MAX_EXACT_GOODS_IDS_PER_PRESCREEN <= 20`).
- `TOP_RANKED_FAMILIES = 2` (PROJECT bound).
  - Reason: under the existing `HARD_MAX_GOODS_IDS = 10` and
    `HARD_MAX_VALUATION_REQUESTS_PER_RUN = 60`, two families
    keep the run inside the existing budget envelope with one
    fallback slot reserved for sequential-rank expansion.
- `MAX_EXACT_GOODS_IDS_PER_PRESCREEN = 10` (PROJECT bound).
  - Aligns with the existing `HARD_MAX_GOODS_IDS = 10`.

## 5. Structural output geometry (offline, no live listings)

For one RecipeFamily:

- `output_rarity = next(input_rarity)` (from
  `app.services.metadata_service.get_next_rarity`).
- `represented_outputs` is the set of canonical non-Souvenir
  output skin records whose `(collection_name, rarity)` matches
  one of the family collections and the next input rarity, and
  whose `stattrak == (stattrak_mode == stattrak)`. Source:
  pinned metadata snapshot only.
- `output_stattrak = (stattrak_mode == stattrak)`.
- `structural_probability_denominator` is the canonical
  recipe-solver denominator given the family input distribution;
  the per-output probability contribution equals
  `1 / structural_probability_denominator` for the single-cohort
  case (per-output contributions are exact-fraction in the
  multi-cohort case via the protected solver probability
  authority).
- All structural probabilities MUST come from the existing
  probability authority in
  `app/services/recipe_solver.py` /
  `app/services/scanner_recipe_composition.py`. No duplicate
  probability math.

What is structural (independent of concrete input identity /
float / price):

- next rarity,
- represented collections,
- eligible exact outputs,
- per-output probability contribution,
- output StatTrak mode.

What is NOT structural:

- actual float distribution (depends on concrete input floats),
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
transport and assert zero HTTP.

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
5. `family_request_count <= MAX_EXACT_GOODS_IDS_PER_PRESCREEN = 10`

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
  page-1/default-sort fetch (`MAX_EXACT_GOODS_IDS_PER_PRESCREEN =
  10` per run; aggregated across selected families).
- `unresolved_identity_count > 0` -> plan diagnostic; family
  still proceedable but with diagnostic counters raised.
- `hard_request_count <= MAX_EXACT_GOODS_IDS_PER_PRESCREEN = 10`
  total per pre-screen.
- First-page/default-sort only; no pagination expansion in 16A.
- `MarketUniverseBuilder` retained for fallback structural
  planning, exact eligibility, and goods_id mapping diagnostics.
  NOT the primary discovery brain.

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
     `family.represented_outputs`.
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