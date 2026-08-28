# Phase 13N-2 — BUFF Native Goods Identity Source Investigation (Decision)

## Architecture Outcome

**C — No verified source; continue identity freeze.**

## Justification

1. The BUFF native goods-info endpoint is the only remaining candidate identity source not surveyed in `D-IDENTITY-003` or `D-IDENTITY-004`.
2. From current repository evidence, that endpoint is **possible but unverified** (Class C): no endpoint path documented as verified, no response schema documented as verified, no live smoke harness exists, no probe has ever been executed, the `BuffGoodsInfo` shape is unimplemented placeholder, and `BuffHttpClient.get_goods_info()` raises `NotImplementedError(UNCONFIRMED_MAPPING_ERROR)`.
3. No `classid` / `instanceid` / `appid` reference exists anywhere in the repository. Even if the goods-info endpoint exists and returns a market name, no Steam-economy identifier is exposed anywhere in the project that could cross-reference an independent verified source — therefore an **indirect** identity chain (Class B) is also impossible from current evidence.
4. Authorizing a live probe of the goods-info endpoint would require (a) explicit relaxation of `D-AUTH-001` (anonymous client contract) to permit a second endpoint, (b) explicit relaxation of `D-BUFF-001` to permit a new live smoke, and (c) explicit verification of the response field map. None of these has been granted in this audit.
5. The four prior identity decisions (`D-IDENTITY-001`, `D-IDENTITY-002`, `D-IDENTITY-003`, `D-IDENTITY-004`) collectively rule out every other candidate source. The goods-info endpoint is the only remaining candidate, and it is also unverified.
6. The forward `BuffItemIdentityResolver` protocol stays abstract; `market_hash_name=None` continues to be the only real answer; production wiring remains blocked.

## Why not A

A would require an independently verified BUFF goods-info endpoint with documented response semantics, lifecycle/freshness/case/StatTrak/Souvenir handling, and anonymous accessibility. No such evidence exists in the repository. Authorizing one would require a separate live-probe phase with explicit user approval — out of scope for this research-only audit.

## Why not B

B would require an indirect conversion chain: `goods_id → Steam identifier → market_hash_name`. The repository contains zero references to `classid`, `instanceid`, or `appid`. Even if a goods-info endpoint exposed one of these, no independent verified source of `Steam identifier → market_hash_name` exists to chain against. Class B is impossible from current evidence.

## New Decision Record

**D-IDENTITY-005 — Phase 13N-2 goods-info endpoint survey confirms no native BUF identity source.**

- **Date:** 2026-08-22 (Phase 13N-2)
- **Decision:** Repository-wide search of BUFF endpoint inventory, legacy `BuffGoodsInfo` shape, response-field documentation, and live smoke harnesses confirms that the only remaining candidate — the BUF native goods-info endpoint — is unverified. The forward `BuffItemIdentityResolver` protocol stays abstract; `market_hash_name=None` continues to be the only real answer; production wiring remains blocked.
- **Status:** Active.
- **Reason:**
  - No BUF endpoint URL other than `GET /api/market/goods/sell_order` is documented as verified.
  - The goods-info endpoint is listed as TODO `#5` in `docs/BUFF_API_NOTES.md:62-64`. Checkboxes are unchecked.
  - The legacy `BuffGoodsInfo` dataclass is a shape-only placeholder; `BuffHttpClient.get_goods_info()` raises `NotImplementedError(UNCONFIRMED_MAPPING_ERROR)`.
  - No live smoke harness for the goods-info endpoint exists.
  - No `classid`/`instanceid`/`appid` reference exists anywhere in the repository — no indirect conversion chain is possible.
  - No fixture, test, or smoke output pairs a specific `goods_id` (e.g. `1115941`) with a verified response.
  - Authorizing a live probe requires explicit relaxation of `D-AUTH-001` and `D-BUFF-001`, neither of which has been granted.
- **Alternatives considered:**
  - A (verified BUF native identity source found): no evidence supports A.
  - B (partially verified, needs separate implementation phase): partially verified would require (i) anonymous probe authorized, (ii) response schema documented, (iii) lifecycle semantics confirmed. None of these has been done. Therefore B is not yet reachable.
  - C (no verified source, continue identity freeze): the only outcome supported by current evidence.
- **Outcome:** Decision is **C**.
- **Future revisit:** only when (a) an independently verified goods-info probe with documented response is committed, OR (b) a manual offline mapping file satisfying `FR-4.1`–`FR-4.5` is committed. Either path requires its own implementation phase.

## Frozen contracts (unchanged)

All previously frozen contracts remain active and unchanged:

- `D-IDENTITY-001` — abstract bridge with no implementation.
- `D-IDENTITY-002` — identity source frozen; synthetic/offline only.
- `D-IDENTITY-003` — Phase 13L-0 four-source survey.
- `D-IDENTITY-004` — Phase 13N-1 BUF anonymous response field inventory.
- `D-ADAPTER-003` — adapter does not resolve identity.
- `D-AUTH-001` — anonymous client contract.
- `D-BUFF-001`, `D-BUFF-002`, `D-BUFF-003` — anonymous research path, listing provider abstraction, anonymous-client hardening.
- `D-STEAMDT-001`, `D-STEAMAPIS-001` — SteamDT and SteamApis as identity source (both rejected).

