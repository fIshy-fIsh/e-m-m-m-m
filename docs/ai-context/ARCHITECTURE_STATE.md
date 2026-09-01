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

### Phase 13P / Phase 13T live one-shot opportunity scan (read-only; manual; no scheduler)

```
configured ordered goods_id allowlist or bounded auto-universe planner
  → BuffListingProvider.get_listings
  → IdentityResolvingBuffListingProvider (13N-3C; identity-only)
  → IntrinsicFlagResolvingBuffListingProvider (13O-1; canonical-name classifier)
  → convert_buff_listing_to_candidate
  → TradeUpInputCandidate
  → TradeUpInputEnrichment (decimal→float exactly once; candidate-owned Souvenir preserved)
  → scanner_recipe_composition.enumerate_scanner_recipe_selections (13T-2)
      → exact eligible pairs
      → canonical-offer duplicate-identity preflight (fail closed)
      → per-bucket fair-share aggregate candidate/state budget
        (first min(active_buckets, C) buckets participate; no redistribution; no second pass)
      → recipe_solver.enumerate_recipe_selections (13T-1; Protected Core additive API)
        → baseline P0..P9 first
        → deterministic radius-one substitutions ordered by (r-d, r, d, RecipeSelectionKey)
        → existing calculate_tradeup_results (Protected Core engine)
      → exact candidate-owned InputItem rehydration after temporary souvenir=False view
      → globally ordered returned candidates
  → ValuationService.value_tradeup_results (existing ValuationService + recording PriceProvider)
  → calculate_opportunity_metrics
  → evaluate_opportunity (existing risk filter)
  → ScannerRunResult
```

Production uses `enumerate_scanner_recipe_selections` and `enumerate_recipe_selections`. The legacy `construct_scanner_recipe_selections` and `construct_recipe_selections` paths remain available for compatibility but are not the production run path.

`app/services/scanner_orchestrator.py::LiveScannerOrchestrator.run_once(goods_ids)` implements one bounded run with dependency injection and per-goods acquisition isolation. Successful enriched inputs are accumulated across the existing hard-max-10 goods-ID universe before recipe construction, allowing exact normal and Souvenir pages to coexist without expanding the scan universe. `scripts/run_live_scan_once.py` is the explicit manual entry point; it performs one run and exits. No APScheduler, daemon, background loop, Discord requirement, or marketplace writes.

Phase 13P-4 applies Valve's current rule effective May 21, 2026: normal and Souvenir inputs may coexist, selected Souvenir input facts remain attached to provenance, and every standard-path output is normal/non-Souvenir. `scanner_recipe_composition` gives unchanged Protected Core a temporary input `souvenir=False` compatibility view, supplies only canonical `SkinMetadata` output records with `souvenir=False` and the matching homogeneous StatTrak mode, then verifies and rehydrates the exact candidate-owned `InputItem` tuple before valuation/risk. No prefix stripping or canonical metadata mutation occurs. The old `tradeup_engine.py` mixed-Souvenir rejection is retained as historical Protected Core behavior and is not the current domain rule at this composition seam. The pinned Knight pre-fix set was four names (two normal, two Souvenir); the corrected set is `M4A1-S | Knight (Factory New)` and `M4A1-S | Knight (Minimal Wear)` only.

Phase 13P-1 adds an explicit live-valuation gate and a run-level request guard:

- CLI refuses live work unless `STEAMDT_DRY_RUN=false` and `STEAMDT_API_KEY` is present.
- `max_valuation_requests_per_run` is required and validated in `[1, 60]`; CLI default is 5.
- unique output names are counted before valuation; a recipe that would exceed the remaining cap is rejected without partial lookup.
- counters expose attempted/succeeded/failed/blocked requests and fully-valued/valuation-failed recipes.
- `LiveRecipeEvaluation` preserves existing valuation, `OpportunityMetrics`, and `RiskDecision` values for accepted and rejected recipes; CLI/JSON do not recompute domain values.
- current CLI directly uses `SteamDTHttpClient`; existing cache adapters are not wired, so no cache-hit metric or freshness timestamp is invented.

Current live valuation status (Phase 13P-5): **full read-only opportunity path verified**. The Phase 13P-3 `base_url` transport fix remains active. A post-semantics Knight scan requested only the two canonical normal Knight outputs; Factory New resolved while Minimal Wear remained an expected strict `buff_sell_price_non_positive` selection failure. A second bounded technical scan for goods ID `35458` consumed ten real BUFF listings, resolved both canonical `PP-Bizon | Carbon Fiber` output prices through SteamDT's strict BUFF sell policy, completed valuation and EV/ROI, and produced a real `RiskDecision.passed=False` under unchanged thresholds. No opportunity passed, but the complete `BUFF → recipe → SteamDT → valuation → metrics → risk` path is verified. No scheduler, auto-buy, or marketplace writes were introduced.

Bounded multi-recipe enumeration status (Phase 13T-1 through 13T-4A): **bounded additive Protected Core API in production**. The legacy `construct_recipe_selections` retains its zero-or-one behavior. The new `enumerate_recipe_selections(candidates, skins, solver_config, *, enumeration_config)` adds:

- `RecipeEnumerationConfig(max_recipe_candidates_returned, max_candidate_states_explored)` with strict `__post_init__` validation: exact integers in `[1, 6]` candidates, `[1, 1024]` states, `states >= candidates`. Defaults `2 / 256`.
- `RecipeEnumerationDiagnostics(eligible_input_count, retained_input_count, theoretical_radius_one_states, states_explored, raw_candidates_found, unique_candidates_returned, duplicates_suppressed, engine_rejected_states, baseline_state_rejected, candidate_limit_reached, exploration_limit_reached)`.
- `RecipeEnumerationResult(selections, diagnostics)`.
- Canonical offer identity `(source, goods_id, listing_id)`; duplicate canonical keys fail closed before sort/cap/search.
- Baseline state explored first; radius-one substitutions ordered by `(r-d, r, d, RecipeSelectionKey)`; no radius-two; no beam search; no financial ranking; no exhaustive combinations; cross-candidate listing reuse allowed.

Scanner composition (Phase 13T-2): `enumerate_scanner_recipe_selections` wraps the bounded enumerator across active StatTrak buckets. Aggregate candidate/state budgets are owned by the composition layer:

- Active buckets ordered normal → StatTrak.
- `P = min(active_buckets, C)` participating buckets; only the first `P` receive quota.
- Candidate quota per bucket: `C // P + (1 if i < C % P else 0)`.
- State quota per bucket: `1 + (S - P) // P + (1 if i < (S - P) % P else 0)`.
- No redistribution, no second pass, no quota stealing.
- Every returned candidate is rehydrated from the temporary `souvenir=False` solver projection back to exact candidate-owned `InputItem` before downstream services see it.

