# DEVELOPMENT_HANDOFF.md

## Current Git State (verify live)

- **Branch:** `feature/steamdt-cache-rate-limit`
- **HEAD:** `a70b0e63661ad7165bd023fa9a35d82b21bf4310`
- **HEAD message:** `add identity and orchestration architecture reviews`
- **Uncommitted work:** none as of this checkpoint; working tree is clean. The 13L-0 and 13M-0 spec trilogies are part of HEAD (`specs/2026-08-22-identity-bridge-architecture-review/`, `specs/2026-08-22-production-scanner-orchestration-review/`).

Recent commit history (oldest → newest, including the latest 18 unpushed local commits on this branch):

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
b398bcc add trade-up input candidate boundary
560f4dd add buff identity contract and ai context
330bdcb add synthetic trade-up pipeline integration
f34f25f add trade-up input enrichment boundary
1549248 add synthetic scanner-scale validation
5d19096 add BuffListing candidate adapter boundary
a70b0e6 add identity and orchestration architecture reviews
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

### Phase 13I-3 — Trade-up input enrichment boundary (implemented, uncommitted)

- Adds `app/services/trade_up_input_enrichment.py` with
  `TradeUpInputMetadata`, `TradeUpInputMetadataResolver`,
  `InMemoryTradeUpInputMetadataResolver`,
  `TradeUpEnrichmentRejectionReason`, `TradeUpEnrichmentRejection`,
  `TradeUpEnrichedInput`, `TradeUpInputEnrichmentResult`,
  `TradeUpInputEnricher`, `InMemoryTradeUpInputEnricher`,
  `enrich_candidates`.
- Defines the explicit boundary
  `TradeUpInputCandidate + metadata → InputItem` with `kept` and
  `rejected` partitions in input order.
- Ownership split per 13I-0 / 13I-1:
  - candidate supplies `market_hash_name`, `price_cny`, `paintwear`,
    `stattrak`, `souvenir`;
  - metadata supplies `collection_name`, `rarity`, `min_float`,
    `max_float`;
  - `paintwear` (Decimal) is converted to `actual_float` (float)
    exactly once at the boundary.
- Rejection vocabulary: `MARKET_HASH_NAME_UNRESOLVED`,
  `METADATA_NOT_FOUND`. No identity inference; no default fallback.
- `TradeUpInputCandidate`, `InputItem`, `tradeup_engine`,
  `recipe_solver`, all metadata layers, `BuffListing`,
  `BuffItemIdentity`, the 13H-0 synthetic `trade_up_pipeline.py`,
  and all live provider / scanner / scheduler / BUFF / SteamDT /
  SteamApis code remain untouched.
- No adapter to a real metadata provider, no runtime wiring,
  no enrichment-layer call site.

### Phase 13I-2 — Trade-up input candidate intrinsic flags (implemented, uncommitted)

- Adds exactly two intrinsic item-instance flags to `TradeUpInputCandidate`:
  `stattrak: bool = False`, `souvenir: bool = False`.
- `_ALLOWED_FIELDS` and the `_validate_exact_bool` helper are extended
  in lockstep with the existing fixed-error contract.
- Default values stay `False`; explicit `True` is preserved; strict bool
  validation rejects int / str / `None` / float.
- Candidate remains the sole owner of these flags; metadata / catalog
  enrichment can never override them (Phase 13I-0 decision).
- No `collection_name` / `rarity` / `min_float` / `max_float` was added
  to the candidate.
- `InputItem`, `tradeup_engine`, `recipe_solver`, all metadata layers,
  `BuffListing`, `BuffItemIdentity`, the synthetic `trade_up_pipeline`,
  and all live provider / scanner / scheduler / BUFF / SteamDT /
  SteamApis code remain untouched.
- No enrichment module, no adapter, no runtime wiring is added.

### Phase 13I-1 — Metadata provider contract audit (uncommitted)

- Design-only review under `specs/2026-08-22-trade-up-metadata-provider-contract-audit/`.
- Conclusion: `SkinMetadata` already covers every catalog field the
  planned enrichment boundary needs; the only outstanding gap is the
  two intrinsic flags added in 13I-2 on the candidate side.

