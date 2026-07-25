# Phase 12E2B — Requirements

## Context

Phase 12E2B separates format-valid `BuffTradableCandidate` data from the explicit policy decision that allows a listing to proceed toward a future solver. This follows the deterministic, explainable, read-only principles in `specs/mission.md` and keeps the business boundary independent of FastAPI, clients, persistence, scheduling, and configuration in accordance with `specs/tech-stack.md`.

The current roadmap's scanner, enrichment, solver, and opportunity-risk phases remain broader future integration concerns. This milestone adds only an isolated listing-level policy contract and does not update roadmap status.

## Scope and decisions

- Remain on `feature/steamdt-cache-rate-limit` from starting commit `443c2336668d4526003fabd6c8d95690b79db45f`.
- Add `BuffListingEligibilityFacts` with exact boolean `is_stattrak`, `is_souvenir`, and `has_special_seed` values supplied explicitly by the caller.
- Never infer facts from market names, paint seeds, wear, stickers, listing identifiers, or external metadata.
- Add an immutable policy with defaults:
  - `min_available_quantity=1`
  - `require_positive_price=True`
  - `require_float_value=True`
  - `allow_stattrak=False`
  - `allow_souvenir=False`
  - `allow_special_seed=False`
- Require an exact positive integer quantity threshold and exact boolean flags; perform no coercion or environment/config lookup.
- Use stable lowercase snake-case `StrEnum` values for six ineligibility reasons in fixed rule order.
- Preserve every applicable reason; do not short-circuit after the first failure.
- Keep `is_eligible` as a read-only derived property equal to whether the reason tuple is empty.
- Make facts, policy, and decision frozen, keyword-only, and repr-suppressed.
- Defensively reconstruct candidate, facts, and policy and validate that directly supplied decisions contain exactly the canonical complete ordered reason tuple.
- Preserve candidate values exactly and leave E1/E2A domain/parser semantics unchanged: zero quantity, zero price, and missing float remain format-valid data.
- Use a fixed safe validation error message and never expose listing content, rejected values, secrets, URLs, raw payloads, or nested exception text.
- Do not catch `MemoryError`, `KeyboardInterrupt`, or other `BaseException` values.

## Explicit exclusions

- No real classification-facts provider.
- No BUFF HTTP, endpoint, authentication, signing, login, Cookie, crawler, captcha, risk-control bypass, browser automation, or purchase behavior.
- No SteamDT, Redis, cache, provider, valuation, EV, recipe solving, risk-filter execution, pipeline, scheduler, FastAPI, Discord, config, environment, database, Docker, or migration integration.
- No changes to the existing BUFF listing domain/parser, scanner, solver, risk filter, or runtime wiring.
- No commit, push, or next phase.

## Approved file scope

Primary files:

- `app/services/buff_listing_eligibility.py`
- `tests/test_buff_listing_eligibility.py`
- `README.md`
- `docs/BUFF_LISTING_NOTES.md`

The user approved these feature-spec files as the only additional scope:

- `specs/2026-07-24-buff-listing-eligibility/plan.md`
- `specs/2026-07-24-buff-listing-eligibility/requirements.md`
- `specs/2026-07-24-buff-listing-eligibility/validation.md`