Orchestrator integration (Phase 13T-3A): `LiveScannerOrchestrator.run_once(goods_ids)` consumes `enumerate_scanner_recipe_selections` and accepts `enumeration_config: RecipeEnumerationConfig | None = None` (default `2 / 256`). Returned recipe candidates are processed in deterministic structural composition order. The existing final opportunity display ordering by `expected_profit_cny desc, roi desc` is unchanged and does not affect enumeration, valuation order, valuation-cap consumption, or risk evaluation order.

CLI wiring (Phase 13T-3B): `scripts/run_live_scan_once.py` exposes `--max-recipe-candidates-returned` and `--max-candidate-states-explored` (argparse integer syntax). The CLI constructs exactly one `RecipeEnumerationConfig` and forwards it to `LiveScannerOrchestrator`; domain validation remains owned by `RecipeEnumerationConfig.__post_init__`.

Valuation budget semantics (orchestrator-owned cumulative): within one recipe, first-seen unique exact output `market_hash_name` is the logical request set. Across recipes there is no run-level cache; the same exact output name in a second recipe is a separate logical request. `required == remaining cap` is allowed. `required > remaining cap` causes the entire recipe to be blocked before any provider lookup, with `VALUATION_REQUEST_CAP_EXCEEDED`; no partial lookup, no zero fallback, no probability renormalization, no metric/risk/opportunity work. Run-level SteamDT output-price cache is **NOT IMPLEMENTED** (Phase 13T intentionally excluded it). Same exact output name in separate recipe valuation calls is a separate logical request today.

Metadata uses the pinned local snapshot `data/metadata/skin_metadata_v1.json` (ByMykel/CSGO-API at commit `8a785962...`, MIT, raw SHA-256 `7aeb9582...`, canonical snapshot SHA-256 `55e4d446...`). `scripts/build_skin_metadata_snapshot.py` reproduces it byte-for-byte from `research/metadata/by_mykel_skins.json`. `app/services/skin_metadata_resolver.py::PinnedSkinMetadataResolver` performs exact-string O(1) lookup and exposes the immutable existing `SkinMetadata` catalog to the existing recipe solver. Runtime metadata lookup performs zero network I/O.

### Identity bridge (runtime resolver + binding layer; provisional under D-IDENTITY-006)

```
market_hash_name → BuffCommunityIdentityResolver.resolve()            → BuffItemIdentity | None
goods_id         → BuffCommunityIdentityResolver.resolve_goods_id()   → BuffItemIdentity | None

market_hash_name → CanonicalNameIntrinsicFlagResolver.resolve()       → BuffListingIntrinsicFlagsValue
                                                                              (stattrak: bool | None,
                                                                               souvenir: bool | None)

BUFF_READONLY_SMOKE_GOODS_ID (caller context)
  → BuffAnonymousListingHttpClient GET /api/market/goods/sell_order
  → strict all-item parser
  → list[BuffListing]                       (BuffListing.market_hash_name = None at this layer)
  → IdentityResolvingBuffListingProvider    (13N-3C; identity-only)
       ↓   resolve_goods_id(goods_id)  exactly once per provider fetch
  → list[BuffListing]                       (BuffListing.market_hash_name = resolved exact name | None)
  → IntrinsicFlagResolvingBuffListingProvider  (13O-1; intrinsic-flag-only)
       ↓   canonical-name exact-prefix classification, one resolve per listing
  → list[BuffListingIntrinsicFlags]         (wrapper preserves every other field)
  → BuffListingCandidateAdapter               (13K-1; reads market_hash_name + flags off the DTO)
       ↓   convert_buff_listing_to_candidate
  → TradeUpInputCandidate                   (bool | None for statted/souvenir since 13O)
  → TradeUpInputEnrichment
  → InputItem
```

The architecture is three independent composition stages after the
underlying provider: identity-only, intrinsic-flag-only, and the
adapter. Each stage has exactly one responsibility and a closed
invariants contract.

* **Identity binding** (`app/services/buff_identity_listing_provider.py`,
  Phase 13N-3C; Phase 13O-1 removed the intrinsic-flag kwargs):
  identity-only. Exactly one `resolve_goods_id(goods_id)` per fetch.
  Three closed integrity errors (`resolver_goods_id_mismatch`,
  `listing_goods_id_mismatch`, `market_hash_name_conflict`).
* **Intrinsic-flag binding**
  (`app/services/buff_intrinsic_flag_listing_provider.py`, Phase 13O-1):
  wraps an upstream provider with a `BuffListingIntrinsicFlagResolver`
  (default `CanonicalNameIntrinsicFlagResolver`) and attaches
  `stattrak` / `souvenir` to each listing. The resolver is invoked
  once per listing. When `market_hash_name` is `None` (identity
  unresolved), both flags remain `None` (unknown).
* **Canonical-name classifier**
  (`app/services/buff_intrinsic_flag_resolver.py`, Phase 13O-1):
  pure exact-canonical-string-prefix classifier using the canonical Steam community
  market naming convention (`'StatTrak™ '` and `'Souvenir '` prefixes).
  Verified against the full 34,402-entry pinned catalog with zero
  contradictions under `D-INTRINSIC-002`. No HTTP, no filesystem,
  no BUFF / SteamDT / SteamApis / Redis / DB / Discord.

The intrinsic-flag binding layer is the seam. Production correctness
never depends on caller assertions about intrinsic flags; the
canonical classifier establishes the value deterministically from the
canonical name only.

The binding layer is **not** the adapter. The adapter still reads
`market_hash_name` and the intrinsic flags off the supplied DTO.

### Trade-up input candidate → enrichment boundary (synthetic/offline only)

```
BuffListing / future source
        ↓
TradeUpInputCandidate  (candidate-owned fields: market_hash_name, price_cny,
                       paintwear, asset_id, source, stattrak, souvenir)
        ↓
TradeUpInputEnrichment  (offline enricher + metadata resolver)
        ↓
InputItem
        ↓
existing trade-up engine
        ↓
EV / ROI / Risk
```

Phase 13I-3 established the explicit seam `TradeUpInputCandidate + metadata → InputItem` with `kept` + `rejected` partitions in input order. Ownership is split:

- Candidate owns: `market_hash_name`, `price_cny`, `paintwear`, `asset_id`, `source`, `stattrak`, `souvenir`.
- Metadata owns: `collection_name`, `rarity`, `min_float`, `max_float`.
- `paintwear` (Decimal) is converted to `actual_float` (float) exactly once at the boundary.
- **Phase 13O migration:** intrinsic flags (`stattrak`, `souvenir`) are `bool | None = None`, not `bool = False`. The three states (`True` established, `False` established, `None` not-established-by-this-source) are explicit at the candidate boundary. No `None → False` coercion occurs at any upstream layer.

Rejection vocabulary (13O): `MARKET_HASH_NAME_UNRESOLVED`, `METADATA_NOT_FOUND`, `INTRINSIC_FLAG_UNRESOLVED`. No identity inference; no default fallback; no live adapter. `INTRINSIC_FLAG_UNRESOLVED` surfaces a candidate whose intrinsic flags are `None` (the upstream did not establish the value).

### Future (not yet wired)

```
BuffListing → TradeUpInputCandidate → TradeUpInputEnrichment → (future trade-up engine)
```

## Existing Modules (responsibility map)

- `app/clients/buff_anonymous_listing_client.py` — hardened anonymous BUFF GET; exact independent request, header allowlist, auth/redirect disabled.
- `app/services/buff_listing_provider.py` — `BuffListing` DTO, strict parser, `BuffListingProvider`.
- `app/services/buff_item_identity.py` — `BuffItemIdentity`, `BuffItemIdentityResolver` protocol (unresolved).
- `app/services/buff_community_identity_resolver.py` — concrete forward + reverse resolver over the pinned snapshot (13N-3B); O(1) lookup, zero network I/O.
- `app/services/buff_identity_listing_provider.py` — identity-binding composition layer (13N-3C); wraps `BuffListingProvider` and a `BuffGoodsIdIdentityResolver`, performs exactly one `resolve_goods_id` lookup per fetch, and rebinds `BuffListing.market_hash_name` before the adapter sees it.
- `app/services/buff_listing_intrinsic_flags.py` — three-state intrinsic-flag representation (13O); `BuffListingIntrinsicFlags` wrapper, `coerce_intrinsic_flag`, `IntrinsicFlagValidationError`. Distinguishes `True` / `False` / `None`. Source capability was UNKNOWN at the start of 13O; the canonical-name classifier (13O-1) now establishes `True` / `False` for every well-formed canonical name, leaving `None` only for unresolved identity (`D-INTRINSIC-002`).
- `app/services/buff_intrinsic_flag_resolver.py` — canonical-name exact-canonical-string-prefix classifier (13O-1). Pure: no I/O, no network. Verifies the canonical Steam community market prefix rule against every pinned catalog entry with zero contradictions.
- `app/services/buff_intrinsic_flag_listing_provider.py` — intrinsic-flag binding composition layer (13O-1). Identity-only provider output → intrinsic-flag-wrapped listings; one resolver call per page after exact page-identity consistency validation.
- `app/services/skin_metadata_resolver.py` — pinned local exact-name `TradeUpInputMetadataResolver` + immutable `SkinMetadata` catalog (13P); O(1), zero runtime network I/O.
- `app/services/scanner_orchestrator.py` — dependency-injected read-only one-shot opportunity scanner (13P/13P-4; Phase 13T-3A bounded enumeration integration); bounded goods-id universe, per-goods acquisition isolation, run-wide enriched-input pool, existing valuation/EV/risk composition, no scheduler, accepts `enumeration_config: RecipeEnumerationConfig | None = None` (default `2 / 256`).
- `app/services/scanner_recipe_composition.py` — Phase 13P-4 current-rule output-eligibility and Protected Core compatibility seam (Phase 13T-2 additive `enumerate_scanner_recipe_selections` API); candidate-owned filtering, homogeneous StatTrak buckets, canonical non-Souvenir outputs, exact input rehydration for every returned candidate, per-bucket fair-share aggregate budgeting, no name mutation.
- `tests/test_multi_recipe_scanner_scale_validation.py` — Phase 13T-4A offline bounded multi-recipe scale validation (deep-pool primary, exact/one-below cap atomicity, two-bucket aggregate, 1/1 legacy compatibility, determinism).
- `app/services/recipe_solver.py` — deterministic greedy recipe construction; additive bounded enumeration API (Phase 13T-1): `RecipeEnumerationConfig`, `RecipeEnumerationDiagnostics`, `RecipeEnumerationResult`, `enumerate_recipe_selections`. Legacy `construct_recipe_selections`, `construct_recipes`, `solve_recipes` retained unchanged.
- `app/services/trade_up_input_candidate.py` — `TradeUpInputCandidate` DTO (13I-2 intrinsic flags `stattrak`/`souvenir`; widened to `bool | None = None` in 13O).
- `app/services/trade_up_input_enrichment.py` — `TradeUpInputMetadata`, `TradeUpInputMetadataResolver`, `TradeUpInputEnricher`, `enrich_candidates`, rejection model (13I-3, offline only).
- `app/clients/buff_client.py` — legacy `BuffHttpClient` (unimplemented), `MockBuffClient`, `DryRunBuffClient`, legacy `BuffSellOrder`/`BuffGoodsInfo`.
- `app/services/buff_listing.py` + parser/facts/eligibility/qualification/solver_adapter — Phase 12 offline contract chain.
- `app/services/market_scan_service.py` — `CandidateListing`, legacy synchronous scanner (`scan_goods`/`scan_watchlist`).
- `app/services/recipe_solver.py` — deterministic greedy recipe construction; additive bounded enumeration API (Phase 13T-1): `RecipeEnumerationConfig`, `RecipeEnumerationDiagnostics`, `RecipeEnumerationResult`, `enumerate_recipe_selections`. Legacy `construct_recipe_selections`, `construct_recipes`, `solve_recipes` retained unchanged.
- `app/services/tradeup_engine.py` — `InputItem`/`OutputCandidate`/`TradeupResult`, trade-up math.
- `app/services/ev_service.py` — fee application, EV/ROI metrics.
- `app/services/risk_filter.py` — `RiskDecision`, ROI/profit/probability/liquidity gates.
- `app/services/valuation_service.py` + `live_recipe_valuation.py` — strict complete-price valuation.
- `app/services/steamdt_*` + `app/clients/steamdt_client.py` — SteamDT aggregate client/parser/limiter/cache/providers.
- `app/services/steamapis_*` + `app/clients/steamapis_*` — SteamApis WebSocket offer stream (paused/unverified live).
- `app/services/metadata_*` — skin metadata normalization (name-based; no BUFF goods ID).
- `app/services/pipeline_service.py` + `app/jobs/scheduler.py` — legacy mock BUFF pipeline (fixture-backed).

## Protected Core (modification requires explicit migration authorization)

