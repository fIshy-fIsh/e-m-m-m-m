# Phase 13K-0 — Production Candidate Adapter Architecture Review (Plan)

## Status

- Design-only review.
- Date: 2026-08-22.
- Branch: `feature/steamdt-cache-rate-limit`.
- Anchors: `D-IDENTITY-001`, `D-IDENTITY-002`, `D-ENRICH-001`, `D-MIGRATION-001`, `D-VALIDATION-001`, Phase 13H-0 / 13I-2 / 13I-3 / 13J-1.
- No code, no Protected Core edits.

## Decisions Locked In This Review (from intake)

1. **Module placement:** new file `app/services/buff_listing_candidate_adapter.py`. Offline-only; no dependency on `tradeup_engine`, `recipe_solver`, EV, risk, scheduler, purchase.
2. **Failure surface:** return-rejection pattern. `convert()` returns `TradeUpInputCandidate | CandidateRejection`. Caller partitions kept vs rejected. Stable StrEnum rejection codes.
3. **Identity handling:** when no resolver exists (current state), the adapter emits `TradeUpInputCandidate` with `market_hash_name=None`. Downstream `TradeUpInputEnrichment` rejects it as `MARKET_HASH_NAME_UNRESOLVED`. No guessing.
4. **Integration boundary:** adapter consumes the existing `BuffListingProvider` directly. No `CandidateListing`, no `market_scan_service`.

## Context

The current canonical seam is:

```
TradeUpInputCandidate → TradeUpInputEnrichment → InputItem → trade-up engine → EV / ROI / Risk
```

There is no production wiring from any listing source into `TradeUpInputCandidate`. The only validated upstream DTO is `BuffListing` from `BuffListingProvider`. This phase freezes the production adapter contract that will eventually bridge the two halves of the seam.

## Task Groups

### Group 1 — Module placement and dependencies

1.1. New module: `app/services/buff_listing_candidate_adapter.py`. Single responsibility: convert one `BuffListing` into one `TradeUpInputCandidate | CandidateRejection`.

1.2. Dependency direction (strict, verified by static guard):
   - May import: `app.services.buff_listing` (the `BuffListing` DTO), `app.services.buff_listing_provider` (the provider protocol), `app.services.trade_up_input_candidate` (the candidate boundary).
   - Must NOT import: `app.services.tradeup_engine`, `app.services.recipe_solver`, `app.services.ev_service`, `app.services.risk_filter`, `app.services.valuation_service`, `app.services.live_recipe_valuation`, `app.services.metadata_models`, `app.services.metadata_provider`, `app.services.metadata_service`, `app.services.live_metadata_catalog`, `app.services.trade_up_input_enrichment`, `app.jobs.scheduler`, `app.api.*`, `app.db.*`, `app.cache.*`, `app.webhook.*`, `app.services.scanner`.
   - Must NOT import: `httpx`, `asyncio`, `requests`, `aiohttp`, `websockets`, `os.environ`, `open(`, `json`, anything reading `BUFF_*` env config, anything importing `SteamApis` / `steamdt` / `steamapis` modules.

1.3. The adapter is offline-only. It accepts a `BuffListing` argument that has already been acquired; it does not call any HTTP / WebSocket / network code.

### Group 2 — Public surface

2.1. Public exports (`__all__`, exact tuple):
   - `CandidateAdapterRejectionReason` (StrEnum)
   - `CandidateAdapterRejection` (frozen dataclass)
   - `BuffListingCandidateAdapter` (Protocol)
   - `convert_buff_listing_to_candidate(BuffListing) -> TradeUpInputCandidate | CandidateAdapterRejection`
   - `convert_buff_listings(Sequence[BuffListing]) -> tuple[TradeUpInputCandidate, ...]`

