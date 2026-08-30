# DEVELOPMENT_HANDOFF.md

## Current Git State (verify live)

- **Branch:** `feature/scanner-valuation-integration` (Phase 14C functional branch). Tracked canonical `main` remains P3 (`24c95c029f583d5cc0b0a67986e48c06d0ef7957`) and is unchanged.
- **HEAD:** Phase 14C checkpoint commit `add scanner fresh-only price cache reads` (verify exact SHA from Git).
- **HEAD message:** `add scanner fresh-only price cache reads`.
- **Phase:** `PHASE_14C_COMPLETE`.
- **R0-A / R0-B / R0-C / post-R0-C docs checkpoint / R0-D:** COMPLETE. R0-D completion documentation checkpoint PR #3 merged on `main` at P3 (`24c95c029f583d5cc0b0a67986e48c06d0ef7957`); final-main push CI green (`CI` / run `33240760167`, conclusion `success`).
- **Uncommitted implementation work:** none after the Phase 14C checkpoint commit. The two protected research JSON files remain local/untracked and untouched.

Recent push history (oldest → newest) on canonical main includes:

```
b13201b sync docs after R0-C repository consolidation
9cfaf36 Merge pull request #1 from fIshy-fIsh/repo/main-consolidation
3aa44e9 reconcile main history (topology only)
4c2f1ef sync docs after minimum CI validation
7a6349e add minimum GitHub Actions CI
1dbc6f1 sync public docs and roadmap after Phase 13T
9288794 add bounded multi-recipe scale validation
33675ee wire bounded recipe enumeration CLI
ac26e9b integrate bounded multi-recipe scanner orchestration
74332e7 add bounded scanner recipe composition
4a6b85c add bounded recipe enumeration
010d8cc design bounded multi-recipe solver migration
d161ec4 add structural cohort-depth universe allocation
c543a01 add bounded automatic market universe
```

`git status` remains `0 0` against `origin/main`. Phase 13T-4B intentionally produced no commit (live observation only).

Historical reference: prior pre-R0-D active development line was `feature/steamdt-cache-rate-limit`; that branch was removed during R0-D cleanup. Its tip `4c2f1ef` is preserved as a historical DEV ancestor of `main`.

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

### Phase 13N-1 — BUF anonymous response field inventory (uncommitted)

- Design-only audit under `specs/2026-08-22-buff-identity-reality-verification/`.
- Architecture decision: **C — Freeze identity and continue synthetic-only** (per `D-IDENTITY-004`).
- Confirmed: parser reads exactly six item-level fields; `market_hash_name=None` hardcoded at construction; zero references to `classid`/`instanceid`/`appid`; smoke harness rejects `market_hash_name` if seen.
- No `app/` or `tests/` changes.

### Phase 13N-2 — BUF goods-info endpoint survey (uncommitted)

- Design-only audit under `specs/2026-08-22-buff-native-goods-identity-investigation/`.
- Architecture decision: **C — No verified source; continue identity freeze** (per `D-IDENTITY-005`).
- Goods-info endpoint is TODO `#5`; `BuffGoodsInfo` is a placeholder; `BuffHttpClient.get_goods_info` raises `NotImplementedError`. No live probe authorized.
- No `app/` or `tests/` changes.

### Phase 13N-3A — BUF community catalog identity revalidation (uncommitted)

- Research/evidence-only audit under `specs/2026-08-22-buff-community-identity-revalidation/`.
- Architecture decision: **PROVISIONAL_COMMUNITY_CATALOG_ACCEPTABLE — EricZhu-42** (per `D-IDENTITY-006`).
- Quantitative analysis of three sources:
  - EricZhu-42/SteamTradingSite-ID-Mapper `buff/730.json`: 34,402 valid records (99.96%), 0 collisions, 15 `-1` sentinels (all Sticker Slab). Commit SHA: `093adde1f9f3b0a5fd14957cd52fb988154251c3`. File SHA-256: `a7f370a61dd34f7d206e0372f6806cbcb936e1ba89e33f48bbb89adaa273d72f`.
  - ModestSerhat/cs2-marketplace-ids: 40,844 valid records, 0 collisions. License: **LICENSE_UNCLEAR**. Used as consistency-checker; not primary.
  - TimofeyIvanenko/cs2-marketplace-mapping: 35,975 valid records, 14 whitespace collisions, 1013 null. License: MIT. **Derived** from EricZhu + ModestSerhat + ByMykel; not independent.
- Cross-source independent agreement: EricZhu-42 vs ModestSerhat, 34,272 of 34,273 overlapping keys agree exactly (99.997%). One disagreement (Austin 2025 souvenir charm).
- 12-category spot check (normal weapon, knife, rare, StatTrak, Souvenir, sticker, older skin, knife Fade, vanilla Fade, three cases): all three sources unanimous.
- All ten criteria from the phase prompt satisfied for EricZhu-42 (one ⚠ on license attribution, manageable).
- Research artifacts (NOT in production tree): `research/identity_revalidation/data/{eric_zhu_730,modest_serhat,timofey_ivanenko}.json`, `research/identity_revalidation/scripts/analyze.py`, `research/identity_revalidation/analysis_report.txt`.
- No `app/`, `tests/`, `scripts/` modifications.

### Phase 13N-3B — Offline BUFF identity snapshot + bidirectional resolver (uncommitted)

- Implementation per the phase prompt and `D-IDENTITY-006`.
- **Files added:**
  - `data/identity/buff_identity_v1.json` (canonical snapshot; SHA-256 `e3aab46d570869e0b6866eac44b26bca7492ea7c2c54669e74b2b4feeec506ac`).
  - `scripts/build_buff_identity_snapshot.py` (deterministic offline builder; verifies raw source SHA-256).
  - `app/services/buff_community_identity_resolver.py` (runtime resolver; forward `resolve` + reverse `resolve_goods_id`; zero network I/O at runtime).
  - `tests/test_build_buff_identity_snapshot.py` (builder tests).
  - `tests/test_buff_community_identity_resolver.py` (runtime resolver tests).
  - `tests/test_buff_identity_pinned_snapshot.py` (integration test against the canonical snapshot).
- **Files modified:**
  - `app/services/buff_item_identity.py` (no actual change in 13N-3B; the additive `BuffGoodsIdIdentityResolver` Protocol was instead defined locally in `buff_community_identity_resolver.py` to preserve the frozen exact-public-API contract of `buff_item_identity.py` enforced by `tests/test_buff_item_identity.py`).
  - `docs/ai-context/PROJECT_CONTEXT.md`, `ARCHITECTURE_STATE.md`, `DEVELOPMENT_HANDOFF.md` (status updates per section 24 of the phase prompt).
- **Behavior:**
  - `BuffCommunityIdentityResolver.from_snapshot_path(path)` loads the snapshot once, builds forward and reverse indexes, validates schema + provenance.
  - Forward: `await resolver.resolve(market_hash_name)` returns `BuffItemIdentity | None`.
  - Reverse: `await resolver.resolve_goods_id(goods_id)` returns `BuffItemIdentity | None`.
  - Both lookups are O(1) dict reads; no I/O; no fuzzy inference.
  - All unknown or malformed lookids → `None`. Fail-closed.
- **Validation:** ruff passes; mypy passes; pytest passes 2969 / 23 skipped / 0 failed; reproducibility verified (build twice → identical bytes).
- **NOT done (intentional):** no scanner wiring, no candidate adapter change, no enrichment change, no `BuffHttpClient` change, no live BUF HTTP.

### Phase 13N-3C — BUF listing identity binding (uncommitted)