The protected-core files below may be modified only under an explicit reviewed migration plan. Phase 13T deliberately migrated two protected modules under explicit authorization while preserving their existing observable contracts:

- `app/services/tradeup_engine.py`
- `app/services/valuation_service.py`
- `app/services/live_recipe_valuation.py`
- `app/services/ev_service.py`
- `app/services/risk_filter.py`
- `app/services/recipe_solver.py` — Phase 13T-1 added the additive bounded enumeration API (`RecipeEnumerationConfig`, `RecipeEnumerationDiagnostics`, `RecipeEnumerationResult`, `enumerate_recipe_selections`). Legacy `construct_recipe_selections`, `construct_recipes`, and `solve_recipes` remain unchanged and continue to expose their pre-13T zero-or-one contract verbatim.
- `app/services/scanner_orchestrator.py` — Phase 13T-3A integrated bounded recipe enumeration; Phase 14B added fresh run sessions and atomic NEW-LIVE admission; Phase 14C added optional injected cached resolver and per-plan cache counter aggregation. It constructs no cache backend/runtime.
- `scripts/run_live_scan_once.py` — Phase 14D composes `create_steamdt_price_cache_runtime` and injects `ScannerCachedBuffPriceResolver(runtime.cache)` into the orchestrator; default in-memory; Redis optional; invalid cache config fails before live client work; deterministic cleanup; no write-after-live.
- `app/services/scanner_valuation_session.py` — Phase 14B scanner-owned boundary, extended by Phase 14C. Stage A now performs deterministic exact memo → optional sequential FRESH_ONLY cache → NEW LIVE classification. Fresh strict success/failure enter the memo; MISS/EXPIRED/POLICY_BLOCKED remain unmemoized live candidates. Stage B remains live-provider-only and reuses existing `ValuationService`; no cache write or refresh call.
- `app/services/scanner_cached_buff_price_resolver.py` — Phase 14C structural composition wrapper. Accepts the existing Phase12D cache-reader protocol, internally constructs `SteamDTCachedPriceResolver` with `select_scanner_cached_buff_price`, and exposes only fixed FRESH_ONLY scanner resolution. Arbitrary generic-selector resolvers cannot satisfy the scanner public API.
- `app/services/scanner_cached_buff_price_selector.py` — Phase 14C scanner-owned adapter matching the raw cached resolver selector protocol while delegating policy to `select_buff_output_price`; exact BUFF, positive finite sell, source `steamdt:buff`, no generic platform/bid fallback.
- `app/services/market_scan_service.py` (`CandidateListing`)
- Phase 12 BUFF domain: `buff_listing.py`, `buff_listing_parser.py`, `buff_listing_facts.py`, `buff_listing_eligibility.py`, `buff_listing_qualification.py`, `buff_listing_solver_adapter.py`
- `app/clients/buff_client.py` (legacy skeleton)
- SteamDT client/core, SteamApis modules, metadata providers.
- `app/services/buff_listing_provider.py` and `app/clients/buff_anonymous_listing_client.py` (recently hardened; change only with explicit new spec).
- Phase 12D cache modules (`app/services/price_cache.py`, `app/services/price_cache_codec.py`, `app/services/redis_price_cache.py`, `app/services/price_cache_factory.py`, `app/services/steamdt_price_cache_adapter.py`, `app/services/steamdt_cached_price_resolver.py`, `app/services/steamdt_price_snapshot_source.py`, `app/services/steamdt_price_refresh_service.py`, `app/services/steamdt_refresh_planner.py`, `app/services/steamdt_refresh_executor.py`) — implemented and unit-tested standalone. Phase 14C consumes only the existing read-only resolver contract from scanner-owned Stage A; no Phase12D implementation module was modified. Default CLI backend/resolver composition remains Phase 14D.

### Phase 14B / 14C implemented seam

Phase 14B implements the fresh run-scoped session, exact-name memo, immutable plan safety, live-only Stage B, and NEW-LIVE atomic admission. Phase 14C extends Stage A through an optional scanner-owned `ScannerCachedBuffPriceResolver` over the injected Phase12D cache-reader boundary. The wrapper internally fixes the raw `SteamDTCachedPriceResolver` to `select_scanner_cached_buff_price`, preventing generic cross-platform authority from entering public scanner composition. Memo is consulted first; unresolved names are read sequentially with explicit `FRESH_ONLY`; selected outcomes independently require FRESH lookup state; the scanner adapter delegates strict selection to `select_buff_output_price`. Fresh SELECTED and reason-preserving SELECTION_FAILURE outcomes enter the run memo. MISS, EXPIRED, and POLICY_BLOCKED remain unmemoized ordered NEW LIVE names. Backend/codec/adapter/resolver exceptions propagate and never become live candidates. Stage B performs no cache work or persistent writeback. Nothing in the memo survives across runs.

`max_valuation_requests_per_run` means NEW LIVE exact-name demand after memo/cache classification. Legacy logical valuation counters retain their recipe-facing semantics. Additive `run_reuse_*`, `cache_*`, and `live_*` counters are active. Completed-run invariants remain: `run_reuse_hits = run_reuse_successes + run_reuse_failures`, `live_demand = live_attempted + live_atomically_blocked`, and `live_attempted = live_succeeded + live_failed`.

No Phase12D implementation module changed. The scanner service/session now supports persistent FRESH_ONLY reads, but default `scripts/run_live_scan_once.py` cache composition remains Phase 14D. Scanner write-after-live is not implemented. Snapshot freshness comes from stored writer-owned `PriceCachePolicy`; no scanner read-time numeric TTL config exists. `D-CACHE-001` remains Active until runtime composition lands.

### Phase 14A design authority retained

Phase 14A (`specs/2026-08-29-scanner-valuation-integration-design-freeze/`) and Phase 14A-R1 (`D-PHASE14A-R1-COHERENCE`) freeze the design for any future Phase 14 implementation that integrates the existing Phase 12D cache stack into the live scanner valuation path and closes `D-CACHE-001` (run-scoped cross-recipe exact-price reuse). The single sanctioned seam is a **scanner-owned `RunScopedValuationSession` boundary that lives OUTSIDE `app/services/valuation_service.py` and `app/services/live_recipe_valuation.py`** (both Protected Core). The boundary does NOT resolve BUFF listing identity, does NOT alter recipe enumeration, and does NOT cache-cross-reference `BuffCommunityIdentityResolver`. The session exposes a **two-stage contract**: Stage A `prepare_output_prices(names)` issues ZERO live SteamDT calls (consults run memo; in 14C, also performs FRESH_ONLY cache reads); Stage B `resolve_prepared(plan)` is only called after the orchestrator's atomic-cap admission succeeds. Initial scanner cache policy is `PriceCacheReadPolicy.FRESH_ONLY`. Initial Phase 14C is scanner cache READ-only (no scanner writeback). `max_valuation_requests_per_run` is redefined as NEW LIVE SteamDT provider demand / attempts within a run, exclusive of run-reuse hits and `FRESH + SELECTED` cache hits.