## What This Decision Does NOT Change

- `BuffItemIdentity` / `BuffItemIdentityResolver` shape, validation, or protocol.
- `BuffListing.market_hash_name = None` production behavior.
- `BuffGoodsInfo` dataclass shape (it remains a placeholder; no field is added or removed).
- `BuffListingCandidateAdapter` rejection vocabulary and adapter behavior.
- `TradeUpInputEnrichment` rejection vocabulary and seam contract.
- The frozen canonical path: `BuffListingProvider → BuffListingCandidateAdapter → TradeUpInputCandidate → TradeUpInputEnrichment → InputItem → tradeup_engine`.
- The synthetic scale validation (Phase 13J-1), the synthetic candidate adapter (Phase 13K-1), and all other offline seam tests.

## Out of Scope (frozen here)

- No live probe of the goods-info endpoint.
- No `D-AUTH-001` relaxation.
- No `D-BUFF-001` relaxation.
- No invented endpoint path.
- No invented response schema.
- No invented authentication or signature logic.
- No concrete resolver implementation.
- No mapping file.
- No parser modification.
- No browser automation, cookie scraping, or anti-bot bypass.

## Remaining Blockers (unchanged from prior phases)

- **Primary:** verified `market_hash_name ↔ BUF goods_id` source. **Unchanged by this phase**; this audit deepens the negative evidence for the only remaining native candidate and adds `D-IDENTITY-005`.
- **Secondary:** intrinsic flag source on `BuffListing` (`D-MIGRATION-002`). Unchanged.
- **Tertiary:** no production scanner orchestration runtime. Unchanged.

## Recommended Next Phase

**Independent of identity**, the most actionable next steps remain (from the prior state audit):

- **Phase 13N-3** — Manual Offline Identity Mapping (Source D), gated on the availability of a documented verification procedure and a first attested entry. Permissible under `FR-4.1`–`FR-4.5`. Separate implementation phase.
- **Phase 13M-1** — `ScannerOrchestrator` skeleton (per Phase 13M-0 design).
- **Phase 13O** — `BuffListing` intrinsic flag exposure (per `D-MIGRATION-002`).
- **Phase 13R** — Roadmap + `docs/ARCHITECTURE.md` refresh.

Identity remains the unblocking prerequisite for production wiring, but it does **not** block the four non-identity phases above.

## Direct Answers to Audit Questions

### Q1. Does BUFF expose a native goods information endpoint?

The repository **does not contain evidence of a verified one**. The endpoint is listed as TODO `#5` in `docs/BUFF_API_NOTES.md:62-64`. The legacy `BuffGoodsInfo` dataclass (`app/clients/buff_client.py:53-68`) is a placeholder shape with no verified response schema. `BuffHttpClient.get_goods_info()` raises `NotImplementedError(UNCONFIRMED_MAPPING_ERROR)`. No live smoke harness exists for this endpoint. No fixture pairs a `goods_id` with a verified response.

### Q2. If a possible endpoint exists, can `goods_id=1115941` return `{goods_id, market_hash_name}`?

**Not verifiable from current evidence.** The repository contains zero references to `goods_id=1115941`. No smoke script, fixture, test, log, or doc exercises this id with a real response. The goods-info endpoint is unprobed; the `BuffGoodsInfo` shape is unimplemented; no anonymous-accessibility claim is documented. Any claim about what the endpoint would return for `1115941` would be **speculation**, which is forbidden by `docs/BUFF_API_NOTES.md:107-118` ("Do not invent endpoint paths. Do not invent response fields or field mappings.").

### Q3. Anonymous compatibility check

**Unknown.** The goods-info endpoint has never been probed. There is no documented header allowlist, no documented auth mechanism, no documented query/path contract. The current anonymous client (`app/clients/buff_anonymous_listing_client.py`) is hardcoded to one URL (`/api/market/goods/sell_order`) and four query params; it cannot be reused for a goods-info probe without explicit modification, which is out of scope for this audit.

### Q4. Identity confidence classification

- **A (Direct authoritative identity source):** None.
- **B (Indirect but verifiable):** None — no Steam identifiers are exposed anywhere in the repository.
- **C (Possible but unverified):** **The goods-info endpoint.** Listed as TODO, never probed, schema unknown, lifecycle unknown. **NOT ACTIONABLE** for production wiring.
- **D (Not usable):** SteamDT `platformItemId`, SteamApis `source_offer_id`, BUF anonymous sell-order.

## Critical Files

Add (this research phase, no implementation):

- `specs/2026-08-22-buff-native-goods-identity-investigation/findings.md`
- `specs/2026-08-22-buff-native-goods-identity-investigation/decision.md`
- `specs/2026-08-22-buff-native-goods-identity-investigation/validation.md`

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
- No `app/`, `tests/`, `scripts/`, or `docs/` paths modified.
- No commit unless separately requested.