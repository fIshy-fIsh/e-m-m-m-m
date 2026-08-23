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

## D-VALIDATION-001 — Synthetic scale validation as canonical seam regression check

- **Date:** 2026-08-22 (Phase 13J-1)
- **Decision:** Establish synthetic scale validation (SMALL / MIXED / DIRTY cases) as the regression guard for the candidate → enrichment → trade-up engine boundary. The validation is **not** a replacement for production testing; it only protects architecture boundaries before live wiring exists.
- **Validation surface (offline only):**
  - 13H-0 `candidates_to_input_items` path (legacy, predates intrinsic flags).
  - 13I-3 `enrich_candidates` path (canonical).
  - Existing `calculate_tradeup_results`, `calculate_opportunity_metrics`, `evaluate_opportunity`.
- **Required invariants asserted per case:**
  - Partition agreement: pipeline kept count == enrichment kept count.
  - Accepted item signature equivalence: `(market_hash_name, price_cny, actual_float, stattrak, souvenir)` sorted across both paths.
  - Rejection reason coverage: `MARKET_HASH_NAME_UNRESOLVED` and `METADATA_NOT_FOUND` both surface.
  - Engine compatibility: `calculate_tradeup_results` accepts the enriched `InputItem` list without exception; `_validate_input_items` failures are classified and reported, never swallowed.
  - EV / Risk reproducibility: two reruns of the same basket produce byte-equal `OpportunityMetrics` and `RiskDecision`.
  - Determinism: `random.Random(seed)` produces byte-equal baskets across reruns.
- **Status:** Active.
- **Reason:** the candidate → enrichment → engine chain is the only architectural seam with no live wiring. The synthetic validation is the only available regression mechanism until a verified identity source enables production candidate flow.
- **Future revisit:** only to extend the validation surface when the canonical seam gains new fields, never to relax invariants. The validation must continue to pass against any future change touching the seam.

## D-MIGRATION-001 — Intrinsic flag ownership migration requirement

- **Date:** 2026-08-22 (Phase 13J-1)
- **Decision:** Phase 13I-2 moved ownership of `stattrak` / `souvenir` to `TradeUpInputCandidate`. Phase 13H-0 `trade_up_pipeline.py` predates this decision and still hard-codes `stattrak=False, souvenir=False` on the `InputItem` it builds. This is documented technical debt, not a license to copy.
- **Status:** Active.
- **Reason:** the 13H-0 behavior was correct at the time it was written (the candidate had no intrinsic flags yet). Now that 13I-2 has moved the flags onto the candidate, the canonical path must be:
  - `TradeUpInputCandidate` owns `stattrak`, `souvenir`, `market_hash_name`, `price_cny`, `paintwear`, `asset_id`, `source`.
  - `TradeUpInputEnrichment` carries those flags verbatim into `InputItem`.
  - Metadata / catalog layers must not overwrite intrinsic candidate flags.
- **Migration requirement:** before any production / live candidate wiring, the canonical path is the only path. A future production candidate adapter MUST NOT replicate the 13H-0 hard-coded `False`; it MUST route through `TradeUpInputEnrichment` so the candidate-owned flags survive.
- **Future revisit:** when the production candidate adapter is designed, the 13H-0 hard-code is to be retired from any production code path. It remains acceptable only inside the synthetic validation suite that explicitly tests against the historical behavior.

## D-ADAPTER-001 — BuffListing candidate adapter boundary

- **Date:** 2026-08-22 (Phase 13K-1)
- **Decision:** Establish `app/services/buff_listing_candidate_adapter.py` as the dedicated production candidate conversion boundary.
- **Responsibility:** `BuffListing → TradeUpInputCandidate | CandidateAdapterRejection`.
- **Adapter does not own:**
  - Identity resolution.
  - Metadata enrichment.
  - Trade-up calculation.
  - Scanner orchestration.
  - Purchase execution.
