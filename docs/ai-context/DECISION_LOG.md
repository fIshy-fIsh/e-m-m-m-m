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

## D-SCANNER-001 — Phase 13P live read-only one-shot opportunity scanner

- **Date:** 2026-08-23 (Phase 13P)
- **Status:** Implemented (manual one-shot; no scheduler, no daemon).
- **Decision:** Compose the existing anonymous BUFF listing path, offline identity snapshot, catalog-derived intrinsic classifier, pinned local metadata catalog, existing recipe solver, SteamDT valuation, existing EV/ROI metrics, and existing risk filter into one dependency-injected `LiveScannerOrchestrator.run_once(goods_ids)` operation.
- **Pipeline:** `BuffListingProvider → IdentityResolvingBuffListingProvider → IntrinsicFlagResolvingBuffListingProvider → BuffListingCandidateAdapter → TradeUpInputCandidate → TradeUpInputEnrichment → InputItem → recipe_solver.construct_recipe_selections → ValuationService.value_tradeup_results → calculate_opportunity_metrics → evaluate_opportunity → LiveOpportunity`.
- **Opportunity definition:** a recipe becomes a `LiveOpportunity` only when valuation is complete (no missing output prices and no provider errors) and the existing `RiskDecision.passed` is `True`. No Phase-13P-specific ROI/EV thresholds are introduced; thresholds come from the existing `RiskFilterConfig` populated from project settings.
- **Scan-universe policy:** caller supplies an ordered goods-id allowlist; duplicates are removed in first-seen order; more than 10 unique goods IDs fails closed. The orchestrator processes sequentially (configured concurrency = 1). No unbounded `asyncio.gather`.
- **Metadata source:** pinned local snapshot `data/metadata/skin_metadata_v1.json`, derived from `ByMykel/CSGO-API` `public/api/en/skins.json` at commit `8a785962b291d57a023b79408416c6792782712e` (raw SHA-256 `7aeb9582c5f3308be78c78d2fd3681e3c469c67c0aeeeb7a9e54adb5c3be32d7`, MIT; canonical snapshot SHA-256 `55e4d446a5343e1932f24b9069090431f87b0c750d2cb4c091947ec2411dc421`). Runtime lookup is local O(1), exact-string only, no runtime network. Snapshot expands source skins into exact wear-qualified market_hash_name variants and explicit StatTrak™/Souvenir variants where the source marks those variants available. `scripts/build_skin_metadata_snapshot.py` reproduces the snapshot byte-for-byte from `research/metadata/by_mykel_skins.json`.
- **Read-only guard:** one explicit CLI invocation performs one bounded run and exits. No BUFF login, cookies, marketplace writes, purchase execution, browser automation, CAPTCHA/risk-control bypass, proxy/UA rotation, scheduler, cron, background loop, or daemon.
- **Failure isolation:** one goods-id fetch failure is recorded and does not abort the run; `MemoryError` propagates verbatim per `D-MEMORY-001`; metadata/identity/intrinsic/valuation failures fail closed at their existing boundaries.
- **Protected Core:** unchanged. Phase 13P only composes existing public APIs outside Protected Core.
- **Future revisit:** add scheduling/Discord only after the manual one-shot live smoke is reviewed; do not add auto-buy or transaction execution.
- **Manual live smoke (2026-08-23, one read-only run):** goods_id `34279` (`CZ75-Auto | Chalice (Factory New)`, Restricted). Request bounds: BUFF ≤1, valuation ≤2, concurrency=1. Result: 1 goods requested / 1 succeeded / 0 failed; 10 listings; 10 candidates accepted; 10 metadata resolved; 10 InputItems; 1 recipe; 0 opportunities. BUFF acquisition, identity binding, intrinsic classification, pinned metadata lookup, enrichment, and recipe construction all succeeded. Valuation was not live because local `STEAMDT_DRY_RUN=true` and no API key was present; recipe failed closed. No thresholds were weakened.
- **Phase 13P-1 live valuation gate:** the CLI refuses to start any network work unless `STEAMDT_DRY_RUN=false`, `STEAMDT_API_KEY` is present, and `max_valuation_requests_per_run` is an exact integer in `[1, 60]`. The gate was initially blocked, then passed after local configuration was corrected.
- **Phase 13P-3 diagnosis:** root cause of the initial 4/4 `STEAMDT_BUFF_PRICE_LOOKUP_FAILED` results was the CLI-layer injected `httpx.AsyncClient(timeout=10.0)` lacking `base_url`; `SteamDTHttpClient._request_json` sends relative `url=path` when an AsyncClient is injected, so all four failed with `SteamDTTransportError` before HTTP. Minimal non-Protected-Core fix: `build_steamdt_http_client` now creates `httpx.AsyncClient(base_url=settings.steamdt_base_url, timeout=10.0)`. A regression test pins the configured base URL.
- **Post-fix bounded diagnostic:** exactly four sequential `PRICE_SINGLE` lookups, no BUFF request. All returned HTTP 200 and parsed the documented wrapper shape (`success`, `data`, error fields; platform rows with `platform`, `platformItemId`, `sellPrice`, `sellCount`, bidding fields, `updateTime`). Strict BUFF selection succeeded for `M4A1-S | Knight (Factory New)`, `Souvenir M4A1-S | Knight (Factory New)`, and `Souvenir M4A1-S | Knight (Minimal Wear)`. `M4A1-S | Knight (Minimal Wear)` returned one BUFF row but its sell price failed the existing strict policy as `buff_sell_price_non_positive`. No endpoint/auth/rate-limit/retry/valuation/risk policy changed.
- **Valuation request guard:** `LiveScannerOrchestrator` requires an explicit finite run-level cap (1..60); the CLI default is 5. Exact unique recipe output names are counted before lookup. A recipe that would exceed the remaining cap is rejected before any partial valuation (`VALUATION_REQUEST_CAP_EXCEEDED`). Run diagnostics report attempted, succeeded, failed, and blocked valuation counts; cache hits are not reported because the current CLI path does not expose or use the cache abstraction.
- **Currency/unit policy:** BUFF `price_cny` and SteamDT BUFF sell prices are both interpreted as CNY per `D-STEAMDT-002`; no FX conversion occurs. Fee is a Decimal fraction; expected revenue/profit and worst/best-case profit are CNY; ROI is a dimensionless Decimal ratio; probabilities are floats.
- **Price freshness:** SteamDT source records contain `update_time`, but `SteamDTBuffPriceProvider` projects into generic `PriceQuote(raw=None)` and does not expose source/cache timestamps downstream. Phase 13P-1 does not invent a timestamp or freshness claim. The CLI directly wires `SteamDTHttpClient` and does not currently use the existing cache adapter.
- **Phase 13P-5 fully live verification (2026-08-25):** after the current Souvenir correction, one bounded Knight run requested only the two canonical normal Knight outputs; the existing strict Minimal Wear `buff_sell_price_non_positive` result kept that recipe incomplete. A second bounded technical run for goods ID `35458` consumed ten real BUFF `MAC-10 | Urban DDPAT (Well-Worn)` listings, resolved both required SteamDT BUFF sell prices (`PP-Bizon | Carbon Fiber` Factory New and Minimal Wear), completed valuation and `calculate_opportunity_metrics`, and produced a real `RiskDecision.passed=False` with the unchanged policy. This verifies the complete live read-only opportunity path without requiring a risk-passed opportunity. No threshold, formula, provider policy, scheduler, auto-buy, or marketplace-write behavior changed.

## D-TRADEUP-001 — Current standard trade-up outputs are non-Souvenir

- **Date:** 2026-08-24 (Phase 13P-4); game rule effective 2026-05-21.
- **Status:** Active. Supersedes historical project assumptions that Souvenir items cannot participate in Trade Up Contracts, that normal and Souvenir inputs cannot coexist, or that Souvenir inputs imply Souvenir outputs.
- **Official rule change:** Valve's May 21, 2026 Counter-Strike 2 update states that Souvenir quality items may be selected in a Trade Up Contract alongside normal quality items; Souvenir attributes are removed from selected Souvenir inputs; the resulting item is a normal item of one quality higher from a collection represented by the inputs.
- **Input decision:** `TradeUpInputCandidate` remains the owner of exact input `stattrak` / `souvenir` facts. Normal-only, Souvenir-only, and mixed normal/Souvenir input sets are permitted where all other existing rules allow them. Candidate-owned Souvenir facts remain visible in the returned recipe, source provenance, and risk filter.
- **Output decision:** every output candidate for this standard path must be a canonical `SkinMetadata` record with `souvenir=False`. The normal record is selected by exact catalog identity; no `removeprefix("Souvenir ")`, string rewriting, fuzzy lookup, or metadata deletion is allowed.
- **StatTrak decision:** StatTrak is independent and unchanged. Inputs remain homogeneous by StatTrak mode, and output candidates must match that mode while still being non-Souvenir. The Souvenir update is not a blanket intrinsic-attribute stripping rule.
- **Compatibility seam:** `app/services/scanner_recipe_composition.py::construct_scanner_recipe_selections` filters candidate-owned intrinsic facts, buckets by StatTrak, passes a temporary `souvenir=False` input view and normal-output-only catalog projection to unchanged `recipe_solver.construct_recipe_selections`, then proves that Souvenir was the only projected input difference and restores the exact candidate-owned `InputItem` tuple before returning. No projected item can reach valuation, EV/ROI, risk, logging, or serialization.
- **Scanner scope:** `LiveScannerOrchestrator.run_once` accumulates successful enriched inputs across the existing bounded hard-max-10 goods-ID run before construction. This permits separate exact normal/Souvenir goods pages to coexist without expanding the universe or changing sequential acquisition.
- **Observed defect:** the unfiltered pinned Cobblestone metadata produced four Knight output names: normal Factory New, normal Minimal Wear, Souvenir Factory New, and Souvenir Minimal Wear. The current projection admits only `M4A1-S | Knight (Factory New)` and `M4A1-S | Knight (Minimal Wear)`.
- **Canonical metadata:** unchanged. Souvenir variants continue to exist and remain exactly resolvable as inputs; item existence is distinct from trade-up output eligibility.
- **Protected Core:** unchanged. The historical `tradeup_engine.py` validation text `souvenir items cannot be mixed with non-souvenir items` remains only a compatibility constraint inside Protected Core and is superseded as a current game-domain statement at the scanner composition boundary.
- **Unchanged:** SteamDT transport/parsing/selection, including strict `buff_sell_price_non_positive`; valuation mathematics; profitability/risk thresholds; goods universe; scheduler/daemon behavior; all no-write rules.

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

