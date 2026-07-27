# Phase 12E4C — Requirements

## Context

The existing offline qualification integration returns a complete immutable `BuffListingQualificationRunResult` in input order. The existing strict `adapt_qualified_buff_listing()` converts one valid `QUALIFIED` result into the existing `CandidateListing`. This phase composes those public contracts only; it does not repeat either contract's business work.

## Public integration API

Create one public async runner:

```python
async def run_solver_adapter_integration(
    listings_fixture: Path,
    facts_fixture: Path,
    *,
    qualification_runner: QualificationRunner = run_qualification_integration,
    adapter: Callable[
        [BuffListingQualificationResult], CandidateListing
    ] = adapt_qualified_buff_listing,
) -> BuffListingSolverAdapterIntegrationResult:
    ...
```

The qualification runner is awaited exactly once. Its return value must be the exact existing `BuffListingQualificationRunResult` type.

Add a fixed safe `BuffListingSolverAdapterIntegrationError` with an allow-listed public `stage`. Its message never contains nested exception text, listing data, fixture paths, credentials, or URLs.

## Filtering and adaptation

Traverse `qualification_run_result.ordered_qualification_results` once in original order:

- `QUALIFIED`: call the supplied adapter exactly once and append its exact `CandidateListing` result;
- `REJECTED`: do not call the adapter and count it as skipped rejected;
- `MISSING_FACTS`: do not call the adapter and count it as skipped missing facts;
- any unexpected or malformed status/state: fail closed.

The integration preserves qualified-result order and duplicate occurrences. It never deduplicates, sorts, expands `available_quantity`, retries, falls back, runs concurrently, continues after an adapter failure, or returns a partial result. Ordinary adapter failures become the fixed `adaptation` integration stage. `MemoryError`, `asyncio.CancelledError`, `KeyboardInterrupt`, and other non-`Exception` control flow propagate unchanged as applicable.

Legacy fixture schema v1 remains valid for qualification and produces qualified candidates with `goods_id=None`. The existing adapter must reject the first such qualified result, abort the integration, and cause the command to exit 1 without a partial success summary. The integration must not convert that failure into a skip.

## Immutable result

Add:

```python
@dataclass(frozen=True, kw_only=True, repr=False)
class BuffListingSolverAdapterIntegrationResult:
    qualification_run_result: BuffListingQualificationRunResult
    ordered_solver_candidates: tuple[CandidateListing, ...]
```

The constructor requires:

- the exact existing qualification run-result type;
- an exact tuple for solver candidates;
- every solver candidate to be the exact existing `CandidateListing` type;
- adapted candidate count equal to qualified-result count.

The orchestration runner establishes positional mapping by appending only the direct adapter output for each qualified result during one ordered traversal. It stores no second set of statuses, source indexes, mapping fields, or counts.

Derived properties are exactly:

- `qualification_total_count`;
- `qualified_result_count`;
- `adapted_candidate_count`;
- `skipped_rejected_count`;
- `skipped_missing_facts_count`.

The result repr must not disclose listing ID, goods ID, market name, price, float, seed, or raw candidate state.

## CLI

Create `scripts/buff_listing_solver_adapter_integration.py` with both entrypoints:

```bash
py -3.13 -m scripts.buff_listing_solver_adapter_integration
py -3.13 scripts/buff_listing_solver_adapter_integration.py
```

Accept only:

```text
--listings-fixture
--facts-fixture
```

Defaults are the existing repository-anchored v2 qualification listing fixture and existing qualification facts fixture. Importing the module reads no fixture or environment and creates no client, service, task, thread, executor, or runtime.

Exit codes:

- `0`: complete qualification and adaptation success, including normal rejected/missing-facts skips;
- `1`: qualification, adaptation, orchestration, result, or safe-summary failure;
- `2`: invalid CLI or fixture path;
- `130`: `KeyboardInterrupt` reaching `main()`.

## Safe output

Success output contains at least:

```text
Mode: offline-fixture
Qualification results: 4
Qualified results: 2
Adapted solver candidates: 2
Skipped rejected: 1
Skipped missing facts: 1
Recipe solver executed: no
BUFF requests sent: 0
SteamDT requests sent: 0
Redis used: no
```

For each adapted candidate, output only:

- zero-based adapted index;
- safe market name;
- source;
- float present as `yes` or `no`.

The corresponding qualified source candidate is passed to the existing shared safe market-name renderer. The renderer redacts embedded listing/goods IDs, credentials, secrets, URLs, domains, and sensitive punctuation and JSON-escapes control characters. No new redaction rules are copied.

Never output goods ID, listing ID, price, numeric float value, paint seed, inspect link, raw data, fixture path, exception text, traceback, object repr, credential-shaped content, or URL-shaped content. Build the complete summary before calling the printer so handled failures cannot publish a partial success summary.

## Safe helper reuse

Minimally promote the existing private renderer in `scripts/buff_listing_qualification_integration.py` to the public, purpose-specific `render_safe_buff_candidate_market_name()` name. Its behavior must remain unchanged. Both qualification and solver-adapter commands reuse it; no generic utility or application-service module is introduced.

## Approved scope

Create:

- `scripts/buff_listing_solver_adapter_integration.py`;
- `tests/test_buff_listing_solver_adapter_integration.py`;
- `specs/2026-07-27-buff-solver-adapter-integration/plan.md`;
- `specs/2026-07-27-buff-solver-adapter-integration/requirements.md`;
- `specs/2026-07-27-buff-solver-adapter-integration/validation.md`.

Modify minimally:

- `scripts/buff_listing_qualification_integration.py`;
- `tests/test_buff_listing_qualification_integration.py`;
- `README.md`;
- `docs/BUFF_LISTING_NOTES.md`.

## Explicit exclusions

Do not modify BUFF domain/parser/facts/eligibility/qualification, the single-record adapter, `CandidateListing`, market scanner, recipe solver, metadata, fixtures, risk, valuation, pipeline, scheduler, FastAPI, clients/network/auth, SteamDT, Redis/cache, config, environment, Docker, database, Discord, API notes, roadmap, or earlier feature specs.

The command performs no recipe-solver execution, metadata lookup, BUFF/SteamDT request, Redis use, scanner/pipeline/runtime wiring, batch worker, concurrency, retry, fallback, login, Cookie operation, crawler, automatic purchase, or market write. It is synthetic, manual, offline, and not production-ready. No commit or push occurs unless separately requested.