### Phase 13I-0 — Trade-up metadata enrichment boundary review (uncommitted)

- Design-only review under `specs/2026-08-22-trade-up-metadata-enrichment-boundary-review/`.
- Conclusion: keep candidate minimal, candidate owns intrinsic item
  flags (`stattrak`, `souvenir`), metadata / catalog layer owns the
  five catalog fields, future enrichment is a separate module seam.

### Phase 13H-0 — Synthetic trade-up pipeline integration (in progress)

- Adds `app/services/trade_up_pipeline.py`: `TradeUpInputMetadata`, `TradeUpInputMetadataResolver`, `InMemoryTradeUpInputMetadataResolver`, `candidates_to_input_items`.
- Proves `TradeUpInputCandidate` can feed the existing trade-up engine via a synthetic metadata adapter; unresolved/unknown names are skipped.
- No live provider, no identity resolver, no BUFF endpoint, no SteamApis, no scanner/scheduler, no purchase flow.

### Phase 13G-0 — Identity source decision (in progress)

- See `D-IDENTITY-002` in `DECISION_LOG.md`.
- Choice **D**: freeze identity source work and proceed with synthetic/offline pipeline only.
- No new endpoint, mapping, or resolver backend is added.
- The forward direction (`BuffItemIdentityResolver.resolve(market_hash_name) → BuffItemIdentity | None`) remains the only verified resolver surface; `None` is the only real answer.

### Phase 13F-0 — Identity resolution architecture review (in progress)

- Docs-only review of candidate identity providers (BUFF goods metadata, SteamDT identity fields, external metadata catalog, manual verified mapping).
- Forward direction (`resolve(market_hash_name) → BuffItemIdentity | None`) is supported.
- Reverse direction (`resolve_by_goods_id(goods_id) → BuffItemIdentity | None`) is recorded as a missing contract to be added later; no current module is modified.
- No candidate provider is approved for live wiring. No new endpoint, mapping, or resolver backend is added.

### Phase 13E-0 — Trade-up input candidate boundary (in progress)

- Adds the standalone `TradeUpInputCandidate` DTO between `BuffListing` and the future trade-up engine.
- `market_hash_name` is `None` by default; identity resolution is explicitly deferred.
- No adapter, no resolver, no scanner, no solver, no SteamApis, no purchase.

- `BuffListing` DTO, strict all-item parser, `BuffListingProvider`, shared one-request smoke runtime, provider live smoke, anonymous client hardening.

### Phase 13D-0 — identity bridge contract (UNCOMMITTED)

- `BuffItemIdentity` + `BuffItemIdentityResolver` protocol. `None` = unresolved. No mapping data, no concrete resolver. `BuffListing` unchanged.

### Phase 13D-1 / 13D-2 — source investigation (read-only, no code)

- No verified source for `market_hash_name ↔ BUFF goods_id`; no validated goods/product/search endpoint. Do not invent one.

### Phase 13L-0 — Identity bridge architecture review (committed `a70b0e6`)

- Design-only review under `specs/2026-08-22-identity-bridge-architecture-review/`.
- Architecture decision: **C — Freeze identity and continue synthetic-only**.
- All four candidate sources (BUFF native, SteamApis, SteamDT, manual offline mapping) evaluated as non-actionable for production wiring as of 2026-08-22.
- New decision record: `D-IDENTITY-003`. Existing `D-IDENTITY-001` and `D-IDENTITY-002` unchanged.
- Frozen contracts preserved: `BuffItemIdentity`, `BuffItemIdentityResolver`, `BuffListing.market_hash_name=None`, `TradeUpInputCandidate.market_hash_name=None` still accepted.
- Manual offline mapping is permissible only under the five `FR-4.1`–`FR-4.5` constraints recorded in `requirements.md`. Not implemented.
- No `app/` or `tests/` changes.
- Next recommended phase: none. Identity remains the unblocking prerequisite for any future production wiring.

### Phase 13M-0 — Production scanner orchestration architecture review (committed `a70b0e6`)

