# Phase 13N-1 — BUFF Identity Reality Verification (Decision)

## Architecture Outcome

**C — Freeze identity; continue synthetic-only.**

## Justification

1. The BUFF anonymous/read-only sell-order response carries **no `market_hash_name`, no `name`, no Steam identifiers (`classid` / `instanceid` / `appid`)** in the empirical probe (`docs/BUFF_ANONYMOUS_READONLY_NOTES.md`, 2026-08-20) and in every field the parser reads (`app/services/buff_listing_provider.py`). The parser never accesses any candidate identity field.
2. The parser **hardcodes** `BuffListing.market_hash_name = None` at `buff_listing_provider.py:212` for every parsed item. The identity bridge from the anonymous path is **structurally impossible** without parser modification, which is out of scope for a verification phase.
3. No `classid`, `instanceid`, or `appid` reference exists anywhere in the repository. Indirect conversion via Steam economy is impossible.
4. SteamDT `platformItemId` is opaque (per `D-STEAMDT-001`); SteamApis `source_offer_id` is a project-local SHA-256 explicitly NOT a BUF goods ID (per `D-STEAMAPIS-001`). Neither can serve as identity.
5. The only remaining candidate sources — the goods-info, buy-orders, and price-history endpoints — are documented as TODO in `docs/BUFF_API_NOTES.md`. They are **NOT ACTIONABLE** for production wiring until independently verified.
6. The four-source survey of `D-IDENTITY-003` (2026-08-22) already concluded the same outcome for the broader identity question. The present audit deepens the BUFF-anonymous-specific evidence and adds zero new positive evidence.
7. The canonical seam (`D-ENRICH-001`, `D-ADAPTER-004`) operates correctly with `market_hash_name=None` flowing through as a candidate and being rejected downstream as `MARKET_HASH_NAME_UNRESOLVED`. The seam continues to function; production wiring remains blocked on a future verified source.

## Why not A

A verified identity bridge would require either (a) an empirical BUFF response field that the present audit could not locate, or (b) a parser modification that exposes a hidden field — both out of scope for this verification phase. No evidence supports A.

## Why not B in this phase

Manual offline mapping (Source D) is **permissible** under `FR-4.1`–`FR-4.5` of `specs/2026-08-22-identity-bridge-architecture-review/requirements.md`, but it is a separate **implementation phase** (not a verification phase). It requires a documented verification procedure, a first attested entry, and a mapping loader module. The present phase is research-only and does not implement mapping infrastructure. Option B remains the most likely next **implementation** step (separate from this audit), but is not the conclusion of this audit.

## New Decision Record

**D-IDENTITY-004 — Phase 13N-1 BUFF anonymous response field inventory confirms no identity bridge.**

- **Date:** 2026-08-22 (Phase 13N-1)
- **Decision:** Repository-wide inventory of BUFF anonymous response fields, parser access patterns, fixtures, and live smoke probes confirms that the anonymous path cannot provide a verified `market_hash_name ↔ goods_id` bridge. `BuffListing.market_hash_name` stays `None` indefinitely; the abstract `BuffItemIdentityResolver` protocol stays the only public surface; `None` continues to be the only real answer.
- **Status:** Active.
- **Reason:**
  - The anonymous endpoint (`GET https://buff.163.com/api/market/goods/sell_order`) carries exactly six item-level fields verified by the Phase 13B empirical probe: `id`, `price`, `asset_info.paintwear`, `asset_info.assetid`, `asset_info.paintseed`. No other field was probed, claimed, or verified.
  - The parser (`app/services/buff_listing_provider.py`) accesses exactly those six item-level fields and hardcodes `market_hash_name=None` on every parsed item.
  - Zero references to `classid`, `instanceid`, or `appid` exist anywhere in `app/`, `tests/`, `scripts/`, or `docs/`. No Steam economy identifiers are exposed; no indirect conversion chain is possible.
  - SteamDT `platformItemId` is opaque (per `D-STEAMDT-001`); SteamApis `source_offer_id` is a project-local SHA-256 explicitly not authoritative (per `D-STEAMAPIS-001`).
  - The goods-info, buy-orders, and price-history endpoints are documented as TODO in `docs/BUFF_API_NOTES.md` and remain NOT ACTIONABLE.
- **Alternatives considered:** A (verified BUFF identity bridge) — no evidence. B (manual offline mapping) — permissible but a separate implementation phase, not the conclusion of this verification phase. D (impossible) — confirmed; decision must be C.
- **Outcome:** Decision is **C**. The forward `BuffItemIdentityResolver` protocol remains abstract; `None` is the only real answer; production wiring remains blocked.
- **Future revisit:** only when (a) an independently verified anonymous/read-only BUF goods-info endpoint is discovered with documented response semantics, OR (b) a manual offline mapping file satisfying `FR-4.1`–`FR-4.5` is committed. Either path requires its own implementation phase; neither is authorized by this verification.

## Frozen contracts (unchanged)

