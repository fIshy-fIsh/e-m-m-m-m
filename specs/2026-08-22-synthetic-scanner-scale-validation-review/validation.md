# Phase 13J — Synthetic Scanner-Scale Validation Review (Validation)

## Validation Strategy

Three concentric rings, in order. Each ring must pass before the next is attempted. Each ring produces a deterministic, byte-reproducible artifact.

### Ring 1 — Static surface and dependency guards

- **R1.1 Public API exactness.**
  - Read `app/services/trade_up_pipeline.py` source.
  - Assert `__all__` is an exact tuple equal to:
    `("TradeUpInputMetadata", "TradeUpInputMetadataResolver", "InMemoryTradeUpInputMetadataResolver", "candidates_to_input_items", "SyntheticBasketConfig", "SyntheticBasket", "SyntheticScaleCase", "build_synthetic_basket", "drive_pipeline_path", "drive_enrichment_path", "compare_partition_paths")`.
  - Fail if any 13H-0 export is missing or reordered.

- **R1.2 Forbidden-token guard on `trade_up_pipeline.py`.**
  - Read the module source. Assert none of: `httpx`, `asyncio`, `requests`, `os.environ`, `open(`, `json`, `BUFF_READONLY_SMOKE_GOODS_ID`, `SteamApis`, `SteamDT`, `aiohttp`, `websockets`.
  - Fail on any match. (Regression guard for the 13H-0 contract.)

- **R1.3 Forbidden-token guard on the new test module.**
  - Read `tests/test_synthetic_scanner_scale_validation.py`. Parse the AST. Collect all `import` targets. Assert none of: `app.services.buff_listing`, `app.services.buff_item_identity`, `app.services.buff_client`, `app.services.steamdt`, `app.services.steamapis`, `app.services.live_recipe_valuation`, `app.services.metadata_provider`, `app.services.live_metadata_catalog`, `app.services.market_scan_service`, `app.jobs.scheduler`, `app.api`, `app.db`, `app.cache`, `app.webhook`, `app.services.scanner`.
  - Fail on any match. (Validates the synthetic validation cannot accidentally reach a live source.)

- **R1.4 Protected-Core diff check.**
  - Run `git diff --name-only` and grep against the Protected Core regex recorded in `ARCHITECTURE_STATE.md`. Assert no match.
  - Also assert no path under `app/services/{recipe_solver,tradeup_engine,ev_service,risk_filter,valuation_service,live_recipe_valuation,metadata_models,metadata_service,market_scan_service,buff_listing,buff_listing_parser,buff_listing_facts,buff_listing_eligibility,buff_listing_qualification,buff_listing_solver_adapter,buff_client,trade_up_input_enrichment,trade_up_input_candidate}` is modified.

### Ring 2 — Determinism and partition invariants

- **R2.1 Basket determinism.**
  - Build the same `SyntheticBasketConfig` twice.
  - Assert `tuple(c.listing_id for c in basket1.candidates) == tuple(c.listing_id for c in basket2.candidates)`.
  - Assert the two `metadata` mappings and `enrichment_metadata` mappings contain the same key set.

- **R2.2 Partition agreement across the two paths.**
  - For every `SyntheticScaleCase`, run `drive_pipeline_path` and `drive_enrichment_path`.
  - Assert `compare_partition_paths(...)` returns `partition_agreement is True`.
  - Assert the pipeline skip histogram and the mapped enrichment rejection histogram agree bucket-by-bucket (`MARKET_HASH_NAME_UNRESOLVED → "unresolved"`, `METADATA_NOT_FOUND → "missing_metadata"`).

- **R2.3 Enrichment success ratio equals the configured contamination.**
  - For each case, compute the empirical `enrichment_kept_count / (enrichment_kept_count + enrichment_rejected_count)`.
  - Assert it equals `1 - (unresolved_ratio + missing_metadata_ratio)` within `1e-9`.

