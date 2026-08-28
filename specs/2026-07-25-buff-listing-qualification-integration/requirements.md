# Phase 12E4A — Requirements

## Context

Phase 12E2A owns strict project-owned listing fixture parsing, E1 owns normalization, E3A owns explicit offline facts lookup, E2B owns eligibility facts/policy/reasons/evaluation, and E3B owns single-candidate qualification. This phase adds only a manual offline integration command that invokes those existing contracts in order. It does not add a second domain, fixture parser, facts model, policy, evaluator, or qualification rule.

The existing listing and facts fixtures intentionally do not share listing IDs and therefore cannot demonstrate every qualification outcome together. Dedicated synthetic integration fixtures will be added without changing their semantics.

## Processing contract

The command must execute exactly this sequence:

1. Load the complete listing fixture with `load_buff_listing_fixture()`.
2. Call `normalize_buff_listing()` once for every observation in fixture order.
3. Load the complete facts fixture with `load_buff_listing_facts_fixture()`.
4. Construct `OfflineBuffListingFactsProvider` from those records.
5. Construct one existing default `BuffListingEligibilityPolicy()`.
6. Construct `BuffListingQualificationService` with that provider.
7. Sequentially call `qualify(candidate, policy)` once for each candidate in order.
8. Return an immutable ordered run result only after the complete run succeeds.
9. Render a fixed, safe summary.

No listing is deduplicated. Repeated listing identities retain input order and are independently normalized and qualified. The command never joins facts itself, infers metadata from names or paint seeds, retries, falls back, continues after a processing failure, or returns a partial success result.

## Run result

The new script-level result is frozen, keyword-only, and repr-suppressed. It stores only:

- `ordered_candidates: tuple[BuffTradableCandidate, ...]`
- `ordered_qualification_results: tuple[BuffListingQualificationResult, ...]`

Tuple lengths must match, and each result candidate must equal the candidate at the same index. `total_count`, `qualified_count`, `rejected_count`, and `missing_facts_count` are derived properties rather than caller-supplied state.

The three existing status values remain authoritative:

- `qualified`
- `rejected`
- `missing_facts`

`MISSING_FACTS` remains distinct from `REJECTED`, keeps `lookup_result.facts=None`, and never creates all-false facts. Rejection reasons come unchanged from the existing eligibility decision.

## Dedicated fixtures

`qualification_listings_v1.json` and `qualification_facts_v1.json` use the existing strict fixture schemas. Their ordered outcomes are:

1. qualified using explicit all-false facts;
2. rejected using explicit `is_stattrak=true` facts and the default policy;
3. a repeated occurrence of the first identity, qualified again;
4. missing facts because the compound identity has no record.

Expected counts are total 4, qualified 2, rejected 1, and missing facts 1. All data is explicitly project-owned and synthetic, not a BUFF response or confirmed transport mapping. Decimal values remain JSON strings. Fixtures contain no seller/account data, Cookie, authorization, token, password, URL, inspect link, endpoint, or raw transport payload.

## CLI and output

Both forms must work:

```text
py -3.13 scripts/buff_listing_qualification_integration.py
py -3.13 -m scripts.buff_listing_qualification_integration
```

The only options are:

```text
--listings-fixture <path>
--facts-fixture <path>
```

Both default to the dedicated repository fixtures through paths anchored to the script location, not the process working directory. Importing the module performs no fixture or environment read, service/client/runtime construction, network or Redis I/O, or task creation.

A successful summary includes mode, total/status counts, zero BUFF requests, zero SteamDT requests, and no Redis use. Each listing includes only zero-based index, safe canonical market name, qualification status, rejection reason values when present, and facts status.

Market names are redacted for credential/URL-shaped segments and JSON-escaped to prevent control-character injection. Output never includes listing IDs, raw objects or payloads, facts objects, paths, Cookie, Bearer/Authorization values, tokens, passwords, URLs, exception messages, nested exception text, or tracebacks. Failures use command-owned fixed stage labels rather than arbitrary exception class names.

## Exit codes and failures

- `0`: the complete command ran, including any normal rejected or missing-facts outcomes.
- `1`: fixture content parsing, normalization, provider construction/lookup, qualification, run-result validation, or orchestration failed.
- `2`: CLI syntax or fixture path validation failed because a path is missing or is not a regular file.
- `130`: `KeyboardInterrupt` reached `main()`.

A failure prints no fabricated partial success summary. Provider and evaluator failures never become `MISSING_FACTS` or `REJECTED`. `MemoryError` and `asyncio.CancelledError` propagate instead of being wrapped as a command result.

## Approved file scope

Create:

- `scripts/buff_listing_qualification_integration.py`
- `tests/test_buff_listing_qualification_integration.py`
- `tests/fixtures/buff/qualification_listings_v1.json`
- `tests/fixtures/buff/qualification_facts_v1.json`
- `specs/2026-07-25-buff-listing-qualification-integration/plan.md`
- `specs/2026-07-25-buff-listing-qualification-integration/requirements.md`
- `specs/2026-07-25-buff-listing-qualification-integration/validation.md`

Modify:

- `README.md`
- `docs/BUFF_LISTING_NOTES.md`

## Explicit exclusions

Do not modify existing listing domain, parser, facts, eligibility, or qualification behavior. Do not add or connect a BUFF endpoint/client, login, Cookie, authentication, crawler, metadata fetch, network, SteamDT, Redis/cache, database, scanner, recipe solver, risk, valuation, pipeline, scheduler, FastAPI, Discord, config/environment input, Docker, deployment, retry, fallback, batch worker, thread, background task, browser automation, risk-control bypass, or automatic purchase.

Do not modify `docs/BUFF_API_NOTES.md`, `docs/STEAMDT_API_NOTES.md`, or `specs/roadmap.md`. Do not commit, push, or start the next phase.