The strict-BUFF cache-selection adapter is composed at the session level via reuse/adaption of `select_buff_output_price` (`app/services/steamdt_buff_price_policy.py:73-77`); `select_steamdt_price_quote` (`app/clients/steamdt_price_selection.py:81-89`) is generic cross-platform and CANNOT be configured strict BUFF-only. `SteamDTCachedPriceResolver` and `select_steamdt_price_quote` are NOT modified by R1 or 14C. Cache backend / codec / adapter exceptions propagate by identity from the resolver; they are NOT `MISS`, NOT live candidates, NOT memo entries. `D-CACHE-001` remains `Active` until Phase 14B / 14C land and are verified. Phase 14A and Phase 14A-R1 do NOT modify any production code.

## Verified vs Assumed vs Unknown

- **Verified (manual, one request):** anonymous BUFF sell-order first page returns `items[]` with id/price/`asset_info.paintwear`/`asset_info.assetid`; paintseed absent in that run.
- **Assumed (project decision):** SteamDT sell/bid interpreted as CNY/RMB; BUFF `price_cny` project-facing naming.
- **Unknown:** official currency/fees, canonical `market_hash_name` mapping, goods/product/search endpoint, quantity/freshness/removal, pagination/page size, rate limits, classification facts, purchase handoff.

## Current Blockers

- No new blocker for the completed Phase 13T bounded multi-recipe migration. The previously listed blockers are closed:
  - Identity binding is wired into the runtime (`D-IDENTITY-007`).
  - The orchestrator consumes `enumerate_scanner_recipe_selections` (Phase 13T-3A).
  - Bounded enumeration has been validated offline (Phase 13T-4A) and live (Phase 13T-4B).
- Phase 14 run-scoped exact-name reuse, NEW-LIVE atomic accounting, FRESH_ONLY Phase 12D scanner cache reads with strict-BUFF selection, and the default one-shot CLI cache composition are **canonically integrated on `main`** via PR #4. Canonical main P4 = `26c69bae9e482452f56f380277d8b10fefa29d52`, tree `39a82914...`. Feature branch `feature/scanner-valuation-integration` safely retired. `D-CACHE-001` is superseded for the originally tracked run-reuse + CLI composition gap.

## Completed Capabilities (cumulative)