- Implementation per the phase prompt and `D-IDENTITY-006` / `D-ADAPTER-003`.
- **Architecture:** explicit composition between `BuffListingProvider` and `BuffListingCandidateAdapter`. The binding layer is **not** the adapter; the adapter still does NOT resolve identity. Identity resolution remains outside the adapter (`D-ADAPTER-003`).
- **Files added:**
  - `app/services/buff_identity_listing_provider.py` (`IdentityResolvingBuffListingProvider`, `bind_identity_to_provider`, `resolve_listings_identity`, `BuffIdentityBindingError` + three named subclasses).
  - `tests/test_buff_identity_listing_provider.py` (33 binding-layer tests).
  - `tests/test_buff_identity_listing_provider_pinned_snapshot.py` (3 pinned-snapshot integration tests).
- **Files modified:**
  - `docs/ai-context/PROJECT_CONTEXT.md`, `ARCHITECTURE_STATE.md`, `DECISION_LOG.md`, `DEVELOPMENT_HANDOFF.md` (status updates per section 19 of the phase prompt; new decision `D-IDENTITY-007`).
- **Files NOT modified (intentional):**
  - `app/services/buff_listing_provider.py` (Protected Core; composition is used instead of inheritance).
  - `app/clients/buff_anonymous_listing_client.py` (Protected Core).
  - `app/services/buff_listing_candidate_adapter.py` (adapter is unchanged; it continues to read `market_hash_name` off the supplied DTO).
  - `app/services/buff_community_identity_resolver.py`, `app/services/buff_item_identity.py`, `app/services/trade_up_input_enrichment.py`, `app/services/trade_up_input_candidate.py`.
- **Behavior:**
  - `bind_identity_to_provider(provider, resolver)` returns a wrapped provider exposing only `async get_listings(goods_id) -> list[BuffListing]`.
  - One provider fetch triggers exactly one `resolve_goods_id(goods_id)` call (verified by `test_one_provider_fetch_performs_exactly_one_identity_lookup`).
  - Resolved name is rebound onto every returned listing via `dataclasses.replace`; every other field preserved verbatim.
  - Three closed integrity failures (fail closed):
    - `resolver_goods_id_mismatch` — resolver returned identity for a different `goods_id`;
    - `listing_goods_id_mismatch` — provider returned a listing for a different `goods_id`;
    - `market_hash_name_conflict` — existing `market_hash_name` on the listing disagrees with the resolved exact name.
  - `MemoryError` propagates verbatim (consistent with `D-MEMORY-001`).
  - Unresolved `resolve_goods_id` → `market_hash_name` stays as-is (typically `None`) → adapter emits candidate with `market_hash_name=None` → enrichment rejects as `MARKET_HASH_NAME_UNRESOLVED`. No new rejection vocabulary at the adapter boundary.
- **Validation:** ruff passes; mypy passes (`75 source files`); pytest passes 3005 / 23 skipped / 1 warning (the single warning is the pre-existing Starlette/httpx deprecation in `fastapi/testclient.py`; no new `pytest.mark.asyncio` unknown-mark warning was introduced).

### Phase 13O — Intrinsic-flag three-state representation (uncommitted)

- Implementation per the phase prompt and `D-INTRINSIC-001`.
- **Architecture:** additive DTO module (`BuffListingIntrinsicFlags`) that wraps the frozen `BuffListing` and adds `stattrak: bool | None` / `souvenir: bool | None`. The wrapper delegates every other field via `__getattr__` so all existing callers continue to work transparently.
- **Files added:**
  - `app/services/buff_listing_intrinsic_flags.py` (`BuffListingIntrinsicFlags`, `IntrinsicFlagValidationError`, `coerce_intrinsic_flag`, `is_intrinsic_flag_value`, `with_intrinsic_flags`, `replace_intrinsic_flags`).
  - `tests/test_buff_listing_intrinsic_flags.py` (46 tests covering all enumerated cases 1–13 plus auxiliary).
- **Files modified (NOT Protected Core):**
  - `app/services/trade_up_input_candidate.py` — `stattrak` and `souvenir` widened from `bool = False` to `bool | None = None`. Validation now accepts `True` / `False` / `None`; rejects every other type.
  - `app/services/buff_listing_candidate_adapter.py` — added one closed rejection reason `INTRINSIC_FLAG_INVALID`. Adapter reads flags via `getattr(..., default=None)` and forwards them verbatim. Malformed values → `INTRINSIC_FLAG_INVALID`.
  - `app/services/trade_up_input_enrichment.py` — added one closed rejection reason `INTRINSIC_FLAG_UNRESOLVED`. Enricher rejects a candidate whose `stattrak` or `souvenir` is `None`.
  - `app/services/buff_identity_listing_provider.py` — added optional `stattrak` / `souvenir` keyword arguments to `get_listings` and `resolve_listings_identity`. The binding layer wraps every returned listing in `BuffListingIntrinsicFlags`. Defaults are `None`.
  - `tests/test_buff_listing_candidate_adapter.py` — replaced `test_stattrak_default_is_false` / `test_souvenir_default_is_false` with `test_stattrak_default_is_none_when_listing_does_not_expose_it` / `test_souvenir_default_is_none_when_listing_does_not_expose_it`. Added forwarding, malformed-rejection, and `INTRINSIC_FLAG_UNRESOLVED` tests.
  - `tests/test_trade_up_input_candidate.py` — replaced `test_intrinsic_flag_defaults_are_false_and_independent` with `test_intrinsic_flag_defaults_are_none_and_independent`; added three-state-distinction tests; updated the rejection parametrization (removed `None` from the rejection list; `None` is now valid).
  - `tests/test_buff_identity_listing_provider.py` — updated two tests for the new intrinsic-flag keyword arguments and the wrapper semantics. Renamed `test_adapter_rejection_vocabulary_unchanged` → `test_adapter_rejection_vocabulary_added_intrinsic_flag_invalid`.
  - `tests/test_buff_identity_listing_provider_pinned_snapshot.py` — updated the full-seam test to pass explicit `stattrak=False, souvenir=False`.
  - `docs/ai-context/PROJECT_CONTEXT.md`, `ARCHITECTURE_STATE.md`, `DECISION_LOG.md`, `DEVELOPMENT_HANDOFF.md` (status updates; new decision `D-INTRINSIC-001`).
- **Files NOT modified (Protected Core preserved):**
  - `app/services/tradeup_engine.py` (frozen; `InputItem.stattrak: bool = False` preserved).
  - `app/services/buff_listing_provider.py` (frozen; wrapped, not edited).
  - `app/clients/buff_anonymous_listing_client.py` (frozen).
  - `app/services/buff_listing_facts.py` and other Phase-12 BUFF domain files (frozen).
  - All trade-up / valuation / risk / engine / solver modules.
- **Behavior:**
  - **Three-state representation:** `True` (established true), `False` (established false), `None` (not established by this source).
  - **No fabrication.** Default is `None`, never `False`.
  - **No inference.** No inference from `goods_id`, `listing_id`, `asset_id`, `paintseed`, `price`, `URL`, or any other BUFF response field.
  - **Strict validation.** `int 0/1`, `str "true"/"false"`, `float`, `bool` subclasses, etc. are rejected at the candidate boundary, the adapter boundary, and the wrapper boundary.
  - **Verbatim preservation.** Every other `BuffListing` field is preserved exactly via `__getattr__` delegation; no mutation of the underlying DTO.
  - **Fail-closed at the enrichment boundary.** A candidate with `None` flags is rejected as `INTRINSIC_FLAG_UNRESOLVED`; the listing never reaches the engine under a fabricated flag.
- **Source capability:** **UNKNOWN** — the authorized anonymous BUFF sell-order payload does not currently expose these fields. No verification has been authorized. The `None` default is therefore the only correct representation.
- **Validation:** ruff passes; mypy passes (`76 source files`); pytest passes 3059 / 23 skipped / 1 warning (the single warning is the pre-existing Starlette/httpx deprecation; no new unknown-mark warning was introduced).

### Phase 13O-1 — Intrinsic-flag canonical-name classifier + binding separation (uncommitted)

