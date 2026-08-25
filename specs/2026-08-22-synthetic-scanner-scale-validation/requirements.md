# Phase 13J — Synthetic Scanner-Scale Validation Review (Requirements)

## Goal

Validate that the existing trade-up chain — `TradeUpInputCandidate → TradeUpInputEnrichment → InputItem → trade-up engine → EV / ROI / Risk` — behaves deterministically and partition-consistently on a synthetic candidate basket larger than the previous single-recipe integration tests, without touching any Protected Core module and without introducing any live / external dependency.

## Functional Requirements

### FR-1 — Synthetic basket construction (offline only)

- FR-1.1 The validation module must produce `TradeUpInputCandidate` fixtures deterministically from a fixed seed; two runs with the same `SyntheticBasketConfig` must yield byte-equal candidate streams and metadata mappings.
- FR-1.2 The basket must contain at least 20 candidates per `SyntheticBasketConfig` so the two-path partition comparison always has both kept and rejected buckets.
- FR-1.3 The basket must support four contamination knobs — `unresolved_ratio`, `missing_metadata_ratio`, `stattrak_ratio`, `souvenir_ratio` — applied independently. Defaults are 0.
- FR-1.4 Each candidate's `market_hash_name` must come from a closed set of strings that appear in the metadata fixture (when `missing_metadata_ratio == 0`) or be deliberately absent from it (when `missing_metadata_ratio > 0`); no string is fabricated at runtime beyond the fixture set.
- FR-1.5 Each candidate's `paintwear` and `price_cny` must be drawn from within the per-collection float band and price range specified by the config; the boundary check on `TradeUpInputCandidate.__post_init__` must reject any out-of-band draw with `ValueError`, surfacing the bug at basket-build time.
- FR-1.6 Both metadata stores (`basket.metadata` for 13H-0 `TradeUpInputMetadata` and `basket.enrichment_metadata` for 13I-3 `TradeUpInputMetadata`) must be constructed from the same logical source so the two paths see the same name → record mapping. The two classes are not aliased; they are parallel fixtures.

### FR-2 — Dual-path driver

- FR-2.1 The driver must feed every `TradeUpInputCandidate` in `basket.candidates` through `candidates_to_input_items` (13H-0) using `basket.metadata`, returning `list[InputItem]` and a per-skip reason string drawn from the closed set `{"unresolved", "missing_metadata"}`.
- FR-2.2 The driver must feed the same candidate stream through `enrich_candidates` (13I-3) using an `InMemoryTradeUpInputEnricher(InMemoryTradeUpInputMetadataResolver(basket.enrichment_metadata))`, returning a `TradeUpInputEnrichmentResult` with full `enriched` and `rejected` partitions in input order.
- FR-2.3 The driver must NOT short-circuit, deduplicate, or reorder candidates; input order must be preserved through both paths.

### FR-3 — Partition comparison

- FR-3.1 `compare_partition_paths` must report `partition_agreement: True` iff the count of `InputItem` values returned by `drive_pipeline_path` equals the count of `TradeUpEnrichedInput` values returned by `drive_enrichment_path`. This is the canonical invariant: pipeline silently skips, enrichment surfaces rejections, but the kept counts must agree for the same basket.
- FR-3.2 `compare_partition_paths` must report two histograms — pipeline skip histogram (`{"unresolved", "missing_metadata"}` → `int`) and enrichment rejection histogram (`TradeUpEnrichmentRejectionReason` → `int`). The two histograms must agree on counts by reason class after mapping (`MARKET_HASH_NAME_UNRESOLVED → "unresolved"`, `METADATA_NOT_FOUND → "missing_metadata"`).
- FR-3.3 No market_hash_name, listing_id, goods_id, asset_id, or price value may appear in `compare_partition_paths` output; the comparison result is structural.

### FR-4 — Engine math stability

- FR-4.1 For each basket, group the enriched inputs by collection. For each collection with at least 10 enriched inputs of homogeneous `stattrak` / `souvenir` / `rarity`, attempt `calculate_tradeup_results` against an `output_candidates_by_collection` built via `build_output_candidates_by_collection` from a hand-curated `SkinMetadata` fixture set. **Historical synthetic-validation requirement: Phase 13P-4 / `D-TRADEUP-001` supersedes homogeneous Souvenir grouping for the current standard Trade Up Contract path; normal and Souvenir inputs may coexist and outputs are non-Souvenir.**
- FR-4.2 Successful recipes must be reproducible: running the basket through the full pipeline twice must produce `ConstructedRecipe` instances with identical `recipe_hash` (where `recipe_hash` is the SHA-256 from `recipe_solver.build_recipe_hash`).
- FR-4.3 For every successful recipe, `sum(result.probability for result in recipe.tradeup_results) == 1.0` within `1e-9` (mirroring `PROBABILITY_TOLERANCE`).
- FR-4.4 Engine `ValueError` failures from `_validate_input_items` (mixed-rarity, mixed-stattrak, mixed-souvenir, missing-collection) must be captured as redacted reason strings (substring of the error message, no input identity leakage) and routed to a `recipes_rejected_by_engine` bucket.

