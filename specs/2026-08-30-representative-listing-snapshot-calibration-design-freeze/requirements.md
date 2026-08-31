# Phase 15C-1 — Representative Listing Snapshot Calibration Design Freeze — Requirements

## Status and authority

- **Date:** 2026-08-30.
- **Branch:** `feature/representative-snapshot-calibration`.
- **Canonical baseline:** `7a73cc026f93bbed9d9c089c96e6565a6c43c68d`; tree `bae6f6db88b52ec08db279cab60a2498bab08a36`; PR #6 merged; main push CI run `33350081125` / job `quality` SUCCESS.
- **Phase type:** design/specification checkpoint only.
- **Implementation status:** Phase 15C-2 collection/replay implementation is **NOT STARTED / NOT AUTHORIZED**.
- **Controlling policy:** production default remains `5` under `NO_PRODUCTION_DEFAULT_CHANGE_PENDING_REPRESENTATIVE_SNAPSHOT`; hard maximum remains `60` under `HARD_MAX_60_REVIEW_DEFERRED`.
- **Scope:** documents, specifications, protocol, and a synthetic example only. No application/test/script/workflow/dependency/config edit; no live dataset; no network request; no scheduler.

This design follows `specs/mission.md`, `specs/tech-stack.md`, the Phase 15A evidence, Phase 15B `POLICY_DECISION.md`, the current code boundaries, and the confirmed-vs-TODO distinctions in `docs/BUFF_API_NOTES.md` and `docs/BUFF_LISTING_NOTES.md`.

## Goal

Freeze a reproducible, read-only, privacy-minimal protocol that can later measure the current scanner's production-like NEW-LIVE exact-name demand without turning designed structural coverage into unsupported production-frequency claims.

The future collector and replay remain separate:

```text
current catalog-only universe plan
  -> bounded anonymous first-page listing acquisition
  -> exact identity binding
  -> canonical-name intrinsic classification
  -> pinned metadata enrichment
  -> immutable minimal normalized snapshot
  -> offline-only replay through unchanged composition/solver
  -> calibration metrics
```

The collector MUST NOT call SteamDT or valuation. The replay MUST NOT call BUFF, SteamDT, Redis, or any network interface.

## 1. Frozen population and sampling frame

### 1.1 Observation unit

One observation is one timestamped, full read-only capture attempt for the exact current auto-universe planning result for **one productive input rarity/StatTrak stratum**, before valuation.

Every observation rebuilds the universe from the campaign-pinned identity and metadata snapshots by calling the current `build_universe_goods_ids` contract with:

- `cap=10`;
- `allocation_strategy=COHORT_DEPTH`;
- `target_cohort_count=3`;
- `souvenir_inclusion=INCLUDE`;
- the observation's frozen input rarity;
- the observation's frozen normal/StatTrak mode.

The expected result is exactly ten ordered goods IDs. The snapshot records the order, selected cohort, catalog facts, and provenance. A plan that fails or returns fewer than ten goods IDs is recorded and classified `INVALID_FOR_CALIBRATION`; it is never silently replaced with a different rarity, mode, allocation strategy, or allowlist.

### 1.2 Frozen productive strata

The campaign uses a deterministic balanced rotation over the eight productive Phase 15A strata:

1. Consumer Grade / normal;
2. Industrial Grade / normal;
3. Mil-Spec Grade / normal;
4. Mil-Spec Grade / StatTrak;
5. Restricted / normal;
6. Restricted / StatTrak;
7. Classified / normal;
8. Classified / StatTrak.

Consumer Grade / StatTrak and Industrial Grade / StatTrak remain explicit unsupported strata under the current pinned catalog; they are not converted into zero-demand observations.

The balanced campaign is a protocol-defined equal allocation, not evidence of the real production mix. Overall results are reported as **balanced-protocol results**. A production-weighted aggregate MUST NOT be claimed unless a future, separately reviewed source establishes production stratum-selection weights. Every major stratum is also reported separately.

### 1.3 Observable population boundary

The live observable population is narrowly defined as:

> listings returned by the current confirmed anonymous compatibility path for page 1 with `sort_by=default`, for each of the ten goods IDs in the rebuilt current scanner universe, at the observation time.