- Implementation per the phase prompt and `D-INTRINSIC-002`.
- **Goal:** determine whether intrinsic flags can be reliably established from canonical `market_hash_name`, and separate identity binding from intrinsic-flag binding.
- **Result:** **YES** for both flags. The canonical Steam community market naming convention establishes the values deterministically. The two binding layers are now strictly separated.
- **Files added:**
  - `app/services/buff_intrinsic_flag_resolver.py` (`CanonicalNameIntrinsicFlagResolver`, `BuffListingIntrinsicFlagResolver` Protocol, `BuffListingIntrinsicFlagsValue` value object, `STATTRAK_PREFIX`, `SOUVENIR_PREFIX`, `IntrinsicFlagInputError`).
  - `app/services/buff_intrinsic_flag_listing_provider.py` (`IntrinsicFlagResolvingBuffListingProvider`, `bind_intrinsic_flags_to_provider`).
  - `tests/test_buff_intrinsic_flag_resolver.py` (50 tests covering all enumerated cases 1–20 plus auxiliary).
  - `scripts/analyze_intrinsic_prefix_catalog.py` (offline analysis script for the pinned catalog).
- **Files modified (NOT Protected Core):**
  - `app/services/buff_identity_listing_provider.py` — removed the `stattrak` / `souvenir` keyword arguments from `get_listings` and `resolve_listings_identity`. Identity binding is identity-only again. The binding layer now returns plain `BuffListing` instances.
  - `tests/test_buff_identity_listing_provider.py` — updated two tests for the new architecture (`test_resolved_listing_flows_into_adapter_and_enricher` → `test_resolved_listing_flows_through_full_seam`; `test_existing_market_hash_name_equal_to_resolved_is_preserved` reflects plain-`BuffListing` return).
  - `tests/test_buff_identity_listing_provider_pinned_snapshot.py` — added a `_wrap_with_intrinsic_flags` helper that composes the identity binding with the intrinsic-flag binding for the full seam.
  - `tests/test_buff_listing_intrinsic_flags.py` — updated `test_wrapper_survives_async_binding_flow` to use the intrinsic-flag binding layer.
  - `docs/ai-context/PROJECT_CONTEXT.md`, `ARCHITECTURE_STATE.md`, `DECISION_LOG.md`, `DEVELOPMENT_HANDOFF.md` (status updates; new decision `D-INTRINSIC-002`).
- **Files NOT modified (Protected Core preserved):**
  - `app/services/tradeup_engine.py` (frozen).
  - `app/services/buff_listing_provider.py` (frozen).
  - `app/clients/buff_anonymous_listing_client.py` (frozen).
  - `app/services/buff_listing_facts.py` and other Phase-12 BUFF domain files (frozen).
  - `app/services/trade_up_pipeline.py` (legacy synthetic-only; documented debt per `D-MIGRATION-001` and `D-MIGRATION-002`).
- **Empirical evidence:**
  - Pinned catalog `data/identity/buff_identity_v1.json` (SHA-256 `e3aab46d...`, 34,402 accepted entries):
    - 3,377 names start with `'StatTrak™ '` (`stattrak=True`).
    - 2,345 names start with `'Souvenir '` (`souvenir=True`).
    - 28,680 names start with neither prefix (`stattrak=False`, `souvenir=False`).
    - 0 names start with both prefixes simultaneously (mutually exclusive).
    - 0 empty or whitespace-padded names.
    - All `'StatTrak™ '` canonical-string-prefix variants are exact; no alternative spellings.
  - **Independent totals (Phase 13O-1A verified):**
    - `stattrak_true=3377`, `stattrak_false=31025` (34402 − 3377).
    - `souvenir_true=2345`, `souvenir_false=32057` (34402 − 2345).
    - `stattrak_true + stattrak_false == 34402`.
    - `souvenir_true + souvenir_false == 34402`.
  - **Joint counts (Phase 13O-1A verified):**
    - `(stattrak=True, souvenir=True)=0`
    - `(stattrak=True, souvenir=False)=3377`
    - `(stattrak=False, souvenir=True)=2345`
    - `(stattrak=False, souvenir=False)=28680`
    - The four joint counts partition the catalog exactly.
  - **Prefix lengths:** `'StatTrak™ '` is 10 Unicode codepoints / 12 UTF-8 bytes. `'Souvenir '` is 9 Unicode codepoints / 9 UTF-8 bytes.
  - **Contradictions:** 0 (zero contradictions under the canonical-name rule on the pinned catalog).
  - **Coverage:** 100% (every well-formed canonical name is classified `True` or `False`; `None` is reserved for unresolved identity or unknown-source resolvers).
- **Important distinction:** the BUFF `sell_order` payload itself does NOT provide these flags. The flags are derived from the canonical `market_hash_name`. The classifier is catalog-derived exact canonical-name classification, corroborated by observed Steam market naming/category behavior.
- **Architecture (final pipeline):**

  ```
  BuffListingProvider
    ↓
  IdentityResolvingBuffListingProvider          (13N-3C; identity-only)
    ↓
  IntrinsicFlagResolvingBuffListingProvider    (13O-1; intrinsic-flag-only; canonical-name classifier)
    ↓
  BuffListingCandidateAdapter                  (13K-1; reads off the DTO)
    ↓
  TradeUpInputCandidate (bool | None)          (13O; widened fields)
    ↓
  TradeUpInputEnrichment                       (rejects None as INTRINSIC_FLAG_UNRESOLVED)
    ↓
  InputItem                                    (frozen; bool required)
  ```
- **Validation:** ruff passes; mypy passes (`78 source files`); pytest passes 3109 / 23 skipped / 1 warning.

### Phase 13O-1A — Intrinsic classifier correctness audit (uncommitted)

- Narrow correctness/fix audit of Phase 13O-1. Implementation was correct; analysis, terminology, and call-count semantics required correction.
- **Files added:** none (audit and fixes only).
- **Files modified:**
  - `app/services/buff_intrinsic_flag_resolver.py` — corrected terminology: "exact-byte" → "exact-canonical-string-prefix"; documented exact codepoint/UTF-8 lengths for both prefixes.
  - `app/services/buff_intrinsic_flag_listing_provider.py` — replaced the per-listing resolver invocation with **per-page** invocation; added `_extract_canonical_name` helper that verifies every non-`None` `market_hash_name` in the page is identical and fails closed (`IntrinsicFlagInputError`) when conflicting names appear.
  - `app/services/buff_identity_listing_provider.py` — added a defensive page-level canonical-name consistency check (the per-listing `existing == resolved_name` check already enforces this for the common case; the new check is a guard against future refactors).
  - `tests/test_buff_intrinsic_flag_resolver.py` — added 14 new tests covering: per-page resolver count, prefix length assertions (codepoint + UTF-8), pinned-catalog matrix invariants (independent and joint counts), canonical-sample classification, unresolved-identity propagation, malformed-input raising `IntrinsicFlagInputError`, deterministic full-catalog result, inconsistent-page fail-closed, three-distinct-pages-each-make-one-resolver-call, and empty-list behavior.
  - `scripts/analyze_intrinsic_prefix_catalog.py` — corrected terminology and output format; now reports independent and joint counts correctly.
  - `docs/ai-context/DECISION_LOG.md` — `D-INTRINSIC-002` revised: replaced "exact-byte" with "exact canonical-string"; documented exact codepoint/UTF-8 lengths; added independent totals and joint counts; clarified that the rule is "catalog-derived exact canonical-name classification, corroborated by observed Steam market naming/category behavior" (not a formal Steam schema contract); emphasized that the BUFF `sell_order` payload itself does NOT provide these flags.
  - `docs/ai-context/ARCHITECTURE_STATE.md` — corrected terminology in 13O-1 entries; documented independent and joint counts; documented per-page resolver-call semantics.
  - `docs/ai-context/DEVELOPMENT_HANDOFF.md` — added prefix-length documentation; added independent-totals block; added joint-counts block; added important-distinction block.