- **Dependency direction (frozen):**
  ```
  BuffListingProvider
        ↓
  Adapter
        ↓
  TradeUpInputCandidate
        ↓
  TradeUpInputEnrichment
        ↓
  InputItem
        ↓
  trade-up engine
  ```
- **Status:** Active.
- **Reason:** the candidate seam established by `D-ENRICH-001` had no upstream bridge; the adapter is that bridge. Localizing it in a single module keeps the dependency graph acyclic and makes the seam testable in isolation.
- **Future revisit:** only if a second listing source is added (different adapter) or if the upstream listing DTO is replaced.

## D-ADAPTER-002 — Candidate adapter uses return-rejection pattern

- **Date:** 2026-08-22 (Phase 13K-1)
- **Decision:** Adapter conversion failures return structured rejection objects; they do not raise. Caller partitions kept vs rejected. Closed rejection vocabulary:
  - `MISSING_IDENTITY` (reserved; not currently triggered — see `D-ADAPTER-003`)
  - `MISSING_PRICE`
  - `INVALID_FLOAT`
  - `MISSING_ASSET_ID`
  - `UNSUPPORTED_SOURCE`
- **Status:** Active.
- **Reason:** aligns with the existing `TradeUpInputEnrichment` return-rejection idiom (`D-ENRICH-001`); fragments of `try/except` control flow around listing conversion would obscure the partition boundary and re-introduce the very kind of mixed-concern code the enrichment seam was created to avoid.
- **Future revisit:** only to extend the vocabulary when the upstream listing DTO grows new required fields.

## D-ADAPTER-003 — Adapter does not resolve identity

- **Date:** 2026-08-22 (Phase 13K-1)
- **Decision:** The adapter does not call `BuffItemIdentityResolver`, does not infer `market_hash_name`, does not map `goods_id`, does not use SteamDT identity fields, does not use SteamApis identity assumptions.
- **Current behavior:** when identity is unavailable, the adapter returns `TradeUpInputCandidate(market_hash_name=None)`. Downstream `TradeUpInputEnrichment` surfaces that as `MARKET_HASH_NAME_UNRESOLVED`.
- **Status:** Active.
- **Reason:** identity resolution remains the unresolved primary blocker (`D-IDENTITY-001`, `D-IDENTITY-002`); the adapter must not invent identity derivation. The `MISSING_IDENTITY` rejection code is reserved for a future explicit-refusal mode and is not triggered in 13K-1.
- **Future revisit:** when a verified anonymous/read-only BUFF identity source is independently obtained, the adapter reads the resolved name from the upstream listing DTO; the adapter itself does not own the derivation.

## D-ADAPTER-004 — Adapter must route through enrichment

- **Date:** 2026-08-22 (Phase 13K-1)
- **Decision:** Production path must remain `TradeUpInputCandidate → TradeUpInputEnrichment → InputItem`. The adapter never directly constructs engine inputs.
- **Status:** Active.
- **Reason:** preserves metadata ownership (candidate does not own `collection_name` / `rarity` / `min_float` / `max_float`); preserves intrinsic flag ownership (candidate owns `stattrak` / `souvenir`); preserves the validation seam (`D-ENRICH-001`); preserves the ability to swap the upstream listing source without touching the engine.
- **Future revisit:** forbidden. This is a permanent structural rule.

## D-IDENTITY-003 — Phase 13L-0 source survey confirms no verified identity bridge

