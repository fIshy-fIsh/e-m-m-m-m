# Phase 13L-0 — Identity Bridge Research and Architecture Review (Requirements)

## Goal

Establish — through repository-only evidence — that no verified identity bridge between BUFF listings and canonical Steam market identity exists, and freeze the architecture accordingly. No code, no resolver implementation, no mappings, no endpoint calls, no modifications to existing identity contracts.

## Functional Requirements

### FR-1 — Source-by-source evaluation

The review must examine each of the four candidate identity sources and produce a verdict for each:

- **FR-1.1 BUFF native metadata** — verdict, with traceable evidence from `app/services/buff_listing_provider.py`, `app/services/buff_listing.py`, `app/services/buff_item_identity.py`, `docs/BUFF_API_NOTES.md`, `docs/BUFF_ANONYMOUS_READONLY_NOTES.md`, `docs/BUFF_LISTING_NOTES.md`.
- **FR-1.2 SteamDT** — verdict, with traceable evidence from `app/services/steamdt_*.py`, `app/clients/steamdt_client.py`, and `D-STEAMDT-001`.
- **FR-1.3 SteamApis** — verdict, with traceable evidence from `app/services/steamapis_*.py`, `app/clients/steamapis_*.py`, and `D-STEAMAPIS-001`.
- **FR-1.4 Manual offline mapping** — verdict, with the strict constraints required for any future acceptance.

### FR-2 — Frozen identity contracts

- FR-2.1 `BuffItemIdentity` must remain unchanged: `market_hash_name: str`, `goods_id: str`. Field types, validation, and contract surface are not modified in this phase.
- FR-2.2 `BuffItemIdentityResolver.resolve(market_hash_name)` must remain a forward-only abstract `Protocol` returning `BuffItemIdentity | None`.
- FR-2.3 `BuffListing.market_hash_name` must remain `None` for anonymous provider output.
- FR-2.4 `TradeUpInputCandidate.market_hash_name` must remain `str | None` with `None` accepted as the unresolved shape.

### FR-3 — Architecture decision

- FR-3.1 The review must commit to one of: A (verified identity source exists), B (partial source exists), C (no verified source). The decision is C: freeze identity, continue synthetic-only.
- FR-3.2 A new decision record `D-IDENTITY-003` must be specified, summarizing the source survey and the C outcome. The existing `D-IDENTITY-001` and `D-IDENTITY-002` remain unchanged.
- FR-3.3 The forward resolver protocol stays abstract; `None` is the only real answer.

### FR-4 — Constraints on a future manual offline mapping

If and when a manual offline mapping is later introduced, it must satisfy ALL of:

- FR-4.1 Offline-only. Never queries BUF / SteamDT / SteamApis / Steam at runtime.
- FR-4.2 Revision-controlled (Git). Immutable within a release.
- FR-4.3 Treated as documentation, not live data. Never used for automatic purchasing, automatic login, automatic bidding, or any production write.
- FR-4.4 Consumed only by an offline identity source the candidate adapter may consult when present; absent it, the adapter stays synthetic.
- FR-4.5 Format documented and versioned; each entry records `market_hash_name`, `goods_id`, source URL or commit of verification, and a human-reviewer attestation.

### FR-5 — Out-of-scope enforcement

The review must explicitly enumerate all forbidden outcomes (resolver backend, mapping file, modification to BuffItemIdentity / TradeUpInputCandidate / BuffListing, BUF endpoint guesses, browser automation, anti-bot bypass, purchase logic, SteamDT identity inference, SteamApis identity assumption, production wiring of any identity source).

## Non-Functional Requirements

- NFR-1 Repository-only evidence. Every claim in the review must trace to a file path already committed to the repository. No external documentation is cited.
- NFR-2 No code changes. The phase produces no `app/` or `tests/` modifications.
- NFR-3 Decision-record honesty. `D-IDENTITY-003` must state explicitly which sources are non-actionable and why.
- NFR-4 Reopen prevention. The spec must list which subsequent decisions would force a reopen (new verified BUF endpoint, new SteamDT field semantics, new SteamApis payload verification, new offline mapping procedure).

## Out of Scope (frozen here)

- No resolver backend.
- No mapping file.
- No modification to `BuffItemIdentity` / `BuffItemIdentityResolver`.
- No modification to `BuffListing` / `TradeUpInputCandidate`.
- No BUF endpoint guesses.
- No browser automation.
- No anti-bot bypass.
- No purchase logic.
- No SteamDT identity inference.
- No SteamApis identity assumption.
- No production wiring of any identity source.

## Acceptance

This review passes if:

- The spec trilogy files are present.
- The plan, requirements, and validation files agree on the C verdict.
- `D-IDENTITY-003` is specified in plan.md with the source-by-source rationale.
- The four constraints on a future manual offline mapping (FR-4.1 through FR-4.5) are explicit.
- All FR-* and NFR-* requirements are met.
- No commit is performed unless separately requested.