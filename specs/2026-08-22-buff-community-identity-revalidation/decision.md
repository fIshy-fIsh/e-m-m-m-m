# Phase 13N-3A — BUFF Identity Source Revalidation (Decision)

## Recommendation

**PROVISIONAL_COMMUNITY_CATALOG_ACCEPTABLE — with a single named source.**

The version-pinned, offline, attribution-preserving snapshot of **EricZhu-42/SteamTradingSite-ID-Mapper `buff/730.json`** at commit `093adde1f9f3b0a5fd14957cd52fb988154251c3` may be used as a **provisional** identity source.

This is **provisional**, not official BUF data. It does not replace a future verified first-party source. It is **bounded, version-pinned, offline, and fail-closed**.

## Why This Recommendation

The investigation evaluated three community catalogs against ten criteria. The summary:

- **EricZhu-42** (CC-BY-4.0, 99.96% coverage, 0 collisions, fully reproducible): meets all 10 criteria.
- **ModestSerhat** (LICENSE_UNCLEAR, 98.16% coverage, 0 collisions): meets 9 of 10 criteria (license unclear). Useful as consistency-checker, not primary.
- **TimofeyIvanenko** (MIT, 97.25% coverage, **derived**): meets coverage but fails the independence test for "independent verification". Not useful as primary.

The only meaningful **independent** cross-source agreement is EricZhu vs ModestSerhat: **34,272 of 34,273 overlapping keys agree exactly (99.997%)**. This is strong independent verification.

The single disagreement (`Souvenir Charm | Austin 2025 Highlight | Wont go quietly`: EricZhu=1134690, ModestSerhat=1118388) is plausibly a freshness race on a very recent item. Future re-pinning will resolve or surface it.

## New Decision Record

**D-IDENTITY-006 — Community offline catalog is acceptable as a provisional V1 identity source.**

- **Date:** 2026-08-22 (Phase 13N-3A)
- **Decision:** A version-pinned, offline, attribution-preserving snapshot of **EricZhu-42/SteamTradingSite-ID-Mapper `buff/730.json`** at commit `093adde1f9f3b0a5fd14957cd52fb988154251c3` may be used as a provisional identity source. This does **not** make the mapping official BUF data. A future verified first-party BUF source (e.g. an independently-verified goods-info endpoint) may supersede or audit community-derived mappings.
- **Status:** Active.
- **Previous decisions remain historically correct.** `D-IDENTITY-001` through `D-IDENTITY-005` are not modified. They remain accurate descriptions of the evidence available at their respective dates.
- **What this changes:**
  - The abstract `BuffItemIdentityResolver` Protocol is no longer the only public surface for identity.
  - A concrete `BuffItemIdentityResolver` implementation may now be built.
  - The forward direction `resolve(market_hash_name) -> identity` continues to be the only `Protocol` direction; reverse lookup must be implemented as an inverted index on goods_id, not as a Protocol change.
  - The downstream `TradeUpInputEnrichment` seam continues to operate as designed.
- **What this does NOT change:**
  - `BuffListing.market_hash_name=None` production behavior (until the resolver becomes operational in production wiring).
  - `BuffListingCandidateAdapter` rejection vocabulary and adapter behavior.
  - `TradeUpInputEnrichment` rejection vocabulary and seam contract.
  - Frozen canonical path.
  - Any Protected Core module.
- **Operating model:**
  - The catalog is committed to the project tree as a static data file, with a documented provenance header (commit SHA, file SHA-256, source URL, license).
  - Runtime performs zero network I/O.
  - Mapping lookups are exact-string equality on `market_hash_name` (no fuzzy inference, no normalization).
  - Missing entries (including the 15 sticker-slab `-1` sentinels in EricZhu) yield `None`, fail closed.
  - The CC-BY-4.0 attribution requirement is preserved in the data file's provenance header.
