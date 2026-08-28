# Phase 13N-2 — BUFF Native Goods Identity Source Investigation (Validation)

## Validation Strategy

Two concentric rings. The first ring validates the spec trilogy itself; the second ring validates the repository state after the spec is written.

The investigation is research-only. No implementation. No production code changes. No live probe.

---

## Ring 1 — Spec trilogy integrity

### R1.1 Spec files present

`specs/2026-08-22-buff-native-goods-identity-investigation/` must contain exactly `findings.md`, `decision.md`, `validation.md`.

### R1.2 Architecture decision is C

`decision.md` must contain a section titled "Architecture Outcome" that names **C — No verified source; continue identity freeze** explicitly and gives a justification with at least six numbered points.

### R1.3 Three confidence classes enumerated

`findings.md` must enumerate confidence classes A, B, C, D, each with a definition and an explicit verdict for the BUFF goods-info endpoint.

### R1.4 Class C verdict for the goods-info endpoint

`findings.md` must state that the goods-info endpoint is **Class C — Possible but unverified**, **NOT ACTIONABLE** for production wiring.

### R1.5 `D-IDENTITY-005` specified

`decision.md` must specify `D-IDENTITY-005` with the source-survey rationale. The existing `D-IDENTITY-001` / `D-IDENTITY-002` / `D-IDENTITY-003` / `D-IDENTITY-004` must not be modified.

### R1.6 Cross-reference with prior decisions

Both `findings.md` and `decision.md` must enumerate the prior identity decisions and state that they remain unchanged by this audit.

### R1.7 `goods_id=1115941` explicitly addressed

`findings.md` must address the specific id `1115941`: the audit searched the repository and found zero references. No claim is made about what the live endpoint would return.

### R1.8 Out-of-scope section

`decision.md` must enumerate the forbidden outcomes (live probe, `D-AUTH-001` relaxation, `D-BUFF-001` relaxation, invented endpoint, invented schema, invented auth, concrete resolver, mapping file, parser modification, browser automation, cookie scraping, anti-bot bypass).

### R1.9 Why-not-A and Why-not-B sections

`decision.md` must include both "Why not A" and "Why not B" sections explaining the absence of direct authoritative and indirect-verifiable sources.

### R1.10 Recommended next phase section

`decision.md` must include a "Recommended Next Phase" section. The recommendation must not assume any future live probe authorization; it must reference the prior state audit's non-identity phases (`13N-3`, `13M-1`, `13O`, `13R`) as alternatives.

---

## Ring 2 — Repository state

### R2.1 `git diff --check` must be clean

No whitespace errors or merge conflicts in the diff.

### R2.2 `git status --short` must show only the three new spec files plus nothing else

(No tracked modifications, no untracked files outside the new directory.)

### R2.3 `git diff --name-only` must show no path under `app/`, `tests/`, `scripts/`, or `docs/`

Tracked file changes are not allowed in this phase.

### R2.4 No Protected Core file path appears in `git diff --name-only`

Protected Core includes (per `docs/ai-context/ARCHITECTURE_STATE.md`):

- `app/services/tradeup_engine.py`
- `app/services/valuation_service.py`
- `app/services/live_recipe_valuation.py`
- `app/services/ev_service.py`
- `app/services/risk_filter.py`
- `app/services/recipe_solver.py`
- `app/services/market_scan_service.py`
- `app/services/buff_listing.py` + `buff_listing_parser.py` + `buff_listing_facts.py` + `buff_listing_eligibility.py` + `buff_listing_qualification.py` + `buff_listing_solver_adapter.py`
- `app/clients/buff_client.py` (legacy skeleton)
- `app/services/buff_listing_provider.py` + `app/clients/buff_anonymous_listing_client.py` (recently hardened)
- SteamDT client/core, SteamApis modules, metadata providers.

### R2.5 `BuffGoodsInfo` unchanged

Read `app/clients/buff_client.py`. Assert the dataclass still defines exactly `goods_id`, `market_hash_name`, `localized_name`, `sell_num`, `buy_num`, `raw` with no field added or removed. Assert `BuffHttpClient.get_goods_info` still raises `NotImplementedError(UNCONFIRMED_MAPPING_ERROR)`.

### R2.6 `BuffListing.market_hash_name` unchanged

Read `app/services/buff_listing_provider.py`. Assert `market_hash_name=None` is still hardcoded at the construction site (line ~212). Assert no parser path reads `name`, `market_name`, `description`, `classid`, `instanceid`, `appid`.

### R2.7 `BuffItemIdentity` unchanged

Read `app/services/buff_item_identity.py`. Assert exactly `BuffItemIdentityValidationError`, `BuffItemIdentity`, `BuffItemIdentityResolver` are exported; assert the forward-only `resolve(market_hash_name) -> BuffItemIdentity | None` protocol signature is unchanged; assert no concrete resolver exists.

### R2.8 `BuffListingCandidateAdapter` unchanged

Read `app/services/buff_listing_candidate_adapter.py`. Assert the rejection vocabulary still contains `MISSING_IDENTITY`, `MISSING_PRICE`, `INVALID_FLOAT`, `MISSING_ASSET_ID`, `UNSUPPORTED_SOURCE`. Assert `stattrak`/`souvenir` still default to `False`. Assert the adapter still does not call any BUFF endpoint or resolve identity.

### R2.9 `TradeUpInputEnrichment` unchanged