- **Date:** 2026-08-22 (Phase 13L-0)
- **Decision:** Repository-only source survey of the four candidate identity sources closes with no verified `market_hash_name ↔ BUFF goods_id` source. The forward `BuffItemIdentityResolver` protocol stays abstract; `market_hash_name=None` is the only real answer; synthetic-only seam work continues.
- **Status:** Active.
- **Source verdicts:**
  - **BUFF native metadata:** not usable. Endpoint unknown, response field mapping unverified, lifecycle / freshness unconfirmed. Phase 13D-2 already closed: "no validated anonymous/read-only goods/metadata endpoint was discovered." No `BuffGoodsInfo` implementation exists; no endpoint was coded or requested.
  - **SteamDT `platformItemId`:** not authoritative. Aggregate-level field; per-aggregate, not per-listing; cannot be traced to a single BUFF `goods_id`. `D-STEAMDT-001` already prohibits using SteamDT as an identity source.
  - **SteamApis `source_offer_id`:** not a BUFF goods ID. Project-local `hashlib.sha256(marketplace + game + purchase_link)`; explicitly documented as non-authoritative. `D-STEAMAPIS-001` records this; live smoke was gated off and never executed.
  - **Manual offline mapping:** permissible only as a future offline verified fallback under the five constraints in `FR-4.1`–`FR-4.5` of `specs/2026-08-22-identity-bridge-architecture-review/requirements.md`. No verified mapping file exists today.
- **`BuffItemIdentityResolver` remains abstract:** no concrete resolver, no mapping data, no fixture, no parser, no loader, no cache, no factory. The forward `resolve(market_hash_name) -> BuffItemIdentity | None` direction is the only verified contract surface; `None` continues to be the normal outcome.
- **`market_hash_name=None` is the only valid unresolved state.** `BuffListing.market_hash_name` stays `None` for the anonymous provider; `TradeUpInputCandidate.market_hash_name` stays `str | None`; `TradeUpInputEnrichment` surfaces the unresolved shape as `MARKET_HASH_NAME_UNRESOLVED`.
- **Reason:** the canonical seam (`D-ENRICH-001`, `D-ADAPTER-004`) is built to operate with `market_hash_name=None` flowing through as a candidate and being rejected downstream as `MARKET_HASH_NAME_UNRESOLVED`. Synthetic scale validation (Phase 13J-1) and the synthetic candidate adapter (Phase 13K-1) operate entirely without identity resolution. The frozen seam continues to work; production wiring remains blocked until a verified source exists.
- **Alternatives considered:** A (BUFF native) — rejected above. B (SteamDT) — rejected above. C (SteamApis) — rejected above. D (manual offline mapping) — permissible only under the five constraints; not implemented in 13L-0.
- **Future revisit:** only when a verified source is obtained (independently verified anonymous/read-only BUFF endpoint, or an attested offline mapping file satisfying `FR-4.1`–`FR-4.5`). Reopening this decision requires explicit new evidence; do not reopen speculatively.

## D-IDENTITY-004 — Anonymous BUFF sell-order response field inventory: no intrinsic flags exposed

- **Date:** 2026-08-22 (Phase 13N-1)
- **Status:** Active (historical record).
- **Decision:** A deep audit of the anonymous BUFF sell-order response confirms the parser reads exactly six item-level fields per listing: `id`, `price`, `asset_info.paintwear`, `asset_info.assetid`, optional `asset_info.paintseed`, and the caller-supplied `goods_id` (request context). The parser deliberately does NOT read any intrinsic-flag field (`stattrak`, `souvenir`, etc.) from the response. `BuffListing.market_hash_name` is structurally hardcoded to `None`.
- **Source verdict:** the anonymous BUFF `GET /api/market/goods/sell_order` endpoint does NOT currently expose authoritative intrinsic flags in its first-page response.
- **Reason:** preserves the rule that the provider never invents fields; structural placeholders (`None`) flow through the seam as `MARKET_HASH_NAME_UNRESOLVED` (or `INTRINSIC_FLAG_UNRESOLVED` once Phase 13O lands).
- **Alternatives considered:** inferring `stattrak`/`souvenir` from `paintseed`, `assetid`, `price`, or any other response field — rejected (would silently invent data).
- **Future revisit:** only if a future audit discovers that the anonymous BUFF endpoint does in fact expose intrinsic flags in a documented field. Phase 13O-1A confirms this is still UNKNOWN.

## D-IDENTITY-005 — BUF goods-info endpoint survey: no verified live source