- **Files NOT modified (Protected Core preserved):**
  - `app/services/tradeup_engine.py` (frozen).
  - `app/services/buff_listing_provider.py` (frozen).
  - `app/clients/buff_anonymous_listing_client.py` (frozen).
  - All Phase-12 BUFF domain files (frozen).
- **Root cause of the prior audit findings:**
  - The previous final report conflated "both flags == False" with "single flag == False". The correct independent totals are `stattrak_false=31025` and `souvenir_false=32057`, not `28680`. The implementation was correct; only the documentation and analysis were wrong.
  - The previous terminology used "9-byte prefix" for `'StatTrak™ '` (incorrect: 10 codepoints / 12 UTF-8 bytes). Implementation used Python `str.startswith` (codepoint semantics) — correct; only the wording was wrong.
  - The previous binding layer invoked the intrinsic resolver once per listing. After auditing, the binding layer now invokes the resolver exactly once per page because every non-`None` `market_hash_name` in the page must share the same canonical value (an invariant the identity-binding stage already enforces; the new check is a defensive guard).
- **Validation:** ruff passes; mypy passes (`78 source files`); pytest passes 3126 / 23 skipped / 1 warning.

### Phase 13P — Live read-only one-shot opportunity scanner MVP (uncommitted)

- **Application files added:**
  - `app/services/scanner_orchestrator.py` — `LiveScannerOrchestrator.run_once(goods_ids)`, immutable `ScannerRunResult`, `ScannerRunStageCounters`, `ScannerRunDiagnostics`, `LiveOpportunity`.
  - `app/services/skin_metadata_resolver.py` — pinned local exact-name `PinnedSkinMetadataResolver` implementing the existing `TradeUpInputMetadataResolver` and exposing the immutable existing `SkinMetadata` catalog to `recipe_solver`.
  - `scripts/run_live_scan_once.py` — explicit manual CLI, one cycle, human or `--json` output, then exit. Read-only.
  - `scripts/build_skin_metadata_snapshot.py` — deterministic offline builder for the pinned metadata snapshot; verifies ByMykel raw SHA-256 and emits canonical compact UTF-8 JSON.
  - `data/metadata/skin_metadata_v1.json` — pinned metadata snapshot derived from `ByMykel/CSGO-API` at commit `8a785962b291d57a023b79408416c6792782712e`; raw source SHA-256 `7aeb9582c5f3308be78c78d2fd3681e3c469c67c0aeeeb7a9e54adb5c3be32d7`; canonical snapshot SHA-256 `55e4d446a5343e1932f24b9069090431f87b0c750d2cb4c091947ec2411dc421`; MIT. 16,868 exact wear-qualified variants.
  - `research/metadata/by_mykel_skins.json` — pinned raw source required for snapshot reproducibility (5.5 MB).
- **Tests added:**
  - `tests/test_skin_metadata_resolver.py` — exact lookup, unknown/case/whitespace no-match, Unicode, malformed/duplicate snapshot rejection, validation, O(1), static/no-network, MemoryError, pinned catalog load.
  - `tests/test_scanner_orchestrator.py` — clean run, zero listings, per-goods failure isolation, unresolved identity/intrinsic, metadata unresolved, recipe/valuation/risk branches, ordering, diagnostics, invocation counts, hard max, MemoryError, repeatability, pinned full seam.
- **Pipeline:** `BuffListingProvider → IdentityResolvingBuffListingProvider → IntrinsicFlagResolvingBuffListingProvider → BuffListingCandidateAdapter → TradeUpInputCandidate → TradeUpInputEnrichment → InputItem → recipe_solver.construct_recipe_selections → ValuationService.value_tradeup_results → calculate_opportunity_metrics → evaluate_opportunity → LiveOpportunity`.
- **Opportunity acceptance:** complete valuation + existing `RiskDecision.passed == True`; no Phase-13P-specific thresholds. Config values come from existing settings (`sell_fee_rate`, `min_roi`, `min_expected_profit_cny`, `max_worst_case_loss_pct`, `min_profit_probability`, `max_input_total_cost_cny`).
- **Universe:** explicit goods-id allowlist, first-seen dedupe, hard max 10, sequential processing (concurrency 1).
- **Safety:** no scheduler, daemon, background loop, Discord requirement, auto-buy, purchase, login, cookies, marketplace writes, browser automation, CAPTCHA/risk-control bypass, proxy/UA rotation, new BUFF endpoint, Redis, or DB changes.
- **Protected Core:** unchanged; the new orchestrator composes existing public APIs.
- **Validation:** ruff passes; mypy passes (80 source files); pytest passes 3160 / 23 skipped / 1 warning. Manual live smoke completed (read-only): goods_id `34279`, 1 BUFF request, 10 listings/candidates/metadata/InputItems, 1 recipe, 0 opportunities. Valuation failed closed because `STEAMDT_DRY_RUN=true` and no API key was available; the rest of the seam was verified live.

### Phase 13R — Bounded market universe builder + multi-goods live scan (uncommitted)

- **Application file added:** `app/services/market_universe_builder.py` — pure offline deterministic planner. Joins the exact pinned BUFF identity and metadata catalogs by `market_hash_name`, applies one input rarity (`RarityOrder.ORDER[:5]`), one homogeneous StatTrak mode, optional Souvenir inclusion policy, optional exact collection allowlist, hard bound `1..10`. Reuses `is_current_standard_trade_up_output_eligible` and `get_next_rarity`. Deterministic collection round-robin sorted by `(collection_name, stattrak, souvenir, len(market_hash_name), market_hash_name)`. Returns `MarketUniverseResult` with truthful disjoint diagnostics. `MemoryError` propagates verbatim; ordinary contract failures collapse to `BoundedMarketUniverseBuilderError(reason=...)`. No network imports.
- **Additive resolver change:** `app/services/buff_community_identity_resolver.py` gains a public read-only `identities: tuple[tuple[str, str], ...]` property, ordered by `(len(market_hash_name), market_hash_name)`. Built once in `__init__`; existing private `_forward`/`_reverse`/`_items_tuple` and the existing `BuffGoodsIdIdentityResolver` Protocol surface remain unchanged.
- **CLI changes:** `scripts/run_live_scan_once.py` adds `--auto-universe` (mutually exclusive with `--goods-id`), `--stattrak-mode`, `--souvenir`, `--collection` (repeatable), `--max-goods-ids 1..10`, `--universe-preview` (exits before any settings/client construction). Manual `--goods-id` path is preserved byte-identically; default rarity `Restricted`, default valuation cap 5, existing flags unchanged.
- **Tests added:** `tests/test_market_universe_builder.py` (17 pure offline tests including `identities` property determinism, exact intersection, rarity/StatTrak/Souvenir filtering, collection allowlist, deterministic ordering, hard bound, `MemoryError`, AST no-network guard); `tests/test_market_universe_orchestrator_integration.py` (real `PinnedSkinMetadataResolver` + `BuffCommunityIdentityResolver` + `BuffListingProvider` + `LiveScannerOrchestrator.run_once` pinned Cobblestone pair, with `valuation_service=None`); `tests/test_run_live_scan_once.py` (mutually-exclusive sources, `--auto-universe` defaults, `--universe-preview` no-client proof with monkeypatched `httpx.AsyncClient`, `SteamDTHttpClient`, `BuffAnonymousListingHttpClient`, `BuffListingProvider`, `ValuationService`, `LiveScannerOrchestrator`).
- **Offline preview:** `py -3.13 scripts/run_live_scan_once.py --auto-universe --rarity Restricted --stattrak-mode normal --souvenir include --max-goods-ids 10 --universe-preview` selects 10 goods IDs round-robin across 10 collections, prints truthful disjoint diagnostics, exits 0, and constructs no settings/HTTP client/BUFF or SteamDT adapter.
- **Live verification (2026-08-25):** `py -3.13 scripts/run_live_scan_once.py --auto-universe --rarity Restricted --stattrak-mode normal --souvenir include --max-goods-ids 10 --max-valuation-requests 20` selected 10 goods IDs (one per collection across 10 collections), succeeded 10/10, fetched 71 listings, built one recipe (`Dual Berettas | Twin Turbo` × `SG 553 | Integrale` × 5 wear values), attempted 10 SteamDT `PRICE_SINGLE` lookups (10 succeeded, 0 failed, 0 blocked), and produced `RiskDecision.passed=False` under unchanged thresholds. Zero opportunities passed (expected under current market conditions and unchanged policy). No scheduler, no auto-buy, no marketplace writes.
- **Protected Core:** unchanged. The planner lives outside Protected Core and uses only existing public catalog surfaces and the existing current-rule output eligibility. `scanner_orchestrator.py`, `scanner_recipe_composition.py`, `recipe_solver.py`, `tradeup_engine.py`, `ev_service.py`, `risk_filter.py`, `valuation_service.py`, `live_recipe_valuation.py`, all `steamdt_*`, all `buff_listing_*`, and all metadata providers were not modified.
- **Failure semantics:** per-goods acquisition failure isolation, sequential execution, run-wide input pool, valuation cap fail-closed behavior, exact candidate-owned input flag rehydration, and all Phase 13P-4 regressions are preserved.

