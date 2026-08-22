# DECISION_LOG.md

Format per entry: Decision ID, Date, Decision, Status, Reason, Alternatives considered, Why rejected, Future revisit condition.

---

## D-STEAMDT-001 — SteamDT as aggregate/output source only

- **Date:** 2026-08 (Phase 13A)
- **Decision:** Use SteamDT aggregate market data for output valuation, cross-market reference, and ranking. Never as an authoritative input listing source.
- **Status:** Active.
- **Reason:** SteamDT exposes platform aggregate records (sell/bid/count/opaque platformItemId) but no concrete listing, seller, purchase URL, or per-listing float.
- **Alternatives considered:** using SteamDT `platformItemId` as BUFF `goods_id`; using aggregate `sellPrice` as input cost.
- **Why rejected:** identity and per-listing semantics unverified; aggregate price is not executable listing cost.
- **Future revisit:** only if a separately verified SteamDT field is proven to carry authoritative BUFF goods identity and per-listing geometry.

## D-STEAMDT-002 — CNY interpretation for SteamDT sell/bid

- **Date:** 2026-08-14
- **Decision:** Interpret SteamDT `sellPrice`/`biddingPrice` as CNY/RMB for this project; use `_cny` field naming, no conversion.
- **Status:** Active assumption (not an official provider guarantee).
- **Reason:** Provider currency field is unconfirmed; project needed a fixed interpretation to proceed.
- **Alternatives:** neutral currency, USD, dynamic conversion.
- **Why rejected:** no provider signal to choose otherwise; dynamic FX out of scope.
- **Future revisit:** when official currency documentation is obtained.

## D-STEAMDT-003 — Exact "BUFF" sell-only output price policy

- **Date:** 2026-08-15
- **Decision:** Output price = case-sensitive exact `BUFF` record's positive finite `sell_price_cny`; never bidding price; never other platform; never metadata-zero fallback.
- **Status:** Active.
- **Reason:** bids may carry special conditions absent from the aggregate response; only sell is a safe output value.
- **Alternatives:** lowest positive sell across platforms; bid as fallback.
- **Why rejected:** mixed-source/condition risk and non-BUFF ambiguity.
- **Future revisit:** if official semantics document bid conditionality.

## D-STEAMAPIS-001 — SteamApis Buff163 offer stream paused

- **Date:** 2026-08-13
- **Decision:** Built WebSocket client/parser/pool/recipe-construction components but did not verify live; treated as optional listing-level infrastructure, not production input.
- **Status:** Paused/unverified (live smoke was gated off and not executed).
- **Reason:** requires a SteamApis API key + WebSocket subscription; no removal/Deleted event documented; identity is a project SHA-256 of opaque purchase link, explicitly not a BUFF ID.
- **Alternatives:** promote compatibility IDs as authoritative BUFF listing/goods IDs.
- **Why rejected:** no documented stable offer ID, no BUFF goods ID, no removal semantics, no reconnect/resync.
- **Future revisit:** only after live smoke verifies payload compatibility and a BUFF-identity strategy is separately resolved.

## D-BUFF-001 — Anonymous read-only research path

- **Date:** 2026-08-20
- **Decision:** Use a gated, anonymous, read-only, one-request compatibility probe for BUFF sell-order schema; fail closed if anonymous access is unavailable.
- **Status:** Active.
- **Reason:** official BUFF OpenAPI/auth is unconfirmed; the only lawful safe path is a narrow empirical probe with no login/cookie/bypass.
- **Alternatives:** official BUFF developer API; browser automation; scraping; cookie-based session.
- **Why rejected:** endpoint/auth unconfirmed; automation/scraping/cookie/session all violate project policy.
- **Future revisit:** if official read-only documentation or a sanctioned developer endpoint is supplied.

## D-BUFF-002 — BUFF listing provider abstraction

- **Date:** 2026-08-20
- **Decision:** Extract anonymous client + strict all-item parser + `BuffListing` DTO + `BuffListingProvider`; validate the complete page atomically; require asset ID; keep seed optional; keep `market_hash_name=None`.
- **Status:** Active.
- **Reason:** avoid duplicate HTTP/parsing; keep concrete market values out of the core until identity/currency/quantity are verified.
- **Alternatives:** reuse legacy `BuffHttpClient`/`BuffSellOrder`; construct Phase 12 `BuffListingObservation`.
- **Why rejected:** legacy client retries/uses unconfirmed mapping; Phase 12 needs market name + quantity + facts that are not yet verified.
- **Future revisit:** when identity + quantity + classification facts are verified, bridge into the Phase 12 chain.

## D-BUFF-003 — Anonymous client hardening

