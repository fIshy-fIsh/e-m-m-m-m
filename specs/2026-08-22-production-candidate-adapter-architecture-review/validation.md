# Phase 13K-0 — Production Candidate Adapter Architecture Review (Validation)

## Validation Strategy

Three concentric rings. The first two rings are documentation / design verification; the third ring is the future implementation gate.

### Ring 1 — Static guards on the design documents

- **R1.1 Spec file presence.** The directory `specs/2026-08-22-production-candidate-adapter-architecture-review/` must contain exactly `plan.md`, `requirements.md`, `validation.md`.
- **R1.2 Frozen decisions present.** Both `D-ADAPTER-001`, `D-ADAPTER-002`, `D-ADAPTER-003`, `D-ADAPTER-004` must appear in `plan.md` and be cross-referenced from `requirements.md` or `validation.md`.
- **R1.3 Out-of-scope section.** Both `plan.md` and `requirements.md` must enumerate the eight out-of-scope items (no live BUFF / SteamDT / SteamApis call; no identity resolver; no scanner / scheduler / webhook / purchase / db / cache wiring; no modification to `BuffListing*` or `BuffItemIdentity*`; no modification to Protected Core; no production wiring; no JSON report; no diagnostic counters on production DTOs).

### Ring 2 — Repository state

- **R2.1 `git diff --check`** must be clean (after filtering Windows LF→CRLF advisories).
- **R2.2 `git status --short`** must show only the three new spec files plus nothing else.
- **R2.3 `git diff --name-only`** must show no path under `app/`, `tests/`, or `specs/` outside the new directory.
- **R2.4 No Protected Core file path appears in `git diff --name-only`** when matched against the regex recorded in `ARCHITECTURE_STATE.md`.

### Ring 3 — Future implementation gate (Phase 13K-1)

This ring is the acceptance contract for the implementation phase that follows. The implementation phase must:

- **R3.1 Public API exactness.** Read `app/services/buff_listing_candidate_adapter.py` source. Assert `__all__` equals `("CandidateAdapterRejectionReason", "CandidateAdapterRejection", "BuffListingCandidateAdapter", "convert_buff_listing_to_candidate", "convert_buff_listings")`.

- **R3.2 Rejection reason vocabulary.** Assert `CandidateAdapterRejectionReason` is a `StrEnum` whose values are exactly `MISSING_IDENTITY`, `MISSING_PRICE`, `INVALID_FLOAT`, `MISSING_ASSET_ID`, `UNSUPPORTED_SOURCE`. No other values.

- **R3.3 Repr / str redacted.** Build one `CandidateAdapterRejection` from a synthetic `BuffListing` carrying sensitive strings. Assert neither `repr(...)` nor `str(...)` contains any of `listing_id`, `goods_id`, `market_hash_name`, `asset_id`, or any Decimal-printed value.

- **R3.4 Happy-path conversion.** Build one synthetic `BuffListing` with all fields populated. Assert `convert_buff_listing_to_candidate(...)` returns a `TradeUpInputCandidate` whose `listing_id`, `goods_id`, `market_hash_name`, `price_cny`, `paintwear`, `asset_id`, `source` match the source values byte-for-byte. `stattrak` and `souvenir` must be `False`.

- **R3.5 `market_hash_name is None` flows through.** Build a `BuffListing` with `market_hash_name=None`. Assert the adapter returns a `TradeUpInputCandidate` with `market_hash_name is None`. The adapter does NOT raise and does NOT return a rejection.

- **R3.6 Rejection paths.** Parametrize across:
  - `price_cny=Decimal("-1")` → `MISSING_PRICE`
  - `price_cny="not-a-decimal"` → `MISSING_PRICE`
  - `paintwear=Decimal("2.0")` → `INVALID_FLOAT`
  - `paintwear="not-a-decimal"` → `INVALID_FLOAT`
  - `asset_id=""` → `MISSING_ASSET_ID`
  - `asset_id="  "` → `MISSING_ASSET_ID`
  - `source="unknown"` → `UNSUPPORTED_SOURCE`

  Each must produce a `CandidateAdapterRejection` with the expected reason.