- Anonymous BUFF listing acquisition (provider works; gated, read-only).
- Identity abstraction (`BuffItemIdentity` + resolver protocol; unresolved is normal).
- TradeUpInputCandidate boundary (with intrinsic `stattrak`/`souvenir` flags, 13I-2).
- Synthetic trade-up pipeline (13H-0): candidate → engine via offline metadata adapter.
- Enrichment boundary (13I-3): candidate → InputItem seam with kept/rejected partitions.
- Synthetic scale validation (13J-1): SMALL / MIXED / DIRTY cases drive both 13H-0 and 13I-3 paths; partition agreement, signature equivalence, EV / Risk reproducibility, and rejection-reason coverage are asserted offline.
- BuffListing candidate adapter boundary (13K-1): `app/services/buff_listing_candidate_adapter.py`; closed return-rejection vocabulary; routes candidate output through `TradeUpInputEnrichment`; synthetic / offline only at present.
- Identity bridge architecture review (13L-0): source-by-source verdict recorded in `D-IDENTITY-003`. Four candidate sources (BUFF native, SteamDT, SteamApis, manual offline mapping) all non-actionable for production wiring. Frozen contracts preserved; `market_hash_name=None` continues to flow through the seam.
- Production scanner orchestration architecture review (13M-0): design only; boundary B (new standalone `app/services/scanner_orchestration.py`), periodic scheduling, per-cache module ownership. Architecture recommendation recorded; no implementation in 13M-0.
- BUF anonymous response field inventory (13N-1): deep audit of `BuffListingProvider` parser, response envelope, and field access map. Recorded in `D-IDENTITY-004`. Confirms parser reads exactly six item-level fields; `market_hash_name=None` is structurally hardcoded.
- BUF goods-info endpoint survey (13N-2): endpoint listed as TODO `#5` in `docs/BUFF_API_NOTES.md`; `BuffGoodsInfo` is a placeholder; `BuffHttpClient.get_goods_info` raises `NotImplementedError`. Recorded in `D-IDENTITY-005`. No live probe authorized.
- Community catalog identity revalidation (13N-3A): EricZhu-42/SteamTradingSite-ID-Mapper `buff/730.json` accepted as a **provisional** V1 identity source under `D-IDENTITY-006`. Version-pinned (commit `093adde1...`, file SHA-256 `a7f370a6...`), CC-BY-4.0 licensed, 99.96% coverage, 0 in-source collisions, 99.997% independent agreement with ModestSerhat.
- Offline snapshot builder + bidirectional identity resolver (13N-3B): `data/identity/buff_identity_v1.json` (canonical SHA-256 `e3aab46d...`) committed. `scripts/build_buff_identity_snapshot.py` deterministic builder (verifies raw source SHA-256). `app/services/buff_community_identity_resolver.py` runtime resolver exposes both forward `resolve(market_hash_name) -> BuffItemIdentity | None` (existing Protocol) and reverse `resolve_goods_id(goods_id) -> BuffItemIdentity | None`. Runtime performs zero network I/O.
- BUF listing identity binding (13N-3C): `app/services/buff_identity_listing_provider.py` provides `IdentityResolvingBuffListingProvider` and `bind_identity_to_provider(provider, resolver)`. Composition layer that wraps a raw `BuffListingProvider` and a `BuffGoodsIdIdentityResolver`; performs exactly one `resolve_goods_id` lookup per fetch; rebinds `BuffListing.market_hash_name` to the resolved exact name while preserving every other field verbatim; defends against three closed integrity violations (`resolver_goods_id_mismatch`, `listing_goods_id_mismatch`, `market_hash_name_conflict`) by failing closed; never invokes fallback I/O. `BuffListingCandidateAdapter` is **not** modified; the binding layer inserts the resolution step between provider and adapter so the adapter continues to read `market_hash_name` off the supplied DTO. Identity resolution is **not** inside the adapter.
- Intrinsic-flag three-state representation (13O): `app/services/buff_listing_intrinsic_flags.py` defines `BuffListingIntrinsicFlags` (wraps `BuffListing`, adds `stattrak: bool | None` and `souvenir: bool | None`); `coerce_intrinsic_flag` enforces strict `True` / `False` / `None` acceptance; rejects `int 0/1`, `str "true"/"false"`, `float`, and `bool` subclasses. `TradeUpInputCandidate.stattrak` and `.souvenir` widened from `bool = False` to `bool | None = None` (the explicit migration target). `BuffListingCandidateAdapter` reads the flags via `getattr(..., default=None)` and forwards them verbatim; it never coerces `None` to `False`; it returns `INTRINSIC_FLAG_INVALID` for malformed values. `TradeUpInputEnrichment` rejects a candidate whose flags are `None` as `INTRINSIC_FLAG_UNRESOLVED`. **No Protected Core file is modified.** Source capability remains **UNKNOWN**: the anonymous BUFF sell-order payload does not currently expose these fields; no verification has been authorized.
- Intrinsic-flag canonical-name classifier (13O-1; refined by 13O-1A): `app/services/buff_intrinsic_flag_resolver.py` provides `CanonicalNameIntrinsicFlagResolver` — a pure exact-canonical-string-prefix classifier using the canonical Steam community market naming convention (`'StatTrak™ '` prefix → `stattrak=True`; `'Souvenir '` prefix → `souvenir=True`; otherwise `False`). Empirical validation against the pinned 34,402-entry catalog produces zero contradictions. The classifier establishes `True` / `False` for every well-formed canonical name; `None` is reserved for callers that wrap an unknown-source resolver or for inputs that fail input validation (`IntrinsicFlagInputError`). Independent totals (13O-1A verified): `stattrak_true=3377`, `stattrak_false=31025`, `souvenir_true=2345`, `souvenir_false=32057`. Joint counts partition the catalog: `(True,True)=0`, `(True,False)=3377`, `(False,True)=2345`, `(False,False)=28680`.
- Intrinsic-flag binding composition (13O-1; refined by 13O-1A): `app/services/buff_intrinsic_flag_listing_provider.py` provides `IntrinsicFlagResolvingBuffListingProvider` and `bind_intrinsic_flags_to_provider`. Wraps an upstream provider with a `BuffListingIntrinsicFlagResolver`; **invokes the resolver exactly once per page** (not per listing) — every non-`None` `market_hash_name` in the page is verified to share the same canonical value; conflicting non-`None` values fail closed with `IntrinsicFlagInputError`. Flags are attached via `BuffListingIntrinsicFlags`. Architecture is now three independent stages after the underlying provider: **identity-only** (13N-3C; intrinsic-flag kwargs removed in 13O-1), **intrinsic-flag-only** (13O-1; this module), and the **adapter** (13K-1; reads off the DTO).
- Live read-only opportunity MVP (13P): `app/services/scanner_orchestrator.py::LiveScannerOrchestrator.run_once(goods_ids)` + `scripts/run_live_scan_once.py`. Manual one-shot, bounded allowlist (hard max 10), sequential acquisition, per-goods failure isolation, pinned local metadata resolver (`data/metadata/skin_metadata_v1.json`, ByMykel MIT pin), existing recipe solver + SteamDT valuation + EV/ROI + `RiskDecision.passed` opportunity acceptance. No scheduler, daemon, Discord requirement, cache subsystem, or marketplace writes.
- Bounded market universe + multi-goods live scan (13R): `app/services/market_universe_builder.py` is a pure offline planner that joins the exact pinned identity and metadata catalogs by `market_hash_name`, applies the existing `is_current_standard_trade_up_output_eligible` rule with one explicit input rarity (`RarityOrder.ORDER[:5]`), one homogeneous StatTrak mode, optional Souvenir inclusion policy, optional exact collection allowlist, and a hard bound `1..10`. Selection is deterministic collection-round-robin sorted by `(collection_name, stattrak, souvenir, len, name)`. Returns `MarketUniverseResult.goods_ids`; diagnostics report truthful disjoint counters (`excluded_no_identity`, `excluded_no_metadata`, `excluded_invalid_rarity`, `excluded_no_collection`, `excluded_no_valid_output`, `excluded_intrinsic_policy`, `excluded_by_allowlist`). `BuffCommunityIdentityResolver` gains an additive public `identities` property (`((market_hash_name, goods_id), ...)` ordered by `(len, name)`) used by the builder; no other resolver/protocol changes. CLI `--auto-universe` composes the bounded sequence into the unchanged `LiveScannerOrchestrator.run_once` flow; `--universe-preview` exits before any `LiveScanSettings()`/HTTP client construction. Manual `--goods-id` path preserved byte-identically. Protected Core unchanged. Live verification on 2026-08-25: one bounded `--auto-universe --rarity Restricted --stattrak-mode normal --souvenir include --max-goods-ids 10 --max-valuation-requests 20` run requested 10 goods IDs (round-robin across 10 collections), succeeded 10, fetched 71 listings, built 1 recipe (`Dual Berettas | Twin Turbo` × `SG 553 | Integrale` all 5 wear values), attempted 10 SteamDT `PRICE_SINGLE` lookups, resolved 10/10, and produced `RiskDecision.passed=False` under unchanged thresholds. Zero opportunities passed (expected for current market); the complete live path is verified.
- Structural coverage allocation (13S): the Phase 13R planner now has an explicit pure two-stage flow, `exact catalog eligibility -> allocation strategy -> bounded goods IDs`. `BREADTH` remains the default and preserves the collection round-robin sequence. Opt-in `COHORT_DEPTH` uses collection-local allocation cohorts `(collection_name, rarity, stattrak)`, ranks by descending eligible catalog capacity then lexical key, selects at most the configured target (default 3), allocates capacity-aware fair rounds (`10/3 -> 4/3/3`), and interleaves normal/Souvenir exact identities. This cohort is intentionally stricter than legal recipe compatibility `(rarity, stattrak)`; collections may mix and Souvenir is not a compatibility split under the May-2026 seam. Diagnostics expose eligible/selected cohort counts, catalog capacity, intrinsic counts, canonical output count, slots, and identities. Capacity is not liquidity, listing availability, or a financial signal. Planner imports no live-price/EV/risk/network dependency. Live verification on 2026-08-25: 10 IDs across 3 cohorts, 10/10 pages, 94 listings/InputItems, 1 recipe evaluated and fully valued, 10/10 valuation requests, 0 opportunities. Hard goods cap, scanner/orchestrator/composition/metadata/Protected Core, valuation/risk, and no-write/no-scheduler behavior remain unchanged.
- Bounded multi-recipe solver migration (Phase 13T Design freeze + committed/pushed 13T-1 through 13T-4A + live-only 13T-4B at `9288794`). Phase 13T-1 (committed `4a6b85c`) adds the additive bounded enumeration API in `app/services/recipe_solver.py` while preserving the legacy `construct_recipe_selections` zero-or-one contract; canonical offer identity `(source, goods_id, listing_id)`; duplicate canonical key fails closed before sort/cap/search; default `2 / 256`; hard bounds `1..6` candidates, `1..1024` states with `states >= candidates`; baseline first then deterministic radius-one substitutions ordered by `(r-d, r, d, RecipeSelectionKey)`. Phase 13T-2 (committed `74332e7`) adds `enumerate_scanner_recipe_selections`, `ScannerRecipeCompositionDiagnostics`, and `ScannerRecipeBucketDiagnostics`; per-bucket fair-share aggregate candidate/state budgets; no redistribution; exact candidate-owned `InputItem` rehydration after temporary `souvenir=False` solver projection. Phase 13T-3A (committed `ac26e9b`) wires `enumerate_scanner_recipe_selections` into `LiveScannerOrchestrator.run_once` and adds `enumeration_config: RecipeEnumerationConfig | None = None` (default `2 / 256`). Phase 13T-3B (committed `33675ee`) exposes `--max-recipe-candidates-returned` and `--max-candidate-states-explored` on the production CLI; domain validation authority remains `RecipeEnumerationConfig`. Phase 13T-4A (committed `9288794`) adds `tests/test_multi_recipe_scanner_scale_validation.py` covering the deep-pool primary fixture (10 goods / 100 InputItems / 901 theoretical states / 2 returned / 2 explored), exact-cap=20 → 2 fully valued, one-below=19 → 1 fully valued + 1 atomically blocked, two-bucket aggregate allocation `1 / 1` candidates and `128 / 128` states, 1/1 legacy compatibility, and determinism. Phase 13T-4B (no commit, no repository artifact; `LIVE_VALIDATION_PASSED_NO_COMPLETE_VALUATION`) ran one bounded live `--auto-universe --allocation cohort-depth --target-cohorts 3` scan against `9288794`: 10/10 BUFF pages succeeded, 95 listings became 95 InputItems, real bounded composition returned 2 recipes requiring 10 + 20 unique output names, both atomically blocked under effective `max_valuation_requests_per_run=5` before any SteamDT HTTP/provider request; 0 fully valued, 0 risk evaluated, 0 opportunities; all frozen contracts held. No run-level SteamDT output-price cache is implemented (Phase 13T intentionally excluded it).

