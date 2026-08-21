# ARCHITECTURE_STATE.md

## Data Flow (as currently implemented)

### SteamDT (aggregate / output valuation)

```
market_hash_name
  → SteamDTHttpClient GET /open/cs2/v1/price/single (api key)
  → aggregate platform records (BUFF / STEAM / YOUPIN / ... )
  → exact "BUFF" sell price policy (sell only, no bid fallback)
  → SteamDTBuffPriceProvider → PriceQuote(source="steamdt:buff")
  → ValuationService → value_live_recipes → EV / ROI / risk
```

SteamDT gives `marketHashName`, `platform`, `sellPrice`, `sellCount`, `biddingPrice`, `biddingCount`, opaque `platformItemId`, `updateTime`. It does **not** give concrete listings, seller, purchase URL, or exact per-listing float. It is output-valuation only.

### BUFF anonymous (input listing discovery, gated/read-only)

```
BUFF_READONLY_SMOKE_GOODS_ID (caller context, not response-derived)
  → BuffAnonymousListingHttpClient GET /api/market/goods/sell_order
     (game=csgo, goods_id, page_num=1, sort_by=default; one request; no auth/cookie/redirect/retry)
  → strict all-item parser
  → list[BuffListing]
```

`BuffListing` fields: `listing_id`, `goods_id` (request context), `market_hash_name` (always `None` currently), `price_cny`, `paintwear`, `asset_id` (required string), `paintseed` (optional), `source="buff"`.

### Identity bridge (abstraction only, unresolved)

```
market_hash_name → BuffItemIdentityResolver.resolve() → BuffItemIdentity | None
```

`None` is the normal unresolved outcome. No concrete resolver or mapping data exists.

### Future (not yet wired)

```
BuffListing → TradeUpInputCandidate → (future trade-up engine)
```

## Existing Modules (responsibility map)

- `app/clients/buff_anonymous_listing_client.py` — hardened anonymous BUFF GET; exact independent request, header allowlist, auth/redirect disabled.
- `app/services/buff_listing_provider.py` — `BuffListing` DTO, strict parser, `BuffListingProvider`.
- `app/services/buff_item_identity.py` — `BuffItemIdentity`, `BuffItemIdentityResolver` protocol (unresolved).
- `app/clients/buff_client.py` — legacy `BuffHttpClient` (unimplemented), `MockBuffClient`, `DryRunBuffClient`, legacy `BuffSellOrder`/`BuffGoodsInfo`.
- `app/services/buff_listing.py` + parser/facts/eligibility/qualification/solver_adapter — Phase 12 offline contract chain.
- `app/services/market_scan_service.py` — `CandidateListing`, legacy synchronous scanner (`scan_goods`/`scan_watchlist`).
- `app/services/recipe_solver.py` — deterministic greedy recipe construction; source-blind.
- `app/services/tradeup_engine.py` — `InputItem`/`OutputCandidate`/`TradeupResult`, trade-up math.
- `app/services/ev_service.py` — fee application, EV/ROI metrics.
- `app/services/risk_filter.py` — `RiskDecision`, ROI/profit/probability/liquidity gates.
- `app/services/valuation_service.py` + `live_recipe_valuation.py` — strict complete-price valuation.
- `app/services/steamdt_*` + `app/clients/steamdt_client.py` — SteamDT aggregate client/parser/limiter/cache/providers.
- `app/services/steamapis_*` + `app/clients/steamapis_*` — SteamApis WebSocket offer stream (paused/unverified live).
- `app/services/metadata_*` — skin metadata normalization (name-based; no BUFF goods ID).
- `app/services/pipeline_service.py` + `app/jobs/scheduler.py` — legacy mock BUFF pipeline (fixture-backed).

## Protected Core (do not modify without migration plan + approval)

- `app/services/tradeup_engine.py`
- `app/services/valuation_service.py`
- `app/services/live_recipe_valuation.py`
- `app/services/ev_service.py`
- `app/services/risk_filter.py`
- `app/services/recipe_solver.py`
- `app/services/market_scan_service.py` (`CandidateListing`)
- Phase 12 BUFF domain: `buff_listing.py`, `buff_listing_parser.py`, `buff_listing_facts.py`, `buff_listing_eligibility.py`, `buff_listing_qualification.py`, `buff_listing_solver_adapter.py`
- `app/clients/buff_client.py` (legacy skeleton)
- SteamDT client/core, SteamApis modules, metadata providers.
- `app/services/buff_listing_provider.py` and `app/clients/buff_anonymous_listing_client.py` (recently hardened; change only with explicit new spec).

## Verified vs Assumed vs Unknown

- **Verified (manual, one request):** anonymous BUFF sell-order first page returns `items[]` with id/price/`asset_info.paintwear`/`asset_info.assetid`; paintseed absent in that run.
- **Assumed (project decision):** SteamDT sell/bid interpreted as CNY/RMB; BUFF `price_cny` project-facing naming.
- **Unknown:** official currency/fees, canonical `market_hash_name` mapping, goods/product/search endpoint, quantity/freshness/removal, pagination/page size, rate limits, classification facts, purchase handoff.

## Standing Engineering Constraints

The project must not implement any of the following, regardless of upstream capability:

- proxy bypass
- User-Agent rotation
- browser automation
- anti-bot circumvention
- automated purchasing
- purchase execution
- credential or session harvesting

Reason: maintain verified readonly market-data boundaries. SteamDT and BUFF anonymous paths are explicitly silent or fail closed on any inferred evasion, and the project refuses to acquire the credentials, sessions, browser signals, or purchase capability that would enable them. Any future code that would require this is out of scope and must be redirected through a non-evasion alternative or rejected.