- **Date:** 2026-08-22 (Phase 13N-2)
- **Status:** Active (historical record).
- **Decision:** A focused audit of the BUF goods-info endpoint survey concluded that no verified anonymous/read-only BUF goods-info endpoint is currently available. `BuffGoodsInfo` remains a placeholder dataclass; `BuffHttpClient.get_goods_info` raises `NotImplementedError`. Endpoint is recorded as TODO `#5` in `docs/BUFF_API_NOTES.md`. No live probe was authorized or executed.
- **Source verdict:** the BUF native metadata endpoint is NOT usable as a verified identity source.
- **Reason:** preserves the policy that the project refuses to log into BUF, scrape cookies, bypass CAPTCHA, or rotate user-agents; the goods-info endpoint was not authorized for live probing.
- **Alternatives considered:** automated or authenticated probing — rejected (violates project policy).
- **Future revisit:** only if a verified lawful BUF goods-info endpoint becomes available through a documented sanctioned developer API.

## D-IDENTITY-006 — Community offline catalog is acceptable as a provisional V1 identity source

- **Date:** 2026-08-22 (Phase 13N-3A; **implementation completed 2026-08-22 in Phase 13N-3B**)
- **Status:** Active. Implementation completed: snapshot committed, runtime resolver implemented, not yet wired into the candidate pipeline.
- **Implementation status (Phase 13N-3B):** `data/identity/buff_identity_v1.json` is the canonical snapshot (SHA-256 `e3aab46d570869e0b6866eac44b26bca7492ea7c2c54669e74b2b4feeec506ac`). `scripts/build_buff_identity_snapshot.py` is the deterministic offline builder (verifies raw source SHA-256 against `a7f370a61dd34f7d206e0372f6806cbcb936e1ba89e33f48bbb89adaa273d72f`). `app/services/buff_community_identity_resolver.py` is the runtime resolver (forward + reverse, O(1), zero network I/O). Resolver exists but is not yet wired into the candidate pipeline.
- **Previous decisions remain historically correct.** `D-IDENTITY-001` through `D-IDENTITY-005` are not modified. They continue to describe what was true at their respective dates. The new evidence supplements them; it does not invalidate them.
- **What this changes:**
  - The abstract `BuffItemIdentityResolver` Protocol is no longer the only public surface for identity.
  - A concrete `BuffItemIdentityResolver` implementation may now be built (Phase 13N-3B).
  - The forward `resolve(market_hash_name) -> identity` direction remains the only Protocol direction. Reverse lookup `goods_id -> market_hash_name` is implemented as an in-memory inverted index on the snapshot, not as a Protocol change.
  - The downstream `TradeUpInputEnrichment` seam continues to operate as designed.
- **What this does NOT change:**
  - `BuffListing.market_hash_name = None` production behavior (until the resolver is wired in a future phase).
  - `BuffGoodsInfo` dataclass shape (it remains a placeholder).
  - `BuffListingCandidateAdapter` rejection vocabulary and adapter behavior.
  - `TradeUpInputEnrichment` rejection vocabulary and seam contract.
  - The frozen canonical path.
  - Any Protected Core module.
  - The `D-AUTH-001` anonymous client contract.
- **Operating model:**
  - The catalog is committed to the project tree as a static data file with a documented provenance header.
  - The CC-BY-4.0 attribution requirement is preserved in the data file's provenance header.
  - Runtime performs zero network I/O.
  - Mapping lookups are exact-string equality on `market_hash_name` (no fuzzy inference, no normalization).
  - Missing entries yield `None`.
- **Reason:**
  - High coverage (99.96% valid records).
  - Zero in-source collisions.
  - 99.997% independent agreement with ModestSerhat on 34,273 overlapping keys (one disagreement on a recent Austin 2025 souvenir charm, plausibly a freshness race).
  - CC-BY-4.0 license is clear and permissive (attribution only).
  - Commit SHA + file SHA-256 enable exact reproduction.
  - Runtime can operate fully offline via version-controlled snapshot.
  - Downstream code does not need to treat the data as official BUF data.
  - Future first-party verification can supersede or audit.