## D-UNIVERSE-001 — Bounded deterministic market universe builder

- **Date:** 2026-08-25 (Phase 13R)
- **Status:** Active. Implemented, tested offline, live multi-goods scan verified.
- **Decision:** Replace the manual goods-id allowlist with a pure offline deterministic planner that joins the pinned BUFF identity catalog and the pinned skin metadata catalog by exact `market_hash_name`, applies the current Trade Up Contract output eligibility rule, and emits a bounded goods-id sequence (hard max `LiveScannerOrchestrator.HARD_MAX_GOODS_IDS = 10`) suitable for the existing `LiveScannerOrchestrator.run_once`.
- **Catalog contract:** exact-string intersection only; no trimming, case folding, prefix stripping, or fuzzy matching. `BuffCommunityIdentityResolver.identities` exposes the accepted identity pairs ordered by `(len(market_hash_name), market_hash_name)`; `PinnedSkinMetadataResolver.skins` continues to expose the canonical metadata list. Both are version-pinned and unchanged.
- **Eligibility:** one input rarity from `RarityOrder.ORDER[:5]` (Covert excluded because `get_next_rarity("Covert") is None`), one homogeneous StatTrak mode (`normal` / `stattrak`), Souvenir `include` / `exclude` policy, optional exact collection allowlist. Inputs whose collection lacks at least one canonical non-Souvenir next-rarity `SkinMetadata` row at the matching StatTrak mode (per `is_current_standard_trade_up_output_eligible`) are rejected with truthful disjoint diagnostics.
- **Ordering:** sort key `(collection_name, stattrak, souvenir, len(market_hash_name), market_hash_name)`; round-robin across collections so cap > 1 yields cross-collection diversity. Deterministic: two runs with identical inputs return byte-equal universes.
- **Hard bound:** `cap ∈ [1, 10]`. Values outside the range fail closed (`universe_over_hard_max`); collision (`exact_collision`) and duplicate `goods_id` selections also fail closed.
- **Run-wide pool:** the existing scanner accumulates all successfully enriched inputs across the bounded goods-id universe before recipe composition (Phase 13P-4). The planner's selection is deterministic; the scanner still processes goods IDs sequentially with per-goods failure isolation.
- **CLI:** `--auto-universe` is mutually exclusive with `--goods-id`. New flags: `--rarity` (choices restricted to the five productive rarities), `--stattrak-mode {normal,stattrak}`, `--souvenir {include,exclude}`, `--collection` (repeatable), `--max-goods-ids` (1..10, default 10), `--universe-preview` (exits before any settings/HTTP client construction). The existing manual `--goods-id` path is preserved byte-identically.
- **Live verification (2026-08-25):** one bounded automatic run with `--auto-universe --rarity Restricted --stattrak-mode normal --souvenir include --max-goods-ids 10 --max-valuation-requests 20` selected 10 round-robin goods IDs across 10 distinct collections, acquired 10/10 BUFF pages, resolved 71 listings, built one recipe (`Dual Berettas | Twin Turbo` × `SG 553 | Integrale` all 5 wear values), attempted 10 SteamDT `PRICE_SINGLE` lookups (10 succeeded, 0 failed, 0 blocked), and produced `RiskDecision.passed=False` under unchanged thresholds. Zero opportunities passed (expected under current market conditions and unchanged policy). No scheduler, no auto-buy, no marketplace writes.
- **Protected Core:** unchanged. The planner lives outside Protected Core and uses only existing public catalog surfaces and the existing `is_current_standard_trade_up_output_eligible` rule.
- **Failure semantics:** `MemoryError` propagates verbatim; all ordinary contract failures collapse to `BoundedMarketUniverseBuilderError(reason=...)` with a closed reason allowlist. Snapshot, valuation, EV/ROI, risk, scheduler, and no-write behavior are unchanged.
- **Future revisit:** only after the live scheduler is wired and a verified BUFF identity source replaces the provisional community catalog may the planner grow new modes (e.g. StatTrak dual-bucket selection, multi-rarity universes, or replacement/replanning on per-goods failure). Replacement/replanning is intentionally out of scope for V1.

## D-UNIVERSE-002 — Structural cohort-depth allocation under fixed budget

- **Date:** 2026-08-25 (Phase 13S)
- **Status:** Active. Implemented, tested offline, one bounded live depth scan verified.
- **Decision:** Separate pure catalog eligibility from explicit bounded allocation. Preserve `UniverseAllocationStrategy.BREADTH` as the default and Phase 13R collection round-robin behavior. Add opt-in `COHORT_DEPTH` with configurable `target_cohort_count` (default 3) under the unchanged hard goods-ID cap of 10.
- **Compatibility versus allocation:** the smallest legal current-rule recipe bucket is `(input rarity, StatTrak)` because collections may mix and normal/Souvenir inputs may coexist. Phase 13S deliberately uses the stricter allocation key `(collection_name, input rarity, StatTrak)` to concentrate requests around collection-specific next-rarity output pools. This is a planning policy, not a new game-compatibility claim. Souvenir remains an exact input fact and is not part of the cohort key.
- **Structural ranking and allocation:** rank eligible cohorts by `(-eligible catalog capacity, collection_name, rarity, stattrak)`, select at most the configured target, then grant slots in repeated ranked rounds while each cohort has capacity. Budget 10 over three sufficiently large cohorts yields `4/3/3`; exhausted capacity is redistributed among the selected target only. No replacement cohort is introduced after target selection.
- **Within-cohort order:** independently sort normal and Souvenir identities by `(len(market_hash_name), market_hash_name)` and interleave normal/Souvenir, starting with normal and draining the remaining side. `SouvenirInclusion.EXCLUDE` produces normal-only capacity.
- **Catalog diagnostics:** expose eligible/selected cohort counts and, per selected cohort, collection, rarity, StatTrak, exact eligible catalog capacity, normal/Souvenir counts, canonical output count, allocated slots, and exact selected identities. Catalog capacity is explicitly not current listing availability, liquidity, float feasibility, price, EV, ROI, risk, or profitability.
- **Purity:** planner input remains pinned catalogs plus explicit spec only. No BUFF listing, SteamDT price, environment variable, live count, EV/ROI, risk score, trend, randomness, or network dependency is admitted.
- **CLI:** `--allocation {breadth,cohort-depth}` and `--target-cohorts` are auto-universe-only. Explicit use in manual mode fails closed. Target count with BREADTH fails rather than being silently ignored. Preview remains before settings/client construction and now prints structural allocation diagnostics.
- **Controlled integration evidence:** synthetic fake availability under the same 10-goods budget demonstrates BREADTH yielding 3 InputItems/0 selections versus COHORT_DEPTH yielding 10 InputItems/1 selection. Protected Core emits at most one greedy selection per StatTrak bucket, so this is structural constructibility evidence, not a claim of multiple recipes or live liquidity.
- **Live verification:** `Restricted`, normal StatTrak, Souvenir included, cap 10, target 3 selected The 2018 Nuke Collection (4), The Anubis Collection (3), and The Overpass 2024 Collection (3). All 10 BUFF pages succeeded; 94 listings became 94 InputItems; one recipe was constructed and fully valued; all 10 SteamDT requests succeeded; unchanged risk policy rejected it; zero opportunities passed. Phase 13R had one recipe under the same goods-ID budget, so recipe delta was 0 despite deeper structural allocation.
- **Protected Core and safety:** scanner orchestrator, composition seam, metadata resolver, solver, engine, valuation, EV/risk, providers/clients, thresholds, request caps, concurrency, and no-write/no-scheduler behavior are unchanged. No purchase, order, trade, login, cookie, browser, or evasion capability exists.
- **Future revisit:** any tuning of target cohort count, rarity, intrinsic policy, or ranking requires a later reviewed phase. Do not tune from this single live observation.

## D-ENUM-001 — Bounded additive multi-recipe enumeration in Protected Core

- **Date:** 2026-08-26 (Phase 13T-1; design freeze Phase 13T)
- **Status:** Active. Implemented in `app/services/recipe_solver.py` at commit `4a6b85c`. Offline validated (Phase 13T-4A) at commit `9288794`; live observed (Phase 13T-4B).
- **Decision:** Add an additive bounded enumeration API in Protected Core while preserving the legacy zero-or-one API verbatim:
  - `RecipeEnumerationConfig(max_recipe_candidates_returned: int, max_candidate_states_explored: int)` with strict `__post_init__` validation: exact `int` (no `bool`) in `[1, 6]` candidates, `[1, 1024]` states, `states >= candidates`. Defaults `2 / 256`.
  - `RecipeEnumerationDiagnostics` with the exact fields: `eligible_input_count`, `retained_input_count`, `theoretical_radius_one_states`, `states_explored`, `raw_candidates_found`, `unique_candidates_returned`, `duplicates_suppressed`, `engine_rejected_states`, `baseline_state_rejected`, `candidate_limit_reached`, `exploration_limit_reached`.
  - `RecipeEnumerationResult(selections, diagnostics)`.
  - `enumerate_recipe_selections(candidates, skins, solver_config, *, enumeration_config)`.
  - Legacy `construct_recipe_selections`, `construct_recipes`, `solve_recipes` remain unchanged. For eligible unique-offer inputs, `enumerate_recipe_selections` with `max_recipe_candidates_returned=1, max_candidate_states_explored=1` is value-equivalent to the legacy single-selection result. The legacy path deliberately bypasses the stronger new-API duplicate-offer preflight.
