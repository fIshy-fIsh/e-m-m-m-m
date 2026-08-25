# Phase 13J — Synthetic Scanner-Scale Validation Review (Plan)

## Status

- Design-only review.
- Date: 2026-08-22.
- Branch: `feature/steamdt-cache-rate-limit`.
- Anchors: Phase 13H-0 (synthetic `trade_up_pipeline.py`), Phase 13I-2 (intrinsic flags), Phase 13I-3 (enrichment boundary).
- No code, no Protected Core edits, no `requirements.md` / `validation.md` content beyond this plan yet (companion files will be written as part of this review).

## Decisions Locked In This Review (from intake)

1. **Module placement:** extend `app/services/trade_up_pipeline.py` with scale-validation helpers; do not introduce a new file.
2. **Pipeline shape:** drive both 13H-0 `candidates_to_input_items` and 13I-3 `enrich_candidates` against the same synthetic basket and assert agreement on the kept/rejected partition where the two paths overlap.
3. **EV / Risk scope:** compute `ConstructedRecipe` + `OpportunityMetrics` + `RiskDecision` per basket. Record metrics in-memory. No JSON report file, no Discord, no scheduler.
4. **Counters:** test-local only. No new counter fields on `TradeUpInputEnrichmentResult` or on any Protected Core DTO.

## Task Groups

### Group 1 — Synthetic basket builder

1.1. Define `SyntheticBasketConfig` (frozen, kw-only): `target_rarity: str`, `collections: tuple[str, ...]`, `inputs_per_collection: int` (defaults to 10; must equal 10 to satisfy the V1 engine), `price_cny_min: Decimal`, `price_cny_max: Decimal`, `paintwear_distribution: Literal["uniform", "stepped"]`, `stattrak_ratio: float = 0.0`, `souvenir_ratio: float = 0.0`, `unresolved_ratio: float = 0.0`, `missing_metadata_ratio: float = 0.0`, `seed: int` for reproducibility.

1.2. Define `SyntheticBasket` (frozen, kw-only): `candidates: tuple[TradeUpInputCandidate, ...]`, `metadata: Mapping[str, TradeUpInputMetadata]` (from 13H-0 type), `enrichment_metadata: Mapping[str, TradeUpInputMetadata]` (13I-3 type — same shape, distinct class identity; we treat them as parallel fixture stores, not aliases), `config: SyntheticBasketConfig`.

1.3. Implement `build_synthetic_basket(config: SyntheticBasketConfig) -> SyntheticBasket`. Deterministic from `seed`. Internally uses `random.Random(seed)` (stdlib only) so no new dependency.

1.4. Basket sizing rule: total candidate count must be `>= 2 * inputs_per_collection` so the "two paths" comparison always has both a kept and a rejected bucket. Document the lower bound; reject smaller configs with `ValueError`.

### Group 2 — Scale dataset

2.1. Define `SyntheticScaleCase` (frozen): `label: str`, `basket: SyntheticBasket`, `expected_kept_count: int`, `expected_rejection_histogram: dict[TradeUpEnrichmentRejectionReason, int]` (only for 13I-3 path).

2.2. Provide a small, hand-curated table of `SyntheticScaleCase` values (`SMALL`, `MIXED`, `DIRTY`) covering: all-resolvable, mixed-rarity, high-unresolved, high-missing-metadata, all-stattrak, mixed-souvenir. The total candidate count across cases must be >= 100 (sufficient to exercise partition and EV stability; far below any "stress" threshold).

2.3. Each case must document why it exists (one sentence in code comment) and what it asserts.

### Group 3 — Dual-path driver

3.1. Implement `drive_pipeline_path(basket: SyntheticBasket) -> tuple[list[InputItem], list[str]]`: feeds the basket through `candidates_to_input_items` (13H-0) using `basket.metadata`, returns kept `InputItem` list and a list of redacted skip reasons (only `"unresolved"` or `"missing_metadata"` strings; no market_hash_name leakage).

3.2. Implement `drive_enrichment_path(basket: SyntheticBasket) -> TradeUpInputEnrichmentResult`: feeds the basket through `enrich_candidates` (13I-3) using `InMemoryTradeUpInputEnricher(InMemoryTradeUpInputMetadataResolver(basket.enrichment_metadata))`.

