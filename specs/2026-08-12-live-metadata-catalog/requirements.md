# Phase 13A Step 2D — Requirements

## Purpose

Add only the deterministic offline boundary:

```text
SteamApisOfferPoolSnapshot
→ existing Step 2B CandidateListing adapter
→ exact SkinMetadata catalog lookup
→ eligible/rejected classification
→ solver-compatible bucket index
```

This seam advances metadata enrichment without completing a roadmap phase or creating production/runtime wiring.

## Approved scope

Exactly these seven paths may differ from `3b610d4d04dffaafb56be02967f74850f1379f02`:

```text
README.md
app/services/live_metadata_catalog.py
docs/STEAMAPIS_MARKET_DATA_NOTES.md
specs/2026-08-12-live-metadata-catalog/plan.md
specs/2026-08-12-live-metadata-catalog/requirements.md
specs/2026-08-12-live-metadata-catalog/validation.md
tests/test_live_metadata_catalog.py
```

All prior SteamApis modules, `CandidateListing`, metadata models/providers/services, recipe solver, trade-up engine, Phase 12 BUFF modules, dependencies, config/env, fixtures, runtime services, clients, pipeline, scheduler, FastAPI, database, Docker, SteamDT, Redis, Discord, and earlier specs remain unchanged.

## Public API

`app/services/live_metadata_catalog.py` exports exactly:

- `LiveMetadataCatalogError`
- `LiveCandidateRejectionReason`
- `LiveSolverBucketKey`
- `LiveCandidateBinding`
- `LiveCandidateRejection`
- `LiveSolverBucket`
- `LiveCandidateClassification`
- `SkinMetadataCatalog`
- `classify_steamapis_snapshot`

The public DTO field order is:

```text
LiveSolverBucketKey:
  input_rarity
  stattrak
  souvenir

LiveCandidateBinding:
  source_offer_id
  candidate
  skin_metadata

LiveCandidateRejection:
  source_offer_id
  reason_code

LiveSolverBucket:
  key
  bindings
  affected_collections

LiveCandidateClassification:
  eligible
  rejected
  buckets
```

All DTOs are frozen, keyword-only, repr-suppressed, and tuple/frozenset backed. Classification-wide `affected_collections` is derived from buckets rather than stored as a fourth field.

`SkinMetadataCatalog` exposes only:

```python
SkinMetadataCatalog(*, skins: Sequence[SkinMetadata])
get_by_market_hash_name(market_hash_name: str) -> SkinMetadata | None
get_by_solver_bucket_key(key: LiveSolverBucketKey) -> tuple[SkinMetadata, ...]
```

The classifier is:

```python
classify_steamapis_snapshot(
    snapshot: SteamApisOfferPoolSnapshot,
    catalog: SkinMetadataCatalog,
) -> LiveCandidateClassification
```

## SkinMetadata contract and catalog hardening

The legacy source model fields are:

```text
market_hash_name: str
name: str | None
weapon: str | None
rarity: str
category: str | None
collection_name: str | None
min_float: float
max_float: float
stattrak: bool
souvenir: bool
paint_index: int | None
raw: dict[str, Any] | None
```

The legacy model enforces only nonblank `market_hash_name`, nonblank `rarity`, and `min_float < max_float`; it is shallowly frozen because `raw` can be mutable. The catalog therefore requires the exact `SkinMetadata` type and defensively reconstructs every semantic record with `raw=None`.

Catalog construction additionally requires exact annotated primitive types needed for safe deterministic indexing: exact strings for required string fields, `None` or exact strings for optional strings, exact finite floats with `min_float < max_float`, exact booleans, and `None` or exact integers for paint index. It does not impose a new metadata `[0, 1]` range rule and does not strip, case-fold, infer, or otherwise rewrite semantic values.

The catalog never retains, traverses, serializes, or exposes source `raw` payloads. It snapshots the input sequence and is unaffected by later source-list, ordering, record, or raw-dictionary mutation.

## Exact indexes and duplicate policy

The catalog builds immutable indexes for:

```text
market_hash_name → SkinMetadata
(input_rarity, stattrak, souvenir) → tuple[SkinMetadata, ...]
```

Name lookup is exact and case-sensitive. It performs no trim or case normalization. Case-distinct names remain distinct and a valid unknown name returns `None`.

