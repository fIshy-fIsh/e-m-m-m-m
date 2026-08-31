# Phase 15C-1 — Representative Listing Snapshot Calibration Design Freeze — Plan

## Status

- **Design/specification only.** Phase 15C-1 authorizes no collector, replay implementation, test change, live request, scheduler, dataset, budget change, PR, or merge.
- **Date:** 2026-08-30.
- **Branch:** `feature/representative-snapshot-calibration`.
- **Baseline:** canonical main `7a73cc026f93bbed9d9c089c96e6565a6c43c68d` / tree `bae6f6db88b52ec08db279cab60a2498bab08a36`; CI run `33350081125` SUCCESS.
- **Frozen choices:** balanced eight-stratum rotation; immutable normalized JSON per observation plus append-only JSONL manifest; 112 planned attempts over 14 UTC days with the validity gates in `requirements.md`.

## Numbered task groups

### 1. Freeze baseline, safety, and policy authority

1. Record the verified canonical main, merge tree, PR #6 merge, and successful main CI.
2. Preserve Phase 15B: default `5` unchanged; hard max `60` unchanged; designed Phase 15A replays are not production probabilities.
3. Freeze documents/specs/research-protocol/synthetic-example scope only.
4. Preserve the protected untracked JSONs and local-only baseline tag.
5. Prohibit all live calls, `.env` inspection, scheduler/background work, production/test/script changes, and invented BUFF behavior.

Deliverable: status/authority blocks in the design trilogy and protocol.

### 2. Freeze the observable population and balanced sampling frame

1. Define one observation as one timestamped full capture attempt for one exact current auto-universe plan before valuation.
2. Rebuild the ten-goods universe for every observation using current `COHORT_DEPTH`, three target cohorts, and Souvenir inclusion.
3. Freeze the eight productive rarity/mode strata and deterministic balanced rotation.
4. Declare the aggregate balanced-protocol, not production-weighted.
5. Bound the observable population to page 1/default sort from the current confirmed anonymous compatibility path.
6. Record unavailable goods, empty pages, and failures without substitution or silent dropping.
7. Mark complete-market/order-book or pagination-complete claims as an interface gap.

Deliverable: sampling-frame contract in `requirements.md` and `SNAPSHOT_PROTOCOL.md`.

### 3. Freeze the multi-time collection candidate plan

1. Freeze 14 consecutive UTC days, eight three-hour nominal slots daily, and 112 planned observations.
2. Rotate strata by `(slot + day) mod 8` so no stratum stays tied to a UTC time of day.
3. Freeze deterministic `[-10,+10]` minute jitter and store its derivation in the campaign manifest.
4. Freeze collector-derived UTC start/completion timestamps because provider timestamps are unavailable.
5. Record missed slots rather than retrying or replacing them.
6. Freeze ten sequential requests per observation, minimum two seconds between starts, no automatic retry, and a campaign ceiling of 1,120 requests.
7. State explicitly that implementation/scheduling remains Phase 15C-2 work and is not authorized here.

Deliverable: time-sampling section and campaign manifest requirements.

### 4. Freeze existing interface use and field provenance

1. Map the current universe builder, anonymous payload client, listing provider, identity binding, intrinsic binding, candidate adapter, metadata resolver/enrichment, scanner composition, and Phase 15A measurement API.
2. Classify every snapshot field as direct compatibility fact, exact derived fact, collector/protocol-derived fact, or unavailable.
3. Preserve the project's caveats for item `id`, CNY naming, missing provider timestamp, pagination, and market completeness.
4. Freeze `LiveScannerOrchestrator` as architecture reference only; Phase 15C-2 must compose a research collector that stops before valuation.
5. Freeze conditional `PHASE15C1_LIVE_COLLECTION_INTERFACE_GAP` for any broader market/order-book population.

Deliverable: interface/field provenance matrix.

### 5. Freeze normalized snapshot and manifest schemas

1. Freeze schema version `1` and exact protocol ID.
2. Freeze deterministic IDs and timestamps, campaign/stratum/provenance, universe/page/listing records, summary counts, and observation status.
3. Store exact decimal price/paintwear as strings.
4. Retain compatibility listing/asset references only because current replay/candidate boundaries require them; label listing-ID semantics as compatibility, not official.
5. Freeze closed acquisition/binding/enrichment/candidate status fields and stable reasons.
6. Require strict unknown-key, duplicate-key, type, cross-record, count, and hash validation.
7. Create `snapshot_schema_v1.example.json` with synthetic/example values only.
8. Freeze one immutable snapshot file plus one append-only manifest line per attempted slot.

