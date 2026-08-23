# Phase 13N-1 — BUFF Identity Reality Verification (Findings)

## 1. Evidence Table

All evidence collected is repository-traceable. Every finding cites a file path and line range. The audit is exhaustive across `app/`, `tests/`, `scripts/`, and `docs/`.

| # | Evidence | Location | Finding | Impact |
|---|---|---|---|---|
| 1 | Anonymous BUFF endpoint | `app/clients/buff_anonymous_listing_client.py` lines defining `BUFF_ANONYMOUS_BASE_URL` and `BUFF_ANONYMOUS_SELL_ORDER_PATH` | Endpoint: `GET https://buff.163.com/api/market/goods/sell_order` (HTTPS, no port). One request, no auth, no cookie, no redirect. | Single endpoint is the only live BUFF surface in the project. |
| 2 | Allowed request parameters | `buff_anonymous_listing_client.py` — `validate_buff_anonymous_listing_request` | Exactly four params, exact order: `game=csgo`, `goods_id=<caller>`, `page_num=1`, `sort_by=default`. No filter, no pagination beyond page 1, no market-name filter. | Caller must supply a `goods_id` they already know. The endpoint cannot discover a `goods_id` from a `market_hash_name`. |
| 3 | Allowed request headers | `buff_anonymous_listing_client.py` — `_ALLOWED_HEADER_NAMES = frozenset({"accept", "host", "user-agent"})` | Only `Accept`, `Host`, `User-Agent`. No `Cookie`, no `Authorization`, no `Referer`, no `Origin`, no `X-Requested-With`. | Per `D-AUTH-001`. Anonymous and read-only. |
| 4 | Response bytes returned, not parsed | `buff_anonymous_listing_client.py` — `fetch_sell_order_payload` returns `bytes(response.content)` | The client does NOT parse JSON; it returns raw bytes to the caller. | All parsing logic lives in `buff_listing_provider.py`. |
| 5 | Response envelope required | `app/services/buff_listing_provider.py` — `parse_buff_listing_response` | Required: `code == "OK"`, `data` is `dict`, `data["items"]` is `list`. | Top-level response is a thin envelope. |
| 6 | Per-item response fields accessed | `buff_listing_provider.py` — strict atomic parser | Six fields are read: `items[].id` → `listing_id`; `items[].price` → `price_cny`; `items[].asset_info.paintwear` → `paintwear`; `items[].asset_info.assetid` → `asset_id`; `items[].asset_info.paintseed` → `paintseed`. `goods_id` comes from caller context. `source` is hardcoded `"buff"`. `market_hash_name` is **hardcoded `None`** at line ~212. | The parser accesses exactly six item-level fields. Every other item key is silently ignored by `.get(...)`. |
| 7 | `market_hash_name` construction | `buff_listing_provider.py` line 212 | `market_hash_name=None` is set unconditionally on every parsed `BuffListing`. | Identity bridge from anonymous path is **structurally impossible** without parser modification. |
| 8 | `goods_id` origin | `buff_listing_provider.py` — `parse_buff_listing_response(payload, *, goods_id: str)` | `goods_id` is the caller's request argument, never derived from the response. | Anonymous endpoint does not echo `goods_id`; caller must supply it. |
| 9 | `source` origin | `buff_listing_provider.py` line 217 | `source="buff"` is hardcoded. | No response-derived provenance field. |
| 10 | `classid` / `instanceid` / `appid` grep | entire repo | **Zero matches** anywhere in `app/`, `tests/`, `scripts/`, or `docs/`. | No Steam economy identifiers are referenced. Indirect conversion chain cannot be built. |
| 11 | `market_hash_name` grep (live path) | `app/` | Only two references: field declaration on `BuffListing` and the `None` assignment at `buff_listing_provider.py:212`. Zero access patterns. | No production code reads `market_hash_name` from a BUFF response. |
| 12 | Wire-format fixture carries `asset_info.market_hash_name` | `tests/fixtures/buff/anonymous_sell_orders_provider_v1.json` | The fixture contains `"market_hash_name": "Unverified Synthetic Name"` and `"Another Unverified Synthetic Name"` inside `asset_info`. | This is a **project-owned placeholder**, not verified BUFF evidence. The string is explicitly marked "Unverified". |
| 13 | Smoke harness rejects `market_hash_name` | `tests/test_live_buff_anonymous_sell_order_schema_smoke.py` | Asserts that `market_hash_name`, `seller`, `msg`, `Cookie` are NOT present in items. | The live smoke contract treats `market_hash_name` as an unwanted leak. The parser refuses it on purpose. |
| 14 | Empirical live probe outcome | `docs/BUFF_ANONYMOUS_READONLY_NOTES.md` (Phase 13B) | First-item verified: `id`, `price`, `asset_info.paintwear`, `asset_info.assetid`. `paintseed` was absent in that run. **No other fields were probed.** | The empirical evidence covers only those fields; absence of `market_hash_name` is not proven — but its presence is also not proven. The probe is narrow by design. |
| 15 | `BuffListing` DTO field set | `buff_listing_provider.py` — `BuffListing` dataclass | 8 fields: `listing_id`, `goods_id`, `market_hash_name`, `price_cny`, `paintwear`, `asset_id`, `paintseed`, `source`. None reference `classid`/`instanceid`/`appid`/`description`/`name`. | DTO surface is closed; no hidden field. |
| 16 | `BuffItemIdentity` DTO | `app/services/buff_item_identity.py` | Exactly two fields: `market_hash_name`, `goods_id`. | Forward-only contract: `resolve(market_hash_name) -> BuffItemIdentity | None`. No reverse direction. |
| 17 | Concrete `BuffItemIdentityResolver` | `app/services/buff_item_identity.py` + grep | **No concrete implementation exists anywhere.** Only the abstract `Protocol`. | Per `D-IDENTITY-001`, `D-IDENTITY-002`, `D-IDENTITY-003`. `None` is the only real answer. |
| 18 | Phase 12 fixtures carry `market_hash_name` | `tests/fixtures/buff/listings_v1.json`, `listings_v2.json`, `listing_facts_v1.json`, `qualification_*`, `pipeline/mock_buff_orders.json` | All carry `market_hash_name` and sometimes `goods_id`, but every fixture either (a) repeats the same name across all records (no join key), or (b) pairs the same name with the same `goods_id` redundantly (one-to-one with no discrimination power). | Fixtures cannot serve as an identity bridge. |
| 19 | `tests/fixtures/pipeline/mock_buff_orders.json` join | `mock_buff_orders.json` | 10 records all share `goods_id="goods-1"`; `market_hash_name` ranges from `"Input Skin 0"` to `"Input Skin 9"`. | Every distinct hash name maps to the same id. Cannot serve as a bridge. |
| 20 | `listings_v2.json` join | `listings_v2.json` | 2 records both share `listing_id="listing-001"`, `goods_id="synthetic-goods-001"`, and `market_hash_name="AK-47 | Redline (Field-Tested)"`. | Encodes no `market_hash_name ↔ goods_id` mapping. |
| 21 | BUFF API notes — endpoint inventory | `docs/BUFF_API_NOTES.md` | `GET /api/market/goods/sell_order` is the **only** documented endpoint, marked "empirical only — not official OpenAPI". Sell-orders, goods-info, buy-orders, price-history endpoints all marked TODO. | No second endpoint is even available in our knowledge to query for identity. |
| 22 | BUFF API notes — goods-info endpoint | `docs/BUFF_API_NOTES.md` | "Goods Info Endpoint — TODO: confirm endpoint path; map response to `BuffGoodsInfo`." | A potential identity source is unconfirmed and unprobed. |
| 23 | BUFF API notes — TODO list (numbered) | `docs/BUFF_API_NOTES.md` items 1–9 | Endpoint discovery, authentication, request params, sell-orders endpoint, **goods-info endpoint**, buy-orders endpoint, price-history endpoint, response fields, data-quality semantics — **all TODO**. | The repo has not verified a single alternative endpoint that might carry identity. |
| 24 | Phase 13D-0 goods-identity TODO | `docs/BUFF_API_NOTES.md` | Requires confirmation of: authoritative mapping source, one-to-one vs one-to-many vs time/version dependent, collision/alias/case/wear/StatTrak/Souvenir behavior, update/removal lifecycle, failure/ambiguity semantics, reverse lookup. | All of these remain TODO. None has been verified. |
| 25 | `D-BUFF-002` provider abstraction | `docs/ai-context/DECISION_LOG.md` | "Keep `market_hash_name=None`. Avoid duplicate HTTP/parsing; keep concrete market values out of the core until identity/currency/quantity are verified." | Decision is explicit: identity is deferred. |
| 26 | `D-BUFF-003` anonymous-client hardening | `docs/ai-context/DECISION_LOG.md` | "Public client builds the exact request independently, enforces header allowlist, disables per-send auth/redirect, strips only external goods-ID padding, raises context-free fixed errors." | The client cannot be relaxed to accept a wider header set without re-opening `D-AUTH-001`. |
| 27 | `D-AUTH-001` anonymous contract | `docs/ai-context/DECISION_LOG.md` | No `Cookie`, no `Authorization`, no `Proxy-Authorization`, no API key, no session, no `Device-Id`, no CSRF, no `Referer`, no `Origin`, no `X-Requested-With`, no browser/session/auth header set. `auth=None` and `follow_redirects=False` per send. No retries, no pagination, no second page, no fallback endpoint. | Adding a second request (e.g. to a goods-info endpoint) would either violate `D-AUTH-001` or require an explicit, separate authorization phase. |
| 28 | SteamDT and SteamApis identifiers | `app/services/steamdt_market_data.py`, `app/services/steamapis_listing.py` | SteamDT `platformItemId` is opaque; SteamApis `source_offer_id` is `hashlib.sha256(marketplace + game + purchase_link)`. Both documented as not authoritative for BUF goods IDs. | Per `D-STEAMDT-001`, `D-STEAMAPIS-001`. Not usable as BUFF identity. |
| 29 | `buff_listing_parser.py` fixture shape | `app/services/buff_listing_parser.py` | Fixture schema is project-owned (v1/v2). v1 lacks `goods_id`; v2 adds required `goods_id`. Both versions use normalized names — `market_hash_name`, `goods_id`, `listing_id`, `price_cny`, `quantity`, `float_value`, `wear_name`, `paint_seed`, `sticker_metadata`. | This parser reads project fixtures, NOT live BUFF responses. |
| 30 | `BuffTradableCandidate` requirement | `app/services/buff_listing.py` | `BuffTradableCandidate.market_hash_name: str` (required, non-blank trimmed). The candidate contract requires a non-`None` name. | The downstream candidate cannot tolerate `None`. Any bridge must produce a non-empty string. |

