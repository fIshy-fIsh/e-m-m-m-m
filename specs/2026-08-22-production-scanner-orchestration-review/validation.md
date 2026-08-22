# Phase 13M-0 — Production Scanner Orchestration Architecture Review (Validation)

## Validation Strategy

Two concentric rings. The first ring validates the spec trilogy itself; the second ring validates the repository state after the spec is written.

### Ring 1 — Spec trilogy integrity

- **R1.1 Spec files present.** `specs/2026-08-22-production-scanner-orchestration-review/` must contain exactly `plan.md`, `requirements.md`, `validation.md`.
- **R1.2 Architecture decision is B.** `plan.md` must contain a section titled "Scanner orchestration boundary" that names B explicitly and gives a justification with at least three numbered points.
- **R1.3 Scheduling decision is periodic scan.** `plan.md` must contain a section titled "Scheduling model" that names "periodic scan" explicitly and rejects both event-driven and manual-only.
- **R1.4 Cache ownership decision is per-cache module ownership.** `plan.md` must contain a section titled "Cache ownership" that names per-cache module ownership and lists the four cache modules (listing, metadata, valuation, identity).
- **R1.5 Opportunity lifecycle specified.** `plan.md` must contain a section titled "Opportunity lifecycle" enumerating exactly five stages (listing observed → candidate conversion → enrichment → trade-up evaluation → opportunity result) in order.
- **R1.6 Failure handling specified.** `plan.md` must contain a section titled "Failure handling" enumerating exactly four categories (provider failure, enrichment rejection, valuation failure, stale data) and naming the owner of each.
- **R1.7 Rejected alternatives named.** `plan.md` must contain a section titled "Rejected alternatives" that names A (extend `market_scan_service`) and C (provider-driven pipeline runner) under boundary, and event-driven and manual-only under scheduling.
- **R1.8 Frozen contracts preserved.** `requirements.md` FR-6 must list `BuffItemIdentity`, `BuffListing`, `TradeUpInputCandidate`, `TradeUpInputEnricher`, and `BuffListingCandidateAdapter` as unchanged.
- **R1.9 FR-3 enumerates four cache modules.** `requirements.md` FR-3.1 must list listing, metadata, valuation, identity caches with their paths.
- **R1.10 Future implementation order specified.** `plan.md` must contain a section titled "Future Implementation Order" with at least five numbered steps.
- **R1.11 Remaining blockers specified.** `plan.md` must contain a section titled "Remaining Blockers" naming identity bridge (`D-IDENTITY-003`), intrinsic flag migration (`D-MIGRATION-002`), and absence of any production orchestration today.
- **R1.12 Out-of-scope section.** `plan.md` and `requirements.md` must enumerate the forbidden outcomes (scanner implementation, scheduler implementation, BUFF endpoint, identity resolver, database, webhook, purchase, cache implementation, manual HTTP trigger, event-driven ingestion, modification to existing modules).

### Ring 2 — Repository state

- **R2.1 `git diff --check`** must be clean (after filtering Windows LF→CRLF advisories).
- **R2.2 `git status --short`** must show only the three new spec files plus nothing else.
- **R2.3 `git diff --name-only`** must show no path under `app/`, `tests/`, or `specs/` outside the new directory.
- **R2.4 No Protected Core file path appears in `git diff --name-only`** when matched against the regex recorded in `ARCHITECTURE_STATE.md`.
- **R2.5 BuffItemIdentity unchanged.** Read `app/services/buff_item_identity.py` source. Assert the file still defines exactly `BuffItemIdentityValidationError`, `BuffItemIdentity`, `BuffItemIdentityResolver`, with the field set `{market_hash_name, goods_id}` and the forward-only `resolve` Protocol.
- **R2.6 BuffListing unchanged.** Read `app/services/buff_listing_provider.py` source. Assert `BuffListing.market_hash_name` is still typed as `str | None` and the parser still sets it to `None`.
- **R2.7 TradeUpInputCandidate unchanged.** Read `app/services/trade_up_input_candidate.py` source. Assert the candidate still carries `market_hash_name: str | None`, `price_cny`, `paintwear`, `stattrak: bool`, `souvenir: bool`, and accepts `None` for `market_hash_name`.
- **R2.8 TradeUpInputEnrichment unchanged.** Read `app/services/trade_up_input_enrichment.py` source. Assert the rejection vocabulary still contains `MARKET_HASH_NAME_UNRESOLVED` and `METADATA_NOT_FOUND`.
- **R2.9 BuffListingCandidateAdapter unchanged.** Read `app/services/buff_listing_candidate_adapter.py` source. Assert the rejection vocabulary still contains `MISSING_IDENTITY`, `MISSING_PRICE`, `INVALID_FLOAT`, `MISSING_ASSET_ID`, `UNSUPPORTED_SOURCE`.
- **R2.10 No scanner module created.** Assert no `app/services/scanner_orchestration.py` exists in the working tree.
- **R2.11 No cache module created.** Assert none of `app/services/listing_cache.py`, `app/services/metadata_cache.py`, `app/services/valuation_cache.py`, `app/services/identity_cache.py` exist in the working tree.
- **R2.12 No scheduler code added.** `grep -r "apscheduler\|AsyncIOScheduler\|BlockingScheduler" app/` returns only the existing mock BUFF pipeline reference (not new).

## Acceptance Checklist

- [ ] R1.1 spec files present
- [ ] R1.2 architecture decision is B
- [ ] R1.3 scheduling is periodic scan
- [ ] R1.4 cache ownership is per-cache module ownership
- [ ] R1.5 opportunity lifecycle enumerated
- [ ] R1.6 failure handling enumerated
- [ ] R1.7 rejected alternatives named
- [ ] R1.8 frozen contracts preserved
- [ ] R1.9 four cache modules named
- [ ] R1.10 future implementation order present
- [ ] R1.11 remaining blockers listed
- [ ] R1.12 out-of-scope section present
- [ ] R2.1 git diff --check clean
- [ ] R2.2 only spec files in git status
- [ ] R2.3 no `app/` / `tests/` modification
- [ ] R2.4 no Protected Core diff
- [ ] R2.5 BuffItemIdentity unchanged
- [ ] R2.6 BuffListing unchanged
- [ ] R2.7 TradeUpInputCandidate unchanged
- [ ] R2.8 TradeUpInputEnrichment unchanged
- [ ] R2.9 BuffListingCandidateAdapter unchanged
- [ ] R2.10 no scanner module created
- [ ] R2.11 no cache module created
- [ ] R2.12 no new scheduler code

## Failure Handling

If any ring fails, the implementation phase MUST NOT commit. The failure must be reported with the failing assertion and the offending source location. Do not retry with relaxed thresholds; the design numbers and contract shapes are the contract.