# Phase 13N-2 — BUFF Native Goods Identity Source Investigation (Findings)

## 1. Searched Repository Locations

The audit exhaustively searched the following paths (read-only; no production changes):

| Path | Search intent |
|---|---|
| `app/` (all `*.py` files) | Module-level references to BUFF endpoint paths, `goods_id` flows, `market_hash_name` access patterns |
| `app/clients/buff_client.py` | Legacy `BuffClient` Protocol + `BuffHttpClient` skeleton + DTO shapes (`BuffGoodsInfo`, `BuffSellOrder`, `BuffBuyOrder`, `BuffPricePoint`) |
| `app/clients/buff_anonymous_listing_client.py` | Anonymous client implementation and endpoint URL/header/query contract |
| `app/services/buff_listing_provider.py` | Response parsing logic and field access map |
| `app/services/buff_listing*.py` | All BUFF listing surface modules |
| `app/services/buff_item_identity.py` | Identity contract module |
| `tests/test_buff_*.py` | All BUFF-related test modules |
| `tests/test_live_buff_*.py` | All BUFF live-smoke harnesses |
| `tests/fixtures/buff/*.json` | All BUFF fixture files |
| `tests/fixtures/pipeline/mock_buff_orders.json` | Legacy mock pipeline fixture |
| `scripts/run_live_buff_*.py` | All BUFF live-smoke entrypoint scripts |
| `scripts/buff_listing_*.py` | All BUFF integration scripts |
| `docs/BUFF_API_NOTES.md` | Endpoint inventory and TODO list |
| `docs/BUFF_ANONYMOUS_READONLY_NOTES.md` | Empirical probe documentation |
| `docs/BUFF_LISTING_NOTES.md` | Offline fixture contract documentation |
| `docs/SPEC.md` | V1 technical specification |
| `docs/ai-context/DECISION_LOG.md` | All frozen decisions (`D-IDENTITY-*`, `D-BUFF-*`, `D-AUTH-001`) |

## 2. Discovered BUFF Endpoints (Repository Evidence)

### 2.1 Endpoints documented in the repository

| Endpoint | Status | Source |
|---|---|---|
| `GET https://buff.163.com/api/market/goods/sell_order` | **Empirically probed** (2026-08-20); one-request; anonymous; narrow first-item verification. Six fields verified: `id`, `price`, `asset_info.paintwear`, `asset_info.assetid`, `asset_info.paintseed` (absent at probe time). | `app/clients/buff_anonymous_listing_client.py:8-9`; `docs/BUFF_API_NOTES.md:33` |
| `GET /api/market/goods/sell_order` — alternate forms | **Same endpoint**, referenced in legacy `app/clients/buff_client.py` Protocol declaration. All real network calls raise `NotImplementedError(UNCONFIRMED_MAPPING_ERROR)`. | `app/clients/buff_client.py:107-126, 218-244` |
| `GET /api/market/goods` (goods info / detail) | **Not empirically probed.** Endpoint path unconfirmed. Listed as TODO `#5` in `docs/BUFF_API_NOTES.md:62-64`. No live smoke harness exists for it. No header/query contract documented. No response schema documented. No authentication requirement documented. | `docs/BUFF_API_NOTES.md:62-64` |
| Buy orders endpoint | **Not empirically probed.** Endpoint path unconfirmed. TODO `#6`. No live smoke harness exists. No documented URL/method/headers/schema/auth. | `docs/BUFF_API_NOTES.md:66-68` |
| Price history endpoint | **Not empirically probed.** Endpoint path unconfirmed. TODO `#7`. No live smoke harness exists. No documented URL/method/headers/schema/auth. | `docs/BUFF_API_NOTES.md:70-72` |

### 2.2 Specific `goods_id=1115941` question

The audit checked whether `goods_id=1115941` (or any other specific id) appears anywhere in the repository with a verified response payload. **Result: no matches.** No fixture, no test, no smoke script, no log, no doc contains the literal `1115941` paired with any verified response. The id does not appear at all.

