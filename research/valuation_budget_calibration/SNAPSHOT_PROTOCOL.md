# Representative Listing Snapshot Protocol v1

## Status

- **Protocol ID:** `representative-listing-snapshot-v1`
- **Schema version:** `1`
- **Phase:** 15C-1 design freeze only
- **Collection status:** NOT STARTED / NOT AUTHORIZED
- **Production policy:** default `5` unchanged; hard maximum `60` unchanged

This is the normative research protocol for a future, separately authorized Phase 15C-2 implementation. It does not authorize a live request, dataset, scheduler, or policy change.

## 1. Sampling unit and observable frame

One observation is one timestamped full capture attempt, before valuation, for one exact current scanner auto-universe plan in one productive rarity/StatTrak stratum.

For every observation, rebuild the universe from the campaign-pinned identity and metadata catalogs using the current `MarketUniverseBuilder` contract:

```text
cap = 10
allocation = cohort-depth
target cohorts = 3
souvenir inclusion = include
rarity/mode = assigned campaign stratum
```

The observable population is limited to the ordered listings returned by the existing anonymous compatibility path for **page 1 / default sort** for each of the ten planned goods IDs. This supports a current-scanner workload study; it is not a complete BUFF-market or order-book sample.

## 2. Balanced campaign v1

Productive strata, in frozen order:

```text
0  Consumer Grade / normal
1  Industrial Grade / normal
2  Mil-Spec Grade / normal
3  Mil-Spec Grade / StatTrak
4  Restricted / normal
5  Restricted / StatTrak
6  Classified / normal
7  Classified / StatTrak
```

Candidate campaign:

- 14 consecutive UTC days;
- 8 slots daily at `00:17`, `03:17`, `06:17`, `09:17`, `12:17`, `15:17`, `18:17`, `21:17` UTC;
- 112 planned attempts, 14 per stratum;
- stratum index `(slot_within_day + utc_day_index) mod 8`;
- deterministic jitter formula: SHA-256 the exact UTF-8 string `<campaign_id>|<nominal_slot_utc>`, interpret the first eight digest bytes as an unsigned big-endian integer, then use `value mod 21 - 10` minutes;
- slot missed if not started within 30 minutes after scheduled time;
- missed slots are manifested and never replaced;
- ten sequential page requests per started observation;
- future collector-owned minimum two seconds between request starts;
- no automatic retry or polling.

This equal-stratum campaign estimates the balanced protocol distribution. It does not estimate a production-weighted distribution unless future evidence supplies production stratum weights.

## 3. Existing interface boundary

| Purpose | Confirmed existing boundary |
|---|---|
| Plan ten goods | `build_universe_goods_ids` with current pinned resolvers and `MarketUniverseSpec` |
| Fetch one page | `BuffAnonymousListingHttpClient.fetch_sell_order_payload(goods_id)` |
| Parse one page | `BuffListingProvider.get_listings(goods_id)` |
| Bind exact identity | `bind_identity_to_provider` / pinned `resolve_goods_id` |
| Classify intrinsics | `bind_intrinsic_flags_to_provider` / `CanonicalNameIntrinsicFlagResolver` |
| Candidate semantics | `convert_buff_listing_to_candidate` |
| Metadata enrichment | `PinnedSkinMetadataResolver` / `InMemoryTradeUpInputEnricher` |
| Offline recipes | `enumerate_scanner_recipe_selections` with `RecipeEnumerationConfig()` |
| Metrics | Phase 15A `measure_output_name_sequences` and R-7 summary |

A future collector composes these narrow layers and stops after immutable normalized snapshot construction. It does not call `LiveScannerOrchestrator.run_once`, valuation, SteamDT, cache, or Redis.

## 4. Field provenance

### Direct compatibility facts

- `listing_reference`: normalized item `id`; labelled compatibility reference because official canonical semantics remain TODO;
- `asset_reference`: normalized `asset_info.assetid`;
- `price_cny`: exact positive Decimal serialized as a string; official currency/fee semantics remain unconfirmed;
- `paintwear`: exact bounded Decimal serialized as a string;
- optional `paintseed`;
- `source=buff`.

### Request/universe-derived

- `goods_id`;
- universe rank;
- selected cohort and allocation facts;
- target rarity/mode and protocol configuration.

### Existing binding-derived