- **Reason:**
  - High coverage (99.96% valid records).
  - Zero in-source collisions.
  - 99.997% independent agreement with ModestSerhat on overlapping keys.
  - CC-BY-4.0 license is clear and permissive (attribution only).
  - Commit SHA + file SHA-256 enable exact reproduction.
  - Runtime can operate fully offline via version-controlled snapshot.
  - Downstream code does not need to treat the data as official BUF data.
  - Future first-party verification can supersede or audit.
- **Alternatives considered:**
  - **A (BLOCKED):** all five prior `D-IDENTITY-*` decisions remain accurate as historical records, but the present-day evidence supports reopening. Pure "stay blocked" would ignore new evidence.
  - **B (PROVISIONAL):** chosen. Specific catalog named.
  - **C (MORE_EVIDENCE_REQUIRED):** not needed. The independent verification pair (EricZhu vs ModestSerhat) is already decisive.
- **Why not use ModestSerhat as primary:** license is unclear (no LICENSE file). Cannot rely on for production use.
- **Why not use TimofeyIvanenko:** derived from EricZhu + ModestSerhat + ByMykel; not independent evidence; no incremental value.
- **Why Policy B (community source + consistency checker) over Policy A (single source):** EricZhu is the primary; ModestSerhat can serve as a future consistency-checker if and only if its license is clarified.
- **Future revisit:**
  - When a verified first-party BUF goods-info endpoint becomes available (see `D-IDENTITY-005`), it may supersede or audit community mappings.
  - When ModestSerhat's license is clarified, it may become a consistency-checker.
  - When EricZhu-42 (or its successor) adds new items, the project should re-pin a new snapshot.
  - **Do NOT auto-refresh at runtime** — refresh is a manual, version-controlled operation.

## Frozen contracts (unchanged)

All previously frozen decisions remain active and unchanged:

- `D-IDENTITY-001` — abstract bridge, no implementation.
- `D-IDENTITY-002` — freeze identity source work; synthetic/offline only.
- `D-IDENTITY-003` — Phase 13L-0 four-source survey.
- `D-IDENTITY-004` — Phase 13N-1 BUF anonymous response field inventory.
- `D-IDENTITY-005` — Phase 13N-2 goods-info endpoint survey.
- `D-ADAPTER-003` — adapter does not resolve identity (forward direction stays abstract).
- `D-AUTH-001` — anonymous client contract.
- `D-BUFF-001`, `D-BUFF-002`, `D-BUFF-003` — anonymous research path.
- `D-STEAMDT-001`, `D-STEAMAPIS-001` — SteamDT and SteamApis as identity source.

## What This Decision Does NOT Change

- `BuffItemIdentity` / `BuffItemIdentityResolver` shape, validation, or Protocol direction.
- `BuffListing.market_hash_name = None` production behavior (until the resolver becomes operational).
- `BuffGoodsInfo` dataclass shape (it remains a placeholder).
- `BuffListingCandidateAdapter` rejection vocabulary and adapter behavior.
- `TradeUpInputEnrichment` rejection vocabulary and seam contract.
- The frozen canonical path.
- Protected Core.
- The synthetic scale validation (Phase 13J-1) and synthetic candidate adapter (Phase 13K-1).

## Recommended Next Phase

**Phase 13N-3B — Offline snapshot builder + identity index + tests.**

This is a separate **implementation** phase, gated on the present decision. It will:

1. Commit a pinned snapshot of EricZhu-42/SteamTradingSite-ID-Mapper `buff/730.json` at commit `093adde1f9f3b0a5fd14957cd52fb988154251c3` to the project tree as a static data file (e.g. `data/identity/buff_market_hash_to_goods_id_v1.json`).
2. Add a provenance header documenting: source URL, commit SHA, file SHA-256, license (CC-BY-4.0 + attribution string).
3. Build a small in-memory loader (`app/services/buff_community_identity_resolver.py` or similar) that reads the snapshot and exposes:
   - Forward: `market_hash_name → BuffItemIdentity | None` (the existing Protocol direction).
   - Reverse (in-memory inverted index): `goods_id → BuffItemIdentity | None` (used by the production path).