- **Alternatives considered:**
  - A (BLOCKED): all five prior `D-IDENTITY-*` decisions remain accurate as historical records. Pure "stay blocked" would ignore new evidence.
  - B (PROVISIONAL): chosen. Specific catalog named.
  - C (MORE_EVIDENCE_REQUIRED): not needed. The independent verification pair (EricZhu-42 vs ModestSerhat) is already decisive.
- **Why not use ModestSerhat as primary:** license is unclear (no LICENSE file).
- **Why not use TimofeyIvanenko:** derived from EricZhu + ModestSerhat + ByMykel; not independent evidence.
- **Future revisit:**
  - When a verified first-party BUF goods-info endpoint becomes available (see `D-IDENTITY-005`), it may supersede or audit community mappings.
  - When ModestSerhat's license is clarified, it may become a consistency-checker.
  - When EricZhu-42 (or its successor) adds new items, the project should re-pin a new snapshot manually.
  - **Do NOT auto-refresh at runtime.** Refresh is a manual, version-controlled operation.

## D-IDENTITY-007 — Identity binding inserts between BuffListingProvider and BuffListingCandidateAdapter; adapter does not resolve identity

- **Date:** 2026-08-22 (Phase 13N-3C, implementation completed 2026-08-22)
- **Status:** Active. Implementation completed; production wiring into orchestration pending.
- **Decision:**
  - Insert a thin composition layer `IdentityResolvingBuffListingProvider` (module `app/services/buff_identity_listing_provider.py`) **between** `BuffListingProvider` and `BuffListingCandidateAdapter`.
  - The composition layer wraps the raw provider and a `BuffGoodsIdIdentityResolver` (forward direction of the existing `BuffItemIdentityResolver` protocol is unused).
  - The composition layer performs exactly **one** `resolve_goods_id(goods_id)` call per provider fetch (the BUFF sell-order page is already scoped to one caller-provided `goods_id`).
  - The composition layer rebinds `BuffListing.market_hash_name` to the resolved exact name. Every other field (`listing_id`, `goods_id`, `price_cny`, `paintwear`, `asset_id`, `paintseed`, `source`) is preserved verbatim via `dataclasses.replace`.
  - The composition layer fails closed on three closed integrity violations:
    - `resolver_goods_id_mismatch` — resolver returned an identity whose `goods_id` did not equal the requested `goods_id`;
    - `listing_goods_id_mismatch` — provider returned a listing whose `goods_id` did not equal the requested `goods_id`;
    - `market_hash_name_conflict` — provider returned a listing whose existing `market_hash_name` did not equal the resolved exact name.
  - When `resolve_goods_id` returns `None`, the binding layer leaves `BuffListing.market_hash_name` unchanged (typically `None`); the downstream adapter continues to produce `TradeUpInputCandidate(market_hash_name=None)`, which the existing `TradeUpInputEnrichment` rejects as `MARKET_HASH_NAME_UNRESOLVED`. No new rejection vocabulary is introduced at the adapter boundary.
  - `MemoryError` from the resolver propagates verbatim (consistent with `D-MEMORY-001`); no fallback I/O is attempted.
- **What this changes:**
  - The pipeline gains an explicit identity-binding step between provider and adapter. This is the production seam that closes the gap identified in 13N-3B (resolver implemented but not wired).
  - The downstream `BuffListingCandidateAdapter` continues to operate unchanged (it reads `market_hash_name` off the supplied DTO).
  - The frozen contracts of `buff_listing_provider.py`, `buff_anonymous_listing_client.py`, `buff_listing_candidate_adapter.py`, `buff_item_identity.py`, and `buff_community_identity_resolver.py` are all preserved verbatim.