## 2. BUFF Response Field Analysis

### 2.1 Endpoint and request shape (verified)

- **Endpoint**: `GET https://buff.163.com/api/market/goods/sell_order`
- **Method**: GET, body empty
- **Required query params (exact, in order)**: `game=csgo`, `goods_id=<caller>`, `page_num=1`, `sort_by=default`
- **Required headers**: `Accept: application/json`, `Host: buff.163.com`, `User-Agent: cs2-tradeup-readonly-schema-smoke/1.0`
- **Body**: empty
- **Auth**: none (`D-AUTH-001`)
- **Redirects**: disabled
- **Retries**: none
- **Pagination**: page 1 only

### 2.2 Response fields the parser actually reads (six total)

| JSON path | Domain field | Source of value |
|---|---|---|
| `code` (must be `"OK"`) | (envelope check) | response |
| `data` (must be `dict`) | (envelope check) | response |
| `data.items` (must be `list`) | iteration target | response |
| `items[].id` | `BuffListing.listing_id` | response |
| `items[].price` | `BuffListing.price_cny` | response |
| `items[].asset_info.paintwear` | `BuffListing.paintwear` | response |
| `items[].asset_info.assetid` | `BuffListing.asset_id` | response |
| `items[].asset_info.paintseed` | `BuffListing.paintseed` | response (optional) |
| (caller-supplied `goods_id` arg) | `BuffListing.goods_id` | caller context |
| (literal constant) | `BuffListing.source = "buff"` | hardcoded |
| (literal constant) | `BuffListing.market_hash_name = None` | hardcoded |