4. Tests:
   - Deterministic exact-string lookup on a snapshot of known mappings.
   - Sentinel-handling tests (the 15 sticker-slab `-1` entries).
   - `None` semantics for missing entries.
   - Reverse-index lookup correctness.
   - Reproducibility test (file SHA-256 matches recorded hash).
7. No scanner wiring, no candidate adapter change, no enrichment change. The resolver becomes available but is not wired in.
8. Phase 13N-3B does **not** modify any frozen decision or Protected Core.

After 13N-3B, the natural follow-on is **13N-3C** which would wire the resolver into `BuffListingCandidateAdapter` (still respecting `D-MIGRATION-002` for intrinsic flags), subject to the same gating.

## Direct Answers to the Audit Questions

### Q1. Is the previously frozen identity blocker now reopenable?

Yes, narrowly. The new evidence (EricZhu-42 catalog) meets all 10 criteria from the phase prompt. The recommendation is provisional, version-pinned, attribution-preserving, and fail-closed.

### Q2. Is the recommendation a full reversal of `D-IDENTITY-001`..005?

No. Those decisions remain historically accurate. They continue to describe what was true at their respective dates. The new evidence does not invalidate them; it supplements them.

### Q3. Is runtime network I/O introduced?

No. The catalog is committed as a static data file. Runtime performs zero network I/O. Refresh is a manual, version-controlled operation.

### Q4. Does downstream code trust the catalog as official BUF data?

No. The catalog is **provisional**. Downstream code does not need to treat it as authoritative. A future verified first-party source can supersede it.

### Q5. Is fuzzy inference involved?

No. All lookups are exact-string equality on `market_hash_name` and exact-integer equality on `goods_id`. No normalization, no case folding, no wear-name parsing.

### Q6. Can unresolved items return `None`?

Yes. Missing entries (including the 15 sticker-slab `-1` sentinels) yield `None`. The downstream `TradeUpInputEnrichment` surfaces `None as `MARKET_HASH_NAME_UNRESOLVED`.

### Q7. What about coverage gaps?

The 15 sticker-slab entries in EricZhu legitimately lack BUF IDs (community flagged them with `-1`). These continue to be unresolved. Other gaps (e.g. a brand-new item) would also surface as `None` until the snapshot is re-pinned.

## Critical Files

Add (this research phase):

- `specs/2026-08-22-buff-community-identity-revalidation/plan.md`
- `specs/2026-08-22-buff-community-identity-revalidation/findings.md`
- `specs/2026-08-22-buff-community-identity-revalidation/decision.md`
- `specs/2026-08-22-buff-community-identity-revalidation/validation.md`

Plus research artifacts (not part of the production tree):

- `research/identity_revalidation/data/eric_zhu_730.json`
- `research/identity_revalidation/data/modest_serhat.json`
- `research/identity_revalidation/data/timofey_ivanenko.json`
- `research/identity_revalidation/scripts/analyze.py`
- `research/identity_revalidation/analysis_report.txt`

Plus AI context updates per section 22:

- `docs/ai-context/PROJECT_CONTEXT.md`
- `docs/ai-context/ARCHITECTURE_STATE.md`
- `docs/ai-context/DECISION_LOG.md` (add `D-IDENTITY-006`)
- `docs/ai-context/DEVELOPMENT_HANDOFF.md`

No other path may change in this phase.

## Verification

```bash
git diff --check
git diff --name-only
git status --short
```

Acceptance requires:

- `git diff --check` clean.
- `git status --short` shows only the spec files, research artifacts, and AI context updates.
- No `app/`, `tests/`, `scripts/` modifications.
- Protected Core not touched.
- No commit unless separately requested.