Read `app/services/trade_up_input_enrichment.py`. Assert the rejection vocabulary still contains `MARKET_HASH_NAME_UNRESOLVED` and `METADATA_NOT_FOUND`. Assert no live metadata resolver backend exists.

### R2.10 `BUFF_API_NOTES.md` TODO #5 still unchecked

Read `docs/BUFF_API_NOTES.md:62-64`. Assert the goods-info endpoint checkboxes (`Confirm endpoint path`, `Confirm response fields mapping to BuffGoodsInfo`) are still unchecked.

### R2.11 No new scripts added

`git status --short` must show no new file under `scripts/`.

### R2.12 No new tests added

`git status --short` must show no new file under `tests/`.

### R2.13 No new client / no new config / no new cache / no new scanner

`git status --short` must show no new module under `app/clients/`, no modification to `app/config.py`, no new module under `app/services/*_cache.py`, no new module under `app/jobs/`.

---

## What Evidence is Accepted

- Repository file content (read directly from disk).
- Documentation (`docs/BUFF_API_NOTES.md`, `docs/BUFF_ANONYMOUS_READONLY_NOTES.md`, `docs/BUFF_LISTING_NOTES.md`, `docs/ai-context/DECISION_LOG.md`, `docs/SPEC.md`).
- Code analysis (source listings, grep results, frozen contracts).
- Existing empirical probe outcomes (`docs/BUFF_ANONYMOUS_READONLY_NOTES.md`, 2026-08-20).
- Fixture field inventories (read from `tests/fixtures/buff/*.json`).
- Decision records (`D-IDENTITY-001` through `D-IDENTITY-004`, `D-AUTH-001`, `D-BUFF-001/002/003`).

## What Evidence is Rejected

- **Live BUFF HTTP probes.** Per `D-AUTH-001` and `D-BUFF-001`, all live probes must be explicitly authorized, anonymous, one-request, no auth/cookie, gated by env flag. No authorization for a goods-info probe has been granted in this audit. Any unprobed claim about live behavior is rejected.
- **Invented endpoints, signatures, parameters, fields.** Per `docs/BUFF_API_NOTES.md:107-118`, the project must not invent any of these. Any conclusion that requires inventing a BUFF endpoint is rejected.
- **Unverified external documentation.** The project rule (PROJECT_CONTEXT.md rule 7) requires "record uncertainty as TODO in `docs/BUFF_API_NOTES.md`" rather than rely on external documentation. No external doc is cited as evidence.
- **Speculation about what `goods_id=1115941` would return.** The id appears nowhere in the repository paired with a verified response. Any claim about its response is speculation.
- **Browser automation, cookie scraping, anti-bot bypass.** All forbidden by CLAUDE.md standing rules.

## Why the Conclusion is Reliable

The conclusion that the BUFF goods-info endpoint is **Class C — Possible but unverified (NOT ACTIONABLE)** is reliable because:

1. **Repository evidence is exhaustive.** Every relevant path was searched (`app/`, `tests/`, `scripts/`, `docs/`, `specs/`).
2. **No positive evidence exists.** The endpoint is listed as TODO; the shape is unimplemented; no probe has been executed; no fixture carries a verified response.
3. **No indirect evidence exists.** No `classid`/`instanceid`/`appid` reference exists anywhere — even if the endpoint returned a market name, no chain is possible.
4. **All five prior identity decisions are reinforced, not contradicted.** None of `D-IDENTITY-001` / `D-IDENTITY-002` / `D-IDENTITY-003` / `D-IDENTITY-004` / `D-AUTH-001` is weakened.
5. **The audit explicitly does not act on absence.** The audit does not claim "the endpoint does not exist"; it claims "no repository evidence proves it exists, and no live probe has been authorized." This is a positive fact about the project's knowledge, not a positive fact about BUFF itself.
6. **No new code was written, no contract was modified, no decision was weakened.** The audit is strictly additive: one new decision record (`D-IDENTITY-005`) is added to the existing record set; nothing else changes.

## Acceptance Checklist

- [ ] R1.1 spec files present
- [ ] R1.2 architecture decision is C
- [ ] R1.3 four confidence classes enumerated
- [ ] R1.4 goods-info endpoint is Class C
- [ ] R1.5 D-IDENTITY-005 specified
- [ ] R1.6 prior decisions cross-referenced
- [ ] R1.7 `goods_id=1115941` addressed
- [ ] R1.8 out-of-scope section present
- [ ] R1.9 Why-not-A and Why-not-B sections present
- [ ] R1.10 Recommended Next Phase section present
- [ ] R2.1 `git diff --check` clean
- [ ] R2.2 only spec files in `git status --short`
- [ ] R2.3 no `app/` / `tests/` / `scripts/` / `docs/` modifications
- [ ] R2.4 no Protected Core diff
- [ ] R2.5 `BuffGoodsInfo` unchanged
- [ ] R2.6 `BuffListing.market_hash_name` still `None`
- [ ] R2.7 `BuffItemIdentity` unchanged
- [ ] R2.8 `BuffListingCandidateAdapter` unchanged
- [ ] R2.9 `TradeUpInputEnrichment` unchanged
- [ ] R2.10 `BUFF_API_NOTES.md` TODO #5 still unchecked
- [ ] R2.11 no new scripts added
- [ ] R2.12 no new tests added
- [ ] R2.13 no new client / config / cache / scanner wiring

## Failure Handling

If any ring fails, the implementation phase MUST NOT commit. The failure must be reported with the failing assertion and the offending source location. Do not retry with relaxed thresholds; the design numbers and contract shapes are the contract.