- `market_hash_name`: pinned exact identity binding, not BUFF-supplied;
- `stattrak` / `souvenir`: exact canonical-name classification, not BUFF-supplied;
- `rarity` / `collection_name`: pinned metadata, not BUFF-supplied.

### Collector/protocol-derived

- nominal/scheduled/start/completion UTC timestamps;
- snapshot and campaign IDs;
- acquisition, binding, metadata, candidate, and observation statuses;
- stable redacted reasons;
- hashes and counts.

### Unavailable/unresolved

Provider observation timestamp, quantity, full depth, seller count, pagination completeness, listing lifecycle/freshness, trade-lock state, provider-supplied intrinsic/metadata facts, and official listing-ID/currency semantics are not available from the current confirmed path.

## 5. Snapshot file v1

One JSON object, encoded UTF-8 with sorted keys and one trailing newline, is atomically written for every attempt that materializes an exact ten-goods universe.

`snapshot_id` is deterministic: `snap-v1-` plus the first 24 lowercase hex characters of SHA-256 over exact UTF-8 `<campaign_id>|<nominal_slot_utc>|<input_rarity>|<stattrak_mode>`.

Required top-level keys:

```text
schema_version
protocol_id
campaign_id
snapshot_id
nominal_slot_utc
scheduled_for_utc
observed_at_utc
capture_completed_at_utc
timestamp_source
observation_status
stratum
provenance
universe
acquisition_summary
pages
```

`timestamp_source` is exactly `collector_host_utc_clock`; no timestamp is attributed to BUFF.

`provenance` records:

- collector Git commit;
- identity snapshot relative path and SHA-256;
- metadata snapshot relative path and SHA-256;
- universe configuration (`cap=10`, `cohort-depth`, target 3, Souvenir include);
- recipe enumeration (`2 / 256`);
- protocol/schema version.

`universe.planned_goods` contains ten ordered records with goods ID, rank, exact planned market name, rarity, normal/StatTrak, Souvenir, cohort collection, and allocated cohort slot.

`pages` contains ten ordered records aligned with planned goods. Each page has acquisition status, stable failure reason/detail or null, listing count, and ordered normalized listings.

Each normalized listing has:

```text
listing_reference
listing_reference_kind = anonymous_item_id_compatibility
asset_reference
goods_id
market_hash_name (nullable)
price_cny (decimal string)
paintwear (decimal string)
paintseed (nullable integer)
stattrak (nullable boolean)
souvenir (nullable boolean)
rarity (nullable)
collection_name (nullable)
source = buff
identity_status
intrinsic_status
metadata_status
candidate_status
replay_status
rejection_reason (nullable)
```

The schema parser must reject unknown or duplicate keys, invalid exact types, invalid Decimal strings, duplicate page goods IDs, duplicate listing references within an observation, count mismatches, and impossible status combinations.

## 6. Append-only manifest v1

Actual datasets remain outside Git by default:

```text
<artifact-root>/valuation_budget_calibration/<campaign_id>/
  campaign.v1.json
  manifest.v1.jsonl
  snapshots/
    snap-v1-<nominal-UTC>-<stratum-slug>-<snapshot-id>.json
```

One canonical JSON line is appended per planned slot. Required manifest facts include campaign/snapshot IDs, nominal/scheduled/start/completion times, stratum, outcome, stable reason, snapshot relative path or null, snapshot SHA-256 or null, and counts. A missed slot or planning failure has no fabricated snapshot file.

Snapshot files and existing manifest lines are never rewritten. A correction appends a superseding record that references the prior record; no history is deleted.

## 7. Status and missingness

### Page acquisition statuses

- `SUCCESS` — atomically parsed nonempty page;
- `EMPTY_PAGE` — atomically parsed empty page;
- `FETCH_FAILED` — request/non-2xx/transport failure;
- `PARSE_FAILED` — complete page rejected by atomic parser;
- `BINDING_FAILED` — integrity/conflict aborted the page.

### Row-stage statuses

- identity: `RESOLVED` / `UNRESOLVED`;
- intrinsic: `RESOLVED` / `UNRESOLVED` / `CONFLICT`;
- metadata: `RESOLVED` / `NOT_FOUND` / `NOT_ATTEMPTED`;
- candidate: `ACCEPTED` / `REJECTED` / `NOT_ATTEMPTED`.