### 2.3 Response fields that are silently ignored (every other key)

Every other key in the top-level envelope, in `data`, in `items[]`, and in `asset_info` is passed over by `.get(...)` calls that target only the six item-level keys above. There is **no parser code path** that reads:

- `items[].market_hash_name`
- `items[].name`, `items[].item_name`, `items[].goods_name`, `items[].localized_name`, `items[].description`
- `items[].classid`, `items[].instanceid`, `items[].appid`, `items[].app_id`
- `items[].original_asset_id`, `items[].asset_description`
- `items[].seller_id`, `items[].user_id`, `items[].user_name`, `items[].steam_id`
- `items[].currency`, `items[].cny`, `items[].price_cny` (response field is `price`; project names it `price_cny`)
- `items[].icon_url`, `items[].original_icon_url`
- `items[].info`, `items[].trans`, `items[].trans_name`, `items[].name_cn`, `items[].name_en`
- `items[].quantity` (the wire-format fixture does carry it; the parser does not)
- `items[].goods_id` (the response does not echo it; caller context is used)

Note: a project-owned **fixture** (`tests/fixtures/buff/anonymous_sell_orders_provider_v1.json`) invents `asset_info.market_hash_name` with the placeholder strings `"Unverified Synthetic Name"` and `"Another Unverified Synthetic Name"`. The smoke harness explicitly **rejects** `market_hash_name` in items, and the parser never reads it. This is a project-owned invention, not verified BUFF evidence.

### 2.4 Live probe scope