- **Date:** 2026-08-21
- **Decision:** Public client builds the exact request independently, enforces header allowlist, disables per-send auth/redirect, strips only external goods-ID padding, and raises context-free fixed errors.
- **Status:** Active.
- **Reason:** injected HTTPX defaults (base URL, cookies, auth, redirects, browser headers) could otherwise violate the anonymous one-request contract.
- **Alternatives:** validate only before transport; rely on smoke runtime config.
- **Why rejected:** client-level auth/hooks could mutate a request after validation.
- **Future revisit:** if a stricter shared transport abstraction is justified.

## D-MEMORY-001 — MemoryError propagation contract

- **Date:** 2026-08 (commit `08b919e`)
- **Decision:** `MemoryError` must propagate by identity through the valuation composition layers (`ValuationService`, `SteamDTHttpClient`, `live_recipe_valuation`, `A5` composition).
- **Status:** Active.
- **Reason:** Out-of-memory conditions are infrastructure failures. They must not be converted into normal valuation errors, retried, or swallowed, because doing so would hide a real exhaustion and could corrupt trade-up decisions.
- **Contract:**
  - `ValuationService` re-raises `MemoryError` immediately after it is detected.
  - `SteamDTHttpClient` and `live_recipe_valuation` re-raise `MemoryError` instead of mapping it to a bounded response error.
  - The A5 closed composition lets `MemoryError` propagate verbatim, not as `request_failed`.
  - Other `BaseException` values (cancellation, `KeyboardInterrupt`, `SystemExit`) propagate naturally and do not get reclassified.
- **Future revisit:** only if a separately authorized retry policy proves `MemoryError` is recoverable in a specific layer.

## D-IDENTITY-002 — Freeze identity source work and proceed with synthetic/offline pipeline only

- **Date:** 2026-08-21 (Phase 13G-0)
- **Decision:** Choose option D — freeze identity source work and proceed with a synthetic/offline pipeline only. No native BUFF identity source, no external provider, no hybrid, no resolver backend. The resolver contract remains a forward-only abstraction; `None` continues to be the only real answer.
- **Status:** Active.
- **Reason:** No verified anonymous/read-only native BUFF source exists; SteamDT identity fields are explicitly unverified and violate the anonymous-only stance; SteamApis compatibility IDs are documented as not authoritative for BUFF; a manual verified mapping is acceptable only as a future offline fallback, not as a primary source.
- **Alternatives considered:** A (continue searching for native BUFF identity source), B (accept external identity provider), C (hybrid approach).
- **Why A is not chosen now:** the open `docs/BUFF_API_NOTES.md` TODOs remain unresolved; no empirically verified anonymous/read-only source is available.
- **Why B is rejected:** the project's anonymous-only policy forbids key-driven providers; no in-scope provider is verified.
- **Why C is rejected:** there is no verified primary source to combine with any fallback.
- **Future revisit:** if a separately verified anonymous/read-only BUFF identity source is obtained, Phase 13F-0's reverse direction can be added; a manual verified mapping can be introduced as a future offline fallback only.

## D-IDENTITY-001 — No verified goods_id ↔ market_hash_name mapping (Path B)

- **Date:** 2026-08-21
- **Decision:** Add only `BuffItemIdentity` + `BuffItemIdentityResolver` protocol with `None` as normal unresolved; no mapping data, no concrete resolver, no `BuffListing` change.
- **Status:** Active (uncommitted as of this write).
- **Reason:** no committed live source proves the canonical relationship; fixture pairs are synthetic; legacy goods-info is unimplemented; SteamDT/SteamApis IDs are opaque/non-authoritative.
- **Alternatives:** static catalog; infer from URL/name/IDs; reuse `BuffGoodsInfo` as resolver.
- **Why rejected:** invented/derived mappings; unverified semantics; would blur client/service boundary.
- **Future revisit:** after a separately verified anonymous goods/product endpoint or sanitized response proves both canonical fields together.

## D-FIXTURE-001 — Synthetic fixtures are test-only

- **Date:** ongoing.
- **Decision:** Project-owned fixtures (BUFF Phase 12, provider-shaped anonymous sell-order, pipeline mocks) only exercise offline flow. They never represent real market opportunities or verified provider mappings.
- **Status:** Active.
- **Reason:** prevent accidental promotion of fabricated identity/price pairs into authoritative data.
- **Future revisit:** n/a (principle).

## D-AUTH-001 — BUFF anonymous client security contract