This is a sample of the workload observable by the current scanner path. It is **not** the full BUFF market, complete order book, all pages, or an official BUFF API population.

No pagination, page size, alternative sorting, listing-status inference, seller count, market depth, or historical completeness is assumed. Expanding the target population beyond the current first-page/default-sort boundary is a live-collection interface gap until separately confirmed.

### 1.4 Unavailable goods and listings

- Every planned goods ID has a page-attempt record, even when fetch or parse fails.
- A successfully parsed empty page is recorded as `EMPTY_PAGE`; it is a real observed zero-listing page and does not make the observation partial.
- Fetch/transport/non-2xx failure is `LISTING_FETCH_FAILED` and makes the observation `PARTIAL`.
- Atomic parser failure is recorded at page level with its stable provider reason and optional item index; no valid prefix is retained. It makes the observation `PARTIAL`.
- Identity, intrinsic, metadata, and candidate rejection outcomes are recorded per page/record and are replayed with the same exclusion semantics as the current scanner. They are not silently dropped from the audit record.

## 2. Frozen time-sampling protocol

### 2.1 Proposed campaign

Phase 15C-2, if separately authorized, should implement a bounded candidate campaign:

- **duration:** 14 consecutive UTC days;
- **nominal cadence:** one observation every 3 hours, eight observations per UTC day;
- **planned observations:** 112;
- **planned distribution:** exactly 14 attempts per productive stratum;
- **minimum valid observations:** 96 `COMPLETE` observations;
- **minimum per-stratum valid observations:** 10;
- **minimum temporal coverage:** valid observations on at least 12 distinct UTC calendar dates.

These are proposed protocol requirements, not already collected evidence and not an authorization to collect.

### 2.2 Stratum rotation

To avoid assigning one stratum permanently to one time of day:

```text
stratum_index = (slot_within_utc_day + utc_day_index) mod 8
```

The campaign manifest freezes the ordered eight-stratum list and campaign start date. Over eight days each stratum rotates through every nominal UTC time slot; the remaining six days continue the same deterministic rotation.

### 2.3 Nominal times and deterministic jitter

- Nominal slots occur every three hours at minute 17 UTC: `00:17`, `03:17`, `06:17`, `09:17`, `12:17`, `15:17`, `18:17`, and `21:17`.
- Each slot receives a deterministic bounded jitter in `[-10, +10]` minutes: encode the exact UTF-8 string `<campaign_id>|<nominal_slot_utc>`, compute SHA-256, read the first eight digest bytes as an unsigned big-endian integer, then set `jitter_minutes = value mod 21 - 10`. The campaign ID, nominal UTC string, formula version, and result are stored in the campaign manifest; operators cannot choose favorable times after seeing market state.
- One collection attempt is made for the assigned slot. There is no polling loop and no automatic retry.
- A slot not started within 30 minutes after its jittered target is recorded as `MISSED_OBSERVATION` in the append-only manifest. It is not rescheduled or replaced.

### 2.4 Timestamp source

BUFF's current confirmed path exposes no provider observation timestamp. Therefore:

- `observed_at_utc` is collector-derived from the host UTC wall clock immediately before the first page request;
- `capture_completed_at_utc` is collector-derived immediately after the last page outcome;
- `nominal_slot_utc` and `scheduled_for_utc` are protocol-derived;
- timestamps are RFC 3339 UTC strings with `Z`;
- the manifest records the timestamp source as `collector_host_utc_clock`, never as BUFF-supplied time.

### 2.5 Request-volume safety

A future collection attempt is bounded to ten first-page GET requests, one per planned goods ID, strictly sequentially. Phase 15C-2 MUST add conservative collector-owned pacing (minimum two seconds between request starts), issue no automatic retries, and stop/classify failures rather than poll. The planned campaign ceiling is 1,120 requests over 14 days. This is project safety pacing, not a claim about an official BUFF rate limit.

## 3. Frozen interface and field provenance matrix

### 3.1 Existing interfaces confirmed usable for the narrow frame