### 2.3 Legacy `BuffGoodsInfo` shape (unimplemented)

`app/clients/buff_client.py:53-68` defines a `BuffGoodsInfo` dataclass as a **shape only**:

```python
@dataclass(frozen=True)
class BuffGoodsInfo:
    goods_id: str
    market_hash_name: str
    localized_name: str | None
    sell_num: int | None
    buy_num: int | None
    raw: dict[str, Any]
```

This shape is **never constructed by any real network call**. `BuffHttpClient.get_goods_info()` at line 228 raises `NotImplementedError(UNCONFIRMED_MAPPING_ERROR)` ("BUFF API endpoint mapping is not confirmed. See docs/BUFF_API_NOTES.md."). `MockBuffClient.get_goods_info` returns pre-seeded in-memory values. `DryRunBuffClient.get_goods_info` returns `BuffGoodsInfo(market_hash_name=f"DRY-RUN:{goods_id}", ...)`. There is **no** live path producing a `BuffGoodsInfo` with a real `market_hash_name`.

## 3. Request/Response Evidence

### 3.1 For the only empirically probed endpoint (sell-order)

- **Method**: GET.
- **URL**: `https://buff.163.com/api/market/goods/sell_order`.
- **Required query parameters (exact, in order)**: `game=csgo`, `goods_id=<caller>`, `page_num=1`, `sort_by=default`.
- **Required headers**: `Accept: application/json`, `Host: buff.163.com`, `User-Agent: cs2-tradeup-readonly-schema-smoke/1.0`.
- **Authentication**: none.
- **Cookies**: none.
- **Redirects**: disabled.
- **Body**: empty.
- **Retry**: none.
- **Pagination**: page 1 only.
- **Verified response envelope**: `code == "OK"`, `data` dict, `data.items` list.
- **Verified per-item fields (six total)**: `id`, `price`, `asset_info.{paintwear, assetid, paintseed}`. Caller supplies `goods_id`. Parser hardcodes `market_hash_name=None` and `source="buff"`.
- **Probe scope**: first item only. No wider field inventory.

### 3.2 For the goods-info endpoint

- **Method**: unknown.
- **URL**: unknown. Documented TODO. No live probe.
- **Required parameters**: unknown. No documented query/path/body contract.
- **Required headers**: unknown. No documented header allowlist.
- **Authentication**: unknown. Could require login, cookie, or API key; or could be anonymous. No evidence either way.
- **Response schema**: unknown. The legacy `BuffGoodsInfo` shape is **speculative**; it was never validated against a real response.
- **Probe history**: zero. No smoke script, no test, no fixture carries a verified goods-info response.

### 3.3 Project stance on probing

`docs/BUFF_API_NOTES.md:107-118` explicitly forbids:

> Do not invent endpoint paths. Do not invent authentication or signature logic. Do not invent response fields or field mappings.

And `#5. Goods Info Endpoint` reads:

> - [ ] Confirm endpoint path.
> - [ ] Confirm response fields mapping to `BuffGoodsInfo`.

The checkboxes are unchecked. The audit is research-only and cannot perform a live probe without explicit user authorization (per `D-BUFF-001` and `D-AUTH-001`). No authorization has been granted for a goods-info probe in this phase.

## 4. Identity Mapping Conclusion

The BUFF native goods-info endpoint **cannot be confirmed as an identity source** from the current repository evidence.

- No endpoint URL is documented as verified.
- No response schema is documented as verified.
- The only `BuffGoodsInfo` shape is **unimplemented** and was never validated against a real response.
- No live smoke harness exists for the goods-info endpoint.
- The empirical Phase 13B probe covered only `sell_order` and verified only six fields on the first item.
- The `goods_id=1115941` value (or any specific id) appears nowhere in the repository paired with a verified payload.

