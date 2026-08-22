# Phase 13I-1 — Metadata Provider Contract Audit — Requirements

## 1. Required `InputItem` fields (engine side)

From [app/services/tradeup_engine.py:18-29](app/services/tradeup_engine.py#L18-L29) and the
constraints enforced by `calculate_tradeup_results` /
`_validate_input_items` ([app/services/tradeup_engine.py:107-134](app/services/tradeup_engine.py#L107-L134)):

| `InputItem` field | Type    | Engine invariant |
| ----------------- | ------- | ---------------- |
| `market_hash_name`| `str`   | exact match for the same identity; used by recipe hash |
| `collection_name` | `str`   | must appear as a key in the output pool dict |
| `rarity`          | `str`   | must be **identical** across all 10 inputs |
| `actual_float`    | `float` | used by adjusted-float math; 0 ≤ float ≤ 1 |
| `min_float`       | `float` | per-collection float band, fed into adjusted-float |
| `max_float`       | `float` | per-collection float band, fed into adjusted-float |
| `price_cny`       | `Decimal`| aggregated for cost; must be positive |
| `stattrak`        | `bool`  | must be **identical** across all 10 inputs |
| `souvenir`        | `bool`  | must be **identical** across all 10 inputs |

Constraints to honor at the enrichment boundary:

1. The engine requires **exactly 10** `InputItem`s per recipe. The
   enrichment boundary must produce at most 10 accepted candidates; the
   solver is responsible for recipe construction, not the enricher.
2. `rarity`, `stattrak`, `souvenir` must be homogeneous across the 10.
   The enricher must therefore emit one (rarity, stattrak, souvenir)
   per recipe — a future concern, out of scope for this audit.
3. `actual_float` must lie within `[min_float, max_float]` of the same
   `collection_name`. The enricher must surface that mismatch as a
   diagnostic, not a fatal (it can simply skip the candidate). This is
   exactly what `LiveCandidateRejectionReason.FLOAT_OUTSIDE_SKIN_RANGE`
   already models ([app/services/live_metadata_catalog.py:41-48](app/services/live_metadata_catalog.py#L41-L48)).
4. `collection_name` must be non-null; `SkinMetadata` already allows
   `collection_name: str | None` ([app/services/metadata_models.py:14-18](app/services/metadata_models.py#L14-L18)).
   `MISSING_COLLECTION` rejection already exists in the live catalog.

## 2. Existing `SkinMetadata` fields (metadata side)

From [app/services/metadata_models.py:7-31](app/services/metadata_models.py#L7-L31):

| `SkinMetadata` field | Type    | Required by engine? | Notes |
| -------------------- | ------- | ------------------- | ----- |
| `market_hash_name`   | `str`   | yes (via `InputItem`) | unique key in `SkinMetadataCatalog` |
| `name`               | `str | None` | no | display only |
| `weapon`             | `str | None` | no | display only |
| `rarity`             | `str`   | yes | required by `__post_init__` (non-empty) |
| `category`           | `str | None` | no | display only |
| `collection_name`    | `str | None` | yes (must be non-null on input) | nullable in `SkinMetadata` itself |
| `min_float`          | `float` | yes | required (`< max_float`) |
| `max_float`          | `float` | yes | required (`> min_float`) |
| `stattrak`           | `bool = False` | per 13I-0, candidate-owned | metadata carries it but is NOT authoritative for the candidate |
| `souvenir`           | `bool = False` | per 13I-0, candidate-owned | metadata carries it but is NOT authoritative for the candidate |
| `paint_index`        | `int | None` | no | display / future paint-seed correlation |
| `raw`                | `dict | None` | no | provenance |

The engine reads **only** `market_hash_name`, `collection_name`,
`rarity`, `min_float`, `max_float` from metadata. `stattrak` /
`souvenir` are read today by `recipe_solver._build_eligible_pairs`
([app/services/recipe_solver.py:317-327](app/services/recipe_solver.py#L317-L327)), but 13I-0 decided
those should move to the candidate. So for the audit's purposes the
**metadata's authoritative contribution** is the five catalog fields.

## 3. Existing `TradeUpInputCandidate` fields (candidate side)

From [app/services/trade_up_input_candidate.py:7-50](app/services/trade_up_input_candidate.py#L7-L50):

| `TradeUpInputCandidate` field | Type           | Future role per 13I-0 |
| ---------------------------- | -------------- | ---------------------- |
| `listing_id`                 | `str`          | listing-snapshot identifier |
| `goods_id`                   | `str`          | provider-side identifier |
| `market_hash_name`           | `str | None`   | identity; optional; `None` → skip |
| `price_cny`                  | `Decimal`      | pricing; passed to `InputItem.price_cny` |
| `paintwear`                  | `Decimal`      | source of `actual_float` (Decimal → float, once) |
| `asset_id`                   | `str`          | provider-side identifier |
| `source`                     | `str`          | provider tag |
| `stattrak`                   | **TODO add**   | intrinsic item flag (per 13I-0) |
| `souvenir`                   | **TODO add**   | intrinsic item flag (per 13I-0) |

Note: `stattrak` / `souvenir` are not yet present on the candidate. 13I-0
recommended adding them but did not implement the change.

## 4. Gap analysis

For each `InputItem` field, where it will come from under the planned
boundary:

| `InputItem` field  | Source            | Existing today?                              | Gap |
| ------------------ | ----------------- | -------------------------------------------- | --- |
| `market_hash_name` | candidate         | yes (`str | None`)                           | none |
| `collection_name`  | metadata          | partial: `SkinMetadata.collection_name: str | None`, nullable | none — enricher must reject `None` |
| `rarity`           | metadata          | yes (`SkinMetadata.rarity: str`, non-empty)  | none |
| `actual_float`     | candidate         | yes via `paintwear: Decimal` (one conversion at boundary) | none |
| `min_float`        | metadata          | yes (`SkinMetadata.min_float: float`)        | none |
| `max_float`        | metadata          | yes (`SkinMetadata.max_float: float`)        | none |
| `price_cny`        | candidate         | yes (`Decimal`)                              | none |
| `stattrak`         | candidate         | **no** — 13I-0 deferred                       | candidate must grow two fields |
| `souvenir`         | candidate         | **no** — 13I-0 deferred                       | candidate must grow two fields |

**Field gap summary**: every catalog field `InputItem` needs is
already present on `SkinMetadata`. The only outstanding gap is on the
candidate side: `stattrak` and `souvenir`.

**Rule gaps the enricher will need to enforce** (none of these are
missing on the metadata side; they are enrichment-layer concerns):

- skip when `candidate.market_hash_name is None`;
- skip when `metadata.lookup(...)` returns `None`;
- skip when `metadata.collection_name is None`;
- skip when `not metadata.min_float <= actual_float <= metadata.max_float`;
- never let metadata overwrite candidate `stattrak` / `souvenir` (per
  the AskUserQuestion answers for this phase).

These four rules match the existing
`LiveCandidateRejectionReason` enum
([app/services/live_metadata_catalog.py:41-48](app/services/live_metadata_catalog.py#L41-L48)),
suggesting the enricher can reuse the same rejection vocabulary without
introducing a parallel set of codes.

## 5. Does the current metadata layer need a future extension?

**No.** For the `TradeUpInputCandidate → InputItem` boundary:

- `SkinMetadata` already carries the five catalog fields the engine
  reads (`market_hash_name`, `collection_name`, `rarity`, `min_float`,
  `max_float`).
- `normalize_skin` already enforces the non-blank `rarity` invariant
  ([app/services/metadata_service.py:23-29](app/services/metadata_service.py#L23-L29)).
- `SkinMetadataCatalog` already supports
  `get_by_market_hash_name` and bucket-keyed lookups
  ([app/services/live_metadata_catalog.py:252-281](app/services/live_metadata_catalog.py#L252-L281)),
  which the future enrichment layer can build on.
- The two `MetadataProvider` implementations
  ([app/services/metadata_provider.py:17-47](app/services/metadata_provider.py#L17-L47))
  both already return `list[SkinMetadata]`, which is what the future
  enricher needs.
- The existing synthetic `trade_up_pipeline.InMemoryTradeUpInputMetadataResolver`
  already proves the seam. Its `TradeUpInputMetadata` is a strict
  subset of `SkinMetadata` (only the five fields above plus
  `market_hash_name`); a future live enricher can be wired on top of
  `SkinMetadataCatalog` without reshaping the metadata side.

**Conclusion**: the metadata layer does **not** require a new field or
shape to satisfy the planned enrichment boundary. The only contract
work is on the candidate side (add `stattrak`, `souvenir`) and on the
enrichment-layer module itself (which is a future phase, not this
audit).

## 6. Recommended future enrichment contract (design only)

Shape:

```text
TradeUpInputEnricher (Protocol)
    enrich(candidate) -> TradeUpEnrichedInput | EnrichmentRejection

InMemoryTradeUpInputEnricher
    (wraps SkinMetadataCatalog + TradeUpInputCandidate)

enrich_candidates(candidates, enricher) -> list[TradeUpEnrichedInput]
```

Field rules (per AskUserQuestion answers):

1. `InputItem.market_hash_name := candidate.market_hash_name` (skip if `None`).
2. `InputItem.collection_name := metadata.collection_name` (skip if `None`).
3. `InputItem.rarity := metadata.rarity` (non-empty enforced upstream).
4. `InputItem.min_float := metadata.min_float`.
5. `InputItem.max_float := metadata.max_float`.
6. `InputItem.actual_float := float(candidate.paintwear)` (single conversion at boundary).
7. `InputItem.price_cny := candidate.price_cny`.
8. `InputItem.stattrak := candidate.stattrak` — **candidate wins**, metadata cannot override.
9. `InputItem.souvenir := candidate.souvenir` — **candidate wins**, metadata cannot override.

Rejection codes (reusing existing vocabulary from
`LiveCandidateRejectionReason` where possible):

- `METADATA_NOT_FOUND` — catalog has no row for `market_hash_name`.
- `MISSING_COLLECTION` — `SkinMetadata.collection_name is None`.
- `CANDIDATE_FLOAT_MISSING` — `candidate.paintwear is None`.
  (Not currently a field on `TradeUpInputCandidate`; the validator
  already requires it to be present and in `[0, 1]`, so this rejection
  code is moot for the current candidate contract — kept for symmetry
  with the live catalog only.)
- `FLOAT_OUTSIDE_SKIN_RANGE` — `actual_float` lies outside
  `[min_float, max_float]`.

New rejection codes that do not exist today and would be introduced if
the future enricher needed them:

- `MARKET_HASH_NAME_UNRESOLVED` — `candidate.market_hash_name is None`.
  This is the "unresolved identity" case from 13D-0 and 13E-0; today
  the synthetic adapter silently drops such candidates, but a future
  enricher may want a count for diagnostics.

## 7. Limitations

- This audit is read-only. No code, schema, or model changed.
- The audit does not decide whether the future enrichment module is a
  single function, a Protocol-implementing class, or a re-shape of
  `trade_up_pipeline.py`. That is implementation work for a later phase.
- The audit assumes 13I-0's ownership split remains in force:
  `stattrak` / `souvenir` on the candidate; `collection_name`,
  `rarity`, `min_float`, `max_float` on metadata. If that split is
  revisited, the field table above must be re-derived.
- The audit covers only the **input** side of the engine. Output pool
  construction (`build_output_candidates_by_collection`,
  `OutputCandidate`) is unchanged: those flows already derive from
  `SkinMetadata` and remain viable as-is.
- `solve_recipes` / `value_live_recipes` still read
  `skin.stattrak` / `skin.souvenir` from `SkinMetadata`
  ([app/services/recipe_solver.py:317-327](app/services/recipe_solver.py#L317-L327)).
  13I-0 decided those should move to the candidate, but the solver
  itself is not modified in this audit. The audit only confirms that
  the metadata side is ready; the solver rewrite is a future phase.
- `ByMykelMetadataProvider` carries the
  "raw external field shapes may evolve" assumption; the audit treats
  that as out of scope.
- `LiveCandidateRejectionReason` is a `StrEnum` imported in
  `live_metadata_catalog.py`. Reusing it from a future enrichment
  module is possible but would introduce a dependency on the live
  catalog from a generic enrichment layer. That is a packaging
  question, not a correctness question.