- `D-IDENTITY-001` — abstract bridge, no implementation. Remains active.
- `D-IDENTITY-002` — freeze identity source work; synthetic/offline only. Remains active.
- `D-IDENTITY-003` — Phase 13L-0 source survey. Remains active.
- `D-ADAPTER-003` — adapter does not resolve identity. Remains active.
- `D-AUTH-001` — anonymous client contract. Remains active; would require explicit authorization to relax for a second endpoint.
- `D-STEAMDT-001`, `D-STEAMAPIS-001` — SteamDT and SteamApis as identity source. Both rejected; remain active.

## What This Decision Does NOT Change

- `BuffItemIdentity` / `BuffItemIdentityResolver` shape, validation, or protocol.
- `BuffListing.market_hash_name = None` production behavior.
- `BuffListingCandidateAdapter` rejection vocabulary and adapter behavior.
- `TradeUpInputEnrichment` rejection vocabulary and seam contract.
- The frozen canonical path: `BuffListingProvider → BuffListingCandidateAdapter → TradeUpInputCandidate → TradeUpInputEnrichment → InputItem → tradeup_engine`.
- The synthetic scale validation (Phase 13J-1), the synthetic candidate adapter (Phase 13K-1), and all other offline seam tests.

## Out of Scope (frozen here)

- No concrete resolver implementation.
- No mapping file.
- No parser modification.
- No second BUF endpoint call.
- No `D-AUTH-001` relaxation.
- No live identity-source probe beyond the existing Phase 13B empirical check.
- No browser automation, cookie scraping, or anti-bot bypass.

## Remaining Blockers

- **Primary:** verified `market_hash_name ↔ BUFF goods_id` source. **Unchanged by this phase**; this audit deepens the negative evidence and adds `D-IDENTITY-004`.
- **Secondary:** intrinsic flag source on `BuffListing` (`D-MIGRATION-002`). Unchanged.
- **Tertiary:** no production scanner orchestration runtime (per `D-MIGRATION-002` and Phase 13M-0). Unchanged.

## Recommended Next Phase

**Phase 13N-2 — Manual Offline Identity Mapping (Source D)**, gated by the following prerequisites:

1. A documented verification procedure for human reviewers (proof-of-attestation workflow).
2. A first attested `(market_hash_name, goods_id)` entry committed under revision control.
3. A loader module (`app/services/identity_mapping_loader.py`) that reads the file offline and exposes a concrete `BuffItemIdentityResolver` backend.
4. Frozen contracts remain unchanged. The new module composes via `TradeUpInputEnrichment`; it does not bypass the seam.

This is a **separate implementation phase**, not a continuation of this verification phase. It does not require re-opening any of `D-IDENTITY-001/002/003/004`.

If the prerequisites for Phase 13N-2 cannot be met, the project remains in the synthetic-only state and the next **non-identity** phase (per Phase 13M-1, Phase 13O, Phase 13P, or Phase 13R from the prior audit) becomes the most actionable step.

## Direct Answers to Audit Questions

1. **Is the BUFF anonymous API truly unable to provide `market_hash_name`?**
   It is unable **from current evidence**. The probe never verified a wider field set. The parser deliberately ignores every potentially identity-bearing key. The wire-format fixture invents a placeholder `asset_info.market_hash_name` field that is **explicitly synthetic** (the strings say "Unverified Synthetic Name") and that the smoke harness rejects. No concrete evidence proves the live response carries the field; no concrete evidence proves it does not. The audit concludes "impossible from current evidence" because the parser is closed and no verified endpoint provides it.

2. **Is it worth continuing to investigate the BUF endpoint?**
   It is not **in this verification phase** — there is no candidate to investigate without inventing endpoints or relaxing `D-AUTH-001`. If a future, independently verified anonymous/read-only BUF goods-info endpoint is discovered, the investigation becomes a separate phase with explicit authorization.

3. **Should we proceed to Phase 13N manual mapping?**
   Phase 13N-1 (this phase) is research-only and concludes **C**. The next step is **Phase 13N-2 (implementation)** which is permissible under `FR-4.1`–`FR-4.5`. Whether to actually proceed to 13N-2 is a separate decision; it depends on the availability of a documented verification procedure and a first attested entry. This phase does not authorize 13N-2.

4. **What is the best next step right now?**
   - **Short term:** freeze identity (this decision).
   - **Conditional on prerequisites:** Phase 13N-2 (manual offline mapping), if the verification procedure and first entry can be established.
   - **Independent of identity:** Phase 13M-1 (`ScannerOrchestrator` skeleton), Phase 13O (`BuffListing` intrinsic flag exposure), or Phase 13R (roadmap + `ARCHITECTURE.md` refresh) — all from the prior state audit — remain actionable without identity.

## Critical Files

Add (this design phase, no implementation):

- `specs/2026-08-22-buff-identity-reality-verification/plan.md`
- `specs/2026-08-22-buff-identity-reality-verification/findings.md`
- `specs/2026-08-22-buff-identity-reality-verification/decision.md`

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