Therefore: even if the goods-info endpoint exists and returns `market_hash_name`, the project has **no empirical evidence** of (a) its path, (b) its anonymous accessibility, (c) its response schema, (d) its lifecycle/freshness semantics, (e) its auth requirement. All five would have to be verified before the endpoint could be wired into production.

## 5. Confidence Classification

| Class | Definition | Verdict for the goods-info endpoint |
|---|---|---|
| **A — Direct authoritative identity source** | Endpoint exists, response carries `market_hash_name` reliably, lifecycle/freshness/case/StatTrak/Souvenir semantics understood. | **Not applicable.** No direct authoritative source has been verified. |
| **B — Indirect but verifiable** | Endpoint carries Steam identifiers or other fields that can be cross-referenced against an independent verified source. | **Not applicable.** No Steam identifiers (`classid`/`instanceid`/`appid`) are referenced anywhere in the repo, including this hypothetical endpoint. |
| **C — Possible but unverified** | Endpoint is mentioned in project docs as TODO; shape exists as a dataclass; no live probe has been performed. | **APPLIES.** The goods-info endpoint is listed as TODO `#5`; the `BuffGoodsInfo` shape exists as a placeholder; no live probe has been executed. **NOT ACTIONABLE** for production wiring. |
| **D — Not usable** | Endpoint requires auth/cookie/anti-bot bypass, or carries opaque identifiers without canonical mapping. | **Not applicable at present** because the endpoint has not been probed. Would become applicable if a future probe showed auth is required and cannot be satisfied anonymously. |

### Source classification summary

- **A:** None.
- **B:** None.
- **C:** BUFF goods-info endpoint — listed as TODO, never probed, schema unverified, lifecycle unknown. **NOT ACTIONABLE.**
- **D:** SteamDT `platformItemId` (`D-STEAMDT-001`), SteamApis `source_offer_id` (`D-STEAMAPIS-001`), BUFF anonymous sell-order (`D-IDENTITY-004` / Phase 13N-1).

The BUFF native goods-info endpoint is **C — Possible but unverified**. It cannot be promoted to A or B without explicit, independently verified evidence, which would require a controlled, authorized, anonymous, single-request probe with documented response.

---

## 6. Cross-Reference with Prior Decisions

| Decision | Relationship to Phase 13N-2 |
|---|---|
| `D-IDENTITY-001` (abstract bridge, no implementation) | Reinforced. No concrete resolver exists; the abstract protocol remains the only public surface. |
| `D-IDENTITY-002` (freeze identity; synthetic/offline only) | Reinforced. No alternative source has emerged. |
| `D-IDENTITY-003` (Phase 13L-0 four-source survey) | Reinforced. All four candidate sources remain non-actionable; no new source has emerged. |
| `D-IDENTITY-004` (Phase 13N-1 BUFF anonymous response field inventory) | Reinforced. Anonymous sell-order cannot provide identity; goods-info endpoint is the only remaining native candidate and is also unverified. |
| `D-AUTH-001` (anonymous client contract) | Reinforced. Adding a goods-info call requires explicit relaxation; no relaxation has been authorized. |
| `D-BUFF-001` (anonymous read-only research path) | Reinforced. Empirical probes are permitted only when one-request, anonymous, no auth/cookie, gated by an env flag. |
| `D-BUFF-002` (BUFF listing provider abstraction) | Reinforced. `BuffListing.market_hash_name = None` continues to be the documented production behavior. |
| `D-ADAPTER-003` (adapter does not resolve identity) | Reinforced. No new source has emerged that the adapter could consult. |

## 7. What This Audit Did Not Do

- Did NOT call any BUFF endpoint.
- Did NOT invent an endpoint path.
- Did NOT invent response fields.
- Did NOT modify `BuffGoodsInfo`, `BuffListing`, `BuffItemIdentity`, the adapter, or the enrichment seam.
- Did NOT add tests, fixtures, scripts, or clients.
- Did NOT propose a new resolver implementation.
- Did NOT relax any frozen decision.

The audit is strictly repository-evidence-driven and reaches its conclusion without external network I/O.