| Layer | Existing interface | Confirmed use |
|---|---|---|
| Universe | `build_universe_goods_ids(identity_resolver, metadata_resolver, spec)` | Pure deterministic 10-goods cohort-depth plan and diagnostics |
| Anonymous request | `BuffAnonymousListingHttpClient.fetch_sell_order_payload(goods_id)` | One anonymous read-only HTTPS GET to the existing page-1/default-sort compatibility path |
| Listing normalization | `BuffListingProvider.get_listings(goods_id)` | Atomic parsed ordered first page; raw bytes not retained |
| Identity | `BuffCommunityIdentityResolver.resolve_goods_id(goods_id)` via `bind_identity_to_provider` | Exact pinned `goods_id -> market_hash_name`; no fuzzy/inferred fallback |
| Intrinsics | `CanonicalNameIntrinsicFlagResolver.resolve(name)` via `bind_intrinsic_flags_to_provider` | Catalog-derived exact-prefix StatTrak/Souvenir classification; not BUFF-supplied facts |
| Candidate boundary | `convert_buff_listing_to_candidate` | Existing accepted/rejected normalized candidate semantics |
| Metadata | `PinnedSkinMetadataResolver.resolve(name)` and `InMemoryTradeUpInputEnricher` | Pinned collection, rarity, and float-range enrichment |
| Offline composition | `enumerate_scanner_recipe_selections` | Unchanged bounded recipe composition at `2 / 256` |
| Output measurement | Phase 15A exact-name measurement functions | `run_unique_output_names`, per-recipe names, overlap, incremental NEW, R-7 |

`LiveScannerOrchestrator.run_once` is an architecture reference, not the collector API: it does not expose the required immutable pre-valuation snapshot. Phase 15C-2 should compose the narrower existing layers in a research-only one-shot collector and stop before valuation.

### 3.2 Required listing fact classification

| Snapshot fact | Classification | Exact source/caveat |
|---|---|---|
| `goods_id` | Request context / universe-derived | Current universe plan and caller-supplied request context; not inferred from response |
| `listing_reference` | Direct compatibility field | `BuffListing.listing_id`, parsed from item `id`; official canonical listing-ID semantics remain TODO, so schema names it a compatibility reference |
| `asset_reference` | Direct compatibility field | `BuffListing.asset_id`, parsed from `asset_info.assetid`; retained because current candidate reconstruction requires it |
| `price_cny` | Direct normalized compatibility field | `BuffListing.price_cny`, parsed from item `price`; official currency/fee semantics remain unconfirmed and are not broadened |
| `paintwear` | Direct normalized compatibility field | `BuffListing.paintwear`, parsed from `asset_info.paintwear`, finite and bounded `[0,1]` |
| `paintseed` | Direct optional compatibility field | `BuffListing.paintseed`, parsed from optional/null `asset_info.paintseed`; may be null |
| `source` | Provider-owned normalized constant | Exact `buff` in current provider contract |
| `market_hash_name` | Derived after exact identity binding | Pinned community identity snapshot; anonymous listing response does not establish this value |
| `stattrak` / `souvenir` | Derived intrinsic classification | Exact canonical-name prefix resolver; catalog-derived, not BUFF-supplied |
| `rarity` / `collection_name` | Derived metadata | Pinned metadata resolver exact-name lookup |
| `universe_rank` / `cohort` | Derived universe planning facts | Current builder result and diagnostics |
| `observed_at_utc` | Collector-derived | Host UTC clock; provider timestamp unavailable/unresolved |
| acquisition/normalization statuses | Collector-derived | Closed protocol vocabulary mapped from existing typed outcomes |

### 3.3 Unavailable/unresolved facts

The protocol does not claim or store:

- provider-supplied listing observation timestamp;
- official canonical listing-ID semantics;
- official price currency/fee guarantee beyond the current project compatibility contract;
- quantity, full order depth, seller count, pagination completeness, listing freshness/removal state, trade-lock state, or hidden/delisted semantics;
- provider-supplied StatTrak/Souvenir, rarity, collection, or market hash name;
- any authentication, signature, cookie, account, or seller fields.

### 3.4 Live collection interface gap decision

**For the frozen current-scanner first-page/default-sort sampling frame:** no interface gap requires invented endpoint behavior. The existing interfaces above are sufficient for a research-only collector design.