- **R2.4 Input order preservation.**
  - For each case, the order of `InputItem` values returned by `drive_pipeline_path` must equal the order of `TradeUpEnrichedInput.candidate.listing_id` sequences in `drive_enrichment_path`.
  - The full `TradeUpInputEnrichmentResult` (enriched then rejected concatenation in input order) must match the input `listing_id` order.

### Ring 3 — Engine math, EV / Risk stability

- **R3.1 Recipe reproducibility.**
  - For each `SyntheticScaleCase`, run the full pipeline (`drive_enrichment_path` → group by collection → `calculate_tradeup_results` → `ConstructedRecipe`) twice.
  - For every recipe that succeeded in both runs, assert `recipe.recipe_hash` is byte-equal across runs.

- **R3.2 Probability sums to one.**
  - For every successful recipe, assert `abs(sum(r.probability for r in recipe.tradeup_results) - 1.0) <= 1e-9`.

- **R3.3 EV / Risk stability.**
  - For each successful recipe, capture `(metrics, decision)` twice.
  - Assert `metrics.roi`, `metrics.expected_profit_cny`, and `decision.risk_score` are byte-equal across runs.
  - Assert `decision.reason_codes` is byte-equal across runs.

- **R3.4 Engine validation surfaced, not swallowed.**
  - For each case where `recipes_built < recipes_attempted`, assert the report contains a captured `_validate_input_items` `ValueError` substring mapped to a closed enum: `MIXED_RARITY`, `MIXED_STATTRAK`, `MIXED_SOUVENIR`, `MISSING_COLLECTION`.
  - Assert no captured substring contains any `listing_id`, `goods_id`, `market_hash_name`, `asset_id`, `price_cny`, or `paintwear` value.

- **R3.5 Risk reason histogram reproducibility.**
  - For each case, build the `risk_reason_histogram` twice. Assert byte-equality.

### Required metric assertions (project-level acceptance)

- **M-1 accepted_candidates.** `accepted_candidates >= 1` for at least one of `SMALL`, `MIXED`, `DIRTY`.
- **M-2 rejection_reasons.** Across the three cases, the histogram union covers: `MARKET_HASH_NAME_UNRESOLVED`, `METADATA_NOT_FOUND`, at least one `_validate_input_items` substring, at least one `RiskDecision.reason_codes` value.
- **M-3 enrichment_success_ratio.** See R2.3.
- **M-4 solver_compatibility.** For at least one case (`MIXED`), `recipes_built < recipes_attempted` with a recorded engine-validation substring. For `SMALL`, `recipes_built == recipes_attempted` and equals the number of collections that received ≥ 10 homogeneous enriched inputs.
- **M-5 ev_risk_output_stability.** See R3.3.

## Tooling & Commands

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

## Acceptance Checklist

- [ ] R1.1 — `__all__` exactness
- [ ] R1.2 — production token guard
- [ ] R1.3 — test token guard
- [ ] R1.4 — Protected Core diff = empty
- [ ] R2.1 — basket determinism
- [ ] R2.2 — partition agreement across both paths
- [ ] R2.3 — enrichment success ratio equals config
- [ ] R2.4 — input order preservation
- [ ] R3.1 — recipe hash reproducibility
- [ ] R3.2 — probability sums to one
- [ ] R3.3 — EV / Risk byte-equality
- [ ] R3.4 — engine validation surfaced redacted
- [ ] R3.5 — risk reason histogram reproducibility
- [ ] M-1 accepted_candidates ≥ 1
- [ ] M-2 rejection_reasons covers all three buckets
- [ ] M-3 enrichment_success_ratio
- [ ] M-4 solver_compatibility < 1 for MIXED
- [ ] M-5 ev_risk_output_stability
- [ ] `pytest` total — all green (2878 + new tests pass)
- [ ] `ruff check .` — All checks passed
- [ ] `mypy app` — Success: no issues
- [ ] `git diff --check` — no whitespace errors

## Failure Handling

If any ring fails, the implementation phase MUST NOT commit. The failure must be reported with the failing assertion, the actual value, and the offending `SyntheticScaleCase.label`. Do not retry with relaxed thresholds; the design numbers (`1e-9`, byte-equality, exact tuple) are the contract.