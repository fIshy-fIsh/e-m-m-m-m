# Phase 12E3B — Requirements

## Context

Phase 12E2B owns explicit `BuffListingEligibilityFacts`, policy, reasons, and the eligibility evaluator. Phase 12E3A owns exact listing-identity facts lookup and preserves unavailable metadata as `MISSING` with `facts=None`. This phase adds only the isolated service-layer composition between those existing contracts. It supports the deterministic, traceable, read-only principles in `specs/mission.md` and the modular service boundary in `specs/tech-stack.md`.

No existing module owns this exact responsibility. The new service must not duplicate facts, policy, reasons, or eligibility rules and must not become runtime wiring.

## Scope and decisions

- Reuse `BuffTradableCandidate`, `BuffListingFactsProvider`, `BuffListingFactsLookupResult`, `BuffListingFactsLookupStatus`, `BuffListingEligibilityPolicy`, `BuffListingEligibilityDecision`, and `evaluate_buff_listing_eligibility()` unchanged.
- Add `BuffListingQualificationStatus` with exact stable values `qualified`, `rejected`, and `missing_facts`.
- Add `BuffListingQualificationResult` with exactly candidate, policy, facts lookup result, and optional eligibility decision.
- Qualification status is a derived property and is not accepted or stored as constructor state.
- Result state is frozen, keyword-only, repr-suppressed, and defensively reconstructed; caller/provider/evaluator object identity is not retained.
- Candidate, policy, lookup-result, and decision boundaries require the exact concrete public types. Subclasses are rejected.
- Direct public result construction enforces the same complete invariants as the service.
- The service explicitly receives a facts provider and optionally a synchronous evaluator callable; `None` selects the existing evaluator.
- Provider/evaluator capability validation must not invoke the provider, evaluator, hostile property getter, truthiness method, signature inspection, or external work.
- The service does not own, close, initialize, configure, or replace either collaborator.

## Qualification flow

For each `qualify(candidate, policy)` call:

1. Validate and defensively snapshot exact candidate and policy inputs before collaborator work.
2. Call `provider.lookup_facts()` exactly once with a detached candidate.
3. Require an exact, defensively reconstructed lookup result whose canonical listing ID and market name both equal the queried candidate.
4. A valid `MISSING` lookup returns `MISSING_FACTS` with `decision=None`, does not call the evaluator, and never synthesizes all-false facts.
5. A valid `FOUND` lookup invokes the existing/injected evaluator exactly once with detached candidate, found facts, and policy.
6. Require an exact, defensively reconstructed decision whose candidate, facts, and policy equal the current qualification call.
7. A found decision with no reasons derives `QUALIFIED`; a found decision with one or more reasons derives `REJECTED`.

No name, listing ID, wear, sticker, or paint-seed content is interpreted to create or change facts. Existing eligibility reasons and their canonical order are preserved by the existing decision contract.

## Invariants and fail-closed behavior

- `MISSING_FACTS`: lookup status is `MISSING`, lookup facts is `None`, and decision is `None`.
- `QUALIFIED`: lookup status is `FOUND`, lookup facts exists, decision exists, and decision has no reasons.
- `REJECTED`: lookup status is `FOUND`, lookup facts exists, decision exists, and decision has one or more reasons.
- Lookup identity must exactly match candidate listing ID and market name after existing canonicalization.
- A found decision must match the qualification candidate, lookup facts, and policy.
- Non-result collaborator values, contradictory or tampered lookup state, nested tampering, invalid decisions, mismatched identity/state, and hostile collaborator results fail closed with one fixed qualification validation error.
- Provider errors are not converted to `MISSING_FACTS`.
- Evaluator errors are not converted to `REJECTED`.
- There is no retry, fallback, alternate provider, or all-false default.

## Errors and confidentiality

- `BuffListingQualificationValidationError` uses fixed public text and retains only a stable aggregate `field` classification.
- Errors and public repr never reveal listing identities, market names, raw objects, facts, reasons, payloads, paths, seller information, credentials, Cookie/Bearer/password data, Redis URLs, or nested exception text.
- Ordinary failures while validating completed object state may be translated with suppressed chaining.
- No catch block spans collaborator invocation. Provider and evaluator exceptions propagate unchanged, including ordinary typed errors, `MemoryError`, `KeyboardInterrupt`, `asyncio.CancelledError`, and other `BaseException` values.

## Approved file scope

Create:

- `app/services/buff_listing_qualification.py`
- `tests/test_buff_listing_qualification.py`
- `specs/2026-07-25-buff-listing-qualification/plan.md`
- `specs/2026-07-25-buff-listing-qualification/requirements.md`
- `specs/2026-07-25-buff-listing-qualification/validation.md`

Modify:

- `README.md`
- `docs/BUFF_LISTING_NOTES.md`

## Explicit exclusions

- No real BUFF API, facts adapter, metadata fetch, endpoint, authentication, login, Cookie handling, crawler, captcha handling, browser automation, risk-control bypass, market write, or automatic purchase.
- No facts inferred from market names, listing IDs, wear, stickers, or paint seeds.
- No SteamDT, Redis, cache, database, environment, configuration, Docker, or deployment connection.
- No batch qualification, background task, thread, retry, fallback, provider lifecycle, or file I/O.
- No scanner, recipe solver, risk filter, valuation, provider, pipeline, scheduler, FastAPI, Discord, or runtime wiring.
- No changes to existing BUFF domain, parser, fixture, facts, policy, reason, decision, or eligibility semantics.
- No changes to metadata, solver, risk, pipeline, scheduler, FastAPI, config, client, SteamDT, Redis, Docker, Alembic, PostgreSQL, Discord, `docs/STEAMDT_API_NOTES.md`, or `specs/roadmap.md` files.
- No commit, push, or next phase.