## Current Blockers

- BUFF identity bridge is **provisional** under `D-IDENTITY-006` (community catalog snapshot, runtime implemented in 13N-3B, file `data/identity/buff_identity_v1.json`). Identity binding between `BuffListingProvider` and `BuffListingCandidateAdapter` is implemented (13N-3C) but not yet wired into the orchestration runtime.
- Intrinsic flag source incomplete: `stattrak` / `souvenir` are owned by the candidate layer, but the current `BuffListing` DTO does not expose them. Production adapter wiring is blocked until these values can be preserved (see `D-MIGRATION-002`).
- Phase 14B run reuse, Phase 14C FRESH_ONLY scanner service/session reads, and Phase 14D default one-shot CLI cache composition are complete; see `D-PHASE14B-COMPLETE`, `D-PHASE14C-COMPLETE`, and `D-PHASE14D-COMPLETE`. Deferred write/refresh concerns remain separate future work.

## Technical Debt

- **13H-0 / 13K-1 intrinsic flag compatibility debt** — `trade_up_pipeline.py::candidates_to_input_items` (13H-0) and `buff_listing_candidate_adapter.py::convert_buff_listing_to_candidate` (13K-1) both default `stattrak=False, souvenir=False` because the upstream `BuffListing` DTO does not yet expose those fields. Historical behavior; preserved for compatibility; validated offline by synthetic scale validation (13J-1) and the adapter's own test suite. Forbidden as production behavior. References: `D-MIGRATION-001`, `D-MIGRATION-002`.
- **Run-level exact-name valuation reuse and persistent READ seam** — Phase 14B implements one-run exact success/failure memo; Phase 14C adds optional FRESH_ONLY resolver reads with strict BUFF selection; Phase 14D wires the default one-shot CLI cache composition. No scanner writeback. `D-CACHE-001` is superseded for the originally tracked run-reuse + CLI composition gap.

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

---

## Phase 16A Frozen Next Architecture (2026-08-31)

The Phase 16A design freeze (docs-only on `feature/recipe-first-prescreen-design`) introduces a recipe-first discovery architecture that REUSES the mature downstream calculation/safety stack but REPLACES the current goods-first discovery brain. No production code change in 16A; staged under 16B / 16C / 16D / 16E / 16F.

New authoritative modules (frozen in 16A; corrected in 16A-R1; implemented in later phases):

