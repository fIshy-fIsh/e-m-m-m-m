# Phase 13I-0 — Trade-up Metadata Enrichment Boundary Review — Requirements

## 1. Which fields are required by `InputItem`?

`InputItem` ([app/services/tradeup_engine.py:18-29](app/services/tradeup_engine.py#L18-L29)) currently requires:

| Field             | Type    | Source today                                |
| ----------------- | ------- | ------------------------------------------- |
| `market_hash_name`| `str`   | `BuffListing.market_hash_name` / candidate  |
| `collection_name` | `str`   | `SkinMetadata.collection_name`              |
| `rarity`          | `str`   | `SkinMetadata.rarity`                       |
| `actual_float`    | `float` | `BuffListing.paintwear` / candidate float   |
| `min_float`       | `float` | `SkinMetadata.min_float`                    |
| `max_float`       | `float` | `SkinMetadata.max_float`                    |
| `price_cny`       | `Decimal`| `BuffListing.price_cny` / candidate price |
| `stattrak`        | `bool`  | `SkinMetadata.stattrak`                     |
| `souvenir`        | `bool`  | `SkinMetadata.souvenir`                     |

Constraints enforced by `calculate_tradeup_results` and
`_validate_input_items`:

- exactly 10 input items,
- identical rarity across all 10,
- identical `stattrak` value across all 10,
- identical `souvenir` value across all 10,
- every `item.collection_name` must appear as a key in the supplied
  `output_candidates_by_collection`,
- the engine depends on `collection_name` to select the output pool,
  on `rarity` to validate homogeneity,
- `stattrak` / `souvenir` are filter / homogeneity inputs only — they do
  not appear in `calculate_output_float` / probability math.

`RecipeSolverConfig.target_stattrak` and `target_stattrak` /
`target_souvenir` exist to pre-filter at solve time; they don't change
the engine contract.

`OutputCandidate` ([app/services/tradeup_engine.py:32-41](app/services/tradeup_engine.py#L32-L41))
requires `market_hash_name`, `collection_name`, `rarity`, `min_float`,
`max_float`, `estimated_price_cny` — but the **input** side of the engine
does not need output candidates to construct `InputItem`s; it needs them
later at evaluation time. The enrichment boundary therefore concerns
**input** fields, not output pools.

## 2. Recommended field ownership

Per the three AskUserQuestion answers (keep candidate minimal, add an
explicit enrichment module, split special-item flags from collection
metadata):

### A. `TradeUpInputCandidate` — keep minimal, narrow contract

| Field               | Today? | Notes                                              |
| ------------------- | ------ | -------------------------------------------------- |
| `listing_id`        | yes    | source identifier                                  |
| `goods_id`          | yes    | BUFF goods ID (already owned by BUFF side)         |
| `market_hash_name`  | yes    | optional, can be `None`                            |
| `price_cny`         | yes    | Decimal, positive                                  |
| `paintwear`         | yes    | Decimal, 0..1                                      |
| `asset_id`          | yes    | BUFF asset identifier                              |
| `source`            | yes    | provider tag, default `"buff"`                     |
| `stattrak`          | **add**| identity-of-the-item flag (StatTrak™ has its own listing) |
| `souvenir`          | **add**| identity-of-the-item flag (Souvenir has its own listing) |

Do **not** add: `collection_name`, `rarity`, `min_float`, `max_float`,
`weapon`, `category`, `paint_index`, `name`. Those are collection /
catalog concerns, not candidate concerns.

Rationale:
- The candidate describes **one listing snapshot**. It already carries
  its own provider-specific flags (`source`, `asset_id`, `goods_id`,
  `listing_id`). StatTrak / Souvenir are intrinsic to the listing
  itself, not to a catalog row. Keeping them on the candidate preserves
  the existing BUFF `BuffListing` shape and the synthetic adapter
  contract: BUFF already exposes both flags in different forms.
- Adding `stattrak` / `souvenir` here does **not** force live metadata
  resolution: a candidate whose `market_hash_name is None` remains
  skipped, regardless of these new fields.
- It keeps the candidate provider-agnostic. A future SteamDT or SteamApis
  listing model can map onto the same eight fields.

### B. Metadata enrichment layer — independent module, replaces the synthetic adapter only when a real source exists

The 13H-0 `trade_up_pipeline.py` already establishes the seam. The
metadata enrichment layer should be the **only** place that knows how
to produce `InputItem`s from candidates. Today that layer is a
synthetic, offline `InMemoryTradeUpInputMetadataResolver` returning
`TradeUpInputMetadata`. The recommended boundary makes that contract
explicit and minimal:

| `InputItem` field  | Comes from              |
| ------------------ | ----------------------- |
| `market_hash_name` | `candidate.market_hash_name` (skipped if `None`) |
| `collection_name`  | metadata                |
| `rarity`           | metadata                |
| `min_float`        | metadata                |
| `max_float`        | metadata                |
| `actual_float`     | `candidate.paintwear` (cast `Decimal → float`, once) |
| `price_cny`        | `candidate.price_cny` (no conversion) |
| `stattrak`         | `candidate.stattrak`    |
| `souvenir`         | `candidate.souvenir`    |

Proposed module shape (no implementation here — design only):

```text
app/services/trade_up_input_enrichment.py
    TradeUpEnrichedInput          # (market_hash_name, input_item) pair
    TradeUpInputEnricher          # Protocol: enrich(candidates) -> list
    InMemoryTradeUpInputEnricher  # uses TradeUpInputMetadataResolver
    enrich_candidates(candidates, enricher)
```

Why a separate module name from `trade_up_pipeline.py`? The current
`trade_up_pipeline.py` was deliberately scoped to *synthetic* metadata
proving the candidate-to-engine boundary. A future enrichment layer
should live next to it but be named for what it is, not for what it is
*not*. Keeping `trade_up_pipeline.py` as the synthetic placeholder
also preserves the offline-only invariant from 13H-0: any future live
enricher cannot be invoked from this module.

### C. Identity layer — `BuffItemIdentity`, unchanged

`BuffItemIdentity` ([app/services/buff_item_identity.py:26-36](app/services/buff_item_identity.py#L26-L36))
holds exactly `(market_hash_name, goods_id)`. It must remain that small.
It does not own `collection_name`, `rarity`, float bounds, or special
flags. The metadata enrichment layer consumes an identity, but identity
itself does not own catalog data.

## 3. Should `TradeUpInputCandidate` be expanded or remain minimal?

Expand **only** with the two intrinsic-item flags:
- add `stattrak: bool = False`
- add `souvenir: bool = False`

Do **not** add any other fields. Keep the fixed-field allowlist
contract (the existing `_ALLOWED_FIELDS` frozenset
[trade_up_input_candidate.py:7-17](app/services/trade_up_input_candidate.py#L7-L17))
and update it to include the two new fields. Update the dataclass,
`__post_init__`, `_validate_*` helpers, and `TradeUpInputCandidateValidationError`'s
allowlist.

Reasoning:

- `stattrak` / `souvenir` describe the **listing itself**, not the catalog
  row. They survive identity resolution — the same `market_hash_name`
  exists for both normal and StatTrak variants. Forcing them into
  metadata would require metadata to be per-listing, which contradicts
  the catalog shape of `SkinMetadata`.
- Everything else (`collection_name`, `rarity`, `min_float`, `max_float`)
  is catalog-level data; the candidate should not grow to host a
  catalog row.
- The fixed-allowlist boundary on `TradeUpInputCandidate` is the single
  reason the synthetic pipeline in 13H-0 could not leak provider fields
  into the engine. Preserving it is the cheapest way to keep that
  guarantee.

## 4. How should `stattrak` / `souvenir` / `collection` / `rarity` be supplied in future?

| Concept         | Future source                                  | Today                                       |
| --------------- | ---------------------------------------------- | ------------------------------------------- |
| `stattrak`      | BUFF listing annotation (provider-native)      | absent on `TradeUpInputCandidate`           |
| `souvenir`      | BUFF listing annotation (provider-native)      | absent on `TradeUpInputCandidate`           |
| `collection`    | future metadata enrichment layer (Phase 4)     | synthetic `TradeUpInputMetadata` (13H-0)    |
| `rarity`        | future metadata enrichment layer (Phase 4)     | synthetic `TradeUpInputMetadata` (13H-0)    |

Pipeline future flow:

```text
BuffListing / future SteamDT / SteamApis listing
   ↓  (provider → candidate adapter, Phase 13E / 13I-1+)
TradeUpInputCandidate  (listing_id, goods_id, market_hash_name?, price_cny,
                        paintwear, asset_id, source, stattrak, souvenir)
   ↓  (enrichment layer, Phase 4 successor; may itself be split into
       BuffItemIdentityResolver → metadata resolver → input enricher)
InputItem  (engine input)
```

Constraints for the future enrichment layer:

1. The enricher must remain **replaceable**: an in-memory synthetic
   implementation stays as a fallback when no real metadata source is
   wired.
2. The enricher must **never** synthesize a missing
   `market_hash_name`. Unresolved identity is preserved by skipping the
   candidate. This matches the current `candidates_to_input_items`
   skip-on-`None` behavior.
3. The enricher must never silently coerce `stattrak` / `souvenir`
   away from the candidate. If the candidate says `stattrak=True`, the
   resulting `InputItem.stattrak` must be `True`, regardless of
   metadata.
4. The enricher must produce **exactly one** `InputItem` per
   *resolved* candidate. Candidates without a metadata match drop out
   silently (current behavior) and can be counted via a future
   `EnrichmentDiagnostic` if/when needed — not in this phase.
5. The enrichment layer must not pull `price_cny` from metadata;
   prices live on the candidate / BUFF side, never on `SkinMetadata`.

## 5. Architecture decision

**Decision:** Keep `TradeUpInputCandidate` minimal. Extend it **only**
with `stattrak: bool = False` and `souvenir: bool = False`. Stand up a
dedicated `app/services/trade_up_input_enrichment.py` (design-only this
phase) that owns the `TradeUpInputCandidate → InputItem` transition,
with `collection_name`, `rarity`, `min_float`, `max_float` flowing in
from a metadata resolver and `stattrak` / `souvenir` / `price_cny` /
`paintwear` / `market_hash_name` flowing in from the candidate itself.

**Rationale:**
- Aligns with the three AskUserQuestion answers.
- Honors the existing Protected Core boundary on
  `TradeUpInputCandidate` and `InputItem` — neither is widened.
- Mirrors how `recipe_solver._build_eligible_pairs` already uses the
  candidate-vs-metadata split: candidate brings `market_hash_name`,
  `float_value`, `price_cny`; `SkinMetadata` brings `collection_name`,
  `rarity`, `min_float`, `max_float`, `stattrak`, `souvenir`. The
  proposed boundary corrects one wart: today the recipe solver uses
  `skin.stattrak` / `skin.souvenir` as the source of truth, but those
  are catalog-level flags, not listing-level flags. The candidate-level
  fields are the correct source. Future metadata enrichment must
  therefore defer to the candidate for these two values.
- The synthetic adapter (`trade_up_pipeline.py`) becomes the offline
  reference implementation under the new enrichment module. It is not
  deleted in this phase — it is preserved as the test/demo seam.

**What is NOT decided here:**
- Live metadata provider choice. That remains a Phase 4 successor.
- Whether to fold `solve_recipes` into the enrichment module. Out of
  scope; it remains the production solver chain.
- Whether `market_hash_name` resolution should become a peer
  (`BuffItemIdentityResolver`) inside the enrichment module. It
  already exists as `BuffItemIdentityResolver`; the new layer should
  consume it but not redefine it.