2.2. `CandidateAdapterRejectionReason` StrEnum values (closed set, frozen here):
   - `MISSING_IDENTITY` — `BuffListing.market_hash_name is None`.
   - `MISSING_PRICE` — `BuffListing.price_cny` fails positive-Decimal validation (defensive; provider already enforces this, but the adapter must not assume).
   - `INVALID_FLOAT` — `BuffListing.paintwear` is not in `[0.0, 1.0]`.
   - `MISSING_ASSET_ID` — `BuffListing.asset_id` is empty / not a string (defensive).
   - `UNSUPPORTED_SOURCE` — `BuffListing.source` is not one of the allowlisted source tags (`"buff"` for now; extensible later).

2.3. `CandidateAdapterRejection` is a frozen dataclass that holds the `BuffListing` (for diagnostics), the rejection reason, and a free-text reason code. It MUST suppress `__repr__` to avoid leaking `listing_id`, `goods_id`, `asset_id`, `price_cny`, or `market_hash_name`. The `__str__` form exposes only the rejection code and the source tag.

2.4. `convert_buff_listing_to_candidate` returns:
   - `TradeUpInputCandidate(...)` on success.
   - `CandidateAdapterRejection(...)` on any of the five listed reasons.
   - It never raises for the documented rejection reasons. Programmer errors (wrong argument type) raise `TypeError`.

### Group 3 — Candidate construction contract

3.1. Field ownership at the adapter boundary:

| `TradeUpInputCandidate` field | Source                                |
| ---------------------------- | ------------------------------------- |
| `listing_id`                 | `BuffListing.listing_id`              |
| `goods_id`                   | `BuffListing.goods_id`                |
| `market_hash_name`           | `BuffListing.market_hash_name` or `None` |
| `price_cny`                  | `BuffListing.price_cny`               |
| `paintwear`                  | `BuffListing.paintwear` (Decimal → Decimal passthrough) |
| `asset_id`                   | `BuffListing.asset_id`                |
| `source`                     | `BuffListing.source`                  |
| `stattrak`                   | `False` (default; provider DTO does not surface it yet) |
| `souvenir`                   | `False` (default; provider DTO does not surface it yet) |

3.2. Adapter behavior on unresolved identity: emits `market_hash_name=None`. The candidate passes through `TradeUpInputCandidate.__post_init__` because `None` is the documented "unresolved" shape. Downstream `TradeUpInputEnrichment` rejects it as `MARKET_HASH_NAME_UNRESOLVED`. The adapter does not raise and does not call any resolver. When an upstream identity source exists (out of scope for this phase), the adapter reads `BuffListing.market_hash_name` exactly as the provider emits it; the adapter does not own identity derivation.

3.3. `stattrak` and `souvenir` default to `False` at the adapter boundary. Reason: the current `BuffListing` DTO does not yet expose these as fields; promoting them to candidate-owned flags requires future work on the provider side. The adapter MUST NOT hard-code `False` *for the purpose of suppressing real values*; this is acknowledged technical debt recorded in `D-MIGRATION-001`. When `BuffListing` grows `stattrak` and `souvenir`, the adapter must read them and forward verbatim.

3.4. `paintwear` is `Decimal` in both `BuffListing` and `TradeUpInputCandidate`; the adapter does not convert to float. The single Decimal→float conversion stays at the enrichment boundary (`TradeUpInputEnrichment`).

### Group 4 — Integration with BuffListingProvider

4.1. Adapter consumes `BuffListing` (the value type) directly, not the provider class. This makes the adapter independently testable.

4.2. The future wiring module (not in this phase) is responsible for:
   - Iterating the provider's listings.
   - Calling `convert_buff_listing_to_candidate(listing)` for each.
   - Feeding the resulting `tuple[TradeUpInputCandidate, ...]` to `enrich_candidates(...)` from `TradeUpInputEnrichment`.

4.3. The adapter does not own a provider instance. It does not call `BuffListingProvider.listings_for(...)`. That wiring is a separate future phase (likely Phase 13K-1 or later).

### Group 5 — Rejection histogram surface (test-local, not in production)

5.1. The future test file for this module (`tests/test_buff_listing_candidate_adapter.py`) will own a test-local `AdapterRejectionHistogram` dataclass with bucket counts for each `CandidateAdapterRejectionReason`. No production DTO gains a counter field.