- `RecipeFamily` (frozen dataclass; no `souvenir_inclusion`): `family_key`, `family_spec_version = 1`, `input_rarity`, `stattrak_mode`, `collection_counts` (sum == 10, distinct collections <= 3), `represented_outputs`, `output_rarity`, `output_stattrak`, `structural_probability_denominator`, `family_hash`.
- `RecipeFamilyGenerator`: pure, deterministic, offline, LAZY iterator/generator with analytic counts. Inputs: pinned metadata + pinned identity + `StatTrakMode` (Souvenir is not a structural family axis). Outputs: lazy stream of `RecipeFamily`.
- `StaticFloatFeasibilityAnalyzer`: offline only; canonical float math reused.
- `SteamDTBatchPreScreenAdapter`: mocked transport in tests; strict BUFF selector (case-sensitive `platform == "BUFF"`, positive finite `sellPrice`, single BUFF record per name); batch-size cap `PRESCREEN_BATCH_CHUNK_SIZE = 10` per call; deduplicates exact `market_hash_name`s before issuing any batch call.
- `RecipeFamilyPreScreenEconomics`: optimistic / base / conservative scenarios; separate DTO from `OpportunityMetrics`.
- `RecipeFamilyRanker`: gates + lexicographic ranking keys + `TOP_RANKED_FAMILIES = 2` (ranking signal only).
- `TargetedBuffScanPlanner`: `MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10` (one active family per run; family #2 fallback only BEFORE any BUFF request starts); `MarketUniverseBuilder` retained as fallback utility for goods_id mapping / eligibility / hard-request bounds / diagnostics.

Reused unchanged:

- `MarketUniverseBuilder` (fallback only; not the new brain).
- `BuffListingProvider` / `BuffAnonymousListingClient` (page-1/default-sort only).
- `BuffCommunityIdentityResolver` (pinned offline community catalog, exact fail-closed).
- `BuffListingIntrinsicFlagResolver` (three-state StatTrak / Souvenir).
- `PinnedSkinMetadataResolver`.
- `scanner_recipe_composition` / `recipe_solver` (default 2 / 256; hard max 6 / 1024).
- `tradeup_engine` / `float_math`.
- `RunScopedValuationSession` (Phase 14B atomic NEW-LIVE cap).
- `ScannerCachedBuffPriceResolver` (Phase 14C FRESH_ONLY reads).
- `SteamDTBuffPriceProvider` / `steamdt_buff_price_policy` (strict BUFF selector).
- `ev_service` / `risk_filter` (final EV / risk).
- Phase 12C Redis-shared limiter (optional, via existing settings).

Out-of-scope historical compatibility (do NOT revive under Phase 16A or any later stage): `steamapis_*`, `live_metadata_catalog.py`, `live_pool_recipe_construction.py`, `steamapis_offer_session.py`, `steamapis_websocket_client.py`.

Production defaults and constraints preserved: `max_valuation_requests_per_run` default `5`; hard max `60`; `HARD_MAX_GOODS_IDS = 10`; canonical non-Souvenir output rule; `MemoryError` propagation per `D-MEMORY-001`; no auto-buy / auto-login / cookie / captcha bypass / risk-control bypass / browser automation; no second-platform fallback / no biddingPrice substitution / no metadata-zero reuse / no probability renormalization; no invented BUFF / SteamDT details.

---

## Phase 16A-R1 Coherence Corrections (2026-08-31)

Three material ambiguities in the Phase 16A design freeze are
corrected without any production code change:

1. `RecipeFamily` removes the `souvenir_inclusion` field.
   Souvenir is NOT a structural family identity axis. StatTrak
   mode IS. Normal and Souvenir inputs may coexist; concrete
   selected inputs retain true Souvenir provenance through the
   existing temporary `souvenir=False` solver projection + exact
   rehydration seam. `souvenir_inclusion` does NOT enter
   canonical RecipeFamily bytes, `family_hash`, the duplicate
   key, or the structural enumeration key. If a future targeted
   scan needs a Souvenir acquisition policy, it lives as a
   separate planner/runtime acquisition-policy field, not as
   family identity.
2. The live BUFF request envelope is bounded per run, not per
   family. `TOP_RANKED_FAMILIES = 2` is a ranking / fallback
   signal; exactly ONE family is active for one live targeted
   BUFF scan per run. Family #2 is allowed only as a fallback
   BEFORE any BUFF page request starts. Once any BUFF page
   request starts, family switching in that run is forbidden.
   Total BUFF page requests per run is
   `<= MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10`.
3. RecipeFamily enumeration is lazy and analytic. The K=3
   theoretical family-state counts (~14M total across the eight
   productive strata) are analytic evidence for the project
   bound, NOT an eager-materialization requirement.
   `RecipeFamilyGenerator` MUST support lazy deterministic
   iteration by stratum, analytic counting without materializing
   all family objects, and streaming / top-K ranking without
   retaining all family DTOs simultaneously.

Reused unchanged:

- All items from the prior Phase 16A list.
- Existing probability authority
  (`app.services.recipe_solver` /
  `app.services.scanner_recipe_composition`) is reused via
  extraction in 16B; no divergent math is introduced.
- The existing temporary `souvenir=False` solver projection +
  exact InputItem rehydration seam remains canonical.

Production defaults and constraints preserved unchanged from
the prior Phase 16A pointer.

---

## Phase 16A-R2 Output Identity / Wear Geometry (2026-08-31)

Two distinct output identities are frozen:

1. **StructuralOutputFinish** (finish-level). Used for collection
   output pool membership, trade-up structural probability,
   family geometry, and finish-level duplicate suppression. The
   frozen 6-tuple key
   `(collection_name, rarity, stattrak, name, weapon, paint_index)`
   is collision-free against the pinned snapshot (16868 wear rows
   -> 2148 distinct finish keys; 3 single-wear finishes, 2145
   multi-wear finishes of which 1791 have all 5 wear bands).
   `min_float` and `max_float` are consistent across all variants
   of one finish. The canonical non-Souvenir wear rows form a
   deterministic `(wear_name, exact_market_hash_name)` map per
   finish. Souvenir wear rows are concrete-input provenance and
   never appear in the canonical non-Souvenir output wear map.
2. **Exact market valuation identity** (canonical non-Souvenir
   `market_hash_name` for a finish + concrete output_float).
   Resolved only after wear is known. Resolution is fail-closed:
   zero / multiple mappings for the same finish + wear
   combination -> `FAIL_CLOSED`. No fuzzy / name guessing.

Structural probability operates on UNIQUE FINISH COUNTS, not
wear-qualified market rows:
`(collection_count / 10) / unique_finish_count_in_collection`.
The probability sum over `represented_output_finishes` MUST
equal 1.

`RecipeFamily` replaces `represented_outputs` with
`represented_output_finishes` (finish-level). The exact wear-qualified
output `market_hash_name` is NOT known at RecipeFamily generation
time.

The current production `tradeup_engine.calculate_tradeup_results`
treats each wear-qualified `OutputCandidate.market_hash_name` row
as a separate probability bucket. This wear-row cardinality bug
is recorded as `D-TRADEUP-WEAR-ROW-MIGRATION-001`. Phase 16B
MUST NOT silently reuse the wear-row cardinality; production math
remains unchanged in 16B. The fix is a separately gated narrow
protected-core refactor.

---

## Phase 16B Offline Structural Core Implemented (2026-09-01)

Isolated modules with zero current production callers:
- `app.services.structural_output_finish`
- `app.services.recipe_family`
- `app.services.recipe_family_geometry`

They provide immutable finish indexing, strict exact wear mapping, RecipeFamily identity/eligibility/counting/lazy generation, and finish-level exact-Fraction geometry. Production path, `tradeup_engine.py`, CLI, scanner, providers, cache, and defaults remain unchanged.

---

## Phase 16C Offline Pre-Screen Primitives Implemented (2026-09-01)

Isolated modules with zero current production callers:
- `app.services.float_interval`
- `app.services.static_float_feasibility`
- `app.services.steamdt_batch_prescreen`

They provide exact interval-union/Minkowski reachability, finish-to-wear-to-exact-name static evidence, and strict BUFF-only batch quote evidence. Production scanner remains goods-first; final valuation remains single strict BUFF; no cache/risk/EV integration exists in 16C.