### Observation statuses

**COMPLETE:** exact ten-goods plan; all ten pages are `SUCCESS` or `EMPTY_PAGE`; every returned listing resolves through the same pinned identity/intrinsic/metadata contracts used by the plan and reaches an accepted replay input; all schema/provenance/count/hash checks pass. Empty pages do not make it partial. If fewer than ten accepted listings exist, unchanged composition truthfully returns zero recipes; retain the COMPLETE observation with `recipe_count=0` and `run_unique_output_names=0`.

**PARTIAL:** exact plan exists, but one or more pages are `FETCH_FAILED` or `PARSE_FAILED`. Retain successful pages for audit, but exclude the observation from policy-facing metrics.

**INVALID_FOR_CALIBRATION:** planning does not produce exact ten goods; binding fails; any returned listing cannot reproduce its planned identity/intrinsic/metadata/candidate facts (catalog/provenance drift); schema/provenance/hash/catalog drift or internal invariants fail; or snapshot-level failure prevents truthful replay. Retain a manifest record and exclude it from metrics.

`MISSED_OBSERVATION` is a manifest outcome for a slot never started on time; it has no snapshot file.

Stable reasons are defined in `requirements.md`. Store safe reason/detail codes only, never raw exception text or rejected values.

## 8. Retention and redaction

- Persist only normalized minimal records; raw provider payload retention is prohibited by default.
- Persist no headers, URLs, query strings, cookies, tokens, authorization values, API keys, seller/account/personal data, or complete exception text.
- Scan keys and string values for secret/header/cookie/token patterns before atomic write; any hit fails closed.
- Hash each final immutable snapshot with SHA-256 before manifest append.
- Do not commit, upload, share, or extend retention for live snapshots without separate approval.
- Git may contain protocol/schema/synthetic examples and future separately authorized code/tests/aggregate reports only.

## 9. Offline replay and metrics

The replay process reads only schema-valid COMPLETE snapshots, verifies hashes and pinned provenance, reconstructs accepted candidate/enrichment inputs, and calls unchanged current composition with default `2 / 256`.

Report:

- `run_unique_output_names`;
- recipe count and zero-recipe share among COMPLETE observations;
- per-recipe unique exact names/counts;
- recipe-2 incremental NEW names;
- cross-recipe overlap and reuse ratio;
- rarity/mode and participating cohorts;
- universe goods and explored state counts;
- threshold counts/shares at `5/10/15/20/30/60`;
- exact R-7 `min/P25/P50/P75/P90/P95/max`;
- COMPLETE/PARTIAL/INVALID/MISSED counts and reason rates;
- balanced-protocol overall, each stratum, and UTC date/slot coverage.

PARTIAL and INVALID observations never enter primary quantiles or threshold shares. No result is labelled production-weighted without independently established production stratum weights.

## 10. Phase 15D eligibility gate

A numeric-policy review may start only if:

- 112 planned attempts are fully manifested;
- at least 96 are COMPLETE;
- each productive stratum has at least 10 COMPLETE;
- at least 12 distinct UTC dates have COMPLETE observations;
- missing/partial/invalid rates and reasons are reported overall/by stratum;
- immutable snapshot hashes and pinned provenance reproduce replay byte-for-byte;
- balanced overall and all stratum distributions are reported;
- default `5` and hard max `60` are evaluated within the declared observable frame;
- first-page/default-sort limitations remain explicit.

Otherwise return `INSUFFICIENT_REPRESENTATIVE_SNAPSHOT_EVIDENCE`.

Any proposed hard-max increase additionally requires a separate external-call safety-envelope review and explicit authorization. Satisfying this gate authorizes review only, not a policy or code change.

## 11. Interface gap

No invented-interface gap blocks a future collector limited to the current first-page/default-sort scanner frame.

`PHASE15C1_LIVE_COLLECTION_INTERFACE_GAP` blocks any broader full-market/order-book/pagination-complete claim. Phase 15C-2 must not cross that boundary until pagination, page size, market-depth completeness, official listing/currency semantics, rate limits, and lifecycle fields are separately confirmed and authorized.

## 12. Phase boundary

Phase 15C-1 freezes this protocol and synthetic example only. Phase 15C-2 collector/replay implementation and any live collection are **NOT STARTED / NOT AUTHORIZED**.