5.2. Tests must cover, at minimum:
   - Happy-path conversion preserves all eight non-default candidate fields.
   - `market_hash_name=None` produces a candidate with `market_hash_name=None` (not a rejection at the adapter level — `MISSING_IDENTITY` is reserved for cases where the adapter actively decides to refuse; the current contract is "emit None and let enrichment reject it").
   - `MISSING_PRICE` on non-Decimal / non-positive price.
   - `INVALID_FLOAT` on out-of-band paintwear.
   - `MISSING_ASSET_ID` on empty / non-string asset_id.
   - `UNSUPPORTED_SOURCE` on unknown source tag.
   - Determinism: two conversions of the same listing produce byte-equal candidates.
   - Module-level static guard confirming no live / external / engine / scheduler imports.
   - Static guard confirming no Protected Core import.
   - Repr / str redacted: no `listing_id`, `goods_id`, `market_hash_name`, `asset_id`, or `price_cny` appears in `repr(rejection)` or `str(rejection)`.

### Group 6 — Frozen decisions (from this review)

6.1. **D-ADAPTER-001 — Production candidate adapter lives in `app/services/buff_listing_candidate_adapter.py`.**
   - Active. Revisit only if the upstream listing source changes from BUFF or a future scanner needs a different adapter.

6.2. **D-ADAPTER-002 — Adapter uses return-rejection pattern with stable StrEnum codes.**
   - Active. The five codes listed in §2.2 form the closed vocabulary; future codes require a new decision record.

6.3. **D-ADAPTER-003 — Adapter does not own identity derivation.**
   - Active. When `BuffListing.market_hash_name` is `None`, the adapter emits a candidate with `market_hash_name=None`. No resolver is called, no guessing is performed. Identity resolution is the responsibility of upstream layers (or a future identity-resolver-bearing adapter variant).

6.4. **D-ADAPTER-004 — Adapter must route through `TradeUpInputEnrichment`, never bypass it.**
   - Active. This is the production equivalent of `D-MIGRATION-001`: the adapter must NOT replicate the 13H-0 hard-coded `stattrak=False, souvenir=False` behavior in a way that bypasses the enrichment seam.

## Critical Files

Add (this design phase, no implementation):

- `specs/2026-08-22-production-candidate-adapter-architecture-review/plan.md`
- `specs/2026-08-22-production-candidate-adapter-architecture-review/requirements.md`
- `specs/2026-08-22-production-candidate-adapter-architecture-review/validation.md`

No other path may change in this phase.

## Verification

```bash
git diff --check
git diff --name-only
git status --short
```

Acceptance requires:

- `git diff --check` clean.
- `git status --short` shows only the three new spec files.
- No `app/`, `tests/`, or Protected Core path modified.
- No commit unless separately requested.

## Recommended Next Phase

After this review, the next concrete implementation phase is **Phase 13K-1 — Production candidate adapter implementation**, gated on:

- The design review above is approved.
- No new live source is added (identity remains unresolved).
- The adapter is implemented offline-only and tested against synthetic `BuffListing` fixtures.
- The adapter is wired to no live provider call site in 13K-1; wiring is a separate future phase.

## Out of Scope (frozen here)

- Any live BUF / SteamDT / SteamApis endpoint call.
- Any identity resolver backend.
- Any scanner / scheduler / webhook / purchase / database / cache wiring.
- Any modification to `BuffListingProvider`, `BuffListing`, `BuffListingObservation`, `BuffTradableCandidate`, `BuffItemIdentity`, or `BuffItemIdentityResolver`.
- Any modification to `TradeUpInputEnrichment`, `TradeUpInputCandidate`, `tradeup_engine`, `recipe_solver`, `ev_service`, `risk_filter`.
- Any production / scheduler wiring that consumes the adapter output.
- Any change to `BuffListing.source` semantics — the adapter only enforces a closed allowlist.