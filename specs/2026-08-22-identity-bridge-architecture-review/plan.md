# Phase 13L-0 — Identity Bridge Research and Architecture Review (Plan)

## Status

- Design-only research phase. No code, no resolver implementation, no mappings, no endpoint calls, no modifications to existing identity contracts.
- Date: 2026-08-22.
- Branch: `feature/steamdt-cache-rate-limit`.
- Anchors: `D-IDENTITY-001`, `D-IDENTITY-002`, `D-ENRICH-001`, `D-ADAPTER-003`, `D-ADAPTER-004`, Phase 13D-0 / 13D-1 / 13D-2 / 13F-0 / 13G-0 / 13K-1.

## Decisions Locked In This Review (from intake)

1. **Architecture decision:** **C — Freeze identity and continue synthetic-only**. No verified anonymous/read-only BUFF identity source exists. SteamDT IDs are opaque. SteamApis IDs are project-local SHA-256 of purchase links and explicitly are not BUFF goods IDs. The forward resolver contract stays abstract; `None` continues to be the only real answer.
2. **Decision-record layout:** one new entry — **D-IDENTITY-003** — that absorbs the 13L-0 source-by-source evaluation and supersedes any future inline speculation. The existing `D-IDENTITY-001` and `D-IDENTITY-002` remain in place.
3. **Next implementation phase:** **none**. The spec recommends no follow-on implementation phase. Identity remains the unblocking prerequisite for any live wiring; synthetic seam work continues to use the frozen identity contract (`market_hash_name=None` flows through and is rejected by `TradeUpInputEnrichment`).

## Research Scope

The review analyzes only repository evidence. It does not introduce new endpoints, do not invent fields, do not speculate, do not consult external documentation. Every claim below traces to a file path already in the repository.

## Research Findings

### F-1 — Existing identity contracts

The repository carries exactly one identity abstraction: `BuffItemIdentity` and `BuffItemIdentityResolver` (in `app/services/buff_item_identity.py`, introduced by Phase 13D-0). `BuffItemIdentity` is a frozen kw-only dataclass with two fields: `market_hash_name: str`, `goods_id: str`. The resolver is a single-method `Protocol` with one forward direction:

```
async def resolve(self, market_hash_name: str) -> BuffItemIdentity | None
```

`None` is the documented normal outcome. There is no concrete resolver, no mapping data, no offline table, no fixture, no parser, no loader, no cache, no configuration, no endpoint, no factory. The reverse direction (`resolve_by_goods_id`) is recorded in Phase 13F-0 as a missing contract but is not implemented.

`BuffListing` (in `app/services/buff_listing_provider.py`, hardened by Phase 13C / `2a8a1e8`) carries `market_hash_name: str | None` that is always set to `None` by the parser. `goods_id` is request context, not response-derived.

`TradeUpInputCandidate` (in `app/services/trade_up_input_candidate.py`, hardened by Phase 13I-2) carries `market_hash_name: str | None` as a candidate-owned field. The candidate boundary treats `None` as the documented unresolved shape and never attempts identity derivation.

### F-2 — SteamDT identifiers

SteamDT modules under `app/services/steamdt_*.py` carry platform records with one aggregate-level field: `platformItemId`. This field is explicitly opaque: `docs/BUFF_API_NOTES.md` records it as not authoritative for BUFF goods identity. The platform ID is per-aggregate, not per-listing, and cannot be traced to a single BUFF `goods_id` without additional context.

`D-STEAMDT-001` already records: "Never as an authoritative input listing source." The current SteamDT surface is aggregate-output valuation only. It is not an identity source.

### F-3 — SteamApis identifiers

`SteamApisListingObservation` (in `app/services/steamapis_listing.py`, line 94) carries `source_offer_id`, which is built by `make_steamapis_source_offer_id(marketplace, game, purchase_link)` (line 223). The construction is a SHA-256 hash of the literal `marketplace + game + purchase_link` triple — a project-local identifier, explicitly documented as not authoritative for BUFF goods IDs.

`D-STEAMAPIS-001` already records: "identity is a project SHA-256 of opaque purchase link, explicitly not a BUFF ID." The SteamApis surface is paused and unverified; no removal/Deleted event semantics are documented; the compatibility IDs are project-local.

### F-4 — BUFF native metadata

No BUFF endpoint, signature, request parameter, or response field is documented in `docs/BUFF_API_NOTES.md`. The empirical Phase 13B probe inspected only the first returned item of `GET /api/market/goods/sell_order` and recorded presence-only compatibility flags. No BUFF response path contains a verified `market_hash_name`. The anonymous provider hard-codes `market_hash_name=None` and never looks it up.

`docs/BUFF_API_NOTES.md` enumerates 9 categories of unconfirmed API details, each of which is still TODO. The goods info endpoint, the buy orders endpoint, the price history endpoint, the response field mapping, the rate limit, the authentication mechanism, and the lifecycle semantics all remain unconfirmed.

### F-5 — Manual offline mapping

The repository contains no manual mapping fixture. Phase 12 used synthetic pairs in `tests/`, never live data. The candidate adapter (`D-ADAPTER-003`) does not own identity derivation. A manually-curated mapping file is permissible only under the constraints listed below; this phase records the constraints but does not introduce such a file.

## Candidate Source Evaluation

### Source A — BUFF native metadata