### Phase 13S — Structural coverage allocation + recipe-depth universe (uncommitted)

- **Planner model:** `app/services/market_universe_builder.py` now separates exact Phase 13R eligibility from explicit allocation. `BREADTH` remains the default and preserves the exact collection round-robin sequence. `COHORT_DEPTH` is opt-in and uses collection-local allocation cohorts `(collection_name, rarity, stattrak)`. Legal recipe compatibility remains `(rarity, stattrak)`; collections may mix and normal/Souvenir inputs remain compatible under the May-2026 seam.
- **Depth algorithm:** rank by descending exact eligible catalog capacity, then `(collection_name, rarity, stattrak)`; select up to `target_cohort_count` (default 3); distribute slots in repeated fair rounds among the selected cohorts. At budget 10, three sufficient cohorts receive `4/3/3`. Capacity exhaustion redistributes within the target only. Normal/Souvenir identities are separately `(len, name)` sorted and deterministically interleaved. Capacity is catalog structure, not liquidity or live availability.
- **Diagnostics/CLI:** immutable entries, cohort keys, and per-cohort allocations expose exact capacities, normal/Souvenir counts, canonical output count, allocated slots, and selected IDs/names. CLI adds auto-only `--allocation {breadth,cohort-depth}` and `--target-cohorts`; manual use fails closed; no-network preview includes cohort diagnostics before any settings/client construction.
- **Offline comparison:** same Restricted/normal/include/cap-10 spec. BREADTH retained the Phase 13R 10-collection sequence (10 × 1). COHORT_DEPTH selected The 2018 Nuke Collection (4), The Anubis Collection (3), and The Overpass 2024 Collection (3), each with catalog capacity 30 (15 normal + 15 Souvenir) and 10 canonical output metadata rows.
- **Controlled integration:** deterministic synthetic availability at the same 10-goods budget yielded BREADTH `3 InputItems / 0 recipes` and COHORT_DEPTH `10 InputItems / 1 recipe`. This demonstrates structural constructibility only. The protected greedy solver still emits at most one selection per StatTrak bucket; no claim of multiple recipes, live availability, or profit is made.
- **Live verification (2026-08-25; exactly one depth run):** selected 10 goods IDs in `4/3/3`; 10 requested/10 succeeded/0 failed; 94 listings, candidates, metadata resolutions, and InputItems; 1 recipe evaluated, 1 fully valued, 0 valuation failures; 10 SteamDT requests attempted/succeeded, 0 failed/blocked; unchanged risk policy rejected the recipe; 0 opportunities. Compared with Phase 13R: 1 recipe -> 1 recipe, delta 0; listings/InputItems increased 71 -> 94 while selected collections decreased 10 -> 3. No post-run tuning or second live run.
- **Validation:** ruff passes; mypy passes (82 source files); pytest passes 3246 / 23 skipped / 1 warning; explicit synthetic scale passes 20; `git diff --check` passes. Protected Core, scanner/orchestrator/composition, metadata resolver, provider/client, snapshots, valuation/risk math and thresholds are untouched.
- **Safety/network:** one-shot, read-only, concurrency 1; 10 BUFF page acquisitions plus 10 SteamDT price requests succeeded as reported by existing counters/provider behavior. No scheduler, retry loop outside existing provider policies, auto-buy, order, purchase, trade, login, cookie, browser automation, or marketplace write.

### Phase 13P-1 — Live SteamDT valuation verification + request guard (uncommitted)

- **Live gate:** `scripts/run_live_scan_once.py::validate_live_valuation_config` refuses live work unless `STEAMDT_DRY_RUN=false`, `STEAMDT_API_KEY` is present, and valuation cap is 1..60. Gate executes before HTTP client construction. Current configuration is blocked (`dry_run=True`, key absent), producing `LIVE_VALUATION_BLOCKED_BY_CONFIGURATION` and exit code 2. No second live BUFF or SteamDT request was issued.
- **Request cap:** `LiveScannerOrchestrator(max_valuation_requests_per_run=...)` requires an explicit finite cap in `[1, 60]`; CLI default is 5. Unique output names are counted before each valuation. If the remaining budget is insufficient, the entire recipe is rejected before any lookup; no partial or fabricated valuation.
- **Accounting:** `ScannerRunStageCounters` now exposes `recipes_fully_valued`, `recipes_valuation_failed`, `valuation_requests_attempted`, `valuation_requests_succeeded`, `valuation_requests_failed`, `valuation_requests_blocked`. `LiveRecipeEvaluation` records requested output names, resolved-price count, missing names, errors, valued results, existing metrics, existing RiskDecision, and rejection reason.
- **Completeness:** missing names, provider errors, fewer quotes than requested, exceptions, and cap rejection cannot produce `LiveOpportunity`. Opportunity rule remains complete valuation + existing `RiskDecision.passed is True`.
- **CLI:** preserves `--json`; human output now prints valuation accounting and live-valued recipe metrics/risk reasons from existing DTO values without recomputation.
- **Units:** BUFF input `price_cny` and SteamDT BUFF output sell prices are interpreted as CNY under `D-STEAMDT-002`; no FX conversion. Fees are Decimal fractions; EV/profit/worst/best values are CNY; ROI dimensionless Decimal; probabilities float.
- **Freshness/cache:** SteamDT source `update_time` is not exposed by generic `PriceQuote(raw=None)`. Current CLI directly wires SteamDTHttpClient; cache-hit count and source timestamp are not measurable and are not invented.
- **Tests added/updated:** config-gate refusal/acceptance, cap validation/exact boundary/exceeded, incomplete valuation, complete risk pass/fail, request counts, MemoryError, unit invariants, effective CLI default. Normal pytest remains offline.
- **Validation:** ruff passes; mypy passes (80 source files); pytest passes 3177 / 23 skipped / 1 warning; synthetic scale gate 20 passes. Protected Core unchanged.

### Phase 13P-3 — SteamDT live price-provider diagnosis (uncommitted)

