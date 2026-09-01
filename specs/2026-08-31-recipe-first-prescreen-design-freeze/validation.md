# Phase 16A — Recipe-first Pre-screen Architecture Validation

## 1. Success / failure tokens

Success tokens (appear only when ALL guards pass):

```text
RECIPE_FIRST_PRESCREEN_DESIGN_FREEZE_COMPLETE
PHASE_16A_DESIGN_FREEZE_COMPLETE
```

Failure tokens (replace success tokens if any guard fails):

```text
PHASE_16A_GUARD_FAILED_<reason>
```

## 2. Phase 16A design-freeze gates (docs-only)

Phase 16A is design-freeze only. The required gates:

```text
git diff --check                                 PASS
ruff check .                                    PASS
mypy app                                        PASS  (85 files)
pytest                                          PASS  (full offline suite)
```

## 3. Mandatory guard checks (Phase 16A)

- `app/**`, `scripts/**`, `tests/**`, `pyproject.toml`,
  `.github/**`, `data/**`, research data: zero production /
  test / dependency / CI / workflow change.
- Protected JSONs untouched / untracked:
  - `research/identity_revalidation/data/modest_serhat.json`
  - `research/identity_revalidation/data/timofey_ivanenko.json`
- Production defaults unchanged: `default = 5`,
  `hard_max = 60`.
- No secret / token / cookie / `.env` / webhook URL introduced
  or printed.
- No live BUFF, SteamDT, Discord, Redis integration test,
  PostgreSQL mutation, scheduler, or Phase 15C campaign slot.
- Tag preserved: `v1-dry-run-baseline -> 32ab47c5b66a0f331457e69f1515e5e9bb2a37e1`.
- Branch created from CURRENT `origin/main`, NOT from
  `feature/representative-snapshot-calibration`.
- `feature/representative-snapshot-calibration` branch
  reference preserved (unmerged).

## 4. Test suites to add for future implementation stages

The following test suites are planned (NOT added in Phase 16A)
for the implementation stages:

### 4.1 RecipeFamily domain (Stage 16B)

`tests/test_recipe_family_domain.py`:

- `RecipeFamily` invariants:
  - `sum(collection_counts[i][1]) == 10`,
  - distinct collections bound `<= 3`,
  - `output_stattrak == (stattrak_mode == stattrak)`,
  - canonical non-Souvenir output rule,
  - `input_rarity` membership in productive rarities,
  - duplicate `(input_rarity, stattrak_mode,
    collection_counts)` suppression.
- Canonical serialization:
  - keys sorted, no whitespace, one trailing newline,
  - `canonicalize(canonicalize(bytes)) == canonicalize(bytes)`,
  - SHA-256 `family_hash` and `family_key` derivation stable
    across reruns.
- Deterministic enumeration order:
  - `(input_rarity, stattrak_mode,
    tuple(collection_counts), family_hash)`.
- Structural output geometry parity with
  `app.services.metadata_service.get_next_rarity` and
  `app.services.scanner_recipe_composition.is_current_standard_trade_up_output_eligible`.

### 4.2 Static float feasibility (Stage 16C)

`tests/test_static_float_feasibility.py`:

- `required_max_avg_adjusted` correctness against canonical
  float math in `app.utils.float_math`.
- `structurally_feasible` boundary cases.
- Reason codes for infeasible / borderline cases.

### 4.3 SteamDT batch pre-screen adapter (Stage 16C)

`tests/test_steamdt_batch_pre_screen_adapter.py`:

- strict selector parity with
  `app.services.steamdt_buff_price_policy.select_buff_output_price`
  semantics (case-sensitive `platform == "BUFF"`,
  positive finite `sellPrice`, single BUFF record per name).
- missing or unusable BUFF record -> `FAIL_CLOSED`.
- duplicate BUFF records -> `FAIL_CLOSED`.
- batch-size hard cap `10` per request.
- NEVER uses `biddingPrice`.
- NEVER substitutes a second platform.
- NEVER picks lowest-price-across-platforms.
- `sellCount` / `updateTime` retained as diagnostics only.
- mock-transport asserts zero live HTTP during tests.

### 4.4 Coarse economics (Stage 16D)

`tests/test_recipe_family_economics.py`:

- optimistic / base / conservative scenario consistency,
- missing-price penalty path,
- DTO separation from
  `app.services.ev_service.OpportunityMetrics`.

### 4.5 Deterministic ranking (Stage 16D)

`tests/test_recipe_family_ranking.py`:

- gates enforced: structurally_feasible, batch_pre_screen
  SUCCESS, no missing-price penalty, supporting wear band,
  request-count bound,
- lexicographic sort stability,
- tie-break by `family_hash`,
- exclusion reason codes:
  `STRUCTURALLY_INFEASIBLE`,
  `BATCH_PRE_SCREEN_FAILED`, `MISSING_PRICE_PENALTY`,
  `NO_SUPPORTING_WEAR_BAND`,
  `REQUEST_COUNT_OVER_BUDGET`, `UNRESOLVED_IDENTITY`,
- Top-N bound `TOP_RANKED_FAMILIES = 2`.

### 4.6 TargetedBuffScanPlanner (Stage 16D)

`tests/test_targeted_buff_scan_planner.py`:

- `MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10` enforcement,
- exactly-one-active-family per run,
- family-switching-after-live-start forbidden,
- unresolved identity diagnostics,
- goods_id mapping correctness via
  `app.services.market_universe_builder`,
- collection role correctness.

### 4.7 Family-constrained concrete search (Stage 16E)

`tests/test_family_constrained_concrete_search.py`:

- family-`collection_counts` match enforcement,
- StatTrak homogeneity,
- normal/Souvenir projection seam with exact InputItem
  rehydration,