- **What this does NOT change:**
  - `BuffListingCandidateAdapter` rejection vocabulary remains closed (5 codes; see `D-ADAPTER-002`, `D-ADAPTER-003`).
  - `TradeUpInputEnrichment` rejection vocabulary remains closed (2 codes; see `D-ENRICH-001`).
  - The frozen canonical path remains `BuffListing → TradeUpInputCandidate → TradeUpInputEnrichment → InputItem`.
  - The community catalog snapshot remains `D-IDENTITY-006`'s provisional source.
  - No Protected Core module is modified.
  - No live BUFF HTTP, no SteamDT, no SteamApis, no metadata backend, no scheduler, no Redis, no Discord.
- **Reason:**
  - The adapter must not own identity resolution (`D-ADAPTER-003`, `D-IDENTITY-003`).
  - The resolver must be invoked exactly once per fetch to avoid O(N) identity lookups (per phase prompt section 4).
  - The composition seam preserves all frozen contracts and enables the adapter to remain identity-free.
  - The three closed integrity failures defend the seam against silent contract drift between provider, resolver, and adapter.
- **Future revisit:**
  - When the orchestration runtime is built (13M-0 follow-on), this composition layer is the insertion point between the scanner and the candidate adapter.
  - When a first-party BUFF identity source is verified, the resolver bound to the binding layer can be replaced without changing the binding layer's API.
  - When `BuffListing` (or its successor) exposes `stattrak` and `souvenir` (per `D-MIGRATION-002`), the binding layer remains unchanged because it does not own those fields; the adapter will then forward them.

## D-INTRINSIC-001 — Intrinsic flags have three-state representation: `True` / `False` / `None`

- **Date:** 2026-08-23 (Phase 13O)
- **Status:** Active. Implementation completed.
- **Decision:**
  - The candidate DTO `TradeUpInputCandidate.stattrak` and `.souvenir` are widened from `bool = False` to `bool | None = None`. The three states are explicit:
    - `True` = established true by the verified source;
    - `False` = established false by the verified source;
    - `None` = not established by this source (capability unknown / unverified).
  - The new module `app/services/buff_listing_intrinsic_flags.py` defines `BuffListingIntrinsicFlags`, a wrapper around `BuffListing` that adds `stattrak` and `souvenir` and preserves every other field via `dataclasses.replace` + `__getattr__` delegation.
  - `coerce_intrinsic_flag(value, field)` accepts only `True`, `False`, and `None`. Anything else (`int 0/1`, `str "true"/"false"`, `float`, `bool` subclasses, etc.) raises `IntrinsicFlagValidationError`.
  - The adapter reads intrinsic flags via `getattr(listing, "stattrak", None)` / `getattr(listing, "souvenir", None)` and forwards them verbatim into the candidate. The adapter never coerces `None` to `False`. Malformed values trigger a new closed adapter rejection `INTRINSIC_FLAG_INVALID`.
  - The enricher rejects a candidate whose `stattrak` or `souvenir` is `None` with a new closed enrichment rejection `INTRINSIC_FLAG_UNRESOLVED`. The enricher's existing checks (`MARKET_HASH_NAME_UNRESOLVED`, `METADATA_NOT_FOUND`) are preserved.
  - The `IdentityResolvingBuffListingProvider` accepts optional `stattrak` and `souvenir` keyword arguments per fetch. The binding layer forwards them verbatim onto every returned listing via `BuffListingIntrinsicFlags`. The binding layer never infers either value from `goods_id`, `listing_id`, `asset_id`, `paintseed`, `price`, or any other upstream field. The defaults are `None`.
  - **No Protected Core file is modified.** The frozen `BuffListing` DTO is wrapped, not edited. The frozen `InputItem` (`bool` typed) is not modified; the enricher fails closed before reaching it.
- **What this changes:**
  - The legacy `False` default (which silently fabricated certainty) is replaced by `None` (explicit unknown).
  - The candidate layer now correctly distinguishes "established false" from "not established".
  - The adapter gains one new closed rejection code (`INTRINSIC_FLAG_INVALID`) and the enricher gains one new closed rejection code (`INTRINSIC_FLAG_UNRESOLVED`). Both are documented; both reject rather than coerce.