- **Diagnosis:** `ROOT_CAUSE_CONFIRMED`. The Phase 13P CLI injected `httpx.AsyncClient(timeout=10.0)` without `base_url`; `SteamDTHttpClient._request_json` uses a relative endpoint path for injected clients. The previous 4/4 failures were `SteamDTTransportError` before HTTP status/parse, surfaced as `STEAMDT_BUFF_PRICE_LOOKUP_FAILED`.
- **Minimal fix:** `scripts/run_live_scan_once.py::build_steamdt_http_client` creates the injected client with `base_url=settings.steamdt_base_url`. No endpoint, authentication, headers, timeout, retry, rate-limit, valuation, EV, or risk semantics changed. Protected Core unchanged.
- **Regression:** `tests/test_run_live_scan_once.py::test_steamdt_borrowed_http_client_has_configured_base_url` verifies the borrowed client has `https://open.steamdt.com` as its base URL.
- **Post-fix diagnostic:** exactly four sequential `PRICE_SINGLE` calls; all HTTP 200 and parsed. BUFF price selection succeeded for 3/4. `M4A1-S | Knight (Minimal Wear)` failed strict selection as `buff_sell_price_non_positive`; all other requested names produced a selected BUFF sell price. No additional BUFF scan was performed.
- **Response shape:** wrapper keys `data`, `errorCode`, `errorCodeStr`, `errorData`, `errorMsg`, `success`; data is list; row keys `platform`, `platformItemId`, `sellPrice`, `sellCount`, `biddingPrice`, `biddingCount`, `updateTime`; exactly one BUFF row in each response.
- **Validation:** full regression rerun because code changed; ruff/mypy/pytest/synthetic-scale/diff-check all pass (see latest session report).

### Phase 13P-4 — Current trade-up intrinsic semantics correction (uncommitted)

- **Domain correction:** Valve's rule effective May 21, 2026 permits Souvenir quality items alongside normal quality items in the standard Trade Up Contract. Selected Souvenir input attributes are removed for result construction, and the resulting item is normal quality one tier higher from represented collections. Older statements that Souvenir cannot trade up, normal/Souvenir cannot mix, or Souvenir input implies Souvenir output are superseded by `D-TRADEUP-001`.
- **Pre-fix reproduction:** `metadata_service.build_output_candidates_by_collection` admitted every next-rarity row from the full pinned catalog. For The Cobblestone Collection / Restricted input this yielded four Knight names: normal Factory New, normal Minimal Wear, Souvenir Factory New, and Souvenir Minimal Wear.
- **Application file added:** `app/services/scanner_recipe_composition.py` — pure current-rule composition boundary. It validates candidate-owned facts, applies `target_souvenir` before projection, buckets StatTrak independently, selects canonical `souvenir=False` output metadata with matching StatTrak mode, invokes unchanged Protected Core through an internal `souvenir=False` compatibility view, and restores exact candidate-owned `InputItem` values before return. No prefix stripping or canonical metadata mutation.
- **Orchestrator change:** `app/services/scanner_orchestrator.py` now accumulates enriched inputs/listing provenance across the existing bounded goods-ID run and constructs once after acquisition. Per-goods acquisition isolation, hard max 10, sequential execution, valuation cap/accounting, EV/ROI, risk, and no-write behavior remain unchanged. Duplicate cross-page listing IDs fail closed.
- **Knight correction:** current output names are exactly `M4A1-S | Knight (Factory New)` and `M4A1-S | Knight (Minimal Wear)`; no `Souvenir M4A1-S | Knight ...` reaches valuation.
- **Input/provenance invariant:** normal-only, Souvenir-only, and mixed normal/Souvenir inputs are supported. Returned recipe inputs and risk evaluation retain exact candidate-owned Souvenir facts; the compatibility projection cannot escape.
- **StatTrak invariant:** unchanged and separate. StatTrak/non-StatTrak inputs are never mixed; canonical output records match the input StatTrak mode while remaining non-Souvenir.
- **Metadata integrity:** `data/metadata/skin_metadata_v1.json` is unchanged; Souvenir variants still exist and remain exactly resolvable as inputs.
- **Tests:** new `tests/test_scanner_recipe_composition.py`; expanded `tests/test_scanner_orchestrator.py` for run-wide mixed inputs, provenance, risk visibility, normal-only valuation names, duplicate IDs, and MemoryError identity.
- **Protected Core / provider:** no Protected Core, SteamDT provider/policy/client, BUFF provider/client, profitability threshold, valuation formula, scheduler, or universe change. Phase 13P-3 HTTPX `base_url` fix remains intact; `buff_sell_price_non_positive` remains strict failure.
- **Network:** Phase 13P-4 is entirely offline; BUFF requests 0, SteamDT requests 0.
### Phase 13P-5 — Post-semantics fully live opportunity-path validation (no code changes)

- **Status:** `LIVE_OPPORTUNITY_PATH_VERIFIED` on 2026-08-25.
- **Knight gate:** one bounded live scan for goods ID `34279` consumed ten real BUFF listings and requested exactly `M4A1-S | Knight (Factory New)` plus `M4A1-S | Knight (Minimal Wear)`; no Souvenir Knight output reached SteamDT. Factory New resolved. Minimal Wear retained the strict expected `buff_sell_price_non_positive` selection failure, so the recipe stayed incomplete without any fallback.
- **Complete path:** a second bounded technical scan selected goods ID `35458` solely because exact identity/metadata and a two-name canonical output universe were available. Ten real `MAC-10 | Urban DDPAT (Well-Worn)` BUFF listings formed one recipe. Both `PP-Bizon | Carbon Fiber` output prices resolved through the live SteamDT BUFF sell policy, valuation completed, `calculate_opportunity_metrics` ran, and `evaluate_opportunity` returned a real `RiskDecision.passed=False` under unchanged thresholds.
- **Outcome:** zero opportunities passed, but the complete `live BUFF → identity → intrinsic → metadata → recipe → SteamDT → valuation → EV/ROI → RiskDecision` path is verified. No projected compatibility input escaped; the live recipes retained original non-Souvenir/non-StatTrak input facts.
- **Request totals:** two bounded BUFF requests and four SteamDT price requests across the two manual runs; concurrency one; no scheduler/loop.
- **Safety:** no code/config changes, threshold changes, price substitution, auto-buy, login, cookies, marketplace writes, browser automation, or evasion behavior.

### Phase 13T Design Freeze — design only (committed `010d8cc`)

- `specs/2026-08-26-multi-recipe-solver-migration/{requirements,plan,validation}.md` finalized Option B: additive bounded enumerator with strict legacy equivalence, greedy-first + radius-one, default `2 / 256`, hard bounds `6 / 1024`, no financial ranking, candidate identity `(source, goods_id, listing_id)`.

### Phase 13T-1 — Protected Core bounded recipe enumerator (committed `4a6b85c`)

- Adds `RecipeEnumerationConfig`, `RecipeEnumerationDiagnostics`, `RecipeEnumerationResult`, `enumerate_recipe_selections(…)`. Defaults `2 / 256`; hard bounds `1..6` candidates, `1..1024` states with `states >= candidates`; baseline first then deterministic radius-one substitutions ordered by `(r-d, r, d, RecipeSelectionKey)`; canonical offer identity `(source, goods_id, listing_id)`; duplicate canonical key fails closed before sort/cap/search. Legacy `construct_recipe_selections`, `construct_recipes`, `solve_recipes` remain unchanged.

### Phase 13T-2 — Scanner composition enumeration adapter (committed `74332e7`)

- Adds `enumerate_scanner_recipe_selections(…)`, `ScannerRecipeCompositionDiagnostics`, `ScannerRecipeBucketDiagnostics`. Per-bucket fair-share aggregate candidate/state budgets (first `min(active_count, C)` participate; no redistribution; no second pass). Exact candidate-owned `InputItem` rehydration after temporary `souvenir=False` solver projection; projected inputs never escape.

### Phase 13T-3A — Orchestrator bounded enumeration integration (committed `ac26e9b`)

- `LiveScannerOrchestrator` accepts `enumeration_config: RecipeEnumerationConfig | None = None` (default `2 / 256`) and consumes `enumerate_scanner_recipe_selections` in `run_once`. Cumulative valuation budget, atomic fail-closed semantics, sequential valuation, and ordering guarantees preserved.