- **Date:** 2026-08-21
- **Decision:** The exported BUFF anonymous client must build and validate its own request independently, enforce an exact header allowlist, and reject any inherited credential, session, browser, or risk-control material before transport.
- **Status:** Permanent unless revisited with explicit evidence.
- **Reason:** The anonymous, read-only, one-request contract is the only authority that allows this code to access BUFF. If a borrowed HTTPX client provides base URL, query, cookies, session, Device-Id, Authorization, client auth, or follow redirects, the anonymous contract is silently violated and the request can no longer be relied on as anonymous or even read-only.
- **Contract:**
  - Independent request construction (no `AsyncClient.build_request`).
  - Fixed BUFF HTTPS host validation; no nondefault port, no URL userinfo.
  - Exact header allowlist: `Host`, `Accept`, `User-Agent` only.
  - No `Cookie`, no `Authorization`, no `Proxy-Authorization`, no API key, no session, no `Device-Id`, no CSRF, no `Referer`, no `Origin`, no `X-Requested-With`, no browser/session/auth header set.
  - `auth=None` and `follow_redirects=False` are explicitly passed per send.
  - No retries, no pagination, no second page, no fallback endpoint.
  - Translated errors expose no payload, no headers, no URL, and have no `__cause__` or `__context__`.
- **Why this prevents accidental credential leakage:** any caller-supplied hostile client defaults cannot merge into the request, and any post-validation mutation attempt (auth application, redirect follow, request hook) is rejected because the contract is closed before `send`.
- **Future revisit:** only with explicit evidence of a new anonymous read-only field family that requires a documented header outside the allowlist.

## D-SMOKE-001 — Every live API path gets a disabled one-request schema smoke first

- **Date:** ongoing.
- **Decision:** Live I/O is gated, disabled by default, single-request, no retry/cookie/auth/browser, redacted output; implementation/validation never auto-runs the smoke.
- **Status:** Active.
- **Reason:** bound blast radius and prove schema before building provider/scanner.
- **Future revisit:** n/a (principle).

## D-ENRICH-001 — TradeUpInputEnrichment as the canonical candidate → InputItem seam

- **Date:** 2026-08-22 (Phase 13I-3, after 13I-0 boundary review and 13I-1 contract audit)
- **Decision:** Establish `app/services/trade_up_input_enrichment.py` as the single seam where `TradeUpInputCandidate + metadata → InputItem`. Enrichment is offline/synthetic only in this phase; no live metadata adapter, no runtime wiring.
- **Field ownership (frozen):**
  - Candidate-owned: `market_hash_name`, `price_cny`, `paintwear`, `asset_id`, `source`, `stattrak`, `souvenir`.
  - Metadata-owned: `collection_name`, `rarity`, `min_float`, `max_float`.
  - `paintwear` (Decimal) → `actual_float` (float) conversion happens exactly once at this boundary.
- **Rejection vocabulary:** `MARKET_HASH_NAME_UNRESOLVED`, `METADATA_NOT_FOUND`. No inference, no default fallback, no synthetic promotion of `market_hash_name`.
- **Status:** Active (uncommitted as of this write).
- **Reason:** Candidate intrinsic flags (`stattrak`, `souvenir`) must never be overridden by catalog-row metadata; catalog fields must never leak into the candidate; the conversion from exact `Decimal` paintwear to float must be single-point to keep the engine deterministic. A dedicated enricher isolates both concerns from `tradeup_engine`, `recipe_solver`, and the live metadata chain.
- **Alternatives considered:** inline enrichment inside `trade_up_pipeline.py`; letting `recipe_solver` read metadata directly; merging enrichment into the candidate boundary.
- **Why rejected:** would couple the synthetic pipeline to live metadata; would force metadata calls into solver-side code; would defeat the 13I-0 ownership rule. The seam must remain a standalone module.
- **Future revisit:** when a verified identity source exists, the seam is the natural place to introduce a real `TradeUpInputMetadataResolver` backend and a real `BuffListing → TradeUpInputCandidate` adapter. Until then, do not add more metadata/enrichment abstraction.

## D-ENRICH-002 — Do not reopen identity / ownership decisions

- **Date:** 2026-08-22 (Phase 13I-3)
- **Decision:** The following are frozen and must not be reopened without explicit new evidence:
  - BUFF `goods_id ↔ market_hash_name` investigation (see `D-IDENTITY-001`, `D-IDENTITY-002`).
  - SteamDT as identity mapping source (see `D-STEAMDT-001`).
  - SteamApis as identity source (see `D-STEAMAPIS-001`).
  - Metadata ownership split (candidate owns intrinsic flags; metadata owns catalog-row fields).
- **Status:** Active.
- **Reason:** the abstract bridge remains unresolved and the candidate/metadata ownership rule is the operative boundary rule. Reopening either would invalidate the seam sealed by `D-ENRICH-001`.
- **Future revisit:** only when a verified anonymous/read-only BUFF identity source is independently obtained, or when a separately authorized ownership review demands a change.
