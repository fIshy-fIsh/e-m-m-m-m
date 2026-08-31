# Phase 15C-1 — Representative Listing Snapshot Calibration Design Freeze — Validation

## Validation strategy

Phase 15C-1 validates design completeness and consistency against current code and confirmed documentation. It does not validate a collector, dataset, schedule, replay implementation, or production policy because none is authorized or created.

Do not run pytest, the application, the live scanner, BUFF/SteamDT/Redis integration, or inspect `.env`.

## Gate 1 — Repository baseline and lifecycle

Require:

```text
origin/main = 7a73cc026f93bbed9d9c089c96e6565a6c43c68d
tree        = bae6f6db88b52ec08db279cab60a2498bab08a36
PR #6       = MERGED at canonical main
main CI     = run 33350081125 / quality / completed success
branch      = feature/representative-snapshot-calibration
base        = canonical main
```

Also verify:

- old `feature/valuation-budget-calibration` tip `c1fd51af2bbc904828f17bdb1667806388c0b904` is an ancestor of main;
- old local branch was deleted by `git branch -d`, not `-D`;
- old remote branch was normally deleted;
- the only unrelated working-tree entries are the two protected untracked JSONs;
- `v1-dry-run-baseline` remains local-only at `32ab47c5b66a0f331457e69f1515e5e9bb2a37e1`.

## Gate 2 — Required artifact integrity

The design checkpoint must contain:

```text
specs/2026-08-30-representative-listing-snapshot-calibration-design-freeze/requirements.md
specs/2026-08-30-representative-listing-snapshot-calibration-design-freeze/plan.md
specs/2026-08-30-representative-listing-snapshot-calibration-design-freeze/validation.md
research/valuation_budget_calibration/SNAPSHOT_PROTOCOL.md
research/valuation_budget_calibration/snapshot_schema_v1.example.json
```

All five must agree on:

- design-only status;
- balanced eight-stratum frame;
- exact current 10-goods cohort-depth universe rebuild per observation;
- first-page/default-sort observable boundary;
- 14 UTC days, 112 attempts, 96 COMPLETE, 10 per stratum, 12 UTC dates;
- one immutable JSON per observation plus append-only JSONL manifest;
- no raw payload retention and no live dataset in Git by default;
- collector/replay/valuation separation;
- `COMPLETE`, `PARTIAL`, `INVALID_FOR_CALIBRATION` semantics;
- Phase 15A metrics and R-7 comparability under the unchanged default `2 / 256` enumeration;
- unchanged default `5`, hard max `60`, CLI, and atomic NEW-LIVE behavior;
- Phase 15C-2 NOT STARTED / NOT AUTHORIZED.

## Gate 3 — Sampling-frame coherence

Confirm:

1. One observation is one full attempt for one rebuilt stratum-specific universe before valuation.
2. The target universe is exactly ten ordered goods IDs under current `COHORT_DEPTH`, target three, Souvenir include.
3. The eight productive strata are listed exactly and rotated deterministically.
4. Each stratum has 14 planned attempts across the campaign.
5. `(slot + day) mod 8` rotates each stratum through UTC times.
6. Nominal slots are every three hours at minute 17 UTC with deterministic bounded jitter.
7. Missed slots are manifested and never replaced.
8. Balanced results are never called production-weighted without future weight evidence.
9. The population is current path first-page/default-sort only; no full-market claim.

Any inconsistency fails the design freeze.

## Gate 4 — Interface and field-source audit

Confirm every required field is classified and no external mapping is invented:

- direct/current compatibility: listing reference, asset reference, price, paintwear, optional paintseed, source;
- request/universe context: goods ID, universe rank, cohort;
- exact identity-derived: market hash name;
- canonical-name-derived: StatTrak/Souvenir;
- pinned-metadata-derived: rarity/collection;
- collector-derived: timestamps and status/reason;
- unavailable: BUFF timestamp, full order depth/pagination completeness, quantity, seller count, listing lifecycle, official listing-ID/currency semantics.

Confirm that the current interfaces are named exactly and the design does not claim `LiveScannerOrchestrator` already emits snapshots.

Confirm conditional gap:

```text
current first-page/default-sort scanner frame: no invented-interface gap
full BUFF market/order-book/pagination-complete frame:
  PHASE15C1_LIVE_COLLECTION_INTERFACE_GAP
```

## Gate 5 — Schema/example validation

Parse the example with a duplicate-key-detecting JSON loader and require:

- schema version exact integer `1`;
- protocol ID exact `representative-listing-snapshot-v1`;
- synthetic campaign/snapshot/listing/goods/asset values visibly prefixed `synthetic-` or documentation-domain values;
- RFC 3339 UTC timestamps in a historical synthetic date;
- ten ordered synthetic goods/page records;
- at least one successful accepted synthetic listing and at least one valid empty page;
- decimal price/paintwear represented as strings;
- no URL, endpoint, header value, cookie, token, authorization, API key, credential, personal, account, or seller data;
- no live BUFF identifiers or captured payload fragments;
- count summaries match array contents and statuses.

The example is explanatory, not a live dataset and not evidence of any external field beyond the frozen source matrix.

## Gate 6 — Missingness and validity coherence

Confirm:

- every nominal slot gets a manifest outcome;
- every planned goods ID gets a page outcome when a snapshot file exists;
- empty parsed page is valid and compatible with COMPLETE;
- fetch/parse page failure makes PARTIAL;
- binding failure or planned identity/intrinsic/metadata/candidate drift makes INVALID;
- universe/schema/provenance/hash/duplicate/conflict failure makes INVALID;
- PARTIAL/INVALID/MISSED never enter primary thresholds/quantiles;
- every returned row in COMPLETE is accepted and replayable under the same pinned planning catalogs;
- a COMPLETE observation with fewer than ten accepted listings remains in the production-frequency denominator and replays to zero recipes / `run_unique_output_names=0`;
- all status/reason counts are reported;
- no failure is dropped, imputed, retried, repaired, or replaced.

## Gate 7 — Retention/redaction audit

Confirm:

- actual datasets default outside the repository;
- committed files contain only design/schema/example/current-state docs;
- raw response bytes are never retained by default;
- paths and filenames are deterministic;
- snapshot write is atomic and manifest append-only;
- SHA-256 binds each immutable snapshot;
- secret scanning occurs before write;
- no cookies/auth/tokens/headers/URLs/query strings/seller/account/personal data/raw exception text are persisted;
- upload/share/Git commit/retention changes require separate approval.

Run a targeted case-insensitive scan. Matches such as `cookie`, `token`, or `authorization` are allowed only in prohibitions/source-classification prose; any secret-shaped assignment/value fails.

## Gate 8 — Calibration and policy gate coherence

Confirm future COMPLETE-only replay retains:

- `run_unique_output_names` primary metric;
- per-recipe unique exact names/counts;
- recipe-2 incremental NEW;
- overlap/reuse;
- rarity/mode and collections/cohorts;
- goods/state counts;
- thresholds `5/10/15/20/30/60`;
- exact R-7 seven-point summary;
- balanced overall plus eight strata;
- missingness and validity rates.

Confirm Phase 15D review remains blocked unless all count/time/stratum/reproducibility/reporting gates hold. Any hard-max increase separately requires external-call safety review and explicit implementation authorization. No gate satisfaction itself changes a numeric value.

## Gate 9 — Frozen code scope

Run:

```text
git diff --check
git diff --name-only 7a73cc026f93bbed9d9c089c96e6565a6c43c68d...HEAD -- app tests scripts .github pyproject.toml .env.example
```

The second command must produce no output.

Before commit, use the equivalent working-tree and staged comparisons. Allowed changed files are only:

- the five required design/protocol/example artifacts;
- `CLAUDE.md`;
- `specs/roadmap.md`;
- `docs/ai-context/DECISION_LOG.md`;
- `docs/ai-context/DEVELOPMENT_HANDOFF.md`;
- `docs/ai-context/PROJECT_CONTEXT.md`.

Any other file fails scope validation.

## Gate 10 — No live activity / checkpoint lifecycle

Verify from the task transcript and repository state:

- no BUFF, SteamDT, Redis, Discord, or other external request occurred;
- no application/CLI/live smoke/pytest was run;
- no `.env` was inspected;
- no scheduler/background collector was created;
- no live snapshot/dataset was created;
- no credentials or secrets were read or stored;
- protected JSONs remain untouched/untracked;
- local tag remains exact;
- exactly one commit has subject `freeze representative snapshot calibration protocol`;
- branch is pushed normally to `origin/feature/representative-snapshot-calibration` at ahead/behind `0/0`;
- no PR is opened and no merge is performed;
- Phase 15C-2 remains NOT STARTED / NOT AUTHORIZED.