**For any claim about the full BUFF market/order book or pagination-complete population:** `PHASE15C1_LIVE_COLLECTION_INTERFACE_GAP` applies. Pagination/page size, complete market depth, official listing-ID/currency semantics, rate-limit behavior, and listing freshness/removal remain unconfirmed. Phase 15C-2 MUST NOT expand into that population without separately confirmed evidence and authorization.

## 4. Frozen normalized snapshot schema

The schema is version `1`. One immutable JSON file represents one attempted observation that reached universe-plan materialization. Manifest-only records represent planning failures or missed slots.

Top-level fields:

- `schema_version` — exact integer `1`;
- `protocol_id` — exact `representative-listing-snapshot-v1`;
- `campaign_id` — non-secret campaign identifier;
- `snapshot_id` — deterministic ID: `snap-v1-` plus the first 24 lowercase hex characters of SHA-256 over exact UTF-8 `<campaign_id>|<nominal_slot_utc>|<input_rarity>|<stattrak_mode>`;
- `nominal_slot_utc` — protocol slot;
- `scheduled_for_utc` — jittered slot;
- `observed_at_utc` — collector start timestamp;
- `capture_completed_at_utc` — collector completion timestamp;
- `timestamp_source` — exact `collector_host_utc_clock`;
- `observation_status` — `COMPLETE`, `PARTIAL`, or `INVALID_FOR_CALIBRATION`;
- `stratum` — input rarity, mode, and Souvenir inclusion;
- `provenance` — collector commit, identity/metadata snapshot paths and SHA-256 hashes, universe/composition configuration;
- `universe` — target/actual goods count, ordered planned goods records, allocation diagnostics;
- `acquisition_summary` — requested/succeeded/empty/failed page counts, listing counts, rejection/missingness counts, stable reasons;
- `pages` — exactly one ordered page record per planned goods ID.

Each universe/page record includes `goods_id`, `universe_rank`, cohort collection/rarity/mode, page acquisition status, listing count, and stable page failure reason or null.

Each normalized listing record includes:

- `listing_reference` and `listing_reference_kind=anonymous_item_id_compatibility`;
- `asset_reference`;
- `goods_id`;
- nullable `market_hash_name` after identity binding;
- decimal strings `price_cny` and `paintwear`;
- nullable integer `paintseed`;
- nullable booleans `stattrak` and `souvenir`;
- nullable `rarity` and `collection_name`;
- `source=buff`;
- `identity_status`, `intrinsic_status`, `metadata_status`, `candidate_status`, and `replay_status`;
- stable nullable `rejection_reason` (existing adapter/enrichment detail code for replay exclusion) plus protocol-level summary reasons.

Decimal values are strings to preserve exact source-normalized precision. Unknown keys, duplicate keys, invalid status combinations, duplicate snapshot IDs, duplicate page goods IDs, or mismatched listing/page goods IDs fail closed.

## 5. Frozen provenance and replay separation

1. **Source listing facts:** `BuffListingProvider` parses one complete page atomically into `BuffListing`; raw bytes exist only in memory and are not persisted.
2. **Exact identity binding:** the pinned identity resolver attaches an exact name or leaves `None`; mismatches fail closed.
3. **Intrinsic flags:** canonical-name classification attaches exact booleans; unresolved identity leaves both null; no `None -> False` coercion.
4. **Metadata enrichment:** pinned exact-name metadata resolves collection/rarity/float bounds; misses retain stable rejection state.
5. **Immutable normalized snapshot:** only the schema-v1 minimal records are atomically written and hashed.
6. **Offline replay:** a separate process reads only normalized files, reconstructs current candidate/enrichment inputs, and calls unchanged `enumerate_scanner_recipe_selections` with `RecipeEnumerationConfig()` (`2 / 256`). It cannot import or call BUFF/SteamDT/Redis clients.
7. **Measurement output:** Phase 15A exact-name measurement logic produces comparable metrics and a report tied to snapshot hashes.

Collector and replay outputs are never combined in one partially successful file. No valuation service or SteamDT provider is constructed during collection or replay.

## 6. Frozen missingness and failure semantics

### 6.1 Stable reason vocabulary

At minimum the future schema/manifest must support:

- `MISSED_OBSERVATION`;
- `UNIVERSE_PLANNING_FAILED`;
- `UNIVERSE_NOT_EXACTLY_TEN`;
- `LISTING_FETCH_FAILED`;
- `LISTING_RESPONSE_INVALID`;
- `EMPTY_LISTING_PAGE` (observed status, not failure);
- `LISTING_REFERENCE_INVALID`;
- `LISTING_PRICE_INVALID`;
- `PAINTWEAR_INVALID_OR_MISSING`;
- `ASSET_REFERENCE_INVALID`;
- `IDENTITY_UNRESOLVED`;
- `IDENTITY_CONFLICT`;
- `INTRINSIC_UNRESOLVED`;
- `INTRINSIC_CONFLICT`;
- `METADATA_NOT_FOUND`;
- `LISTING_REJECTED` with an existing adapter/enrichment detail code;
- `SNAPSHOT_PARTIAL`;
- `SNAPSHOT_ACQUISITION_FAILED`;
- `SNAPSHOT_SCHEMA_INVALID`;
- `PROVENANCE_MISMATCH`.

Raw exception text and rejected values are never stored. Existing closed typed reasons may be stored as a separate safe `detail_code`; unknown exception text is reduced to a stable stage-level reason.

### 6.2 Observation validity classes

**COMPLETE**

- universe plan succeeds with exactly ten ordered goods IDs;
- all ten page requests return and atomically parse, including valid empty pages;
- every returned listing resolves through the same pinned identity/intrinsic/metadata contracts used to build the universe and reaches an accepted replay input;
- provenance, schema, timestamps, hashes, and counts are internally consistent.

A COMPLETE observation may contain empty pages. Identity unresolved/conflict, intrinsic unresolved/conflict, metadata miss, or candidate rejection is impossible under an unchanged exact planned universe and therefore is not treated as ordinary row missingness. A COMPLETE observation may still contain fewer than ten accepted listings; offline composition then truthfully returns zero recipes and the observation contributes `recipe_count=0` and `run_unique_output_names=0` rather than being dropped.

**PARTIAL**

- universe is valid, but one or more page fetches or atomic page parses fail, or a binding stage aborts a page;
- every planned page still has an outcome record;
- successful normalized pages may be retained for audit;
- the observation is excluded from primary production-frequency calibration and threshold/quantile calculations.

**INVALID_FOR_CALIBRATION**

- universe planning fails or does not yield exactly ten goods IDs;
- any returned listing cannot be rebound to its planned exact identity, canonical intrinsic facts, pinned metadata, or accepted candidate contract (catalog/provenance drift);
- schema/provenance/hash/timestamp validation fails;
- campaign configuration or pinned catalog hashes drift;
- duplicate/conflicting IDs or impossible status/count invariants are detected;
- a snapshot-level acquisition failure prevents truthful reconstruction.

INVALID observations remain in the manifest with stable reasons and are never repaired, replaced, or silently dropped.

Only COMPLETE observations enter policy-facing cardinality distributions. COMPLETE, PARTIAL, INVALID, and MISSED counts/rates are all reported.

## 7. Frozen retention, redaction, and artifact policy

### 7.1 Committed artifacts

Git may contain only:

- this protocol and design trilogy;
- schema/manifest definitions;
- small synthetic examples;
- future collector/replay code and focused tests after separate authorization;
- aggregate reports that contain no live listing identities unless separately reviewed.

### 7.2 Live dataset storage

Actual representative snapshots are **not committed to Git by default**. Phase 15C-2 must require an explicit local/artifact root outside the repository. Campaign layout:

```text
<artifact-root>/valuation_budget_calibration/<campaign_id>/
  campaign.v1.json
  manifest.v1.jsonl
  snapshots/
    snap-v1-<nominal-UTC>-<stratum-slug>-<snapshot-id>.json
```

Each snapshot is written atomically, made immutable by convention, SHA-256 hashed, then referenced by one append-only canonical JSON line in `manifest.v1.jsonl`. Missed/planning-failed attempts have manifest entries with `snapshot_path=null` and no fabricated snapshot file. Existing files and manifest lines are never rewritten; corrections append a superseding record without deleting history.

### 7.3 Raw payload and secret policy