- **What this does NOT change:**
  - The frozen `BuffListing` DTO is not modified.
  - The frozen `InputItem` (`tradeup_engine.py`) is not modified.
  - The frozen `BuffListingProvider` is not modified.
  - Phase-12 BUFF domain (`buff_listing_facts.py`, etc.) is not modified.
  - The identity-binding seam (`D-IDENTITY-007`) is preserved; the binding layer adds the optional flags argument without changing its existing semantics.
- **Reason:**
  - The legacy `stattrak=False, souvenir=False` default was a documented debt item (per `D-MIGRATION-001`, `D-MIGRATION-002`). Phase 13O is the explicit migration that resolves the representation.
  - The current authorized anonymous BUFF sell-order payload does not expose these fields; the source capability is **UNKNOWN**. The only correct representation of "unknown" is `None`, not `False`.
  - Inferring intrinsic flags from `goods_id`, `listing_id`, `asset_id`, `paintseed`, `price`, or any other BUFF response field would silently invent data; this is forbidden by project policy.
- **Future revisit:**
  - When a verified BUFF source supplies these fields (any future phase), the binding layer will accept them via the new keyword arguments and the enricher will accept candidates whose flags are `True`/`False`. No further candidate-side change is required.
  - When `InputItem.stattrak` is later widened to `bool | None` (a downstream change to Protected Core), the enrichment-layer `INTRINSIC_FLAG_UNRESOLVED` rejection may be retired; until then, it is the canonical fail-closed signal.

## D-INTRINSIC-002 — Canonical `market_hash_name` prefix is the authoritative classifier for `stattrak` and `souvenir`

- **Date:** 2026-08-23 (Phase 13O-1; revised 2026-08-23 by Phase 13O-1A)
- **Status:** Active. Implementation completed; Phase 13O-1A corrected counts and terminology.
- **Decision:**
  - The intrinsic-flag classifier uses the canonical Steam community market naming convention, applied as an exact canonical-string prefix test on the resolved `market_hash_name`:
    - `stattrak=True` iff the name starts with the exact canonical string `'StatTrak™ '` (the trademark sign U+2122 followed by a single ASCII space; 10 Unicode codepoints; 12 UTF-8 bytes).
    - `souvenir=True` iff the name starts with the exact canonical string `'Souvenir '` (a single ASCII space; 9 Unicode codepoints; 9 UTF-8 bytes).
    - Otherwise the corresponding flag is `False`.
  - The two prefixes are mutually exclusive: a canonical name cannot start with both. This invariant holds for the entire pinned identity catalog.
  - The classifier is **pure**: no HTTP, no filesystem mutation, no BUFF / SteamDT / SteamApis / Redis / DB / Discord. It depends only on its string input.
  - The classifier rejects malformed input (non-string, empty, whitespace-padded) with a fixed-message `IntrinsicFlagInputError`. It never silently fixes bad input.
  - The classifier never produces `None` for a well-formed canonical name; the three states (`True`, `False`, `None`) are produced only when the input fails validation, when `market_hash_name` is `None` (identity unresolved), or when the caller wraps an unknown-source resolver.
- **Evidence source:**
  - Catalog-derived exact canonical-name classification, corroborated by observed Steam community market naming/category behavior across 34,402 pinned entries. The repository does NOT contain a formal "authoritative Steam schema contract"; the rule rests on observed naming convention rather than a published spec.
  - Empirical validation against the pinned identity catalog `data/identity/buff_identity_v1.json` (SHA-256 `e3aab46d...`, 34,402 accepted entries):
    - 3,377 names start with `'StatTrak™ '` (`stattrak=True`).
    - 2,345 names start with `'Souvenir '` (`souvenir=True`).
    - 28,680 names start with neither prefix (`stattrak=False`, `souvenir=False`).
    - 0 names start with both prefixes simultaneously.
    - 0 empty or whitespace-padded names.
    - All `'StatTrak™ '` canonical-prefix variants are exact; no alternative spellings.
  - Independent totals (Phase 13O-1A verified):
    - `stattrak_true=3377`, `stattrak_false=31025` (= 34402 − 3377).
    - `souvenir_true=2345`, `souvenir_false=32057` (= 34402 − 2345).
    - Joint counts: `(True, True)=0`, `(True, False)=3377`, `(False, True)=2345`, `(False, False)=28680`. The four joint counts partition the catalog.