- **Canonical offer identity:** `(source, goods_id, listing_id)`. A duplicate canonical key in the new enumerator input fails closed with exact `ValueError("duplicate recipe offer identity")` before sort/cap/search. Same textual `listing_id` with different source/goods ID is not a duplicate unless the full tuple matches.
- **Search policy:** baseline state `P0..P9` first; then radius-one substitutions `P[d] -> P[r]` for `d ∈ [0,9]`, `r ≥ 10`, ordered by `(r-d, r, d, RecipeSelectionKey)`. No radius-two. No exhaustive combinations. No beam search. No financial ranking. `calculate_tradeup_results` is reused verbatim; no engine-side math changes.
- **Selection output order:** baseline candidate (if valid) precedes successful radius-one alternatives; rejected states occupy state budget but no candidate slot. Successful alternatives retain their structural state order.
- **Phase 13T-4A evidence:** offline real-path validation. 100 retained inputs / 901 theoretical states / 2 returned / 2 explored; primary fixture baseline `P0..P9` and first alternative `P0..P8 + P10`; 10 input offers each, 9 shared, 1 replacement; no duplicate exact offer; engine math unchanged.
- **Protected Core status:** migration was authorized under explicit Phase 13T review. Public API gained; legacy contract preserved; existing `construct_*` paths retain exact observable behavior.
- **Future revisit:** if a future phase ever widens Protected Core search semantics (radius-two, beam, financial ranking), it must be a separately reviewed migration; the additive API must remain.

## D-ENUM-002 — Deterministic aggregate candidate/state allocation across normal/StatTrak scanner buckets

- **Date:** 2026-08-26 (Phase 13T-2)
- **Status:** Active. Implemented in `app/services/scanner_recipe_composition.py` at commit `74332e7`.
- **Decision:** Scanner composition owns aggregate candidate and state budgets across active normal/StatTrak buckets. Bucket order is `normal → StatTrak`. With active buckets `B`, aggregate candidate budget `C`, and aggregate state budget `S`:
  - `P = min(B, C)` participating buckets. Only the first `P` receive quota; later active buckets receive `0 / 0` and no enumeration call.
  - Per participating bucket `i`:
    - `candidate_quota[i] = C // P + (1 if i < C % P else 0)`
    - `state_quota[i] = 1 + (S - P) // P + (1 if i < (S - P) % P else 0)`
  - The `1 +` reserves one baseline state per participant. Quota sums are exactly `C` and `S`. Global configuration invariant `S >= C >= P` ensures every participating bucket satisfies `state_quota >= candidate_quota`.
  - No redistribution. No second pass. No quota stealing. Actual usage may be lower when a bucket exhausts its bounded neighborhood or reaches its candidate quota early.
- **Bucket participation precondition:** a bucket participates only when at least `solver_config.input_count` filtered eligible inputs and a nonempty current-rule projection exist (Phase 13T-2 preserves the existing active-bucket rule).
- **Phase 13T-4A evidence:** real two-bucket fixture (normal + StatTrak both active) under aggregate `C=2, S=256` produced `candidate_quota 1/1` and `state_quota 128/128`; each bucket returned 1 successful candidate and explored 1 state; aggregate `returned_candidates == 2, states_explored == 2`.
- **Phase 13T-4B evidence:** live single-bucket depth run observed `active_bucket_count == 1, participating_bucket_count == 1, candidate_quota == 2, state_quota == 256`, returned 2 candidates from 2 explored states.
- **Protected Core:** unchanged. The fair-share split lives entirely in scanner composition.
- **Future revisit:** no future redistribution/second-pass is permitted; if multi-rarity or dual-bucket simultaneous evaluation is desired, it requires a separately reviewed migration.

## D-ENUM-003 — Per-candidate exact InputItem rehydration after temporary Souvenir solver projection

- **Date:** 2026-08-26 (Phase 13T-2; reaffirmed over Phase 13P-4 / `D-TRADEUP-001`)
- **Status:** Active. Implemented in `app/services/scanner_recipe_composition.py`.
- **Decision:** For every returned bounded candidate, the composition layer:
  1. takes the run-wide enriched `TradeUpEnrichedInput` pool;
  2. applies a temporary `souvenir=False` candidate-owned view to the protected solver for each bucket;
  3. after the protected solver returns a `ConstructedRecipeSelection`, verifies the protected `InputItem` tuple against `replace(item, souvenir=False)` for each selected listing ID;
  4. restores the exact candidate-owned `InputItem` values (including original `souvenir` facts) before downstream services see them.
- **Invariants:**
  - Projected `InputItem` values MUST NEVER reach `ValuationService`, `calculate_opportunity_metrics`, `evaluate_opportunity`, `LiveRecipeEvaluation`, `LiveOpportunity`, or any logging/serialization output.
  - Every returned candidate is rehydrated and validated individually; partial rehydration is not permitted.
  - Mixed normal/Souvenir input sets are supported and produce rehydrated candidates that retain original Souvenir facts.
  - Cross-candidate listing reuse remains allowed and is independent of rehydration.
  - The historical `tradeup_engine.py` mixed-Souvenir rejection text is preserved as a Protected Core compatibility constraint inside the temporary view only; it is not a current game-domain statement at the scanner composition seam.
- **Phase 13T-4A evidence:** primary fixture contained 50 Souvenir / 50 normal inputs; baseline candidate had 5 Souvenir inputs, first alternative had 4 Souvenir inputs; every rehydrated `InputItem` matched the original listing facts (market name, price, paintwear, collection, rarity, StatTrak, Souvenir); projected views with `souvenir=False` could not satisfy the rehydration assertion.
- **Phase 13T-4B evidence:** live run observed 4 Souvenir inputs per returned recipe in both candidates; rehydration held; downstream services retained exact Souvenir facts.
- **Future revisit:** none. This is a permanent structural rule for any new candidate path; do not relax without a separately reviewed decision.

## D-ENUM-004 — Atomic cumulative valuation-request cap semantics for multi-recipe orchestration

- **Date:** 2026-08-26 (Phase 13T-3A; reaffirmed over Phase 13P-1)
- **Status:** Active. Implemented in `app/services/scanner_orchestrator.py`. Offline validated (Phase 13T-4A) and live observed (Phase 13T-4B).
- **Decision:** `max_valuation_requests_per_run` is a cumulative orchestrator-owned budget in `[1, 60]` (default CLI value 5). For each returned recipe in structural composition order:
  - Within one recipe, `first-seen unique exact output market_hash_name` is the logical request set (deduped by `ValuationService` itself within one service call).
  - Across recipes, there is **no run-level cache**; the same exact output name in a second recipe is a separate logical request.
  - `required == remaining cap` is allowed; the recipe is valued completely.
  - `required > remaining cap` causes the entire recipe to be blocked before any provider lookup. The blocked `LiveRecipeEvaluation` records the rejection reason `VALUATION_REQUEST_CAP_EXCEEDED`, zero `valuation_prices_resolved`, zero `valued_tradeup_results`, and no metric/risk/opportunity.
  - No partial lookup. No zero-price fallback. No output skipping. No probability renormalization. No fabricated fallback price. Existing strict provider/domain errors are preserved verbatim.
  - `MemoryError` and unexpected system/programmer exceptions are non-swallowed per the existing contracts.
- **Cap-blocked accounting semantics:** the `valuation_requests_blocked` counter records the full logical demand of the blocked recipe (recipe 0's first-seen unique output name count + recipe 1's count + ...). This is observable from `ScannerRunStageCounters.valuation_requests_blocked`.
- **Phase 13T-4A evidence:** exact-cap=20 → 2 fully valued, `valuation_requests_attempted == 20`, `blocked == 0`; one-below-cap=19 → 1 fully valued, `attempted == 10`, `blocked == 10` for the second recipe (the 10 remaining request slots were not consumed and `provider_calls` stopped at the completed-recipe boundary). Two-bucket aggregate run under cap=2 → both recipes fully valued with `attempted == 2`.
- **Phase 13T-4B evidence:** effective cap=5; recipe 0 required 10 unique output names, recipe 1 required 20. Recipe 0 was blocked before any provider lookup (10 blocked); recipe 1 was then blocked before any provider lookup (20 blocked). `attempted == 0`, `blocked == 30`, `provider_calls == 0`, `recipes_fully_valued == 0`. The 5 available slots were not partially consumed by either recipe.
- **Display vs processing:** structural composition order determines valuation order and cap consumption; the existing final opportunity display ordering by `expected_profit_cny desc, roi desc` does not affect enumeration, valuation order, or risk processing order.
- **Protected Core:** orchestrator-side integration; no engine-side math change.
- **Future revisit:** any future run-level cache that changes the within-recipe or across-recipe counting must be a separately reviewed migration; current semantics are fixed.

## D-CACHE-001 — No run-level SteamDT output-price cache