- Raw provider payload retention is prohibited by default.
- No headers, URLs, query strings, cookies, tokens, authorization values, API keys, seller/account data, personal data, or complete exception messages are stored.
- Before finalizing each file, the future collector must scan keys and string values for credential/header/cookie/token patterns and fail closed on a match.
- Console output and manifest errors use stable reason codes only.
- Dataset sharing, Git commit, upload, or retention beyond the local campaign requires separate approval.

## 8. Frozen calibration metrics

For COMPLETE observations, future replay reports:

- `run_unique_output_names` as the primary metric;
- recipe count and share of COMPLETE observations producing zero recipes;
- per-recipe unique output-name counts and exact-name sets in audit output;
- recipe-2 incremental NEW names;
- cross-recipe overlap and reuse ratio;
- input rarity and normal/StatTrak stratum;
- participating collections/cohorts;
- universe goods count and composition states explored;
- threshold count/share at `5 / 10 / 15 / 20 / 30 / 60`;
- R-7 `min / P25 / P50 / P75 / P90 / P95 / max` using exact rational arithmetic;
- COMPLETE/PARTIAL/INVALID/MISSED counts and rates;
- row/page missingness and rejection rates by stable reason.

Reports show:

1. balanced-protocol overall distribution;
2. each productive rarity/mode stratum separately;
3. time coverage by UTC date and nominal slot;
4. current default-5 admission outcome;
5. current hard-max-60 structural/admission outcome.

No production-frequency claim may include PARTIAL or INVALID observations. No balanced-protocol aggregate may be described as production-weighted unless future evidence establishes the weights.

## 9. Frozen Phase 15D policy gate

Phase 15D may review a numeric recommendation only when all gates hold:

- at least 96 COMPLETE observations;
- at least 10 COMPLETE observations in each of the eight productive strata;
- COMPLETE observations on at least 12 distinct UTC dates across the 14-day window;
- planned 112 attempts and all missed/partial/invalid outcomes are manifested;
- missingness and partial/invalid rates are reported overall, by stratum, and by stable reason;
- replay is byte-reproducible from immutable snapshot hashes and pinned code/catalog provenance;
- balanced overall and major-stratum distributions are reported with R-7 and all six reference thresholds;
- current default `5` and hard max `60` are evaluated without treating Phase 15A designed shares as production probabilities;
- limitations of first-page/default-sort observability are carried into the decision;
- any proposed hard-max increase receives a separate external-call safety-envelope review and explicit implementation authorization.

If any gate fails, the outcome is `INSUFFICIENT_REPRESENTATIVE_SNAPSHOT_EVIDENCE`; collection may not be silently extended or reweighted to obtain a preferred result.

No numeric cap change is authorized in Phase 15C-1, Phase 15C-2, or by satisfying the collection gate alone.

## 10. Non-goals and prohibited behavior

- No live collection in Phase 15C-1.
- No SteamDT, Redis, valuation, cache refresh/writeback, scheduler, daemon, or background collection.
- No production/test/script/workflow/dependency/config change.
- No auto-buy, auto-trade, login, cookie collection, CAPTCHA/risk-control bypass, browser purchasing, proxy rotation, or anti-detection behavior.
- No invented endpoint, signature, parameter, response field, timestamp, identity, listing status, pagination, rate limit, or authentication behavior.
- No raw live dataset in Git.
- No production default/hard-max/CLI/atomic-admission change.

## Acceptance criteria

Phase 15C-1 is complete only when:

- the required design trilogy, protocol, and synthetic example exist;
- the sampling frame, time plan, schema, provenance layers, missingness, retention, metrics, and Phase 15D gate are internally consistent;
- every snapshot fact is classified as direct, derived, or unavailable;
- the first-page/default-sort population limitation and conditional interface gap are explicit;
- `git diff --check` passes;
- changed files are design/spec/research protocol/example/current-state docs only;
- `git diff --name-only 7a73cc026f93bbed9d9c089c96e6565a6c43c68d...HEAD -- app tests scripts .github pyproject.toml .env.example` is empty;
- no live request, pytest, app launch, or `.env` inspection occurs;
- the protected JSONs and local-only tag remain untouched;
- exactly one checkpoint is pushed to `feature/representative-snapshot-calibration` with no PR or merge.