### Phase 13T-3B — CLI enumeration wiring (committed `33675ee`)

- `scripts/run_live_scan_once.py` exposes `--max-recipe-candidates-returned` and `--max-candidate-states-explored` (argparse integer syntax). CLI constructs exactly one `RecipeEnumerationConfig` and forwards it to `LiveScannerOrchestrator`. Domain validation authority remains `RecipeEnumerationConfig`.

### Phase 13T-4A — Offline bounded multi-recipe scale validation (committed `9288794`)

- `tests/test_multi_recipe_scanner_scale_validation.py` (4 tests). Primary fixture: 10 goods / 100 InputItems / 901 theoretical radius-one states / 2 returned / 2 explored; baseline `P0..P9` and first alternative `P0..P8 + P10`; 10 inputs each, 9 shared, 1 replacement. Exact-cap=20 → 2 fully valued; one-below=19 → 1 fully valued + 1 atomically blocked. Two-bucket fixture under `C=2, S=256`: `candidate_quota 1 / 1` and `state_quota 128 / 128`, both buckets returned 1 candidate / 1 state. 1/1 legacy compatibility verified (bounded orchestrator result equals legacy `construct_scanner_recipe_selections` output for the same enriched inputs). Determinism verified across independently reset runs. Regression baseline: `4 + 100 + 35 + 39 + 37 + 3336 passed, 23 skipped, 20 historical`.

### Phase 13T-4B — One bounded live validation (no commit, no repository artifact; `LIVE_VALIDATION_PASSED_NO_COMPLETE_VALUATION`)

- One `--auto-universe --allocation cohort-depth --target-cohorts 3` run, performed against commit `9288794`. Planned universe: 10 goods IDs across three cohorts (The 2018 Nuke Collection / The Anubis Collection / The Overpass 2024 Collection). Live BUFF pages: 10/10 succeeded; 95 listings → 95 enriched InputItems. Real bounded composition returned 2 recipe candidates; under effective `max_valuation_requests_per_run=5`, recipe 0 required 10 unique output names and recipe 1 required 20. Both recipes were atomically blocked before any SteamDT HTTP/provider request; `valuation_requests_attempted=0`, `valuation_requests_blocked=30` (=10+20), `provider_calls=0`, `recipes_fully_valued=0`, `risk_evaluated=0`, `opportunities=0`. Frozen contracts held.
- SteamDT live mode configured during Phase 13T-4B: YES (`STEAMDT_DRY_RUN=false`).
- SteamDT HTTP/provider requests issued during Phase 13T-4B: 0. The cumulative-budget boundary blocked both recipes before any provider lookup; the 5 available request slots were not partially consumed.
- Phase 13T-4B did not exercise SteamDT HTTP and did not complete a live SteamDT valuation. Run-level SteamDT output-price cache remains NOT IMPLEMENTED.

### R0-A — Public Documentation Synchronization (committed/pushed `1dbc6f1`)

- **Status:** **COMPLETE**. Public README, roadmap, mission, architecture, specification, project description, CLAUDE pointer, and PROJECT_CONTEXT were synchronized after Phase 13T.
- Durable baselines distinguish Phase 13T production/test checkpoint `9288794`, post-Phase-13T handoff baseline `bb09068`, and live Git state, which must be verified from Git.

### R0-B — Minimum CI (committed/pushed `7a6349e`)

- **Status:** **COMPLETE**. `.github/workflows/ci.yml` runs on `push` and `pull_request` with `contents: read`, `ubuntu-latest`, Python 3.12, `python -m pip install -e ".[dev]"`, `ruff check .`, `mypy app`, and `pytest`.
- Local validation: ruff PASS; mypy PASS; pytest 3336 passed / 23 skipped / 1 warning.
- Remote validation: GitHub Actions workflow `CI`, job `quality`, run `33098999757`, event `push`, head SHA `7a6349e777ab267ef5db92381783dac80f22a226`; all steps completed successfully.
- Default CI is offline-safe and requires no real secrets. Live / integration paths remain opt-in and environment-gated; no live BUFF, SteamDT, Redis, or Discord operation is performed.

## Current Status

- Bounded multi-recipe scanner: **IMPLEMENTED / PRODUCTION** (Phase 13T-1, 13T-2, 13T-3A, 13T-3B). `LiveScannerOrchestrator.run_once` consumes `enumerate_scanner_recipe_selections`; CLI exposes `--max-recipe-candidates-returned` / `--max-candidate-states-explored`; defaults `2 / 256`.
- Bounded enumeration offline validation: **PASSED** (Phase 13T-4A; `tests/test_multi_recipe_scanner_scale_validation.py`; primary 100/901/2/2 fixture; exact-cap=20 → 2 fully valued; one-below=19 → 1 fully valued + 1 atomically blocked; two-bucket `1 / 1` candidates and `128 / 128` states; 1/1 legacy compatibility; determinism).
- Bounded enumeration live validation: **LIVE_VALIDATION_PASSED_NO_COMPLETE_VALUATION** (Phase 13T-4B; effective cap=5; 10 + 20 = 30 logical demand atomically blocked; 0 SteamDT HTTP requests; frozen contracts held).
- BUFF anonymous listing acquisition: **solved** (provider works; gated, read-only).
- SteamDT output valuation: **fully live path verified** (Phase 13P-5; strict BUFF sell policy).
- Goods identity bridge: **provisional offline resolver and runtime binding implemented** (`D-IDENTITY-006` / `D-IDENTITY-007`).
- Trade-up input normalization and current Souvenir output semantics: **implemented** (Phase 13O through 13P-4).
- Run-scoped exact-name valuation reuse: **IMPLEMENTED** (Phase 14B). Fresh scanner-owned session per `run_once()`; atomic NEW-LIVE admission; success and terminal failure reuse; no same-name retry; no cross-run reuse.
- Scanner service/session persistent cache READ integration: **IMPLEMENTED** (Phase 14C). Optional scanner-owned `ScannerCachedBuffPriceResolver` injection; its internal raw resolver is structurally bound to `select_scanner_cached_buff_price`, so generic cross-platform authority cannot enter public scanner composition. Deterministic memo → sequential explicit-FRESH_ONLY cache → live; independent FRESH validation; stable strict-BUFF failure reasons retained across memo reuse; cache outcome counters active; backend/codec/adapter/contract errors propagate; no stale consumption or writeback.
- Default `run_live_scan_once.py` cache composition: **IMPLEMENTED** (Phase 14D). In-memory default; optional Redis through the existing three-field settings seam. Scanner write-after-live: **NOT IMPLEMENTED**. Stored snapshot `PriceCachePolicy` is writer-owned; no scanner read-time numeric TTL config.
- `D-CACHE-001`: **Superseded** for the originally tracked run-reuse + CLI composition gap; deferred write/refresh concerns remain separate future work.
- Scheduler/continuous scanning: **not implemented**.
- R0-A Public Documentation Synchronization: **COMPLETE** (`1dbc6f1`).
- R0-B Minimum CI: **COMPLETE / REMOTE GREEN** (`7a6349e`; GitHub Actions `CI` / `quality` success).
- R0-C Main History Consolidation: **COMPLETE**. PR #1 (`Reconcile main history with current project lineage`) merged using `Create a merge commit`. Post-R0-C main tip `9cfaf36db028661075a495587ac32e51256fffe8` with parents `{24ece8582d1b3cb1b72322afc15de94b652a8bcc, 3aa44e9364268308d0fbb4c0532f4a910f4f85e8}`. Consolidation commit `3aa44e93…` is topology-only and its tree `7a39d28f2654cdf3b4eb98c8123227de64db5e34` equals the DEV tree `4c2f1ef6cd850985e71f041601ae58489abe947b`. CI workflow blob `02d0ce81d3704d9bc9c513df9b474855ffeae703` is preserved. Post-R0-C main push CI: workflow `CI`, run `33173529766`, event `push`, branch `main`, head SHA `9cfaf36…`, conclusion `success`. The merge was performed manually through the GitHub web UI after automated fine-grained-PAT merge attempts were blocked by GitHub token authorization.
- R0-C docs checkpoint: **MERGED / VERIFIED**. PR #2 (`Sync documentation after R0-C consolidation`) merged using `Create a merge commit` (manual web-UI merge after automated PAT-scope limits). Final canonical `main` tip after the docs checkpoint is `328269112f229faf3fce4cf0be4b9c7875582b65` (P2) with parents `{9cfaf36…, b13201b…}` and tree `b7648ad185aaf9ae4f4ca1057294e4b84010ab8d`. CI workflow blob `02d0ce81…` preserved. Final-main push CI: workflow `CI`, run `33175931060`, event `push`, branch `main`, head SHA `328269112f…`, conclusion `success`.
- R0-D Branch / Repository Cleanup: **COMPLETE**. PR #3 (`R0-D completion documentation checkpoint`) merged on `main` using `Create a merge commit` (manual web-UI merge after automated PAT-scope limits on un-draft). Final canonical `main` tip is `24c95c029f583d5cc0b0a67986e48c06d0ef7957` (P3) with parents `{328269112f229faf3fce4cf0be4b9c7875582b65 (P2), 6964cc4ff25cd4ad72fe65f92f40a5ce70a4a268 (R0-D3 docs commit)}` and tree `608d3e473072afb0d97aadf46ea0be8b1f55ca26`. CI workflow blob `02d0ce81…` preserved unchanged since R0-A. Final-main push CI: workflow `CI`, run `33240760167`, event `push`, branch `main`, head SHA `24c95c0…`, conclusion `success`. Cleanup summary: 305 Claude agent linked worktrees under `D:/CS/.claude/worktrees/agent-*` and their 305 `worktree-agent-a*` local branches removed; 5 named local branches (`docs/r0c-completion-checkpoint`, `repo/main-consolidation`, `feature/steamdt-cache-rate-limit`, `feature/steamdt-data-source`, `feature/buff-tradeup-scanner`) removed; 4 named remote branches removed. `git worktree remove` and `git branch -d` only (no `--force`, no `-D`). `v1-dry-run-baseline` retained locally at exact target `32ab47c5b66a0f331457e69f1515e5e9bb2a37e1` (was always local-only). No unique history lost.
- Phase 14A — Scanner Valuation Integration Design Freeze: **COMPLETE** (docs only; commit `e98cd97`).
- Phase 14A-R1 — Design Coherence Correction: **COMPLETE** (docs only; commit `bb056e5`; decision `D-PHASE14A-R1-COHERENCE`).
- Phase 14B — Run-scoped exact-name valuation reuse: **COMPLETE** at `c7031b61c3c44640ffd76165946809f7383f5d0c`; baseline full offline validation `3382 passed, 23 skipped, 1 warning`.
- Phase 14C — Phase12D FRESH_ONLY cache READ integration: **COMPLETE**. `app/services/scanner_cached_buff_price_selector.py` supplies strict BUFF resolver selection via `select_buff_output_price`; `scanner_valuation_session.py` performs memo/cache/live Stage A classification and retains live-only Stage B; `scanner_orchestrator.py` injects the optional resolver and activates cache counters without constructing runtimes. No Phase12D implementation, CLI, config, refresh, or persistent write behavior changed. Full offline validation: `3413 passed, 23 skipped, 1 warning`; ruff/mypy pass.