### FR-5 — EV / Risk capture

- FR-5.1 Every successful recipe must be passed to `calculate_opportunity_metrics` with `sell_fee_rate=Decimal("0.05")`. The resulting `OpportunityMetrics` must be recorded immutably for reproducibility checks.
- FR-5.2 Every `OpportunityMetrics` must be passed to `evaluate_opportunity` with a pass-through `RiskFilterConfig` (`min_roi=0`, `min_expected_profit_cny=0`, `max_worst_case_loss_pct=1`, `min_profit_probability=0.0`, `max_input_total_cost_cny=999999`) so the test surfaces real reason codes without applying policy suppression.
- FR-5.3 `RiskDecision.reason_codes` and `RiskDecision.risk_score` must be byte-equal across two reruns of the same basket.
- FR-5.4 The pass-through risk config must be defined as a constant inside the test module, not imported from production.

### FR-6 — Required metric surface

The validation report must expose all five metric categories required by the project:

- **FR-6.1 accepted_candidates** — `enrichment_kept_count - recipes_rejected_by_engine` per basket.
- **FR-6.2 rejection_reasons** — histogram union of `TradeUpEnrichmentRejectionReason`, `_validate_input_items` `ValueError` substrings, and `RiskDecision.reason_codes`.
- **FR-6.3 enrichment_success_ratio** — `enrichment_kept_count / (enrichment_kept_count + enrichment_rejected_count)` per basket. Must equal `1 - (unresolved_ratio + missing_metadata_ratio)` within rounding for the basket the ratio was drawn from.
- **FR-6.4 solver_compatibility** — `recipes_built / recipes_attempted`. Where < 1, the captured engine-validation `ValueError` substring must be present in the report.
- **FR-6.5 ev_risk_output_stability** — two reruns produce byte-equal `OpportunityMetrics` (or, at minimum, byte-equal `roi` and `expected_profit_cny`) and byte-equal `RiskDecision.risk_score`.

### FR-7 — Static dependency guards

- FR-7.1 `app/services/trade_up_pipeline.py` source must remain free of: `httpx`, `asyncio`, `requests`, `os.environ`, `open(`, `json`, `BUFF_READONLY_SMOKE_GOODS_ID`, `SteamApis`, `SteamDT`. (Regression guard for the existing 13H-0 contract.)
- FR-7.2 The new test module must not import from: `app.services.buff_listing*`, `app.services.buff_item_identity`, `app.services.buff_client`, `app.services.steamdt_*`, `app.services.steamapis_*`, `app.services.live_recipe_valuation`, `app.services.metadata_provider`, `app.services.live_metadata_catalog`, `app.services.market_scan_service`, `app.jobs.scheduler`, `app.api.*`, `app.db.*`, `app.cache.*`, `app.webhook.*`, `app.services.scanner`.
- FR-7.3 `SyntheticValidationReport` lives only in `tests/test_synthetic_scanner_scale_validation.py`; no production module imports it.

## Non-Functional Requirements

- NFR-1 Determinism: every test must produce byte-equal results across two consecutive runs of `pytest`.
- NFR-2 Scale: total candidate count across `SyntheticScaleCase` fixtures must be ≥ 100 and ≤ 1000. The phase validates partition + math stability, not throughput.
- NFR-3 Performance budget: the new test file must complete within 30 seconds on the local machine; no benchmark artifact is committed.
- NFR-4 Repr safety: `SyntheticValidationReport`, `compare_partition_paths`, and `drive_*_path` outputs must not contain any `listing_id`, `goods_id`, `market_hash_name`, `asset_id`, `price_cny`, or `paintwear` value when rendered. (No leakage of fixture identity into reports.)
- NFR-5 Public API exactness: `app/services/trade_up_pipeline.py.__all__` must be an exact tuple that includes both the 13H-0 exports and the seven new exports added by this phase.

## Out of Scope (frozen here)

- No diagnostic counters on `TradeUpInputEnrichmentResult` or any production DTO.
- No JSON / CSV / log report file.
- No mutation of `recipe_solver.py`, `tradeup_engine.py`, `ev_service.py`, `risk_filter.py`, `metadata_models.py`, `metadata_service.py`, `market_scan_service.py`, `trade_up_input_enrichment.py`, `trade_up_input_candidate.py`.
- No real (non-synthetic) listing data; no BUFF / SteamDT / SteamApis endpoint call; no identity resolver wiring.
- No production scanner or scheduler wiring.
- No Discord webhook, no notification side effects.
- No new third-party dependency (stdlib `random` is the only randomness source).
- No public reporting module or `SyntheticValidationReport` import from production code.

## Acceptance

This design passes if the implementation phase produces:

- A `tests/test_synthetic_scanner_scale_validation.py` that exercises every `SyntheticScaleCase` against all five metric categories and all four functional groups.
- An `app/services/trade_up_pipeline.py` whose `__all__` extends exactly to include the seven new helpers.
- A working `py -3.13 -m pytest` with zero Protected Core diff.
- A reproducible `SyntheticValidationReport` per case, with both runs byte-equal for any given seed.