3.3. Implement `compare_partition_paths(pipeline_items, enrichment_result) -> PathComparison` returning:
   - `pipeline_kept_count`
   - `enrichment_kept_count`
   - `partition_agreement: bool` (true iff pipeline kept count equals enrichment kept count; pipeline silently skips while enrichment returns rejected, but the kept count must match)
   - `pipeline_skip_histogram: dict[str, int]`
   - `enrichment_rejection_histogram: dict[TradeUpEnrichmentRejectionReason, int]`

3.4. Document the deliberately known divergence: pipeline silently drops failures, enrichment surfaces them as rejections. The phase validates that kept counts agree; it does NOT modify either module to suppress or expose more.

### Group 4 — Engine math stability

4.1. For each `SyntheticScaleCase`, build `output_candidates_by_collection` using a small hand-curated `SkinMetadata` fixture (per collection; rarity chosen to be one tier below `target_rarity` per `RarityOrder`). Use `build_output_candidates_by_collection` from `metadata_service.py`; do not bypass it.

4.2. Group enriched inputs by collection. For each collection with `>= 10` enriched inputs of the same `stattrak` / `souvenir` class, attempt `calculate_tradeup_results`. Capture both successes and `ValueError`s from `_validate_input_items` (mixed-rarity, mixed-stattrak, mixed-souvenir, missing-collection). **Historical review plan: Phase 13P-4 / `D-TRADEUP-001` supersedes the homogeneous-Souvenir assumption for current standard trade-ups.**

4.3. Determinism check: rerun the entire basket pipeline twice and assert `ConstructedRecipe.recipe_hash` equality for any recipe that succeeded both times. (Engine math is already deterministic per the existing tests; we just confirm that holds under scale.)

4.4. Output Float stability: for every successful recipe, assert `abs(sum(probability) - 1.0) <= 1e-9` (mirroring `PROBABILITY_TOLERANCE`).

### Group 5 — EV / Risk capture

5.1. For every successful recipe, run `calculate_opportunity_metrics` with a fixed `sell_fee_rate=Decimal("0.05")`. Record `OpportunityMetrics` into a list.

5.2. For every `OpportunityMetrics`, run `evaluate_opportunity` with a hand-built `RiskFilterConfig` (`min_roi=Decimal("0")`, `min_expected_profit_cny=Decimal("0")`, `max_worst_case_loss_pct=Decimal("1")`, `min_profit_probability=0.0`, `max_input_total_cost_cny=Decimal("999999")` — pass-through defaults that surface real reason codes without suppressing any). Record `RiskDecision`.

5.3. Compute test-local counters:
   - `recipes_built: int`
   - `recipes_rejected_by_engine: int`
   - `recipes_with_metrics: int`
   - `risk_passed: int`
   - `risk_rejected: int`
   - `risk_reason_histogram: dict[str, int]`
   - `enrichment_kept_count`, `enrichment_rejected_count`
   - `pipeline_kept_count`, `pipeline_skip_count`
   - `partition_agreement: bool`

5.4. Compute a `SyntheticValidationReport` (frozen dataclass in the test file only — NOT a production module) holding the counters above and the list of `(basket_label, recipe_hash, RiskDecision)` triples.

### Group 6 — Test wiring

6.1. Single test file `tests/test_synthetic_scanner_scale_validation.py`. Public-API-exact test asserting the synthetic basket builder's `__all__` (`SyntheticBasketConfig`, `SyntheticBasket`, `SyntheticScaleCase`, `build_synthetic_basket`, `drive_pipeline_path`, `drive_enrichment_path`, `compare_partition_paths`, `SyntheticValidationReport`). The 13H-0 module gains the helpers but `__all__` MUST be extended to include them — so a guard test ensures the public surface stays exact.

6.2. Determinism: build the same basket twice from the same `SyntheticBasketConfig`; assert `tuple(c.listing_id for c in basket.candidates)` and metadata equivalence.

6.3. Each `SyntheticScaleCase` runs through `drive_pipeline_path` + `drive_enrichment_path` + `compare_partition_paths` and the assertions of Group 4 + Group 5.

6.4. Forbidden-token guard on `trade_up_pipeline.py` source (read at test time): must contain none of `httpx`, `asyncio`, `requests`, `os.environ`, `open(`, `json`, `BUFF_READONLY_SMOKE_GOODS_ID`, `SteamApis`, `SteamDT`. (`trade_up_pipeline.py` already has zero live imports per the 13H-0 tests; this is a regression guard.)

