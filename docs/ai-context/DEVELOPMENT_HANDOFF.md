# DEVELOPMENT_HANDOFF.md

## Current Git State (verify live)

- **Branch:** `feature/steamdt-cache-rate-limit`
- **HEAD:** `2a8a1e8bb23aa0e51ad9ebb73ac50a662a951e4f`
- **HEAD message:** `harden buff listing provider anonymous contract`
- **Uncommitted work:** Phase 13D-0 identity contract (not committed at time of this write). Uncommitted changes remain working tree state and are not part of the canonical committed baseline:
  - Modified: `docs/BUFF_ANONYMOUS_READONLY_NOTES.md`, `docs/BUFF_API_NOTES.md`
  - Untracked: `app/services/buff_item_identity.py`, `specs/2026-08-21-buff-item-identity-contract/`, `tests/test_buff_item_identity.py`

Recent commit history (oldest → newest):

```
1f3355a add steamapis websocket client
b1650cd add steamapis offer session runner
768aa65 add live pool recipe construction
23c2465 add opt-in steamapis live smoke
eed38f8 add steamdt aggregate market data
2c01c46 add buff steamdt price policy
d1e7161 add buff steamdt price provider
08b919e propagate memory errors in valuation service
8d757dc compose buff steamdt live valuation
965164c add live buff steamdt provider smoke
c54e2f9 add deterministic live recipe fixture
04dd00a lock verified steamdt smoke output
fac508c add live steamdt recipe valuation smoke
04ba133 add buff anonymous schema smoke
caf5922 add buff listing provider abstraction
2a8a1e8 harden buff listing provider anonymous contract
```

## Completed Milestones

### Phase 13A — SteamDT aggregate + valuation (committed)

- SteamDT market data client, aggregate DTO, CNY assumption, exact-BUFF price policy, price provider, closed valuation composition, deterministic live-recipe fixture, verified output identity, opt-in live recipe valuation smoke.
- Output valuation works: exact BUFF sell price → EV/ROI/risk. Real input sourcing is NOT part of this milestone.

### Phase 13B Step 2B — BUFF anonymous schema smoke (committed `04ba133`)

- `scripts/run_live_buff_anonymous_sell_order_schema_smoke.py`: one-request, gated, anonymous, schema-only probe of `GET /api/market/goods/sell_order`.

### BUFF anonymous live smoke — manually executed once (verified)

- Result: success; listing_id/price/paintwear valid; asset_id present; paintseed absent; `BUFF requests sent: 1`.
- This confirms anonymous compatibility of the sell-order first page; it does **not** confirm a goods↔name mapping.

### Phase 13D-1 — identity investigation

- Investigation milestone without production code.
- Result: no verified live source for `market_hash_name ↔ BUFF goods_id`.
- See `D-IDENTITY-001` in `DECISION_LOG.md` and `docs/BUFF_API_NOTES.md` for the unresolved TODOs.

### Phase 13D-2 — metadata endpoint investigation

- Investigation milestone without production code.
- Result: no validated anonymous/read-only goods/metadata endpoint was discovered; the candidate `BuffGoodsInfo` shape remains unimplemented; no endpoint was coded or requested.
- Do not invent one.

### Historical SteamApis exploration (paused)

The following commits were made under the SteamApis route. The route is currently paused, **not** wired into the canonical input pipeline:

- `1f3355a` add steamapis websocket client
- `3b610d4` add bounded steamapis offer pool
- `b1650cd` add steamapis offer session runner
- `768aa65` add live pool recipe construction
- `23c2465` add opt-in steamapis live smoke

SteamApis exploration was paused because:

- BUFF goods identity was not verified (the compatibility IDs are project-local SHA-256 hashes, not authoritative BUFF IDs).
- removal / deleted event semantics were not confirmed by the documented contract.
- `ENABLE_LIVE_STEAMAPIS_SMOKE` was left gated and the live smoke was not executed.

The components remain in the tree as paused, offline-tested optional infrastructure. Resume only after a verified live smoke and a separate BUFF identity strategy.

### Phase 13C — BUFF listing provider (committed `caf5922`, hardened `2a8a1e8`) — exact contract preserved.

### Phase 13E-0 — Trade-up input candidate boundary (in progress)

- Adds the standalone `TradeUpInputCandidate` DTO between `BuffListing` and the future trade-up engine.
- `market_hash_name` is `None` by default; identity resolution is explicitly deferred.
- No adapter, no resolver, no scanner, no solver, no SteamApis, no purchase.

- `BuffListing` DTO, strict all-item parser, `BuffListingProvider`, shared one-request smoke runtime, provider live smoke, anonymous client hardening.

### Phase 13D-0 — identity bridge contract (UNCOMMITTED)

- `BuffItemIdentity` + `BuffItemIdentityResolver` protocol. `None` = unresolved. No mapping data, no concrete resolver. `BuffListing` unchanged.

### Phase 13D-1 / 13D-2 — source investigation (read-only, no code)

- No verified source for `market_hash_name ↔ BUFF goods_id`; no validated goods/product/search endpoint. Do not invent one.

## Current Status

- BUFF anonymous listing acquisition: **solved** (provider works; gated, read-only).
- SteamDT output valuation: **solved** (aggregate output valuation).
- Goods identity bridge: **abstraction only**; no verified resolver backend.
- Trade-up input normalization boundary: **not yet built** (Phase 13E-0).

## Next Action (ordered)

1. (In-flight) Phase 13D-0 identity contract is implemented but uncommitted — decide whether to commit it before 13E-0.
2. Phase 13E-0 — design `TradeUpInputCandidate` between `BuffListing` and the future trade-up engine (no solver/EV/scanner wiring). Keep unresolved `market_hash_name` explicit.
3. Later: obtain verified goods↔name evidence before implementing any resolver backend.
4. Later: verify quantity/freshness/classification facts before bridging into Phase 12/solver.

## Current Blockers

- No verified `market_hash_name ↔ BUFF goods_id` source.
- BUFF goods/product/search endpoint undocumented/unauthorized.
- Anonymous sell-order has no verified market name; `BuffListing.market_hash_name` stays `None`.
- Phase 12 requires market name + quantity + classification facts that are not yet verified for the anonymous path.

## Standing Prohibitions (re-asserted)

No auto-buy, auto-login, cookie scraping, CAPTCHA/risk-control bypass, browser purchasing, proxy/UA rotation, mass scraping, or invented endpoints/fields. Live smokes stay gated and never auto-run. Do not modify Protected Core without an explicit migration plan.