Deliverable: schema sections and synthetic example.

### 6. Freeze provenance layers and collection/replay separation

1. Source facts are parsed atomically; raw bytes are not retained.
2. Identity binding remains exact pinned mapping with fail-closed conflicts.
3. Intrinsic classification remains catalog-derived exact-prefix logic.
4. Metadata remains pinned exact-name enrichment.
5. The normalized snapshot is atomically written, hashed, and never mutated.
6. Offline replay reads only normalized snapshots and cannot call/import external clients.
7. Replay uses unchanged current composition and default `RecipeEnumerationConfig()` (`2 / 256`).
8. Measurement reuses Phase 15A exact-name semantics and R-7 method.
9. Collector never constructs valuation or SteamDT dependencies.

Deliverable: seven-layer provenance/replay contract.

### 7. Freeze missingness and observation validity

1. Freeze stable protocol-level reasons plus safe existing detail codes.
2. Record every planned page and every scheduled slot.
3. Define valid empty pages separately from fetch/parse failures.
4. Define `COMPLETE` as a ten-page fully acquired and exact planned-identity/intrinsic/metadata/candidate-consistent replayable observation; valid empty pages are allowed, and fewer than ten accepted listings truthfully yield `recipe_count=0` / `run_unique_output_names=0` rather than exclusion.
5. Define `PARTIAL` as valid universe plus one or more fetch/parse page failures; exclude from primary distributions.
6. Define `INVALID_FOR_CALIBRATION` for universe, binding/catalog drift, schema, provenance, hash, duplicate/conflict, or snapshot-level failures.
7. Preserve all invalid/partial/missed outcomes in manifest and reports.
8. Prohibit repair, imputation, replacement, or silent extension to obtain a preferred result.

Deliverable: closed missingness/status semantics.

### 8. Freeze retention, redaction, and dataset location

1. Commit only protocol/schema/examples/future code/tests/aggregate reports after separate authorization.
2. Keep actual live snapshots outside the repository in an explicitly supplied local/artifact root.
3. Freeze deterministic directory/file naming, atomic writes, SHA-256 manifest references, and append-only supersession.
4. Prohibit raw provider payload retention by default.
5. Prohibit secrets, headers, URLs/query strings, cookies, tokens, auth, seller/account/personal data, and raw exception text.
6. Require pre-write key/value secret scanning and fail closed.
7. Require separate approval for dataset upload, sharing, Git commit, or retention-policy changes.

Deliverable: retention/redaction policy.

### 9. Freeze calibration output and Phase 15D gate

1. Preserve `run_unique_output_names` as primary metric.
2. Preserve per-recipe counts/sets, recipe-2 incremental NEW, overlap/reuse, strata/cohorts, goods count, and state count.
3. Preserve thresholds `5/10/15/20/30/60` and exact R-7 seven-point summary.
4. Report balanced overall and each productive stratum separately.
5. Report COMPLETE/PARTIAL/INVALID/MISSED and reason rates.
6. Require 96 COMPLETE, 10 per stratum, 12 UTC dates, full 112-attempt manifest, reproducible hashes, and time/stratum distributions.
7. Freeze `INSUFFICIENT_REPRESENTATIVE_SNAPSHOT_EVIDENCE` if any gate fails.
8. Require separate external-call safety review for any hard-max increase.
9. State that satisfying the data gate permits review only; it does not implement a numeric policy.

Deliverable: Phase 15D eligibility gate.

### 10. Validate and checkpoint Phase 15C-1

1. Inspect all five required design artifacts for internal agreement.
2. Parse the example JSON and verify it has only synthetic values.
3. Scan artifacts for credential/token/cookie/auth/header material; allow only explicit prohibitions/field-source discussion, not secret-shaped values.
4. Run `git diff --check`.
5. Require the allowed-file scope and empty `app/tests/scripts/.github/pyproject/.env.example` diff from baseline.
6. Verify no live data, payload, credentials, or generated datasets exist.
7. Verify protected JSON status and local tag.
8. Commit exactly `freeze representative snapshot calibration protocol`.
9. Push normally to `origin/feature/representative-snapshot-calibration`.
10. Do not open a PR and do not merge.

Deliverable: one pushed design checkpoint ready for Phase 15C-2 review.