- Design-only review under `specs/2026-08-22-production-scanner-orchestration-review/`.
- Architecture decision: **B — new standalone orchestration module**, periodic scheduling, per-cache module ownership.
- Rejected alternatives: A (extend `market_scan_service`) and C (provider-driven pipeline runner) under boundary; event-driven and manual-only under scheduling; central cache registry and lazy caches under cache ownership.
- Future orchestration module path: `app/services/scanner_orchestration.py` (not yet created). Scheduler adapter is the only reference to `APScheduler`. Four cache modules (`listing_cache`, `metadata_cache`, `valuation_cache`, `identity_cache`) each own their own keyspace, TTL, invalidation, and observability. Cache modules must never import each other.
- Opportunity lifecycle: five stages (listing observed → candidate conversion → enrichment → trade-up evaluation → opportunity result), each owned by exactly one module.
- Failure handling: four categories (provider failure, enrichment rejection, valuation failure, stale data), each owned by exactly one module. No retry-with-backoff inside the orchestrator.
- Frozen contracts preserved: `BuffItemIdentity`, `BuffListing`, `TradeUpInputCandidate`, `TradeUpInputEnricher`, `BuffListingCandidateAdapter` all unchanged.
- No `app/` or `tests/` changes. No scanner, scheduler, cache, or BUFF endpoint code added.

## Current Status

- BUFF anonymous listing acquisition: **solved** (provider works; gated, read-only).
- SteamDT output valuation: **solved** (aggregate output valuation).
- Goods identity bridge: **abstraction only**; no verified resolver backend.
- Trade-up input normalization boundary: **not yet built** (Phase 13E-0).

## Next Action (ordered)

1. **Phase 13M-1 — `ScannerOrchestrator` skeleton implementation.** Implement `app/services/scanner_orchestration.py` with `ScannerOrchestrator.run_once()` and `ScannerOrchestratorConfig`. Compose the four frozen seams (`BuffListingProvider` → `BuffListingCandidateAdapter` → `TradeUpInputEnricher` → `trade_up_engine`) by dependency injection. No scheduler. No cache. No live BUFF polling. No identity resolver. No purchase. Frozen contracts (`BuffItemIdentity`, `BuffListing`, `TradeUpInputCandidate`, `TradeUpInputEnricher`, `BuffListingCandidateAdapter`) must remain unchanged. The skeleton must operate against synthetic test fixtures only.
2. Freeze `TradeUpInputCandidate`, `TradeUpInputEnrichment`, and `BuffListingCandidateAdapter`. No new metadata / enrichment abstraction should be introduced.
3. Before any live wiring: design production provider integration along the path
   ```
   BuffListingProvider
        ↓
   buff_listing_candidate_adapter
        ↓
   TradeUpInputCandidate
        ↓
   TradeUpInputEnrichment
        ↓
   InputItem
        ↓
   trade-up engine
   ```
   See `D-ADAPTER-001` for the dependency direction; see `D-ADAPTER-004` for the routing rule; see `D-MIGRATION-002` for the intrinsic-flag preservation requirement.
4. Identity resolution remains the main blocker (`D-IDENTITY-001`, `D-IDENTITY-002`, `D-IDENTITY-003`). Do NOT add: BUFF identity guessing, SteamDT identity inference, SteamApis identity assumptions, browser automation, anti-bot bypass.
5. Synthetic validation (`D-VALIDATION-001`) remains a mandatory regression gate. Any future change to the adapter, the enrichment boundary, or candidate ownership must pass synthetic seam validation.
6. Intrinsic flag migration is a separate production prerequisite (`D-MIGRATION-002`): `BuffListing` (or its successor) must expose `stattrak` and `souvenir` before any production wiring.
7. Later: verify quantity / freshness / classification facts before bridging into Phase 12 / solver.

## Current Blockers

- No verified `market_hash_name ↔ BUFF goods_id` source.
- BUFF goods/product/search endpoint undocumented/unauthorized.
- Anonymous sell-order has no verified market name; `BuffListing.market_hash_name` stays `None`.
- Phase 12 requires market name + quantity + classification facts that are not yet verified for the anonymous path.

## Standing Prohibitions (re-asserted)

No auto-buy, auto-login, cookie scraping, CAPTCHA/risk-control bypass, browser purchasing, proxy/UA rotation, mass scraping, or invented endpoints/fields. Live smokes stay gated and never auto-run. Do not modify Protected Core without an explicit migration plan.