## Next Action (ordered)

- **Phase 14B and Phase 14C are COMPLETE.** Run reuse, NEW-LIVE accounting, and optional scanner service/session FRESH_ONLY cache reads are implemented and offline validated. `D-PHASE14B-COMPLETE` and `D-PHASE14C-COMPLETE` record the checkpoints.
- **Phase 14:** `CANONICAL MAIN INTEGRATION COMPLETE`. Phase 14A / 14A-R1 / 14B / 14C / 14D merged to main via PR #4 at P4 = `26c69bae9e482452f56f380277d8b10fefa29d52` (parents `{24c95c029..., 47227b33...}`, tree `39a82914...`). Main push CI run `33320657978` SUCCESS. Feature branch `feature/scanner-valuation-integration` safely retired.
- **Valuation Budget Calibration Phase 15A:** **OFFLINE MEASUREMENT COMPLETE** on `feature/valuation-budget-calibration`. The primary metric is exact `run_unique_output_names` across ordered default (`2 / 256`) recipe candidates. A 439-record structural census and 192 deterministic replay observations use normalized pinned identity/metadata and the real COHORT_DEPTH universe builder, scanner composition, recipe solver, and trade-up output construction. Evidence is in `research/valuation_budget_calibration/results.json` and `REPORT.md`; tests are in `tests/test_valuation_budget_calibration.py`. The replay distribution is scenario-coverage evidence, not a market-frequency distribution (`PHASE15A_REPRESENTATIVENESS_LIMITATION`). No production code or budget/default/hard-max/CLI/atomic semantics changed.
- **Valuation Budget Calibration Phase 15B:** NOT STARTED / NOT AUTHORIZED. Phase 15A reference thresholds are analysis only and no final production cap is recommended.
- Scanner write-after-live remains unimplemented and out of scope.
- `D-CACHE-001` is superseded for the originally tracked run-reuse + CLI composition gap; deferred write/refresh concerns remain separate future work and continue to require explicit authorization.
- **R0-C Main History Consolidation is COMPLETE.** Post-R0-C main tip is `9cfaf36db028661075a495587ac32e51256fffe8` (now an ancestor of P2).
- **R0-C docs checkpoint is MERGED / VERIFIED.** Canonical `main` tip is `328269112f229faf3fce4cf0be4b9c7875582b65` (P2); topology / ancestry / tree / CI workflow blob all verified; final-main push CI green.
- **R0-D cleanup execution and completion checkpoint are COMPLETE.** R0-D1 audit, R0-D2 / R0-D2-BIS / R0-D2-TER, and PR #3 post-merge verification are complete. Canonical `main` is P3 (`24c95c0...`). Cleanup summary is captured in `PROJECT_CONTEXT.md` and `specs/roadmap.md`.
- **R0-D completion documentation checkpoint PR is MERGED / VERIFIED.** PR #3 (`R0-D completion documentation checkpoint`) merged on `main` using `Create a merge commit` at P3 = `24c95c029f583d5cc0b0a67986e48c06d0ef7957`; final-main push CI green (`CI` / run `33240760167`, conclusion `success`). R0-D is COMPLETE.
- Scanner Valuation Integration: Phase 14A / 14A-R1 / 14B / 14C / 14D are **canonically integrated on `main`** via PR #4.
- Valuation Budget Calibration Phase 15A is **OFFLINE MEASUREMENT COMPLETE** on `feature/valuation-budget-calibration`; Phase 15B policy decision remains **NOT STARTED / NOT AUTHORIZED**.
- Any future development phase must be explicitly authorized and must not silently relax `D-ENUM-001`–`D-ENUM-004`, `D-CACHE-001..004`, `D-BUDGET-001`, `D-ACCOUNTING-001`, `D-SCANNER-001`, `D-VALIDATION-001`, `D-MEMORY-001`, `D-ADAPTER-003`, or `D-ADAPTER-004`.

## Current Blockers

- None for the completed Phase 15A offline measurement.
- Phase 15B policy work requires separate explicit authorization and representative market-frequency evidence before treating replay threshold coverage as production frequency.

## Standing Prohibitions (re-asserted)

No auto-buy, auto-login, cookie scraping, CAPTCHA/risk-control bypass, browser purchasing, proxy/UA rotation, mass scraping, or invented endpoints/fields. Live smokes stay gated and never auto-run. Do not modify Protected Core without an explicit migration plan.