- **Verdict: not usable.** No verified anonymous/read-only endpoint exists. The repository's empirical probe (`docs/BUFF_ANONYMOUS_READONLY_NOTES.md`) proves schema presence on a single page but does not establish identity semantics. Phase 13D-2 explicitly closed this investigation: "no validated anonymous/read-only goods/metadata endpoint was discovered." No endpoint was coded, no endpoint was requested, no `BuffGoodsInfo` implementation exists.
- **Why rejected:** endpoint path unknown, response field mapping unverified, lifecycle/freshness unconfirmed, no offline evidence of a `goods_id ↔ market_hash_name` payload.
- **Future revisit:** only after an independently verified anonymous/read-only endpoint is discovered and documented per the project rules. The TODO list in `docs/BUFF_API_NOTES.md` is the canonical tracker.

### Source B — SteamDT

- **Verdict: not usable.** `platformItemId` is opaque. There is no documented mapping from a SteamDT `platformItemId` to a BUFF `goods_id`. `D-STEAMDT-001` already prohibits using SteamDT as identity source.
- **Why rejected:** opaque IDs, no canonical relationship, per-aggregate not per-listing. Inferring identity from a SteamDT field would violate the project's anonymous-only stance.
- **Future revisit:** none. SteamDT remains aggregate-output valuation only.

### Source C — SteamApis

- **Verdict: not usable.** `source_offer_id` is a project-local SHA-256 hash of the purchase link, explicitly documented as not a BUFF goods ID. `D-STEAMAPIS-001` already records this.
- **Why rejected:** the IDs are not authoritative, the live smoke was gated off and never executed, no removal/Deleted event semantics are documented, and the WebSocket subscription requires an API key (forbidden by the anonymous-only stance).
- **Future revisit:** only after a live smoke verifies payload compatibility and a separately verified BUFF identity source exists.

### Source D — Manual offline mapping

- **Verdict: permissible only under strict constraints; not implemented in this phase.** A manually-curated mapping file is the only identity source that can be verified by humans and revision-controlled without contacting any external system. It is acceptable only when all of the following hold:
  1. The file is offline-only; it is loaded at startup or test time and never queries BUFF / SteamDT / SteamApis / Steam.
  2. The file is revision-controlled (Git) and immutable within a release.
  3. The file is treated as documentation, not as live data: it must never be used to drive automatic purchasing, automatic login, automatic bidding, or any production write.
  4. The file is consumed only by an offline identity source that the candidate adapter can consult when present; the adapter stays synthetic otherwise.
  5. The file format is documented (CSV / JSON / similar) and versioned; each entry records `market_hash_name`, `goods_id`, source URL or commit of the verification, and an attestation that the pair was verified by a human reviewer.
- **Why deferred:** no verified mapping file exists today. Introducing one is a separate phase (out of scope here) and requires a documented verification procedure that the project has not yet established.
- **Future revisit:** when a verified offline mapping procedure is approved and a first attested entry is committed.

## Architecture Decision

The architecture decision for Phase13L-0 is **C — Freeze identity and continue synthetic-only**.

### Justification

1. No verified anonymous/read-only BUFF identity source exists (Source A).
2. No verified SteamDT identity relationship exists (Source B).
3. No verified SteamApis identity relationship exists (Source C).
4. No manual offline mapping file exists today (Source D); introducing one is out of scope for 13L-0.
5. The canonical seam (`D-ENRICH-001`, `D-ADAPTER-004`) is built to operate with `market_hash_name=None` flowing through as a candidate and being rejected downstream as `MARKET_HASH_NAME_UNRESOLVED`. The frozen seam continues to work without identity resolution.
6. Synthetic scale validation (Phase 13J-1) and the synthetic candidate adapter (Phase 13K-1) operate entirely without identity resolution; they cover the full path except the final live wiring.

### Frozen decisions (cross-references)

- `D-IDENTITY-001` — abstract bridge with no implementation; remains active.
- `D-IDENTITY-002` — identity work frozen; synthetic/offline only; remains active.
- `D-ADAPTER-003` — adapter does not resolve identity; remains active.
- `D-ENRICH-001` — canonical candidate → InputItem seam; remains active.

### New decision

- **D-IDENTITY-003 — Phase 13L-0 source survey confirms no verified identity bridge.** Records that as of 2026-08-22 the four candidate sources (BUFF native, SteamDT, SteamApis, manual offline mapping) are all non-actionable for production wiring; the architecture continues with `market_hash_name=None` flowing through the candidate boundary and being rejected by `TradeUpInputEnrichment`. The forward `BuffItemIdentityResolver` protocol remains abstract; `None` is the only real answer.

## Out of Scope (frozen here)

- No resolver backend.
- No mapping file.
- No modification to `BuffItemIdentity` / `BuffItemIdentityResolver`.
- No modification to `BuffListing` / `TradeUpInputCandidate`.
- No BUF endpoint guesses.
- No browser automation.
- No anti-bot bypass.
- No purchase logic.
- No SteamDT identity inference.
- No SteamApis identity assumption.
- No production wiring of any identity source.

## Remaining Blockers

- **Primary:** verified `market_hash_name ↔ BUFF goods_id` source. Not resolved in 13L-0.
- **Secondary:** intrinsic flag source on `BuffListing` (per `D-MIGRATION-002`). Not resolved.
- **Tertiary:** no production scanner orchestration. Not resolved.

## Recommended Next Phase

**None.** The spec recommends no follow-on implementation phase. Synthetic seam work continues as it has. Identity remains the unblocking prerequisite for any future production wiring; addressing it requires either a verified offline mapping file (Source D) under strict constraints, or an independently verified BUF native source (Source A). Both are out of scope for the immediate project horizon.

## Critical Files

Add (this design phase, no implementation):

- `specs/2026-08-22-identity-bridge-architecture-review/plan.md`
- `specs/2026-08-22-identity-bridge-architecture-review/requirements.md`
- `specs/2026-08-22-identity-bridge-architecture-review/validation.md`

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
- No `app/`, `tests/`, or Protected Core path modified.
- No commit unless separately requested.