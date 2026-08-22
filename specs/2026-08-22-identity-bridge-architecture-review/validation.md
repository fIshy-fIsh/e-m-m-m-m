# Phase 13L-0 — Identity Bridge Research and Architecture Review (Validation)

## Validation Strategy

Two concentric rings. The first ring validates the spec trilogy itself; the second ring validates the repository state after the spec is written.

### Ring 1 — Spec trilogy integrity

- **R1.1 Spec files present.** `specs/2026-08-22-identity-bridge-architecture-review/` must contain exactly `plan.md`, `requirements.md`, `validation.md`.
- **R1.2 Architecture decision is C.** `plan.md` must contain a section titled "Architecture Decision" that names C explicitly and gives a justification with at least four numbered points.
- **R1.3 Four sources evaluated.** `plan.md` must contain four sub-sections (BUFF native, SteamDT, SteamApis, manual offline mapping), each with a verdict.
- **R1.4 D-IDENTITY-003 specified.** `plan.md` must specify `D-IDENTITY-003` with the source-survey rationale. The existing `D-IDENTITY-001` and `D-IDENTITY-002` must not be modified.
- **R1.5 Manual offline mapping constraints.** `plan.md` must list all five constraints (FR-4.1 through FR-4.5) for a future manual mapping. `requirements.md` must reproduce them.
- **R1.6 Out-of-scope section.** `plan.md` and `requirements.md` must enumerate the forbidden outcomes (resolver backend, mapping file, identity-contract modifications, BUF endpoint guesses, browser automation, anti-bot bypass, purchase logic, SteamDT identity inference, SteamApis identity assumption, production wiring).

### Ring 2 — Repository state

- **R2.1 `git diff --check`** must be clean (after filtering Windows LF→CRLF advisories).
- **R2.2 `git status --short`** must show only the three new spec files plus nothing else.
- **R2.3 `git diff --name-only`** must show no path under `app/`, `tests/`, or `specs/` outside the new directory.
- **R2.4 No Protected Core file path appears in `git diff --name-only`** when matched against the regex recorded in `ARCHITECTURE_STATE.md`.
- **R2.5 Existing identity contracts unchanged.** Read `app/services/buff_item_identity.py` source. Assert the file still defines exactly `BuffItemIdentityValidationError`, `BuffItemIdentity`, `BuffItemIdentityResolver`, with the field set `{market_hash_name, goods_id}` and the forward-only `resolve` Protocol.
- **R2.6 Anonymous provider unchanged.** Read `app/services/buff_listing_provider.py` source. Assert `BuffListing.market_hash_name` is still typed as `str | None` and the parser still sets it to `None`.
- **R2.7 Candidate boundary unchanged.** Read `app/services/trade_up_input_candidate.py` source. Assert `TradeUpInputCandidate.market_hash_name` is still typed as `str | None` and `None` is still accepted.
- **R2.8 SteamApis source offer ID still project-local SHA-256.** Read `app/services/steamapis_listing.py` source. Assert `make_steamapis_source_offer_id` still hashes `marketplace + game + purchase_link` and not anything BUFF-specific.

## Acceptance Checklist

- [ ] R1.1 spec files present
- [ ] R1.2 Architecture Decision section names C
- [ ] R1.3 Four source sub-sections present
- [ ] R1.4 D-IDENTITY-003 specified
- [ ] R1.5 Five manual-mapping constraints listed
- [ ] R1.6 Out-of-scope section present
- [ ] R2.1 git diff --check clean
- [ ] R2.2 only spec files in git status
- [ ] R2.3 no `app/` / `tests/` modification
- [ ] R2.4 no Protected Core diff
- [ ] R2.5 BuffItemIdentity unchanged
- [ ] R2.6 BuffListing.market_hash_name still None
- [ ] R2.7 TradeUpInputCandidate.market_hash_name still None-accepted
- [ ] R2.8 SteamApis source offer ID still project-local SHA-256

## Failure Handling

If any ring fails, the implementation phase MUST NOT commit. The failure must be reported with the failing assertion and the offending source location. Do not retry with relaxed thresholds; the design numbers and contract shapes are the contract.