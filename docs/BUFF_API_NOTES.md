# BUFF API Notes / TODO

## Purpose
Track all unconfirmed BUFF API assumptions during the specification and implementation phases. This file exists to prevent the project from inventing endpoints, signatures, request parameters, or response fields.

## Confirmed Constraints
- V1 is read-only and notification-only.
- No auto-buy.
- No auto-login.
- No cookie extraction.
- No captcha bypass.
- No BUFF risk-control bypass.
- No browser-simulated purchasing.
- Tests must use mock responses rather than real BUFF requests.

## Empirical Anonymous Compatibility Boundary

A user-authorized one-request research probe on 2026-08-20 succeeded anonymously against `GET /api/market/goods/sell_order` with explicit `game=csgo`, `goods_id`, `page_num=1`, and `sort_by=default`. The first item exposed compatible `id`, positive `price`, bounded `asset_info.paintwear`, and non-null `asset_info.assetid`; `asset_info.paintseed` was absent/null. This is not official OpenAPI evidence and does not close the TODOs below.

Phase 13C uses only that narrow empirical mapping in a standalone, unwired provider. Goods ID remains explicit request context; market name is not mapped; price uses a project-facing CNY name without an official currency/fee guarantee; asset ID is required by the fail-closed parser; seed remains optional; every returned item is validated atomically. No raw live response is retained. Pagination/page size, rate limits, quantity, freshness/removal, authoritative identity semantics, facts/classification, and production access remain unconfirmed.

## TODO — Unconfirmed API Details

### 1. Endpoint Discovery
- [ ] Confirm which BUFF endpoints provide candidate CS2 material listings suitable for trade-up scanning.
- [ ] Confirm whether separate endpoints exist for listing search, item detail, and market depth/order book data.
- [ ] Confirm whether float is directly available from listing responses or requires another endpoint.

### 2. Authentication / Signing
- [ ] Confirm whether read-only market data used by this project requires authentication.
- [ ] Confirm whether official developer API uses API key, signature, timestamp, nonce, or another auth mechanism.
- [ ] Confirm required headers.
- [ ] Confirm whether any signing scheme is required.
- [ ] Confirm whether cookies are necessary for allowed read-only access.
- [ ] If cookies are required, confirm what officially supported access pattern is permitted for this project scope.

### 3. Request Parameters
- [ ] Confirm pagination fields.
- [ ] Confirm sorting/filter fields relevant to price, float, rarity, and listing status.
- [ ] Confirm request params for sell orders: goods_id, page, page_size, sort, min/max float, and price filters.
- [ ] Confirm rate-limit behavior and any response headers indicating quotas or backoff.

### 4. Sell Orders Endpoint
- [ ] Confirm endpoint path.
- [ ] Confirm response fields mapping to BuffSellOrder.

### 5. Goods Info Endpoint
- [ ] Confirm endpoint path.
- [ ] Confirm response fields mapping to BuffGoodsInfo.

### 6. Buy Orders Endpoint
- [ ] Confirm endpoint path.
- [ ] Confirm response fields mapping to BuffBuyOrder.

### 7. Price History Endpoint
- [ ] Confirm endpoint path.
- [ ] Confirm response fields mapping to BuffPricePoint.

### 8. Response Fields
- [ ] Confirm canonical listing identifier field.
- [ ] Confirm canonical goods identifier field.
- [ ] Confirm price field naming and currency semantics.
- [ ] Confirm float field presence, precision, and nullability.
- [ ] Confirm available quantity / stock field.
- [ ] Confirm whether order depth, seller count, or liquidity-adjacent fields are available.
- [ ] Confirm timestamp fields and their timezone/format.

### 9. Data Quality / Semantics
- [ ] Confirm how delisted, sold, stale, or hidden listings appear in responses.
- [ ] Confirm whether price anomalies can be detected from official fields alone.
- [ ] Confirm whether trade lock / special status flags exist and are relevant.

## Current Spec Assumptions
The current specification intentionally assumes only this minimal internal contract for a listing snapshot:
- `goods_id` (or equivalent item identifier)
- `listing_id` (or equivalent listing identifier)
- `price`
- `float` if available
- `quantity` / availability if available
- raw payload snapshot
- scan timestamp

Anything beyond this contract remains TODO until confirmed.

## Explicit Rules
- Do not implement auto-buying.
- Do not implement login automation.
- Do not scrape cookies.
- Do not bypass captcha.
- Do not bypass BUFF risk control.
- Do not use browser automation for purchasing.
- Do not invent endpoint paths.
- Do not invent authentication or signature logic.
- Do not invent response fields or field mappings.

## Implementation Rule
Until BUFF details are confirmed:
1. do not hard-code uncertain endpoints
2. do not hard-code uncertain signature logic
3. do not hard-code uncertain field mappings into upper-layer business logic
4. keep raw payloads for replay and parser updates only in a future separately approved production mapping; the anonymous research provider intentionally retains no raw live response
5. use mock responses in tests
6. do not invent endpoints, signing methods, request parameters, or response fields
7. wait for the user to provide official BUFF documentation details before finalizing endpoint/signature/field mapping