Any duplicate exact `market_hash_name`, including otherwise identical records, fails the entire catalog construction. There is no first-wins, last-wins, deduplication, or partial catalog. This closes the existing recipe solver's silent dictionary-comprehension last-wins risk before live classification.

Solver-key metadata tuples are sorted by exact market name. A valid unknown key returns `()`. Every lookup returns fresh detached metadata with `raw=None`.

Empty metadata fails closed.

## Classification

The classifier requires exact snapshot and catalog types, reconstructs the public snapshot, and processes observations in deterministic snapshot order. For every observation it:

1. invokes the unchanged `adapt_steamapis_listing_to_candidate()` exactly once;
2. performs one exact metadata lookup;
3. emits exactly one eligible binding or rejection.

Different source IDs are never deduplicated, including when market names are identical. A repeated source ID in one supplied snapshot fails closed so one identity cannot appear more than once.

Eligible and rejected tuples each preserve their corresponding snapshot subsequence. An ordinary failure on any record returns no partial classification.

## Rejection reasons and precedence

The exact typed reason values are:

```text
metadata_not_found
missing_collection
candidate_float_missing
float_outside_skin_range
```

They apply in that order. Missing metadata is never silently skipped.

Only `collection_name is None` is `missing_collection`; no collection is inferred from names or other fields.

Candidate float range uses the inclusive legacy solver geometry:

```text
skin.min_float <= candidate.float_value <= skin.max_float
```

Exact minimum and maximum are eligible. A present value below or above the bounds is rejected. The classifier does not calculate adjusted float.

## Binding and provenance

An eligible binding retains only:

```text
source_offer_id
CandidateListing
SkinMetadata(raw=None)
```

The source ID comes directly from the observation and remains the join key back to `SteamApisOfferPool`. It is not parsed from compatibility IDs or URLs.

`purchase_link` remains only on the observation/pool. It is not copied to bindings, rejections, metadata, buckets, exceptions, or repr. The binding's existing Step 2B candidate may retain its documented `inspect_link`, but enclosing repr and errors remain redacted.

`days_trade_locked` remains observation provenance. Step 2D does not filter it and never treats `None` as zero.

No rarity, collection, StatTrak, Souvenir, special-seed, or trade-lock fact is inferred from a market name, paint seed, link, or other provider text.

## Solver bucket contract

The stable key is exactly:

```text
input_rarity
stattrak
souvenir
```

Collection is intentionally absent. The current solver and trade-up engine allow one same-rarity/mode ten-item recipe to mix multiple collections; collection determines output topology/probability and affected recomputation scope rather than input-group identity.

Bindings within each bucket retain eligible/snapshot order. Buckets are sorted ascending by `(input_rarity, stattrak, souvenir)`, with ordinary boolean order `False` before `True`.

Every bucket is nonempty and homogeneous for its key. Its `affected_collections` is exactly the `frozenset[str]` of binding collection names. Classification-wide affected collections is the union of bucket sets.

The classification exposes no mutable bucket dictionary and does not run the recipe solver.

## Errors and redaction

All ordinary public catalog, DTO, lookup, adapter, and classification contract failures surface as:

```text
invalid live metadata catalog contract
```

through `LiveMetadataCatalogError`. Ordinary wrapped failures suppress displayed chaining. Error text and public repr never reveal purchase link, inspect link, market name, source ID, price, float, raw payload, seller/account data, API key, Authorization value, Cookie, token, or secret.

`MemoryError` propagates unchanged. `KeyboardInterrupt`, cancellation, and other non-`Exception` control flow are not caught.

## Explicit exclusions

Step 2D adds no:

- WebSocket dependency/client or SteamApis connection;
- BUFF, SteamDT, Redis, Discord, database, FastAPI, pipeline, scheduler, or runtime connection;
- metadata provider/client/file/environment/network read;
- recipe construction or solver invocation;
- trade-up output, probability, adjusted-float, EV, ROI, risk, valuation, or profitability calculation;
- trade-lock hard rejection;
- metadata/name/special-seed inference;
- URL parsing, browser opening, login, automatic purchase, or marketplace write;
- retry, timer, task, thread, queue, callback, or background work;
- commit, push, or Step 2E work.