The Phase 13B empirical probe (`docs/BUFF_ANONYMOUS_READONLY_NOTES.md`, 2026-08-20) inspected **only the first item** of the response and recorded presence/compatibility for exactly: `id`, `price`, `asset_info.paintwear`, `asset_info.assetid`, `asset_info.paintseed` (absent at that moment). No other field was probed, claimed, or verified. The probe is narrow by design — it is a "do we get a usable payload at all?" check, not an inventory.

## 3. Identity Chain Analysis

### 3.1 Forward direction: `market_hash_name → goods_id`

There is **no path** from the anonymous BUFF response to a `market_hash_name` value. The parser does not read any field that could carry one, and the response carries no Steam identifiers (`classid`/`instanceid`/`appid`) that could cross-reference an independent verified source. The only public abstraction is the abstract `BuffItemIdentityResolver` protocol with no concrete implementation anywhere in the repository.

### 3.2 Reverse direction: `goods_id → market_hash_name`

There is **no path** either, for the same reason: the response carries no `market_hash_name` field, no Steam identifiers, and no `description`/`name`/`localized_name` field. Reverse lookup is also unrecorded in the project; only forward is mentioned in `D-IDENTITY-001` / Phase 13F-0.

### 3.3 Cross-source indirect paths

- **Via SteamDT** (`platformItemId`): per `D-STEAMDT-001`, SteamDT is aggregate-output only; `platformItemId` is opaque; no canonical mapping to BUFF goods IDs exists.
- **Via SteamApis** (`source_offer_id`): per `D-STEAMAPIS-001`, `source_offer_id` is a project-local SHA-256 of `marketplace + game + purchase_link`, explicitly NOT a BUF goods ID.
- **Via Steam economy** (`classid`/`instanceid`/`appid`): **zero** references in the entire repository. No classid-based conversion chain exists.
- **Via good-id-to-name inference** (e.g. deriving from URL, hash, or ID encoding): explicitly forbidden by `D-IDENTITY-001` (no invented/derived mappings).

### 3.4 Conclusion of the chain analysis

No chain from the anonymous BUFF response to a `market_hash_name` value exists, is verifiable, or can be built without either (a) inventing endpoints, (b) modifying the parser, or (c) introducing a project-local mapping file.

## 4. Source Classification

The four candidate identity sources are classified against repository evidence:

| Source | Class | Evidence |
|---|---|---|
| **BUFF anonymous sell-order response** — does it carry `market_hash_name`? | **D — Impossible from current evidence** | Evidence #1–#7, #11, #13–#14, #21. The parser never reads any candidate field; the probe did not verify a wider field set; the smoke rejects `market_hash_name` if seen. |
| **BUFF anonymous sell-order response** — does it carry Steam identifiers (`classid` / `instanceid` / `appid`)? | **D — Impossible from current evidence** | Evidence #10. Zero references repo-wide. No chain possible. |
| **BUF goods-info endpoint** (separate from sell-order) | **C — Possible but unverified** | Evidence #22, #23. Marked TODO in `docs/BUFF_API_NOTES.md`. Endpoint path unknown, response fields unknown, lifecycle unknown. Would also require relaxing `D-AUTH-001` to permit a second request. **NOT ACTIONABLE.** |
| **BUF buy-orders endpoint** | **C — Possible but unverified** | Evidence #23. Marked TODO. **NOT ACTIONABLE.** |
| **BUF price-history endpoint** | **C — Possible but unverified** | Evidence #23. Marked TODO. **NOT ACTIONABLE.** |
| **SteamDT** `platformItemId` as BUF identity | **D — Impossible** | `D-STEAMDT-001`; opaque; no canonical mapping. |
| **SteamApis** `source_offer_id` as BUF identity | **D — Impossible** | `D-STEAMAPIS-001`; project-local SHA-256; explicitly not authoritative. |
| **Manual offline mapping** (project-internal CSV/JSON) | **B (permissible) — not in this phase's scope** | Permissible under `FR-4.1`–`FR-4.5` of `specs/2026-08-22-identity-bridge-architecture-review/requirements.md`. Requires a separate implementation phase, a documented verification procedure, and a first attested entry. Out of scope for this verification phase. |

### Summary

- **A (Direct identity):** **None.**
- **B (Indirect identity):** **None.** No Steam identifiers are exposed; no conversion chain is possible.
- **C (Possible but unverified):** **Goods-info, buy-orders, price-history endpoints.** All marked TODO. All `NOT ACTIONABLE` until independently verified.
- **D (Impossible from current evidence):** **BUFF anonymous sell-order response, SteamDT, SteamApis.**

The BUFF anonymous path cannot, by itself or in combination with any other committed module, provide a verified `market_hash_name ↔ goods_id` bridge.