- **Date:** 2026-08-26 (Phase 13T design freeze; reaffirmed in Phase 13T-4A / Phase 13T-4B)
- **Status:** Active as the broader scanner-cache/runtime-composition record. Historical Phase 13T state below remains authoritative for Phase 13T. Phase 14B migrated run-scoped reuse; Phase 14C migrated scanner service/session FRESH_ONLY persistent cache READ; default `run_live_scan_once.py` composition remains **not implemented**.
- **Decision:** Phase 13T intentionally excludes a run-scoped exact-name SteamDT price cache. Today, the same exact output `market_hash_name` in separate recipe valuation calls is a separate logical request that the orchestrator's cumulative budget must cover. Within one recipe, dedup is performed by `ValuationService` inside one `value_tradeup_results` call; that single-recipe dedup does not extend across recipes.
- **Why excluded:** cross-recipe deduplication introduces freshness, failure, and request-budget semantics that are not part of the multi-recipe enumeration contract. Phase 13T must not silently redefine the cumulative budget. `valuation_service.py` and `live_recipe_valuation.py` are Protected Core; any cross-recipe cache would require explicit migration authorization.
- **Operational effect:** under `max_valuation_requests_per_run=5` and a multi-recipe run whose recipes demand `10 + 20` unique output names, both recipes are atomically blocked before any provider lookup (`valuation_requests_blocked == 30`,` `provider_calls == 0`). This is the expected Phase 13T-4B behavior, not a regression.
- **Future revisit:** Phase 14B implemented run-scoped exact-name memo/budget migration; Phase 14C implemented optional scanner service/session FRESH_ONLY reads. `D-CACHE-001` remains Active until Phase 14D composes the resolver/cache runtime into the default one-shot CLI. Scanner write-after-live is not implemented.

## D-PHASE13T-COMPLETE — Phase 13T closed end-to-end

- **Date:** 2026-08-26 (Phase 13T-4B)
- **Status:** Active.
- **Decision:** Phase 13T — the additive bounded multi-recipe solver migration — is complete end-to-end:
  - **Phase 13T Design Freeze** (`010d8cc`): the `specs/2026-08-26-multi-recipe-solver-migration/` trilogy finalized Option B (additive bounded enumerator with strict legacy equivalence, greedy-first + radius-one, default `2/256`, hard bounds `6/1024`, no financial ranking, candidate identity `(source, goods_id, listing_id)`).
  - **Phase 13T-1** (`4a6b85c`): Protected Core bounded enumerator implemented (`D-ENUM-001`).
  - **Phase 13T-2** (`74332e7`): Scanner composition enumeration adapter implemented (`D-ENUM-002`, `D-ENUM-003`).
  - **Phase 13T-3A** (`ac26e9b`): Orchestrator integration implemented (`D-ENUM-004`).
  - **Phase 13T-3B** (`33675ee`): CLI wiring (`--max-recipe-candidates-returned`, `--max-candidate-states-explored`).
  - **Phase 13T-4A** (`9288794`): Offline bounded multi-recipe scale validation committed (`tests/test_multi_recipe_scanner_scale_validation.py`).
  - **Phase 13T-4B** (no commit, no repository artifact; live-only validation performed against `9288794`): One bounded live validation completed as `LIVE_VALIDATION_PASSED_NO_COMPLETE_VALUATION`; effective cap=5 atomically blocked both recipes (10 + 20 = 30 logical demand) before any SteamDT HTTP/provider request; SteamDT live mode configured: YES; SteamDT HTTP/provider requests issued during Phase 13T-4B: 0; all frozen contracts held.
- **Final authoritative state:** `HEAD = 92887947e0e1808f1bc23258cf53adb10a0036ee`; `GitHub remote = 92887947...`; `ahead/behind = 0 0`; `PHASE_13T_COMPLETE`.
- **What is NOT implemented:** run-level SteamDT output-price cache (`D-CACHE-001`); any new development phase.
- **Reason:** every completed phase was committed, pushed, and frozen; subsequent reuse must be a separately reviewed phase.
- **Future revisit:** only when a new explicit development phase is authorized. Do not reopen completed phases without new evidence.

## D-CACHE-002 — Run-scoped exact-name reuse is the only Phase 14 seam

- **Date:** 2026-08-29 (Phase 14A design freeze)
- **Status:** Active. Design frozen at `specs/2026-08-29-scanner-valuation-integration-design-freeze/`. No runtime change in Phase 14A.
- **Decision:** the **only** sanctioned seam for any future Phase 14 implementation that performs run-scoped exact-name reuse is a scanner-owned `RunScopedValuationSession` boundary, living **outside** `app/services/valuation_service.py` and `app/services/live_recipe_valuation.py` (both Protected Core). The boundary does NOT resolve BUFF listing identity, does NOT alter recipe enumeration, and does NOT cache-cross-reference `BuffCommunityIdentityResolver`.
- **Run-scoped memo contract:** within one `LiveScannerOrchestrator.run_once()` call, exact `output_market_hash_name` strings are deduplicated against an in-memory memo; successes and terminal failures are both reused; the memo dies at end of `run_once`; nothing is persisted across runs.
- **Reuse key:** exact byte-canonical `output_market_hash_name` — no fuzzy matching, no case folding, no aliases, no `goods_id` substitution, no `platformItemId` substitution, no hidden normalization layer. The current canonicalization is the existing Steam community market canonical name used throughout the engine path.
- **Supersession of D-CACHE-001:** `D-CACHE-001` remains `Active` (the cache is not implemented at runtime). `D-CACHE-002` only freezes the design that any future implementation must satisfy. `D-CACHE-001` is preserved as the historical Phase 13T rule that prohibited silent introduction of cross-recipe cache behavior; Phase 14A explicitly does not promote it to "superseded". `D-CACHE-001` will be reclassified only after Phase 14B lands and is verified, and only with an explicit amendment entry.
- **Why a new scanner-owned boundary and not a generic ValuationService cache manager:** the trade-up engine, EV service, and risk filter must remain unaware of cache mechanics. A generic global cache manager would entangle them with Phase 12D and would silently redefine the atomic preflight.
- **Phase 14B / 14C implementation note:** run-scoped exact-name reuse is implemented by `D-PHASE14B-COMPLETE`; optional scanner service/session FRESH_ONLY persistent reads are implemented by `D-PHASE14C-COMPLETE`. `D-CACHE-001` remains Active only for default Phase 14D runtime composition.

## D-CACHE-003 — Initial scanner cache policy is FRESH_ONLY

- **Date:** 2026-08-29 (Phase 14A design freeze)
- **Status:** Active. Design frozen. No runtime change in Phase 14A.
- **Decision:** initial Phase 14C scanner integration uses `PriceCacheReadPolicy.FRESH_ONLY` exclusively. `ALLOW_STALE`, `ALLOW_STALE_GRACE`, and any future policy that consumes stale data are NOT enabled in Phase 14B or 14C.
- **Cache hit semantics under FRESH_ONLY:**
  - `FRESH + SELECTED` → usable cache hit; zero live-provider budget consumed; valuation may complete for that name subject to the existing strict BUFF selector rerun.
  - `FRESH + SELECTION_FAILURE` → terminal same-run failure; reused within the run; no immediate live retry; no second-platform fallback; no bid substitution; no metadata-zero reuse. Phase 14A explicitly forbids adding a "live fallback on FRESH + SELECTION_FAILURE" path because the selector is the strict BUFF selector and the cached candidates are already the full provider response.
  - `MISS / EXPIRED / STALE / STALE_GRACE / POLICY_BLOCKED` → live refresh candidate if budget allows; not usable as a quote without a successful live attempt.
- **Cache backend / codec exception contract:** `PriceCacheBackendError`, `PriceCacheCodecError`, `SteamDTPriceCacheAdapterError`, and any future typed backend/codec error are propagated by identity from the session to the orchestrator. They are NOT silently reinterpreted as `MISS`. Doing so would erase the operational signal that a Redis failure or codec corruption is sending.
- **Cache write after live success:** OFF by default in Phase 14C. An opt-in `STEAMDT_PRICE_CACHE_WRITE_AFTER_LIVE` setting may be added in a future separately authorized phase; Phase 14A does not decide this.
- **Selector rerun:** every allowed cache hit reruns the scanner strict-BUFF adapter, whose actual authority is `select_buff_output_price`. The generic `select_steamdt_price_quote` selector is not used as scanner valuation authority.
- **No platform filter at write time:** the cache stores the full ordered list of normalized SteamDT platform candidates per item, in provider response order. BUFF-vs-other selection happens at READ time via the existing strict selector.
- **Why FRESH_ONLY:** Phase 13T deliberately excluded any cross-recipe cache and explicitly required that freshness semantics be defined before any implementation. `FRESH_ONLY` is the most conservative policy that still meaningfully reduces NEW LIVE demand when an item was recently refreshed (e.g. by the existing manual `scripts/steamdt_refresh_integration.py` path).
- **Future revisit:** `ALLOW_STALE` / `ALLOW_STALE_GRACE` policies may be added in a future separately authorized phase; today they are NOT enabled.

## D-BUDGET-001 — Atomic live-demand preflight (max_valuation_requests_per_run)

- **Date:** 2026-08-29 (Phase 14A design freeze; supersedes the structural-demand interpretation in `D-ENUM-004` for the scanner runtime ONLY when Phase 14B lands; `D-ENUM-004` remains Active for any code path that has not yet migrated to the new interpretation)
- **Status:** Active. Design frozen. No runtime change in Phase 14A.
- **Decision:** `max_valuation_requests_per_run` is redefined as the count of **NEW LIVE SteamDT provider demand / attempts** within one `run_once()`, exclusive of run-reuse hits and `FRESH + SELECTED` cache hits.
- **Atomic preflight algorithm (single-threaded inside one `run_once`):**
  1. Derive current recipe unique output names in first-seen order.
  2. Consult the run memo; memoed-success / memoed-failure names consume ZERO live-provider budget.
  3. For still-unresolved names, perform `FRESH_ONLY` cache preflight; `FRESH + SELECTED` consumes ZERO; `FRESH + SELECTION_FAILURE` is memoed as terminal failure and consumes ZERO; `MISS / EXPIRED / STALE / STALE_GRACE / POLICY_BLOCKED` are live-refresh candidates. Backend / codec / adapter / resolver exceptions propagate and are NOT live candidates.
  4. Compute `live_demand = count(live_refresh_candidate_names)`.
  5. **Before any live call**, atomically compare `valuation_live_used + live_demand > max_valuation_requests_per_run`; if exceeded, build a blocked evaluation; `live_atomically_blocked += live_demand`; issue ZERO live SteamDT calls for that recipe.
  6. Else `valuation_live_used += live_demand`; Stage B submits the ordered NEW LIVE exact names to the existing live price provider. Each name is charged as attempted when that provider call begins.
- **At-most-one invariant:** at most one SteamDT live attempt per exact name per run. Phase 14A explicitly forbids adding persistent negative caching unless a future separately authorized Phase 14E does so.
- **No partial valuation:** any incomplete recipe yields `valuation_completed=False`, no metrics, no risk, no opportunity. Never drop outputs, renormalize probabilities, substitute a previous recipe's metrics, zero-fill, or stale-fill.
- **Migration of legacy semantics:** the legacy `valuation_requests_attempted / succeeded / failed / blocked` counters continue to record structural Phase13T demand (recipe unique output name count); the new discriminators `run_reuse_hits`, `cache_hits_fresh_selected`, `cache_misses`, `cache_policy_blocked`, `cache_expired`, `cache_selection_failures`, `live_demand`, `live_attempted`, `live_succeeded`, `live_failed`, `live_atomically_blocked` are added additively. Option A (additive) is preferred; Option B (explicit semantics migration) is the fallback if Option A surfaces ambiguity.
- **Future revisit:** any change to the atomic preflight algorithm or the at-most-one invariant requires an explicit reviewed decision.

## D-CACHE-004 — Failure reuse within a run; no automatic same-name retry

- **Date:** 2026-08-29 (Phase 14A design freeze)
- **Status:** Active. Design frozen. No runtime change in Phase 14A.
- **Decision:** within one `LiveScannerOrchestrator.run_once()` call, the run memo records both successes and terminal failures keyed by exact `output_market_hash_name`. A terminal failure is reused for the rest of the run. There is no automatic same-name retry, no second-platform fallback, no bid substitution, no metadata-zero reuse, and no "best-effort" cache-writeback reinterpretation.
- **Terminal failure categories:**
  - Live lookup / selection failure (transport / API / BUFF selector rejection).
  - Fresh-cache selection failure.
  - Backend / codec exception (propagated by identity; not silently re-classified).
- **Non-terminal categories:**
  - Cache miss / expired / stale / stale-grace / policy-blocked under FRESH_ONLY → live refresh candidate if budget allows.
- **No persistent negative caching** in Phase 14B or 14C; a negative outcome is reused only within the run in which it occurred.
- **Why:** re-running a live SteamDT lookup for the same exact name in the same run after a terminal failure would either re-discover the same failure or silently swallow it; both outcomes violate the existing fail-closed valuation contract.
- **Future revisit:** future backoff / persistent negative caching is separate work, requires an explicit reviewed decision, and is NOT implemented in Phase 14B or 14C.

## D-ACCOUNTING-001 — Additive counter migration preserves legacy semantics

- **Date:** 2026-08-29 (Phase 14A design freeze)
- **Status:** Active. Design frozen. No runtime change in Phase 14A.
- **Decision:** Phase 14B uses Option A: additive discriminator counters while preserving the legacy `ScannerRunStageCounters.valuation_requests_attempted / succeeded / failed / blocked` semantics exactly. Phase 14B implementation and tests confirm no Option B rename is required.
- **New discriminators (additive):** `run_reuse_hits`, `cache_hits_fresh_selected`, `cache_misses`, `cache_policy_blocked`, `cache_expired`, `cache_selection_failures`, `live_demand`, `live_attempted`, `live_succeeded`, `live_failed`, `live_atomically_blocked`.
- **Invariants for completed runs:**
  - `run_reuse_hits == run_reuse_successes + run_reuse_failures`.
  - `live_demand == live_attempted + live_atomically_blocked`.
  - `live_attempted == live_succeeded + live_failed`.
  - No arithmetic equality is defined between legacy `valuation_requests_attempted` and the Phase 14 discriminator counters.
- **Why additive and not a rename:** every pre-existing test that asserts on the legacy counters (notably `tests/test_multi_recipe_scanner_scale_validation.py`) must continue to pass unchanged, except for additive assertions on the new discriminators. A silent rename would force a multi-file migration and risk test/doc drift.
- **Future revisit:** Option A is now implemented and verified by Phase 14B (`D-PHASE14B-COMPLETE`). Any future counter rename would require a new explicit migration; it is not part of Phase 14C.

## D-PHASE14A-COMPLETE — Phase 14A design freeze closed

- **Date:** 2026-08-29 (Phase 14A design freeze)
- **Status:** Active.
- **Decision:** Phase 14A — the scanner valuation integration design freeze — is complete. The freeze covers:
  - `specs/2026-08-29-scanner-valuation-integration-design-freeze/{requirements,plan,validation}.md`;
  - `D-CACHE-002` (run-scoped exact-name reuse is the only Phase 14 seam);
  - `D-CACHE-003` (initial scanner cache policy is `FRESH_ONLY`);
  - `D-BUDGET-001` (atomic live-demand preflight);
  - `D-CACHE-004` (failure reuse within a run; no automatic same-name retry);
  - `D-ACCOUNTING-001` (additive counter migration; Option A preferred);
  - the future 14B / 14C / 14D implementation sequence and the future test matrix A-N.
- **Final authoritative state at Phase 14A closure:** branch `feature/scanner-valuation-integration`; `main` unchanged at P3 = `24c95c029f583d5cc0b0a67986e48c06d0ef7957`; the closure commit is the local HEAD of `feature/scanner-valuation-integration` (verify via `git rev-parse HEAD` at task entry); `ahead/behind = 0 0`; `PHASE_14A_COMPLETE`. CI workflow blob `02d0ce81...` preserved unchanged.
- **What is NOT implemented:** Phase 14B / 14C / 14D; the `RunScopedValuationSession` boundary; Phase 12D cache wiring into the scanner path; `D-CACHE-001` remains `Active` (the runtime cache is still not implemented).
- **Reason:** Phase 14A is a design freeze; no application code is touched. The design is the contract that any future implementation must satisfy.
- **Future revisit:** any future Phase 14 implementation must be explicitly authorized and must not silently relax any frozen contract recorded in this decision log.

## D-PHASE14A-R1-COHERENCE — Phase 14A design coherence correction before 14B

- **Date:** 2026-08-29 (Phase 14A-R1 design coherence correction)
- **Status:** Active. Design frozen. No runtime change in R1.
- **Decision:** Phase 14A-R1 corrects nine internal design contradictions found during post-Phase-14A review. R1 is docs/spec/decision-log only; it does not promote Phase 14A to "implemented" and does not start Phase 14B implementation. The corrections are:
  1. **Strict BUFF cache selection.** `select_steamdt_price_quote` is a generic cross-platform selector and CANNOT be configured strict BUFF-only (`SteamDTPriceSelectionConfig` has no platform field; the default strategy `LIQUIDITY_AWARE_SELL_PRICE` with `fallback_to_lowest_positive=True` will happily return a non-BUFF quote). The strict BUFF behavior lives solely in `select_buff_output_price` (`app/services/steamdt_buff_price_policy.py:73-77`): exact `BUFF` platform, exactly one BUFF record, positive finite sell price, no bid, never another platform, never `fallback_to_lowest_positive`. Phase 14C MUST compose a strict-BUFF cache-selection adapter at the session level; the resolver's default selector is replaced/wrapped for scanner use. `SteamDTCachedPriceResolver` and `select_steamdt_price_quote` are NOT modified by R1 or 14C; the strict-BUFF behavior is composed at the session level via an adapter.
  2. **Two-stage prepare/execute session contract.** The single-method `resolve_output_prices(names)` was under-specified because it implicitly returned `live_demand` while requiring the orchestrator to atomically preflight that demand before any live call. R1 freezes an explicit two-stage contract: STAGE A `prepare_output_prices(names)` (no live SteamDT calls; consults run memo; in 14C, also performs FRESH_ONLY cache reads; classifies names into memo successes / memo terminal failures / `cache_hits_fresh_selected` / `cache_terminal_selection_failures` / `cache_misses_or_refresh_candidates`; backend/codec/contract errors propagate by identity); STAGE B `resolve_prepared(plan)` (only called by the orchestrator after the atomic cap admission succeeds; may issue live SteamDT calls; populates the run memo). If the orchestrator's atomic preflight blocks the recipe, Stage B is NEVER called and ZERO live calls are issued.
  3. **Cache backend / codec / adapter errors are NOT live candidates.** `PriceCacheBackendError(RuntimeError)`, `PriceCacheCodecError(ValueError)`, and `SteamDTPriceCacheAdapterError` propagate by identity from `SteamDTCachedPriceResolver` (zero `try`/`except` in `app/services/steamdt_cached_price_resolver.py`). They are NOT `MISS`, NOT live candidates, NOT memo entries, do not consume live budget, and do not silently reinterpret the cached state. The `SteamDTCachedPriceResolutionStatus` enum has exactly five values — `SELECTED`, `MISS`, `POLICY_BLOCKED`, `EXPIRED`, `SELECTION_FAILURE` — and does not invent `BACKEND_ERROR` or `CODEC_ERROR` values; backend/codec/contract errors propagate as typed exceptions.
  4. **Live provider failure semantics preserved.** `SteamDTBuffPriceProvider.get_prices` catches ordinary `SteamDTBuffPriceSelectionError` and other `Exception` per-name and converts to `PriceLookupResult.missing` + `prices.errors` (with redacted text and `item_index`, no name leakage). `MemoryError` propagates by identity (bare `raise` at `app/services/steamdt_buff_price_provider.py:52-53`). Other `BaseException` subclasses (`asyncio.CancelledError`, `KeyboardInterrupt`, `SystemExit`, `GeneratorExit`) propagate because the catch chain stops at `except Exception`. The Phase 14 session records `PriceLookupResult.quotes[name]` as memo SUCCESS and `PriceLookupResult.missing[name]` (with corresponding `errors` entry) as memo TERMINAL FAILURE; identity-mismatch quotes (`quote.market_hash_name != market_hash_name`) are recorded as missing. R1 explicitly does NOT claim that ordinary transport/API/selection failures propagate by identity from `SteamDTBuffPriceProvider.get_prices`; they do not — they are converted to `PriceLookupResult` outcomes and recorded as memo SUCCESS / TERMINAL FAILURE.
  5. **Counter contract (Option A finalized).** Legacy `valuation_requests_attempted / succeeded / failed / blocked` semantics are preserved exactly. `valuation_requests_attempted` is incremented only for ADMITTED recipes (atomic preflight passed); blocked recipes do NOT increment `attempted`. `valuation_requests_blocked` is incremented by `requested_count` for BLOCKED recipes. New additive discriminators: `run_reuse_hits`, `run_reuse_successes`, `run_reuse_failures`, `cache_hits_fresh_selected`, `cache_misses`, `cache_policy_blocked`, `cache_expired`, `cache_selection_failures`, `live_demand`, `live_attempted`, `live_succeeded`, `live_failed`, `live_atomically_blocked`. **Completed-run invariants** (only for runs where `ScannerRunResult` is materialized):
     - `run_reuse_hits == run_reuse_successes + run_reuse_failures`
     - `live_demand == live_attempted + live_atomically_blocked`
     - `live_attempted == live_succeeded + live_failed`
     No arithmetic equality is defined or implied between the legacy `valuation_requests_attempted` counter and any Phase 14 counter. If the run aborts with `MemoryError` / uncatchable `BaseException` / cache-fatal error, no `ScannerRunResult` exists and the completed-run invariants need not describe partial execution.
  6. **14B reuse test corrected.** For Recipe1 `A B C D E F G H I J` and Recipe2 `A B C D E F G H I K` (no persistent cache): distinct names = 11; `live_demand == 11`; `live_attempted == 11`; Recipe2 memo hits = 9 (`A..I`); `run_reuse_hits == 9`, `run_reuse_successes == 9` if all `A..I` succeeded, `run_reuse_failures == 0`. **NOT** `run_reuse_hits == 0`. Failure variant for Recipe1 `X Y` (X succeeds, Y fails live) and Recipe2 `X Y Z`: X reuses as success; Y reuses as terminal failure; Z triggers one new live demand; no second live attempt for Y; Recipe2 incomplete because Y failed; no metrics/risk/opportunity.
  7. **TTL numeric default not frozen.** NO scanner `fresh_ttl` numeric default is frozen in Phase 14A-R1. The 5-minute value at `scripts/steamdt_refresh_integration.py:59` is historical manual-writer precedent only. Phase 14C subsequently adds no read-time TTL config: cache freshness is evaluated from each stored snapshot's writer-owned `PriceCachePolicy`.
  8. **Write-after-live OUT OF initial 14C.** Initial Phase 14C is scanner cache READ integration only. Automatic scanner write-after-live is OFF / OUT OF SCOPE. The existing manual refresh stack (`scripts/steamdt_refresh_integration.py` + `SteamDTPriceRefreshService`) remains the writer. No write-failure runtime test is required for initial 14C. A future separately authorized phase may add scanner writeback and must then define opt-in config, write-failure semantics, write counters, and whether live success survives write failure.
  9. **`D-CACHE-001` remains Active at R1.** R1 itself does not reclassify the decision; subsequent phases must land and be verified before its active scope can narrow.
- **What is unchanged:** the Phase 14A spec trilogy location; canonical main pointer; local-only tag; protected research JSONs. Current runtime status is recorded by the later Phase 14B/14C completion decisions.
- **Reason:** the original Phase 14A prose contained internal contradictions (generic vs strict BUFF selector, single-method vs two-stage contract, MISS reinterpretation, ordinary-failure-vs-typed-error confusion, counter arithmetic ambiguity, ambiguous reuse-test expectations, implicit 5-minute TTL default, ambiguous write-after-live scope). R1 corrects these before Phase 14B implementation begins. R1 is not a status advance.
- **Future revisit:** Phase 14B and Phase 14C were subsequently authorized, implemented, tested, and closed by `D-PHASE14B-COMPLETE` and `D-PHASE14C-COMPLETE`. Phase 14D remains separately authorized future work; the corrected R1 contracts remain binding.

## D-PHASE14B-COMPLETE — Run-scoped exact-name scanner valuation reuse implemented

- **Date:** 2026-08-29 (Phase 14B)
- **Status:** Active. Implementation complete on `feature/scanner-valuation-integration`; checkpoint subject `add run-scoped scanner valuation reuse` (verify exact SHA from Git).
- **Decision:** Phase 14B implements the first Phase 14 production migration without integrating the persistent Phase 12D cache:
  - `app/services/scanner_valuation_session.py` is the scanner-owned boundary. A fresh session is constructed inside every `LiveScannerOrchestrator.run_once()`; nothing persists across runs and no session is stored as reusable orchestrator state.
  - Stage A `prepare_output_prices` is async and memo-only in 14B; it validates exact names, preserves first-seen order, performs zero provider calls, and returns an immutable canonical plan tied to the creating session by opaque token, plan ID, and memo revision.
  - The orchestrator atomically admits `plan.new_live_names` against `max_valuation_requests_per_run`, whose runtime meaning is now NEW LIVE exact-name demand. Exact boundary is allowed. If demand exceeds remaining budget, the whole recipe is blocked, Stage B is never called, zero provider work occurs, and blocked NEW names are not memoized.
  - Stage B `resolve_prepared` requests only NEW exact names. Matching positive finite `PriceQuote`s become memo success. Provider missing, omitted, mismatched, invalid, contradictory, unexpected-extra, malformed, or provider-error outcomes become bounded terminal failures. Raw provider error payloads are not replayed. Ordinary injected-provider exceptions become bounded terminal failures; `MemoryError` and non-`Exception` `BaseException` subclasses propagate verbatim.
  - Later recipes reuse exact-name memo successes and terminal failures with no provider work and no same-name retry. Exact key identity is preserved: no strip-on-store, case folding, aliases, fuzzy matching, `goods_id`, or `platformItemId` substitution. Names with surrounding whitespace fail closed.
  - Full logical lookup is rebuilt deterministically and passed through a session-local fixed `PriceProvider` into the existing `ValuationService`. `_replace_valuation_fields`, probability math, expected-value contribution math, missing-price strategy logic, EV, risk, trade-up formulas, and thresholds are not copied or changed. The scanner completeness gate remains authoritative: any missing/error prevents metrics, risk, and opportunity.
  - `ScannerRunStageCounters` is extended additively. Legacy `valuation_requests_attempted/succeeded/failed/blocked` semantics remain recipe-logical. New `run_reuse_hits/successes/failures`, `live_demand/attempted/succeeded/failed/atomically_blocked`, and 14C `cache_*` placeholder fields are present. All cache counters remain zero in 14B. Completed-run invariants hold: `run_reuse_hits = run_reuse_successes + run_reuse_failures`; `live_demand = live_attempted + live_atomically_blocked`; `live_attempted = live_succeeded + live_failed`.
- **Deep-pool evidence:** existing 100-input / 901-theoretical-state / 2-candidate fixture retains exact bounded recipe order, exact InputItem rehydration, Souvenir provenance, no projected-input escape, deterministic repeatability, metrics/risk behavior, and 20 legacy logical valuation requests. Under Phase 14B the underlying provider receives the 10 shared exact output names once; run-reuse hits = 10. Cap 10 fully values both recipes; cap 9 atomically blocks both before provider work (`attempted=0`, `blocked=20`, `live_demand=20`, `live_atomically_blocked=20`).
- **Failure-reuse evidence:** Recipe1 `X,Y` with X success / Y provider missing and Recipe2 `X,Y,Z` produces provider calls `[(X,Y), (Z)]`; X reuses success, Y reuses terminal failure without retry, Z is the only second-recipe NEW LIVE name; both incomplete recipes have no metrics/risk/opportunity.
- **Validation:** dedicated session suite, orchestrator integration, protected multi-recipe scale, protected synthetic scale, CLI offline tests, valuation compatibility, adversarial review, ruff, mypy, and full pytest pass. Full count: `3382 passed, 23 skipped, 1 warning`.
- **Protected Core / scope:** reviewed modification is limited to `app/services/scanner_orchestrator.py`; new scanner-owned `app/services/scanner_valuation_session.py`; required tests/docs. `valuation_service.py`, `live_recipe_valuation.py`, `steamdt_buff_price_provider.py`, `steamdt_buff_price_policy.py`, `price_provider.py`, `tradeup_engine.py`, `ev_service.py`, `risk_filter.py`, `recipe_solver.py`, `scanner_recipe_composition.py`, and all Phase 12D cache modules are unchanged.
- **D-CACHE-001:** remains Active as the broader runtime-composition record. Run-scoped reuse (14B) and scanner service/session FRESH_ONLY reads (14C) are complete. Default CLI composition remains Phase 14D; scanner write-after-live remains unimplemented.
- **Next:** Phase 14D — default CLI cache composition + scale / bounded-live validation — NOT STARTED / NOT AUTHORIZED.

## D-PHASE14C-COMPLETE — Scanner FRESH_ONLY persistent cache reads implemented

- **Date:** 2026-08-29 (Phase 14C)
- **Status:** Active. Implementation complete on `feature/scanner-valuation-integration`; checkpoint subject `add scanner fresh-only price cache reads` (verify exact SHA from Git).
- **Decision:** Phase 14C layers the existing Phase12D read contract into the Phase14B scanner-owned session without modifying any Phase12D implementation module:
  - `LiveScannerOrchestrator` accepts only an optional scanner-owned `ScannerCachedBuffPriceResolver`, not an arbitrary raw `SteamDTCachedPriceResolver`. The wrapper receives the existing cache-reader boundary and internally fixes `SteamDTCachedPriceResolver(selector=select_scanner_cached_buff_price)`, so generic cross-platform selection cannot enter the public scanner composition path. The orchestrator constructs no cache backend/runtime.
  - Stage A resolves in deterministic exact memo → sequential cache → NEW LIVE order and passes `PriceCacheReadPolicy.FRESH_ONLY` explicitly. Resolver `None` preserves exact Phase14B behavior.
  - `app/services/scanner_cached_buff_price_selector.py` matches the generic resolver selector protocol but delegates actual authority to `select_buff_output_price`: exact `BUFF`, exactly one BUFF row, positive finite sell, no bid, no non-BUFF fallback; selected cached quote source is exactly `steamdt:buff`.
  - FRESH SELECTED becomes memo success only after the session independently confirms `lookup.state == FRESH`; FRESH SELECTION_FAILURE becomes terminal memo failure with its stable strict-BUFF reason code retained across same-run reuse. MISS, EXPIRED, and POLICY_BLOCKED become unmemoized ordered NEW LIVE candidates. Backend/codec/adapter/resolver/selector contract errors propagate and never become live candidates.
  - Cache memo entries are committed during prepare before plan finalization and survive later atomic block. Unresolved blocked misses are not memoized and are read/classified again by later recipes.
  - Stage B remains live-provider-only, performs no cache read/write, and calls no refresh service. Live success is not written to persistent cache; same-run later recipes use run memo; a new session over the same empty cache misses and fetches live again.
  - Cache outcome counters are active and counted per Stage A occurrence. Legacy Option A counters and completed-run run/live invariants remain unchanged. Atomic cap remains NEW LIVE demand after cache classification; exact boundary admitted, over-budget whole recipe blocked before provider work.
  - Snapshot TTL ownership remains with the writer-stored `CachedPriceSnapshot.policy`; no scanner `fresh_ttl` config, env, or `.env.example` change. The manual five-minute policy is historical writer precedent only.
- **Validation:** strict selector, scanner session, orchestrator, protected multi-recipe/synthetic scale, CLI offline path, Phase12D resolver/cache regressions, ruff, mypy, and full pytest pass. Full count: `3413 passed, 23 skipped, 1 warning`.
- **Protected scope:** `valuation_service.py`, strict live BUFF provider/policy, price provider, engine, EV/risk, solver/composition, all Phase12D implementation modules, CLI/config/env, CI, and dependencies are unchanged. Protected scale tests remain green.
- **Runtime boundary:** scanner service/session persistent cache READ support is implemented. Default `scripts/run_live_scan_once.py` resolver/cache composition is not implemented and belongs to Phase 14D. Scanner write-after-live remains not implemented.
- **D-CACHE-001:** remains Active until Phase 14D default runtime composition lands.
- **Next:** Phase 14D — CLI composition + scale / bounded-live validation — NOT STARTED / NOT AUTHORIZED.

## D-CACHE-001 — Supersession of "No run-level SteamDT output-price cache"

- **Date:** 2026-08-30 (Phase 14D)
- **Status:** Superseded for the originally tracked run-level reuse and default CLI composition gap. Writeback/refresh, scheduled refresh, and continuous-scan tasks remain out of scope as deferred future work; the active gap they would have closed never existed inside this decision's authority.
- **Decision:** `D-CACHE-001` originally recorded the historical Phase 13T prohibition against silent cross-recipe cache reuse in the scanner. Subsequent phases separately closed its runtime scope:
  - Phase 14B implemented run-scoped exact-name reuse and NEW LIVE atomic budgeting.
  - Phase 14C implemented optional scanner service/session FRESH_ONLY persistent reads with strict-BUFF selector binding.
  - Phase 14D implements the default one-shot CLI cache runtime/resolver composition with the in-memory default and optional Redis through the existing factory seam.
- **What remains explicitly deferred:** scanner write-after-live, scheduled/background cache refresh, generalized write-policy on the scanner path, refresh-service integration, Redis batching/concurrency, dual session/orchestrator counter ownership redesign, transactional Stage A rollback, blocked-MISS dedup, and broad AST blacklist redesign.
- **Why reclassified now:** with Phase 14B/C/D verified on the canonical `feature/scanner-valuation-integration` branch, the original "no run-level SteamDT output-price cache at runtime" rule no longer holds for the scanner session path. The historical Phase 13T prohibition remains authoritative for code added between then and 14B; future phases that would re-introduce silent cross-run reuse must cite `D-CACHE-002` or newer decisions rather than `D-CACHE-001`.

## D-PHASE14D-COMPLETE — One-shot CLI cache composition + final validation

- **Date:** 2026-08-30 (Phase 14D)
- **Status:** Active. Implementation complete on `feature/scanner-valuation-integration`; checkpoint subject `wire scanner price cache into live CLI` (verify exact SHA from Git).
- **Decision:** Phase 14D closes the final runtime-composition gap for the strict-BUFF FRESH_ONLY scanner cache seam without introducing any new write/scheduler/refresh capability:
  - `scripts/run_live_scan_once.py` now creates an existing `SteamDTPriceCacheRuntime` through `create_steamdt_price_cache_runtime`, enters its async context, and passes `runtime.cache` into a fresh `ScannerCachedBuffPriceResolver` whose value reaches `LiveScannerOrchestrator(cached_price_resolver=...)`. The runtime and HTTP clients are deterministically closed via `AsyncExitStack` plus the existing runtime context. Exactly one `run_once()` is invoked.
  - `app/services/price_cache_factory.py` exposes a narrow `SteamDTPriceCacheSettings` Protocol; `create_steamdt_price_cache_runtime` now accepts that protocol so the CLI does not need to materialize the global `Settings`. All existing behavior (in-memory default, optional Redis validation, zero-I/O construction, ownership, cleanup) is preserved.
  - `LiveScanSettings` adds only the three cache-composition fields already supported by the factory: `steamdt_price_cache_backend`, `steamdt_price_cache_redis_namespace`, `redis_url`. No scanner TTL, no refresh, no scheduler fields. The valuation cap wording now describes the NEW LIVE exact-name demand.
  - Invalid cache configuration fails before any BUFF/SteamDT live client, provider, or orchestrator construction with a stable redacted `LIVE_PRICE_CACHE_BLOCKED_BY_CONFIGURATION` marker; Redis URL and credentials are never printed.
  - `print_human` prints every Phase 14 counter grouped as logical valuation requests, run reuse, persistent cache reads, and NEW LIVE demand/execution. JSON retains the existing `ScannerRunResult` dataclass shape and adds no envelope.
  - The scanner CLI performs no cache write, no `purge_expired`/`delete`/`clear`, no `SteamDTPriceRefreshService`, and no Redis preflight. Default in-memory backend requires no Redis. Live success remains in the run memo only; the persistent cache is not written by the CLI.
- **Validation:** focused CLI tests (default in-memory composition, Redis seam, invalid cache config fails before live work, exactly one scan, no write, deterministic cleanup including `MemoryError`/`CancelledError`/partial HTTP construction, JSON shape preservation, human counter groups), narrowed factory tests (`SteamDTPriceCacheSettings`), Phase 14B/C suites, protected multi-recipe and synthetic scale suites, ruff, mypy, and full pytest pass. Full count: `3428 passed, 23 skipped, 1 warning`.
- **Protected scope:** `valuation_service.py`, `live_recipe_valuation.py`, `steamdt_buff_price_provider.py`, `steamdt_buff_price_policy.py`, `price_provider.py`, `tradeup_engine.py`, `ev_service.py`, `risk_filter.py`, `recipe_solver.py`, `scanner_recipe_composition.py`, every Phase 12D cache module, `.env.example`, `.github/**`, `pyproject.toml`, and the protected scale tests remain unchanged.
- **Runtime boundary:** default one-shot CLI composes the strict-BUFF FRESH_ONLY cache seam. Scanner write-after-live, scheduled background refresh, continuous scanning, and any scanner TTL environment/config setting remain unimplemented.
- **D-CACHE-001:** superseded for the originally tracked run-level cache gap; deferred write/refresh concerns remain separate future-work items.
- **Next:** Valuation Budget Calibration remains NOT STARTED / NOT AUTHORIZED.

## D-PHASE14-MAIN-INTEGRATION-COMPLETE — Phase 14 canonically integrated on `main`

- **Date:** 2026-08-30 (Phase 14-M2)
- **Status:** Active. Phase 14A / 14A-R1 / 14B / 14C / 14D merged to `main` via PR #4 (`Integrate scanner valuation cache and run-level reuse`).
- **Topology:** canonical main P4 = `26c69bae9e482452f56f380277d8b10fefa29d52`, parents `{24c95c029f583d5cc0b0a67986e48c06d0ef7957, 47227b33cd088a0961320254dd6c0de75e3564bb}`, tree `39a82914fa53fd414d141fbb87cbf197c1ff2c19`. The merged Phase 14 tip `47227b33...` is retained in `main` ancestry as a historical implementation checkpoint.
- **CI:** main push run `33320657978` / job `quality` SUCCESS.
- **Branch lifecycle:** `feature/scanner-valuation-integration` safely retired locally and on `origin`; no force push, no reset, no rebase, no prune.
- **Implemented capability:** run-scoped exact-name reuse; NEW LIVE request-budget accounting; FRESH_ONLY Phase 12D scanner cache reads with strict-BUFF cached selection; default one-shot CLI cache composition with in-memory default and optional Redis; no scanner cache writeback; no refresh service; no scheduler/background work; no scanner TTL environment/config.
- **Deferred (separate future work):** scanner write-after-live, scheduled/background refresh, continuous scanning, generalized write-policy on the scanner path, refresh-service integration, Redis batching/concurrency, dual session/orchestrator counter ownership redesign, transactional Stage A rollback, blocked-MISS dedup, broad AST blacklist redesign.
- **Validation:** Phase 14D baseline preserved at `3428 passed, 23 skipped, 1 warning`; CI green on merge push. No live BUFF/SteamDT/Redis request was issued during Phase 14-M2 docs checkpoint.
- **Protected state:** protected research JSONs remain untracked and untouched; local-only tag `v1-dry-run-baseline -> 32ab47c5b66a0f331457e69f1515e5e9bb2a37e1` preserved.
- **Next:** Valuation Budget Calibration Phase 15A was subsequently authorized and completed as offline measurement under `D-VALUATION-BUDGET-MEASUREMENT-001`. Phase 15B policy work remains NOT STARTED / NOT AUTHORIZED.

## D-VALUATION-BUDGET-MEASUREMENT-001 — Calibrate exact-name demand offline before policy

- **Date:** 2026-08-30 (Phase 15A)
- **Status:** Active. Offline measurement complete on `feature/valuation-budget-calibration`; policy unchanged.
- **Decision:** Define the primary calibration metric as `run_unique_output_names`: the number of distinct exact `output_market_hash_name` values across the ordered recipe candidates returned by the current default scanner composition (`2 candidates / 256 states`). With an empty persistent cache and fresh run memo, this is theoretical NEW-LIVE exact-name demand if every required output price must be fetched successfully. Legacy logical `valuation_requests_attempted` is not the primary metric.
- **Method:** use only the normalized repository-pinned identity and metadata snapshots. Produce (1) a structural census of eligible input cohorts and exact next-rarity output pools and (2) deterministic synthetic offer-order replays through the current `COHORT_DEPTH` universe builder, real scanner composition, real recipe solver, and real trade-up output construction. Quantiles use one exact R-7 method: after sorting `x[0..N-1]`, `h=(N-1)p`, interpolate linearly between `x[floor(h)]` and `x[ceil(h)]` using rational arithmetic.
- **Evidence:** `research/valuation_budget_calibration/results.json` (machine-readable full corpus) and `research/valuation_budget_calibration/REPORT.md` (concise human report); harness in `research/valuation_budget_calibration/{corpus,measurement,report}.py`; focused tests in `tests/test_valuation_budget_calibration.py`.
- **Scope boundary:** no production module, valuation/risk/EV/trade-up formula, cache/provider/client, scheduler, CLI, environment, CI, dependency, `max_valuation_requests_per_run` default/hard-max, or atomic NEW-LIVE semantics changes. Reference thresholds `5/10/15/20/30/60` are analysis only.
- **Representativeness:** `PHASE15A_REPRESENTATIVENESS_LIMITATION`. Pinned catalogs establish structural possibilities. Deterministic synthetic prices/floats establish solver-order coverage, not live listing availability, liquidity, or market frequency. A defensible market-frequency distribution requires timestamped representative listing snapshots with a declared sampling frame and exact identity, price, float, StatTrak/Souvenir, rarity, and collection coverage.
- **Next:** Phase 15B reviewed this evidence under `D-VALUATION-BUDGET-POLICY-001`. No numeric production policy change was authorized; representative read-only listing-snapshot calibration is required before reconsideration.

## D-VALUATION-BUDGET-POLICY-001 — No numeric budget change from structural evidence alone

- **Date:** 2026-08-30 (Phase 15B)
- **Status:** Active — no numeric production policy change authorized from Phase 15A alone.
- **Evidence reviewed:** Phase 15A checkpoint `df621d4de162080293553874f7b374a58bc4e6be`; branch CI run `33325598811` / job `quality` SUCCESS; `research/valuation_budget_calibration/results.json`, `REPORT.md`, and `measurement.py`; current default `5`; hard max `60`; atomic NEW-LIVE boundary under `D-BUDGET-001`.
- **Independent verification:** the 192 observation values reproduce the stored R-7 statistics `min=5, P25=20, P50=29.5, P75=45, P90=75, P95=95, max=95`; threshold counts reproduce `5: 5/192`, `10: 25/192`, `15: 47/192`, `20: 61/192`, `30: 108/192`, `60: 162/192`; structural census records = 439; constructible 1–3 cohort maximum = 120; current default cohort-depth-universe maximum = 95.
- **Mandatory interpretation:** Phase 15A is designed structural coverage evidence, not an estimated production-run probability distribution. No threshold count/share may be represented as expected real-run coverage. `PHASE15A_REPRESENTATIVENESS_LIMITATION` remains controlling.
- **Production-default decision:** `NO_PRODUCTION_DEFAULT_CHANGE_PENDING_REPRESENTATIVE_SNAPSHOT`. Default remains `5`. Five is conservative relative to structurally valid designed cases, but Phase 15A does not establish expected production workload or show that five is statistically wrong.
- **Hard-maximum decision:** `HARD_MAX_60_REVIEW_DEFERRED`. Hard max remains `60`. Phase 15A shows structurally valid current-default-universe cases can require up to 95 exact names, so 60 intentionally cannot admit every structural case. That fact does not authorize expanding the external-call safety envelope; any hard-max change requires separate representative evidence, safety review, and explicit authorization.
- **Missing evidence / next gate:** separately authorized, read-only representative listing snapshots with timestamps; declared sampling window/frame; documented goods-id universe selection; exact identity binding; price; float/paintwear; StatTrak/Souvenir mode; rarity; collection; explicit missingness/rejection reasons; and enough observations across time to avoid one-point-in-time bias. Collection must use only confirmed fields/interfaces and must not invent BUFF endpoints, signatures, parameters, or fields.
- **Preserved contracts:** current cohort-depth universe builder; default `2 / 256` enumeration; strict scanner composition; exact NEW-LIVE name semantics and atomic admission; default `5`; hard max `60`; no auto-buy/trade/login/cookie/CAPTCHA/risk bypass/browser purchase; no production/test/script/workflow change.
- **Artifact:** `research/valuation_budget_calibration/POLICY_DECISION.md`.
- **Implementation gate:** no numeric policy implementation is authorized until representative calibration and, for a hard-max change, external-call safety review are separately approved.
- **Next:** Phase 15C-1 froze the representative snapshot protocol under `D-VALUATION-BUDGET-SNAPSHOT-PROTOCOL-001`; Phase 15C-2 remains separately gated.

## D-VALUATION-BUDGET-SNAPSHOT-PROTOCOL-001 — Representative read-only snapshot protocol frozen

- **Date:** 2026-08-30 (Phase 15C-1)
- **Status:** Active design freeze. Collector/replay implementation and live collection are NOT STARTED / NOT AUTHORIZED.
- **Authority:** canonical main `7a73cc026f93bbed9d9c089c96e6565a6c43c68d`, tree `bae6f6db88b52ec08db279cab60a2498bab08a36`; Phase 15A/15B PR #6 merged; main CI run `33350081125` / job `quality` SUCCESS. Phase 15B remains controlling: default `5` and hard max `60` unchanged.
- **Sampling unit:** one observation is one timestamped full pre-valuation capture attempt for one exact current auto-universe planning result in one productive rarity/StatTrak stratum. Every observation rebuilds the ten-goods `COHORT_DEPTH` / target-three / Souvenir-include universe from campaign-pinned identity/metadata catalogs; planning failure or fewer than ten goods is `INVALID_FOR_CALIBRATION`.
- **Population:** deterministic balanced rotation across eight currently productive strata (Consumer/Industrial normal; Mil-Spec/Restricted/Classified normal and StatTrak). The observable population is only page 1/default sort from the current confirmed anonymous compatibility path for the ten planned goods IDs. The balanced aggregate is not production-weighted without future stratum-weight evidence.
- **Time protocol:** proposed 14 consecutive UTC days, eight three-hour slots per day at minute 17, 112 planned attempts, 14 per stratum; `(slot + day) mod 8` rotates strata through time of day; deterministic `[-10,+10]` minute jitter; missed slots recorded, never replaced; no automatic retry/polling. Phase 15D gate requires at least 96 COMPLETE, 10 per stratum, and valid observations across at least 12 UTC dates.
- **Request safety:** future collector, if authorized, is bounded to ten sequential first-page GETs per observation with project-owned minimum two seconds between starts and no automatic retry; campaign ceiling 1,120 requests. This is protocol safety pacing, not an official rate-limit claim.
- **Field provenance:** direct current compatibility facts are item `id` as labelled listing reference, `asset_info.assetid`, positive price, bounded paintwear, optional paintseed, and source. Goods ID/rank/cohort come from request/universe context. Exact name comes from pinned identity binding; StatTrak/Souvenir from canonical-name classification; rarity/collection from pinned metadata; timestamps/statuses from collector/protocol. Provider timestamp, quantity, full depth, pagination completeness, seller count, lifecycle state, and official listing-ID/currency semantics remain unavailable/unresolved.
- **Interface decision:** the existing universe builder, `BuffAnonymousListingHttpClient`, `BuffListingProvider`, identity/intrinsic binding layers, candidate adapter, pinned metadata/enrichment, scanner recipe composition, and Phase 15A measurement boundary are sufficient for the narrow current-scanner frame without invented behavior. `LiveScannerOrchestrator` is architecture reference only because it does not emit immutable pre-valuation snapshots.
- **Interface gap:** `PHASE15C1_LIVE_COLLECTION_INTERFACE_GAP` applies to any full-market, complete-order-book, or pagination-complete claim. Pagination/page size, completeness, official listing/currency semantics, rate limits, and lifecycle fields must be separately confirmed before crossing the narrow frame.
- **Storage:** one minimal immutable normalized schema-v1 JSON per materialized observation plus an append-only JSONL manifest with SHA-256. Actual live snapshots remain outside Git by default. Raw provider payload retention is prohibited by default. No headers/URLs/query strings/cookies/tokens/auth/API keys/seller/account/personal data/raw exception text; future pre-write secret scan fails closed.
- **Validity:** `COMPLETE` requires exact ten-goods plan, ten successfully parsed pages (nonempty or valid empty), and every returned listing consistent with the same planned identity/intrinsic/metadata/candidate contracts. A COMPLETE observation with fewer than ten accepted listings remains valid and replays to zero recipes / `run_unique_output_names=0`; it is not dropped. `PARTIAL` has valid universe but one or more fetch/parse page failures and is excluded from primary metrics. `INVALID_FOR_CALIBRATION` covers planning, binding/catalog drift, schema, provenance, hash, duplicate/conflict, or snapshot-level reconstruction failure. MISSED/PARTIAL/INVALID are always manifested and never silently replaced.
- **Replay and metrics:** collector never calls valuation/SteamDT; offline replay never calls BUFF/SteamDT/Redis. Replay preserves current composition, default `2 / 256`, `run_unique_output_names`, per-recipe names/counts, recipe-2 incremental NEW, overlap/reuse, strata/cohorts, thresholds `5/10/15/20/30/60`, exact R-7 quantiles, and validity/missingness rates. Only COMPLETE observations enter policy-facing distributions.
- **Policy gate:** satisfying valid-count/time/stratum/reproducibility/reporting gates permits Phase 15D review only. Any hard-max increase requires separate external-call safety review and explicit authorization. Failure of any gate returns `INSUFFICIENT_REPRESENTATIVE_SNAPSHOT_EVIDENCE`.
- **Artifacts:** `specs/2026-08-30-representative-listing-snapshot-calibration-design-freeze/{requirements,plan,validation}.md`, `research/valuation_budget_calibration/SNAPSHOT_PROTOCOL.md`, and synthetic-only `snapshot_schema_v1.example.json`.
- **Scope:** design/spec/docs/research protocol/example only; no production/test/script/workflow/config/dependency edit, live request/data, scheduler, valuation, Redis, cache writeback, or budget change.
