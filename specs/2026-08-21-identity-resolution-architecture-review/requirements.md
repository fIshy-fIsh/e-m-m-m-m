# Phase 13F-0 — Identity Resolution Architecture Review

## 1. Current contract inventory

- `BuffItemIdentity(market_hash_name: str, goods_id: str)` — immutable, repr-suppressed, keyword-only. Validates exact nonblank canonical strings.
- `BuffItemIdentityResolver.resolve(market_hash_name) -> BuffItemIdentity | None` — async protocol. `None` = unresolved.
- `TradeUpInputCandidate` exposes `market_hash_name: str | None` (explicit unresolved marker) plus `goods_id: str`, `listing_id`, `price_cny`, `paintwear`, `asset_id`, `source`.
- `BuffListing` exposes `market_hash_name = None` (current parser) plus `goods_id` (request context), `listing_id`, `price_cny`, `paintwear`, `asset_id`, `paintseed`, `source`.
- Metadata providers expose `market_hash_name` but no BUFF `goods_id`.
- No concrete resolver implementation exists (`None` until identity is proven).

## 2. Evaluation of candidate future identity providers

### 2.1 BUFF goods metadata endpoint

- **Data authority:** BUFF server, if an endpoint exists and is anonymous/read-only.
- **Authentication:** unknown; explicit TODO in `docs/BUFF_API_NOTES.md`. Legal patterns may require login or a developer key.
- **Reliability:** potentially authoritative IF endpoint is anonymous and the field semantics are verified.
- **Cardinality risk:** wearable-qualified (Factory New / Minimal Wear / …), StatTrak/Souvenir variants, localized vs canonical names. Multiple cosmetic forms may map to one goods_id or one goods_id may expose only a localized display name.
- **Integration boundary:** new HTTP client; risk of violating the anonymous/no-Cookie/no-login contract; could require a per-goods-id search or a separate goods-info call. Phase 13D-2 confirmed no validated endpoint today.
- **Recommendation:** do **not** wire until a separately verified anonymous/read-only path produces both canonical fields together. Re-evaluate when official documentation or a sanitized sample becomes available.

### 2.2 SteamDT identity fields

- **Data authority:** SteamDT aggregate records.
- **Authentication:** required API key.
- **Reliability:** not authoritative for BUFF. `platformItemId` is documented as opaque platform-local identity; the audit (`docs/STEAMDT_API_NOTES.md`) explicitly asks whether it maps to BUFF `goods_id` and leaves it TODO.
- **Cardinality risk:** high. One `market_hash_name` maps to many platform records; `platformItemId` is platform-scoped, not BUFF-scoped. Even inside one platform (`platform == "BUFF"`), `platformItemId` is not proven to equal the BUFF `goods_id` used by the sell-order endpoint.
- **Integration boundary:** violates the project's anonymous-only stance once a key is required, and the field mapping is unverified.
- **Recommendation:** reject. The current explicit TODO in `docs/STEAMDT_API_NOTES.md` (whether `platformItemId` maps to BUFF `goods_id`) must be resolved before any wrong inference becomes a resolver backend source.

### 2.3 External metadata catalog (ByMykel / Steam-only)

- **Data authority:** community-maintained metadata.
- **Authentication:** none (fetch-only).
- **Reliability:** only provides `market_hash_name` (and rarity/collection/etc.). It does **not** provide BUFF `goods_id`.
- **Cardinality risk:** name-only, cannot bridge to BUFF.
- **Integration boundary:** useful for name authority but cannot alone resolve identity.
- **Recommendation:** useful as a name canonicalizer, not as a BUFF identity resolver. May be combined with a separate BUFF source later.

### 2.4 Manual verified mapping

- **Data authority:** human-verified offline table.
- **Authentication:** none.
- **Reliability:** depends entirely on human review and versioning.
- **Cardinality risk:** manual drift; case, wear, StatTrak/Souvenir; removal/updates.
- **Integration boundary:** an `OfflineBuffItemIdentityResolver` keyed by an immutable `MappingProxyType` with revision/version metadata. Maps to the existing `BuffItemIdentityResolver` protocol.
- **Recommendation:** acceptable as a fallback bridge for `None` only when an externally verified source is unavailable. Manual mappings must be unambiguous, revisioned, and explicitly out of any production automation.

## 3. Current interface adequacy

The existing `BuffItemIdentityResolver.resolve(market_hash_name) -> BuffItemIdentity | None` is sufficient for the **forward** direction: name → identity.

It is **not** sufficient for the **reverse** direction: `goods_id` → `market_hash_name`. The `TradeUpInputCandidate` boundary is constructed from `BuffListing` and arrives with `goods_id` first; populating `market_hash_name` may require a reverse lookup or a unified resolver that supports both directions.

## 4. Required future adapter contracts

The current review identifies **one missing contract**: the reverse direction. The recommended minimum is to extend the existing protocol with a symmetric method while preserving the current contract:

```python
class BuffItemIdentityResolver(Protocol):
    async def resolve(
        self,
        market_hash_name: str,
    ) -> BuffItemIdentity | None: ...

    async def resolve_by_goods_id(
        self,
        goods_id: str,
    ) -> BuffItemIdentity | None: ...
```

Both methods return `None` for unresolved and always return canonical, exact nonblank strings when resolved. No return value contains nested exception text, fetched body, or page metadata.

A future identity-aware adapter from `BuffListing` to `TradeUpInputCandidate` would compose:

```text
BuffListing
  + resolve_by_goods_id(listing.goods_id) -> Optional[BuffItemIdentity]
  -> TradeUpInputCandidate(
       listing_id=listing.listing_id,
       goods_id=listing.goods_id,
       market_hash_name=identity.market_hash_name if identity else None,
       price_cny=listing.price_cny,
       paintwear=listing.paintwear,
       asset_id=listing.asset_id,
       source=listing.source,
     )
```

The adapter is **not** implemented in this phase. It is recorded as a future contract only.

## 5. Decision summary

- D-IDENTITY-001 (Path B: unresolved, abstraction only) remains valid.
- No implementation is added in this phase.
- The current `BuffItemIdentity` DTO and `None` convention are confirmed adequate.
- **Forward direction** is supported: `resolve(market_hash_name) -> BuffItemIdentity | None`.
- **Reverse direction** is identified as a missing contract and recorded as a future addition. It does **not** change the current module; it is a spec-only forward commitment.
- No candidate provider is approved for live wiring. BUFF goods metadata requires separately verified anonymous/read-only evidence; SteamDT identity fields are rejected; external metadata catalogs do not bridge; manual verified mapping is permitted only as a future offline fallback and must be revisioned.

## 6. Protected scope

Do not modify `BuffListing`, the anonymous BUFF client/provider/smokes, `TradeUpInputCandidate`, `BuffItemIdentity`, `BuffItemIdentityResolver`, Phase 12 BUFF modules, SteamDT, SteamApis, metadata, scanner, solver, valuation, EV/risk, pipeline, scheduler, config, dependencies, or any live smoke.

## 7. Allowed files

- `specs/2026-08-21-identity-resolution-architecture-review/{plan,requirements,validation}.md`
- `docs/ai-context/DEVELOPMENT_HANDOFF.md` (single line addition)

No code changes.
