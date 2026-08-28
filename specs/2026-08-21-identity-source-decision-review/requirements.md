# Phase 13G-0 — Identity Source Decision Review

## 1. Candidate sources

### 1.1 BUFF native metadata endpoint

- **Authority:** BUFF server, if an anonymous/read-only goods or product endpoint exists and is documented.
- **Authentication:** unknown — official developer API, login, signed requests, or cookies are all possible. Current state is explicit TODO in `docs/BUFF_API_NOTES.md`.
- **Reliability:** potentially authoritative IF a documented anonymous/read-only endpoint and verified field semantics are obtained. Otherwise it is speculative.
- **Maintenance cost:** medium — single endpoint, but field semantics, pagination, rate limits, and removal/freshness must be verified. Future schema changes require a contract update.
- **Cardinality risk:** medium — wear-qualified, StatTrak/Souvenir, and regional name variants may map one goods_id to multiple display forms or one display form to multiple goods_ids.
- **Acceptable for production automation:** **no**, until a documented anonymous/read-only endpoint and verified field semantics are obtained.
- **Revisit conditions:** official documentation, sanitized sample, or a confirmed user-authorized anonymous probe that exposes both canonical fields together.

### 1.2 SteamDT identity fields (price `platformItemId`, base `platformList[].itemId`)

- **Authority:** SteamDT aggregate records; not BUFF.
- **Authentication:** API key required.
- **Reliability:** not authoritative for BUFF identity. `platformItemId` is opaque platform-local identity. The open TODO in `docs/STEAMDT_API_NOTES.md` ("whether platform item id can help map BUFF goods_id") has not been closed.
- **Maintenance cost:** low once a key is provided, but the mapping is unverified, so any saved work is speculative.
- **Cardinality risk:** high — one `market_hash_name` maps to many platform records; `platformItemId` is platform-scoped, not BUFF-scoped.
- **Acceptable for production automation:** **no**, because the mapping is unverified and the project's anonymous-only stance would be violated.
- **Revisit conditions:** a verified closed TODO in `docs/STEAMDT_API_NOTES.md` proving one or more `platformItemId` values in certain bases is the BUFF `goods_id`.

### 1.3 SteamApis identity possibility

- **Authority:** SteamApis `Buff163` stream; no BUFF authoritative identity.
- **Authentication:** API key + WebSocket.
- **Reliability:** low — the resolved identity is a project SHA-256 of (marketplace, game, opaque purchase link), explicitly **not** a BUFF `goods_id`. The compatibility ID is not canonical BUFF identity.
- **Maintenance cost:** medium — already partially built but currently paused.
- **Cardinality risk:** high — one offer is per-listing; goods_id would have to be inferred from the offer's skin, which is not guaranteed.
- **Acceptable for production automation:** **no**, the compatibility ID is documented as not being authoritative for BUFF.
- **Revisit conditions:** SteamApis documents a BUFF `goods_id` field or equivalent, which is not currently the case.

### 1.4 Manual verified offline mapping

- **Authority:** human-verified, project-owned.
- **Authentication:** none.
- **Reliability:** high for the specific items entered, low for anything else. Drift and version handling are required.
- **Maintenance cost:** low per item, but linear in item count; revisable, not real-time.
- **Cardinality risk:** low (manual), but does not cover the entire catalog.
- **Acceptable for production automation:** **only if** explicit, versioned, immutable, and used as a documented fallback. Not acceptable as a primary live source.
- **Revisit conditions:** a verified authoritative external source becomes available.

## 2. Decision

**Choice D — Freeze identity work and proceed with a synthetic/offline pipeline only.**

Reasoning:

1. No verified anonymous/read-only native BUFF source is available now or is on the project's path.
2. SteamDT identity fields are explicitly unverified and out of policy (anonymous-only, no key-driven authority).
3. SteamApis compatibility IDs are explicitly not authoritative BUFF identity.
4. A manual verified mapping is acceptable only as a future fallback, not as a primary source.

Chosen options:

- **A (continue searching for native BUFF identity source):** kept as a long-term revisit. The open `docs/BUFF_API_NOTES.md` TODO remains in place. No implementation is added.
- **B (accept external identity provider):** rejected. The current policy forbids external non-anonymous sources; no provider in scope is verified.
- **C (hybrid approach):** not applicable now. There is no verified primary source to combine with any fallback.
- **D (chosen):** freeze identity work and proceed with a synthetic/offline pipeline only. The forward direction in `BuffItemIdentityResolver.resolve(market_hash_name)` remains an abstraction; `None` continues to be the only real answer. The trade-up engine can be exercised through `TradeUpInputCandidate` with `market_hash_name=None` using synthetic-only fixture inputs.

## 3. Architecture impact

- `BuffItemIdentity` and `BuffItemIdentityResolver` are unchanged.
- `TradeUpInputCandidate` is unchanged; `market_hash_name` remains the explicit unresolved marker.
- The synthetic-only pipeline is exercised via offline fixtures, not via live integration.
- No new endpoint, no mapping file, no resolver backend, no production wiring is added.
- The `docs/BUFF_API_NOTES.md` TODO remains open for future revisits.

## 4. Required future work

- Phase 13H and beyond may introduce a synthetic-only pipeline that exercises `TradeUpInputCandidate` with `market_hash_name=None` and tests the resolver's contract-only behavior.
- If a separately verified anonymous/read-only BUFF identity source is found, the resolver contract may be extended with the reverse direction `resolve_by_goods_id(goods_id)` per the Phase 13F-0 review.
- If a verified market-name bridge is later obtained, `TradeUpInputCandidate` can be enriched through a future identity-aware adapter without changing this phase's contract.
- The current decision is recorded as `D-IDENTITY-002` in `DECISION_LOG.md`.
