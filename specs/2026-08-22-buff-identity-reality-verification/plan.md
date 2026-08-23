# Phase 13N-1 — BUFF Identity Reality Verification (Plan)

## Status

- Research/design-only audit. No code, no resolver implementation, no mapping file, no HTTP, no modifications to existing modules.
- Date: 2026-08-22.
- Branch: `feature/steamdt-cache-rate-limit`. HEAD: `481dafb`.
- Anchors: `D-IDENTITY-001`, `D-IDENTITY-002`, `D-IDENTITY-003`, `D-ADAPTER-003`, `D-AUTH-001`, Phase 13B / 13C / 13D-0 / 13F-0 / 13G-0 / 13L-0.

## Audit Goal

Definitively answer the question:

> "Can the BUFF anonymous/read-only data source — alone, or in combination with anything already committed to the repository — provide a reliable `market_hash_name ↔ BUFF goods_id` identity bridge?"

This is a single, narrow, repository-evidence-driven question. It does NOT propose an implementation. It does NOT authorize a new endpoint call. It does NOT propose any production wiring.

## Decision Framework

After the audit, exactly one of three architecture outcomes applies:

- **A — Proceed with verified identity bridge.** A BUFF response field (or a project-internal conversion chain) has been verified to provide `market_hash_name` reliably.
- **B — Proceed with manual offline identity mapping.** A different phase may build a Source D mapping file under `FR-4.1`–`FR-4.5` of `specs/2026-08-22-identity-bridge-architecture-review/requirements.md`. This phase does not implement it.
- **C — Freeze identity; continue synthetic-only.** No verified source exists. Production wiring remains blocked on a future verified source.

If the answer is **D from the source classification** (impossible from current evidence), decision must be **C**.

## Audit Scope

### Repository evidence to examine (read-only)

1. **Anonymous BUFF client** — `app/clients/buff_anonymous_listing_client.py`. Endpoint URL, request parameters, response handling.
2. **BUFF response parser** — `app/services/buff_listing_provider.py`. Every field accessed; every field silently dropped; the `market_hash_name=None` construction.
3. **Project-owned BuffListing DTO** — `app/services/buff_listing.py`, `app/services/buff_listing_provider.py`. Field origins (response vs caller context vs hardcoded).
4. **Identity abstraction** — `app/services/buff_item_identity.py`. Public exports, protocol signature.
5. **All BUFF-related fixtures** under `tests/fixtures/buff/` and `tests/fixtures/pipeline/`. Field inventory.
6. **All BUFF test files** under `tests/test_buff_*` and `tests/test_live_buff_*`. Fields asserted.
7. **All BUFF scripts** under `scripts/`. Live smoke harnesses.
8. **Documentation** — `docs/BUFF_API_NOTES.md`, `docs/BUFF_ANONYMOUS_READONLY_NOTES.md`, `docs/BUFF_LISTING_NOTES.md`, `docs/SPEC.md`. Endpoint records; TODO inventory; verified vs unverified claims.
9. **Decision records** — `docs/ai-context/DECISION_LOG.md` (`D-IDENTITY-001/002/003`, `D-BUFF-001/002/003`, `D-AUTH-001`).

### Cross-checks to perform

- Grep `market_hash_name`, `classid`, `instanceid`, `appid`, `name`, `item_name`, `hash_name`, `description`, `goods_name`, `localized_name` across `app/`, `tests/`, `scripts/`, `docs/`.
- Confirm whether the parser genuinely never reads any candidate identity field, or whether the parser has a hidden field path.
- Confirm whether any test fixture carries a real `market_hash_name ↔ goods_id` join (vs redundant co-occurrence of one pair).
- Confirm whether any live smoke documented a field NOT in the six enumerated by `D-BUFF-002`.

## Identity Possibility Classification (per source)

| Class | Meaning | Required action |
|---|---|---|
| **A. Direct identity** | BUFF response contains `market_hash_name` (or canonical Steam market name) reliably, with verified semantics, lifecycle, and freshness. | Proceed with verified identity bridge (decision A). |
| **B. Indirect identity** | BUFF response contains Steam identifiers (`classid`, `instanceid`, `appid`, `asset_id`, etc.) that can be cross-referenced against an independent verified source to derive `market_hash_name`. | Trace the conversion chain; each step requires its own evidence. |
| **C. Possible but unverified** | A field appears in a project-owned fixture or in unverified empirical observation but no live verification, no lifecycle proof, no documented endpoint semantics. | Mark `NOT ACTIONABLE`. Do not enter production wiring. |
| **D. Impossible from current evidence** | No candidate field exists; parser drops every potentially identity-bearing key; no cross-reference is possible from the anonymous path. | Decision must be C (freeze). |

## Explicit Exclusions

The audit MUST NOT:

- Implement any concrete resolver.
- Implement any mapping file.
- Modify `BuffItemIdentity`, `BuffItemIdentityResolver`, `BuffListing`, `BuffListingCandidateAdapter`, `TradeUpInputCandidate`, `TradeUpInputEnrichment`, or the parser.
- Add a new HTTP endpoint call.
- Add a new smoke harness.
- Add browser automation, cookie scraping, or anti-bot bypass.
- Modify Protected Core (`tradeup_engine`, `recipe_solver`, `ev_service`, `risk_filter`, `valuation_service`, `live_recipe_valuation`, `market_scan_service`, `metadata_provider`, `metadata_client`).
- Reach a "verdict" by speculation about undocumented endpoints.

## Deliverables

Three files only:

- `specs/2026-08-22-buff-identity-reality-verification/plan.md` (this file)
- `specs/2026-08-22-buff-identity-reality-verification/findings.md` (evidence table, field analysis, classification)
- `specs/2026-08-22-buff-identity-reality-verification/decision.md` (architecture outcome, `D-IDENTITY-004`)

No other path may change in this phase.

## Verification

```bash
git diff --check
git diff --name-only
git status --short
```

Acceptance requires:

- `git diff --check` clean.
- `git status --short` shows only the three new spec files.
- No `app/`, `tests/`, `scripts/`, `docs/` paths modified.
- No commit unless separately requested.