# Phase 13N-3A — BUFF Identity Source Revalidation (Plan)

## Status

- Research/evidence-only phase. No code, no resolver implementation, no mapping file, no HTTP, no modifications to existing modules.
- Date: 2026-08-22.
- Branch: `feature/steamdt-cache-rate-limit`. HEAD: `481dafb`.
- Anchors: `D-IDENTITY-001`, `D-IDENTITY-002`, `D-IDENTITY-003`, `D-IDENTITY-004`, `D-IDENTITY-005`, `D-AUTH-001`, `D-BUFF-001`, `D-STEAMDT-001`, `D-STEAMAPIS-001`.

## Audit Goal

Determine whether new external evidence — specifically, public community-maintained catalogs mapping CS2 `market_hash_name ↔ BUF goods_id` — is robust enough to permit reopening the previously frozen identity-source decision.

This phase is research-only. It does **not** implement any concrete resolver, mapping file, loader, cache, or scanner wiring. Those would be Phase 13N-3B, gated on this phase's outcome.

## Question

> "Can a version-pinned, offline, provenance-preserving community catalog serve as a provisional `goods_id ↔ market_hash_name` identity source — without violating the frozen decisions `D-IDENTITY-001` through `D-IDENTITY-005`?"

## Audit Scope

### Repository evidence to re-examine (read-only)

1. **Frozen identity decisions** — `docs/ai-context/DECISION_LOG.md`. All five `D-IDENTITY-*` records.
2. **Current identity abstraction** — `app/services/buff_item_identity.py`. The `BuffItemIdentity` DTO and `BuffItemIdentityResolver` Protocol.
3. **Current BUF anonymous provider** — `app/services/buff_listing_provider.py`, `app/clients/buff_anonymous_listing_client.py`. Confirms `market_hash_name=None` and `caller-supplied goods_id`.
4. **Legacy `BuffGoodsInfo` skeleton** — `app/clients/buff_client.py`. Confirms the goods-info endpoint raises `NotImplementedError`.
5. **BUF API notes** — `docs/BUFF_API_NOTES.md`, `docs/BUFF_ANONYMOUS_READONLY_NOTES.md`, `docs/BUFF_LISTING_NOTES.md`.

### External sources to investigate (read-only)

1. **EricZhu-42/SteamTradingSite-ID-Mapper** — `buff/730.json`.
2. **ModestSerhat/cs2-marketplace-ids** — `cs2_marketplaceids.json`.
3. **TimofeyIvanenko/cs2-marketplace-mapping** — `cs2_full_mapping.json`.

### Investigation methodology

- Download raw JSON (no transformation, no edits).
- Compute file SHA-256 hashes for reproducibility.
- Capture repository, file path, commit SHA, license for each source.
- Identify provenance and dependency relationships between sources.
- Run deterministic Python analysis with no third-party dependencies.
- Report all metrics in standardized form.

## Decision Framework

After investigation, exactly one of three outcomes:

- **BLOCKED** — community catalogs do not meet the criteria. `D-IDENTITY-001..005` remain unchanged. Identity freeze continues.
- **PROVISIONAL_COMMUNITY_CATALOG_ACCEPTABLE** — community catalogs meet the criteria. A specific catalog is named; reproduction artifacts (commit SHA, file SHA-256) are recorded; `D-IDENTITY-006` is proposed.
- **MORE_EVIDENCE_REQUIRED** — evidence is partial; freeze continues; specific verification steps are listed.

## Criteria for "PROVISIONAL_COMMUNITY_CATALOG_ACCEPTABLE"

All ten criteria from the phase prompt must be satisfied for any candidate source:

1. High coverage.
2. Low or explicitly manageable conflict rate.
3. Deterministic exact mapping.
4. Reproducible source revision.
5. Identifiable provenance.
6. Acceptable/understood licensing.
7. Runtime can operate fully offline.
8. No fuzzy inference required.
9. Unresolved items can safely return `None`.
10. Downstream code does not need to trust it as official BUF data.

## Explicit Exclusions

The audit MUST NOT:

- Implement any concrete resolver.
- Create a mapping file in the project tree.
- Modify `BuffItemIdentity`, `BuffItemIdentityResolver`, `BuffListing`, `BuffListingCandidateAdapter`, `TradeUpInputCandidate`, `TradeUpInputEnrichment`, `TradeUpInputMetadataResolver`, or the parser.
- Add a new HTTP endpoint call.
- Add a new smoke harness.
- Add browser automation, cookie scraping, or anti-bot bypass.
- Modify Protected Core.
- Make speculative claims about endpoint semantics.
- Treat `TimofeyIvanenko/cs2-marketplace-mapping` as independent evidence (it derives from EricZhu + ModestSerhat + ByMykel).

## Research Artifacts

Temporary analysis scripts live outside `app/`, `tests/`, and `specs/`. The repository's existing convention is followed:

- `research/identity_revalidation/data/` — raw downloaded files (gitignored-friendly, never imported from `app/`).
- `research/identity_revalidation/scripts/analyze.py` — deterministic, stdlib-only analysis script.
- `research/identity_revalidation/analysis_report.txt` — generated spot-check table.

These research artifacts are NOT part of the production tree. They are reproducible from the captured commit SHAs and SHA-256 hashes recorded in `findings.md`.

## Deliverables

Four files only:

- `specs/2026-08-22-buff-community-identity-revalidation/plan.md` (this file)
- `specs/2026-08-22-buff-community-identity-revalidation/findings.md` (evidence)
- `specs/2026-08-22-buff-community-identity-revalidation/decision.md` (recommendation, `D-IDENTITY-006` proposal if justified)
- `specs/2026-08-22-buff-community-identity-revalidation/validation.md` (ring 1 spec integrity, ring 2 repository state)

Plus optional updates to AI context files only if the recommendation is "PROVISIONAL_COMMUNITY_CATALOG_ACCEPTABLE" or "BLOCKED" (per phase prompt section 22).

No other path may change in this phase.

## Verification

```bash
git diff --check
git diff --name-only
git status --short
```

Acceptance requires:

- `git diff --check` clean.
- `git status --short` shows only the new spec files plus the AI context updates (if any).
- No `app/`, `tests/`, `scripts/` modifications.
- Protected Core not touched.
- No commit unless separately requested.