6.5. Forbidden-token guard on the new test module: no `import` from `app.services.buff_listing*`, `app.services.buff_item_identity`, `app.services.buff_client`, `app.services.steamdt_*`, `app.services.steamapis_*`, `app.services.live_recipe_valuation`, `app.services.metadata_provider`, `app.services.live_metadata_catalog`, `app.services.market_scan_service`, `app.jobs.scheduler`, `app.api.*`, `app.db.*`, `app.cache.*`, `app.webhook.*`, `app.services.scanner`. (Validates that synthetic-scale validation cannot accidentally reach into a live source.)

### Group 7 — Required metrics for the validation pass

Per the project requirement, this phase must surface:

- `accepted_candidates` — the count of enriched candidates that made it into a successful recipe (`enrichment_kept_count` minus `recipes_rejected_by_engine`).
- `rejection_reasons` — histogram keyed on the union of (a) `TradeUpEnrichmentRejectionReason` values, (b) `_validate_input_items` `ValueError` substrings, (c) `RiskDecision.reason_codes`. Each bucket asserts at least one occurrence across `MIXED` and `DIRTY` cases; no assertion on absolute counts beyond reproducibility.
- `enrichment_success_ratio` — `enrichment_kept_count / (enrichment_kept_count + enrichment_rejected_count)` for each case; must equal the inverse of the configured `unresolved_ratio + missing_metadata_ratio` (within rounding).
- `solver_compatibility` — `recipes_built / recipes_attempted`. Cases where this is <1 must be accompanied by a recorded engine-validation `ValueError` substring.
- `ev_risk_output_stability` — for each successful recipe, EV/risk numbers must be reproducible across two reruns (`OpportunityMetrics.roi`, `OpportunityMetrics.expected_profit_cny`, `RiskDecision.risk_score` byte-equal).

### Group 8 — Out of scope (frozen here, not implemented later in 13J)

- No diagnostic counters added to production modules.
- No public reporting module (no JSON, no CSV, no logger).
- No benchmarking of large N (>10k). The phase validates partition + math stability, not throughput.
- No mutation of `recipe_solver.py`, `tradeup_engine.py`, `ev_service.py`, `risk_filter.py`, `metadata_models.py`, `metadata_service.py`, `market_scan_service.py`, `trade_up_input_enrichment.py`, `trade_up_input_candidate.py`, or the 13H-0 public surface (`candidates_to_input_items`).
- No new `SyntheticValidationReport` import surface from any production module — it lives only in `tests/`.

## Critical Files

Modify:

- `app/services/trade_up_pipeline.py` — append `SyntheticBasketConfig`, `SyntheticBasket`, `SyntheticScaleCase`, `build_synthetic_basket`, `drive_pipeline_path`, `drive_enrichment_path`, `compare_partition_paths`. Extend `__all__` accordingly. Keep existing exports untouched.

Create:

- `tests/test_synthetic_scanner_scale_validation.py` — single test file holding `SyntheticValidationReport`, the scale-case table, and the assertions.

No other path may change.

## Verification

```bash
py -3.13 -m pytest tests/test_synthetic_scanner_scale_validation.py
py -3.13 -m pytest \
  tests/test_synthetic_scanner_scale_validation.py \
  tests/test_trade_up_input_enrichment.py \
  tests/test_trade_up_input_candidate.py \
  tests/test_trade_up_pipeline.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
git diff --check
git diff --name-only
git diff --stat
git diff --cached --name-only
git status --short
```

Acceptance requires:

- All checks pass.
- Exactly two paths in `git diff --name-only` / `git status --short` (one modified, one added). Spec trilogy files are untracked in this review and will be tracked at commit time alongside implementation.
- No Protected Core diff (the regex in `D-ENRICH-002` covers them).
- `tests/test_synthetic_scanner_scale_validation.py` reports all five required metric categories.
- `partition_agreement` is `True` for every `SyntheticScaleCase`.
- EV/risk output is reproducible across reruns.

## Critical Files (implementation will add these to the plan)

- `app/services/trade_up_pipeline.py` (M)
- `tests/test_synthetic_scanner_scale_validation.py` (A)

Do not commit or push the implementation unless separately requested.