- **R3.7 Determinism.** Convert the same `BuffListing` twice. Assert the two resulting `TradeUpInputCandidate` values are byte-equal (`__eq__` over all fields).

- **R3.8 `convert_buff_listings` partition.** Build a sequence of 5 synthetic listings: 2 happy-path, 1 with `market_hash_name=None`, 1 with `INVALID_FLOAT`, 1 with `UNSUPPORTED_SOURCE`. Assert the returned tuple has exactly 3 candidates (the 2 happy + the unresolved-identity case). The 2 hard-rejected listings are dropped.

- **R3.9 Module-level static guard.** Read `app/services/buff_listing_candidate_adapter.py` source. Assert none of: `tradeup_engine`, `recipe_solver`, `ev_service`, `risk_filter`, `valuation_service`, `live_recipe_valuation`, `metadata_models`, `metadata_provider`, `metadata_service`, `live_metadata_catalog`, `trade_up_input_enrichment`, `scheduler`, `webhook`, `purchase`, `httpx`, `asyncio`, `requests`, `aiohttp`, `websockets`, `os.environ`, `open(`, `json`, `BUFF_READONLY_SMOKE_GOODS_ID`, `SteamApis`, `steamdt`, `steamapis`.

- **R3.10 AST-level static guard.** Read the test file source via AST. Collect all `import` targets. Assert none starts with: `app.services.tradeup_engine`, `app.services.recipe_solver`, `app.services.ev_service`, `app.services.risk_filter`, `app.services.valuation_service`, `app.services.live_recipe_valuation`, `app.services.metadata_models`, `app.services.metadata_provider`, `app.services.metadata_service`, `app.services.live_metadata_catalog`, `app.services.trade_up_input_enrichment`, `app.services.buff_listing`, `app.services.buff_item_identity`, `app.services.buff_client`, `app.jobs.scheduler`, `app.api`, `app.db`, `app.cache`, `app.webhook`, `app.services.scanner`, `app.services.steamdt`, `app.services.steamapis`.

- **R3.11 Protected Core diff check.** `git diff --name-only` after the implementation commit must show no path under the Protected Core list.

- **R3.12 Full pytest run.** All existing tests (currently 2898) plus the new tests must pass. No skipped test should regress.

## Tooling & Commands (for the future 13K-1 phase)

```bash
py -3.13 -m pytest tests/test_buff_listing_candidate_adapter.py
py -3.13 -m pytest \
  tests/test_buff_listing_candidate_adapter.py \
  tests/test_synthetic_scanner_scale_validation.py \
  tests/test_trade_up_input_enrichment.py \
  tests/test_trade_up_input_candidate.py \
  tests/test_trade_up_pipeline.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
git diff --check
git diff --name-only
git diff --stat
git diff --cached --name-only
git status --short
```

## Acceptance Checklist

- [ ] R1.1 spec files present
- [ ] R1.2 frozen decisions in plan.md
- [ ] R1.3 out-of-scope sections present
- [ ] R2.1 git diff --check clean
- [ ] R2.2 only spec files in git status
- [ ] R2.3 no `app/` / `tests/` modification
- [ ] R2.4 no Protected Core diff
- [ ] R3.1 __all__ exact
- [ ] R3.2 rejection vocabulary closed
- [ ] R3.3 repr / str redacted
- [ ] R3.4 happy-path conversion byte-equal
- [ ] R3.5 unresolved identity flows through
- [ ] R3.6 rejection paths
- [ ] R3.7 determinism
- [ ] R3.8 partition in `convert_buff_listings`
- [ ] R3.9 module-level static guard
- [ ] R3.10 AST-level static guard on test file
- [ ] R3.11 Protected Core diff empty
- [ ] R3.12 full pytest green

## Failure Handling

If any ring fails, the implementation phase MUST NOT commit. The failure must be reported with the failing assertion, the actual value, and the offending test name. Do not retry with relaxed thresholds; the design numbers (byte-equality, exact tuples, closed enum) are the contract.