- **Validation population:**
  - 34,402 accepted catalog entries (100% coverage; no entry remains unclassified).
  - 12-spot-check across weapon / knife / sticker / case / StatTrak / Souvenir categories (Phase 13N-3A evidence; `D-IDENTITY-006`).
- **Contradictions:** 0 (zero contradictions under the canonical-name rule on the pinned catalog).
- **Unknown behavior:** None for a well-formed canonical name. `None` is the explicit value emitted when (a) the input fails validation, (b) `market_hash_name` is `None` (identity unresolved), or (c) the caller wraps an unknown-source resolver.
- **Provenance:** the canonical Steam community market naming convention. The classifier does NOT depend on a live BUFF endpoint, a SteamDT field, or a SteamApis assumption. It depends only on the canonical name itself.
- **Important distinction:** the BUFF `sell_order` payload itself does NOT provide these flags. The flags are derived from the canonical `market_hash_name`. The anonymous sell-order parser (Phase 13N-1; `D-IDENTITY-004`) reads exactly six item-level fields and never reads any intrinsic-flag field.
- **Why this does not relax the Phase 13O three-state contract:** the classifier emits `True` or `False` for every well-formed canonical name; it does not coerce `None` to `False`. The three-state representation is preserved at the candidate boundary; the classifier simply establishes the value where the canonical name itself provides evidence.
- **Why this is "catalog-derived intrinsic classification", not "BUFF-supplied intrinsic flag":** the classifier establishes the value from the canonical name, not from the live BUFF sell-order payload. A future verified BUFF endpoint that supplies these fields directly would be a separate (and stronger) source; this classifier remains the conservative catalog-derived baseline.
- **Future revisit:**
  - When a verified BUFF endpoint supplies `stattrak` / `souvenir` directly in the sell-order payload, the canonical-name classifier may be retired in favor of the verified source.
  - The classifier is robust against new catalog entries; any future pinned snapshot that introduces a non-canonical name (e.g. `statTrak` lowercase) will be classified `False` and may warrant review, but the rule itself does not change.

## D-MIGRATION-002 — Intrinsic flag migration remains a production wiring requirement

- **Date:** 2026-08-22 (Phase 13K-1)
- **Decision:** Phase 13K-1's synthetic adapter currently defaults `stattrak=False, souvenir=False` on `TradeUpInputCandidate` because the current `BuffListing` DTO does not expose intrinsic flags. This is acceptable only for synthetic / offline validation.
- **Production wiring requirement:** before any production provider wiring, `BuffListing` (or a future upstream source) MUST expose `stattrak` and `souvenir`. The production conversion must become:
  ```
  BuffListing
        ↓
  TradeUpInputCandidate(
      stattrak=source_value,
      souvenir=source_value,
      ...
  )
  ```
  The old 13H-0 hard-coded `False` behavior MUST NOT be copied into production code paths.
- **Status:** Active.
- **Reason:** without intrinsic flag preservation on the candidate boundary, downstream `TradeUpInputEnrichment` cannot distinguish StatTrak / Souvenir inputs from normal items, breaking the canonical seam sealed by `D-ENRICH-001` and `D-MIGRATION-001`.
- **Future revisit:** when `BuffListing` (or its successor) grows `stattrak` and `souvenir`, the adapter must read them and forward verbatim. The synthetic defaulting is then retired from any production code path.
