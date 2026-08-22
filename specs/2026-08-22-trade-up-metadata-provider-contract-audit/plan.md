# Phase 13I-1 — Metadata Provider Contract Audit — Plan

## Goal

Audit whether the existing metadata models / providers can satisfy the
future enrichment boundary:

```
TradeUpInputCandidate
        ↓
Metadata Enrichment
        ↓
InputItem
```

This is an audit-only phase. No implementation, no provider additions,
no metadata model edits, no `InputItem` edits, no solver edits.

## Constraints (from the task brief)

- Audit-only. No new code that crosses the boundary.
- Do not modify `SkinMetadata`, `CollectionMetadata`,
  `OutputCandidateBuildResult`, `RarityOrder`.
- Do not modify `InputItem`.
- Do not modify `recipe_solver`.
- Do not implement enrichment.

## Approach

1. Tabulate what `InputItem` requires.
2. Tabulate what `SkinMetadata` already provides.
3. Tabulate what `TradeUpInputCandidate` already provides
   (and which two new fields 13I-0 deferred).
4. Compute the gap for the enrichment boundary.
5. Recommend whether the metadata layer needs a future extension.
6. Sketch the recommended future enrichment contract (no
   implementation).

## Sources inspected

- [app/services/tradeup_engine.py:18-29](app/services/tradeup_engine.py#L18-L29) —
  `InputItem` dataclass.
- [app/services/tradeup_engine.py:107-134](app/services/tradeup_engine.py#L107-L134) —
  `_validate_input_items` engine invariants.
- [app/services/metadata_models.py](app/services/metadata_models.py) —
  `SkinMetadata`, `CollectionMetadata`, `OutputCandidateBuildResult`,
  `RarityOrder`.
- [app/services/metadata_provider.py](app/services/metadata_provider.py) —
  `MetadataProvider`, `LocalJsonMetadataProvider`,
  `ByMykelMetadataProvider`.
- [app/services/metadata_service.py](app/services/metadata_service.py) —
  `normalize_skin`, `build_output_candidates_by_collection`.
- [app/services/live_metadata_catalog.py](app/services/live_metadata_catalog.py) —
  `SkinMetadataCatalog`, `LiveSolverBucketKey`,
  `classify_steamapis_snapshot`.
- [app/services/trade_up_pipeline.py](app/services/trade_up_pipeline.py) —
  13H-0 synthetic metadata adapter (offline-only placeholder).
- [app/services/trade_up_input_candidate.py](app/services/trade_up_input_candidate.py) —
  `TradeUpInputCandidate` frozen contract.
- [app/services/recipe_solver.py:255-271](app/services/recipe_solver.py#L255-L271) —
  `build_recipe_hash` (informational only; not modified).

## Tasks

- T1. Field tables: `InputItem` requirements ↔ `SkinMetadata` fields ↔
  `TradeUpInputCandidate` fields.
- T2. Engine invariants column (the rules that any future
  `InputItem` must satisfy).
- T3. Gap analysis (per enrichment-boundary direction: candidate →
  metadata, metadata → candidate).
- T4. Decision: does the metadata layer need a future extension?
- T5. Recommended future enrichment contract (fields, ownership,
  invariant rules).
- T6. Limitations and what must not be inferred.