- duplicate listing identity fail-closed,
- output identity set membership,
- run-scoped atomic NEW-LIVE cap honored via Phase 14B
  `RunScopedValuationSession.prepare_output_prices` /
  `resolve_prepared`,
- Phase 14C `ScannerCachedBuffPriceResolver` FRESH_ONLY
  read seam integration unchanged.

### 4.8 Recipe-first orchestrator composition (Stage 16E)

`tests/test_recipe_first_orchestrator_composition.py`:

- explicit opt-in flag enforced,
- production default OFF,
- offline-only fixtures,
- zero live HTTP during tests,
- Phase 14B / 14C invariants preserved,
- `evaluate_opportunity` + `calculate_opportunity_metrics`
  reuse preserved.

## 5. Invariant / property tests

Across all stages:

- `MAX_DISTINCT_COLLECTIONS_PER_FAMILY = 3` enforced.
- `sum(collection_counts) == 10` enforced.
- `family_key` derivation stable across reruns.
- Lexicographic ranking stable across reruns.
- Pre-screen and final valuation separation:
  pre-screen NEVER produces a `LiveOpportunity`.
- Pre-screen NEVER passes the existing `RiskFilterConfig`.
- Pre-screen DTO is structurally distinct from
  `OpportunityMetrics`.
- Phase 14B atomic NEW-LIVE cap admission honored.
- Phase 14C FRESH_ONLY cache read semantics preserved.
- **`RecipeFamily.represented_output_finishes` is finish-level.**
  No wear-qualified `market_hash_name` is treated as an
  independent structural outcome.
- **Structural probability denominators count unique eligible
  output finishes**, not wear-qualified market rows.
  `per-finish probability = (collection_count / 10) / unique_finish_count_in_collection`.
  The probability sum over `represented_output_finishes` MUST
  equal 1.
- **Exact output wear-qualified `market_hash_name` is resolved
  fail-closed** from pinned finish + wear metadata after output
  float is determined. No fuzzy / name guessing. Souvenir rows
  are excluded from the canonical non-Souvenir wear map.
- `StructuralOutputFinish.finish_key` is collision-free against
  the pinned metadata snapshot. The current offline evidence is
  16868 wear rows -> 2148 distinct finish keys.
- Wear map uniqueness: per finish, exactly one canonical
  non-Souvenir `market_hash_name` per wear band. Zero / multiple
  mappings fail closed.

## 6. Deterministic replay

For each stage, the pre-screen + ranking + plan outputs MUST
be replayable from:

- pinned CS2 metadata snapshot,
- pinned BUFF community identity snapshot,
- a deterministic SteamDT batch response fixture.

Replay MUST produce byte-equal outputs across reruns on the
same pinned inputs.

## 7. Combinatorial bound tests

- RecipeFamily enumeration cardinality matches the offline
  formula `sum_{k=1..K} C(C, k) * C(9, k-1)` for each stratum
  with `K = MAX_DISTINCT_COLLECTIONS_PER_FAMILY = 3`.
- Off-by-one / overflow / negative-count / out-of-bounds
  collection_count rejected.
- Empty / non-eligible stratum yields zero families without
  exception.

## 8. No-network tests

- Mock-transport asserts zero live HTTP for offline test runs.
- Pre-screen adapter unit tests never resolve a live endpoint.
- Recipe-family generator and ranking tests are pure and
  zero-I/O.

## 9. Strict BUFF selector tests

- Case sensitivity: `"buff"` / `"Buff"` rejected as BUFF
  record.
- Duplicate BUFF records rejected.
- Missing or unusable BUFF record rejected.
- `biddingPrice` never selected.
- No second-platform fallback.
- No lowest-across-platforms selection.

## 10. Pre-screen / final separation tests

- Pre-screen DTO never substitutes for `OpportunityMetrics`.
- Pre-screen `LiveOpportunity` count remains zero.
- Pre-screen never passes `RiskFilterConfig`.
- Final valuation path remains unchanged.

## 11. No-fallback tests

- No metadata-zero reuse.
- No `biddingPrice` substitution.
- No second-platform substitute.
- No lowest-price-across-platforms behavior.

## 12. Protected-core diff guards

- `app/services/recipe_solver.py` (probability authority)
  unchanged by Phase 16A and downstream stages.
- `app/services/tradeup_engine.py` (canonical trade-up math)
  unchanged.
- `app/utils/float_math.py` (canonical float math) unchanged.
- `app/services/steamdt_buff_price_provider.py` /
  `app/services/steamdt_buff_price_policy.py` (strict BUFF
  selector) unchanged.
- `app/services/scanner_valuation_session.py` (Phase 14B
  atomic NEW-LIVE cap) unchanged.
- `app/services/scanner_cached_buff_price_resolver.py`
  (Phase 14C FRESH_ONLY reads) unchanged.
- `app/services/ev_service.py` /
  `app/services/risk_filter.py` (final EV / risk) unchanged.

## 13. Eventual bounded-live gates (Stage 16F)

Stage 16F requires:

- fixed campaign identity,
- fixed stratum,
- fixed window,
- at most 10 BUFF page-1/default-sort requests,
- sequential,
- minimum 2-second request-start pacing,
- zero retries / polling / pagination,
- zero SteamDT / Redis / cache write,
- zero `.env` / credential / cookie inspection,
- artifact OUTSIDE Git,
- canonical JSON + SHA-256 + append-only manifest,
- offline replay under disabled socket constructors,
- protected guards re-verified.

Commit: `validate recipe-first prescreen interface`.
No PR. No merge. No force. No tag deletion.

## 14. Reporting tokens

Final report MUST end with:

```text
RECIPE_FIRST_PRESCREEN_DESIGN_FREEZE_COMPLETE
```