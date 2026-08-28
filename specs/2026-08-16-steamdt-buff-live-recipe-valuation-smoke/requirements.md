# Phase 13A Step 2M-A5 — Requirements

## Purpose and evidence boundary

Provide a standalone, explicitly enabled operator harness for this closed path:

```text
build_verified_steamdt_buff_live_recipe_fixture()
→ one deterministic synthetic recipe / ten synthetic inputs
→ one exact historically query-verified output identity
→ one real SteamDT GET /open/cs2/v1/price/single attempt
→ exact case-sensitive BUFF aggregate sell price
→ SteamDTBuffPriceProvider
→ ValuationService
→ value_live_recipes_with_steamdt_buff_prices()
→ existing Step 2F metrics, EV/ROI, and risk
```

Only the output-price lookup is real. The fixture's inputs, collection, prices, floats, paint seeds, timestamp, rarity topology, compatibility provenance, and candidate identities remain synthetic. A successful smoke proves complete valuation plumbing only. It does not prove that the synthetic inputs can produce the real output, that a current buyable or executable opportunity exists, that aggregate output value is guaranteed proceeds, or that the synthetic EV, ROI, profit, or risk has market meaning.

## Allowed scope

New:

- `scripts/run_live_steamdt_buff_live_recipe_valuation_smoke.py`
- `tests/test_live_steamdt_buff_live_recipe_valuation_smoke.py`
- `specs/2026-08-16-steamdt-buff-live-recipe-valuation-smoke/plan.md`
- `specs/2026-08-16-steamdt-buff-live-recipe-valuation-smoke/requirements.md`
- `specs/2026-08-16-steamdt-buff-live-recipe-valuation-smoke/validation.md`

Minimally modified:

- `.env.example`
- `docs/STEAMDT_API_NOTES.md`

No other path may change. In particular, do not modify fixture, policy, provider, aggregate market data, SteamDT client, A3 composition, `ValuationService`, Step 2F, solver, trade-up engine, EV/risk, SteamApis, BUFF Phase 12, cache/Redis/limiter, scheduler, Discord, FastAPI, Docker/database, dependencies, or application configuration.

## Public and CLI contract

The module must expose a testable asynchronous entry point following the existing smoke style:

```python
async def async_main(
    environ: Mapping[str, str] | None = None,
    *,
    printer: Callable[[str], None] = print,
    runtime_factory: SteamDTBuffLiveRecipeValuationSmokeRuntimeFactory | None = None,
) -> int: ...


def main() -> None: ...
```

It must support direct-file and `python -m` execution. It takes no CLI argument and never prompts for a market hash name.

The runtime factory is the only runtime injection seam. The smoke must not expose provider, selector, valuation, price, output-name, metrics, or risk injection as public CLI behavior.

## Dedicated gate and environment order

Add exactly:

```text
STEAMDT_RUN_BUFF_LIVE_RECIPE_VALUATION_SMOKE=false
```

The gate is independent from `STEAMDT_RUN_PRICE_SNAPSHOT_SMOKE` and `STEAMDT_RUN_BUFF_PROVIDER_SMOKE`. It is enabled only when the inherited raw value satisfies:

```python
raw.strip().lower() == "true"
```

The script reads only the supplied mapping or inherited process environment. It does not load `.env`, application settings, files, shell history, or user input. It must never read `STEAMDT_SMOKE_MARKET_HASH_NAME`; the output name comes solely from the zero-argument verified fixture builder.

Strict order:

```text
dedicated gate
→ STEAMDT_API_KEY
→ STEAMDT_BASE_URL
→ build verified fixture
→ pre-network fixture invariants
→ runtime construction
→ one full valuation
```

Gate disabled exits zero before all later reads/actions:

```text
live_smoke_executed: no
reason: opt_in_disabled
SteamDT requests sent: 0
```

Enabled with an absent or blank key exits one before base URL, fixture construction, runtime construction, or network:

```text
live_smoke_executed: no
reason: api_key_missing
SteamDT requests sent: 0
```

The key is stripped before runtime construction and never printed. Base URL uses the existing default when absent and is not printed.

## Verified fixture and pre-network invariants

The script must call exactly:

```python
build_verified_steamdt_buff_live_recipe_fixture()
```

once, with no arguments. Before constructing any HTTP runtime it must fail closed and validate:

```text
exact SteamDTBuffLiveRecipeFixture
recipe count == 1
sole recipe input count == 10
canonical distinct output count == 1
sole exact output identity ==
STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME
```

Canonical identity means the exact existing `TradeupResult.output_market_hash_name`. Do not strip, normalize, case-fold, parse, alias, append wear, repair, or infer it from another field.

Failure precedence:

- ordinary builder failure, wrong fixture/DTO type, malformed nested structure, invalid name value, or exact-name mismatch: `fixture_invalid`;
- recipe count other than one: `recipe_count_invalid`;
- sole recipe input count other than ten: `input_count_invalid`;
- canonical distinct output-name count other than one: `output_count_invalid`.

These failures occur before runtime construction, exit one, and print:

```text
live_smoke_executed: no
result: failed
reason: <allowlisted fixture reason>
SteamDT requests sent: 0
```

Do not modify, repair, rebuild, or rerun an invalid fixture.

## One-attempt owned runtime

The default runtime owns exactly:

- one `httpx.AsyncClient`;
- `timeout=10.0`;
- `follow_redirects=False`;
- one request event hook/counter;
- one `SteamDTHttpClient`;
- `SteamDTClientConfig(timeout_seconds=10.0, max_retries=0, dry_run=False)`.

If SteamDT client construction fails after HTTPX allocation, close that owned HTTPX client and propagate process-control failures. The valuation composition borrows the runtime client and does not own its lifecycle.

The only permitted outbound attempt is:

```text
GET /open/cs2/v1/price/single
one marketHashName query
exact verified fixture output
```

No retry, redirect, fallback, batch, `/base`, `/avg`, kline, wear, second item, loop over market items, Redis, scheduler, task, thread, executor, background work, or SteamApis connection is allowed. Expected success count and maximum outbound-attempt budget are both one.

## Full existing valuation composition

Invoke exactly once:

```python
value_live_recipes_with_steamdt_buff_prices(
    construction_result=fixture.construction_result,
    client=runtime.client,
    solver_config=fixture.solver_config,
    risk_config=fixture.risk_config,
)
```

Do not construct or reimplement `SteamDTBuffPriceProvider`, `ValuationService`, the aggregate helper, BUFF selector, missing-price fallback, fee, EV, ROI, probability, or risk evaluation in the smoke.

Existing authorities must naturally enforce:

- exact case-sensitive platform `BUFF`;
- finite positive `sell_price_cny` under the existing project CNY/RMB interpretation;
- fixed transient `PriceQuote.source == "steamdt:buff"`;
- no bidding-price fallback;
- no STEAM, YOUPIN, C5, HALOSKINS, or other-platform fallback;
- no metadata-zero fallback;
- whole-recipe rejection before metrics/risk when price data is incomplete or invalid.

`LiveRecipeValuationResult` does not retain `PriceQuote.source`. The fixed success line `price_source_path: steamdt:buff` attests that the script invoked the closed A3 composition; it is not dynamically reconstructed from the final DTO.

## Final valuation integrity

Success requires:

- exact `LiveRecipeValuationResult`;
- exactly one opportunity;
- zero rejections;
- opportunity recipe and ordered selected-source provenance structurally aligned with the verified fixture;
- exactly one valued output aligned with the fixture's exact output identity and existing output geometry;
- an exact boolean `risk_decision.passed`.

The script validates structure only. It must not print identity, provenance, seeds, prices, metrics, profit, ROI, or risk reasons.

A structurally valid result with zero opportunities and exactly one aligned rejection maps:

```text
PRICE_PROVIDER_ERROR → price_provider_error
MISSING_OUTPUT_PRICE → missing_output_price
INVALID_VALUATION_RESULT → invalid_valuation_result
```

Other top-level types, cardinalities, mixed success/rejection states, misalignment, or unsupported reason values map to `valuation_result_invalid`. An ordinary exception escaping the A3 call maps to `valuation_failed`. An ordinary runtime factory/setup failure maps to `runtime_failed`.

No exact BUFF, duplicate BUFF, missing/invalid BUFF sell, and ordinary A2 client failures naturally map to `price_provider_error` because existing Step 2F gives provider errors precedence over missing-price evidence.

A false risk decision remains smoke success. It proves that full metrics and risk evaluation completed and returned a valued opportunity; business-filter passage is not required by this plumbing smoke.

## Exact success summary

After successful cleanup, print exactly:

```text
live_smoke_executed: yes
result: success
construction_source: deterministic_versioned_fixture
recipe_count: 1
input_count: 10
distinct_output_count: 1
valuation_opportunities: 1
valuation_rejections: 0
price_source_path: steamdt:buff
ev_evaluated: yes
roi_evaluated: yes
risk_evaluated: yes
risk_passed: yes|no
SteamDT requests sent: 1
```

Only the final risk `yes|no` is dynamic business state. The other evaluation/source lines are fixed attestations to the closed completed path. Exit zero for either risk value.

Never output:

- actual market hash name;
- input or output price;
- expected revenue, EV, expected profit, ROI, loss, or other numeric metric;
- float or paint seed;
- source-offer, listing, or platform item ID;
- provider record, raw response, bid, count, or update time;
- API key, Authorization/header data, base/request URL;
- exception type, message, arguments, representation, traceback, or nested cause.

## Failure allowlist and summaries

The complete permitted reason set is:

```text
opt_in_disabled
api_key_missing
fixture_invalid
recipe_count_invalid
input_count_invalid
output_count_invalid
runtime_failed
price_provider_error
missing_output_price
invalid_valuation_result
valuation_result_invalid
valuation_failed
request_count_invalid
close_failed
```

No other reason may be emitted. Post-runtime failures print exactly:

```text
live_smoke_executed: yes
result: failed
reason: <allowlisted reason>
SteamDT requests sent: <nonnegative integer | unavailable>
```

All details remain fixed and redacted.

## Request-count precedence

A request count is valid only when its exact type is nonnegative `int`; reject booleans, floats, negatives, and property failures.

- Candidate success requires a readable count exactly one; otherwise use `request_count_invalid`.
- During an ordinary valuation/provider/result failure, a readable count greater than one overrides the primary reason with `request_count_invalid`.
- During an ordinary failure, a count of zero or one retains the primary reason. An invalid/unavailable count also retains it and prints `unavailable`.
- Runtime-construction failure has count zero.
- Process-control failures from count access propagate.

## Cleanup and process-control contract

All enabled summaries are buffered until cleanup completes. An assigned runtime is closed exactly once in `finally`.

- An ordinary close failure replaces pending ordinary success/failure with `close_failed`, clears pending success lines, and exits one.
- A body process-control failure still triggers cleanup and prints no summary.
- `MemoryError`, `asyncio.CancelledError`, `KeyboardInterrupt`, `SystemExit`, and other non-ordinary `BaseException` values propagate rather than being converted.
- An ordinary cleanup failure must not suppress an already-active body process-control failure.
- A process-control cleanup failure propagates under normal Python `finally` semantics.
- Printing begins only after cleanup, so a printer failure occurs after owned resources are closed.

## Offline test requirements

Automated tests must perform zero real network. They must cover:

1. gate off → zero network;
2. missing key → zero network;
3. no market-hash-name environment required or read;
4. verified fixture builder used once with no arguments;
5. malformed/wrong exact fixture → `fixture_invalid` before runtime;
6. recipe count other than one → `recipe_count_invalid` before runtime;
7. input count other than ten → `input_count_invalid` before runtime;
8. canonical distinct output count other than one → `output_count_invalid` before runtime;
9. full local-transport success → exactly one request;
10. only `GET /open/cs2/v1/price/single` with one exact query;
11. `max_retries=0`;
12. exact BUFF sell-price path;
13. a higher bid and higher other-platform sells are ignored;
14. no exact BUFF → safe `price_provider_error`;
15. missing/nonfinite/nonpositive BUFF sell → safe `price_provider_error`;
16. ordinary hostile provider/client failure → fixed safe failure;
17. complete valuation → one opportunity and zero rejection;
18. true risk decision → success;
19. false risk decision → still success;
20. valid missing-price rejection → `missing_output_price`;
21. valid invalid-valuation rejection → `invalid_valuation_result`;
22. no metadata-zero fallback and no metrics/risk after incomplete valuation;
23. fixed source-path attestation `steamdt:buff` through the closed A3 path;
24. existing Step 2F metrics/EV authority executes;
25. existing Step 2F ROI is produced without smoke formula/access;
26. existing Step 2F risk authority executes with preserved paint-seed structure;
27. smoke module contains no EV/fee/profit formula;
28. smoke module contains no ROI formula or direct ROI access;
29. smoke module contains no risk formula or direct risk-authority call;
30. no output price printed;
31. no EV/revenue/profit number printed;
32. no ROI number printed;
33. no actual output name printed;
34. no provenance IDs printed;
35. no paint seeds printed;
36. no key, header, URL, raw response, provider ID, bid, or update-time data printed;
37. request count greater than one → `request_count_invalid`;
38. ordinary close failure → `close_failed` with no partial success;
39. `MemoryError` propagates after cleanup;
40. `CancelledError` propagates after cleanup;
41. `KeyboardInterrupt` propagates after cleanup;
42. `SystemExit` propagates after cleanup;
43. no SteamApis import/use or reverse import;
44. no Redis/cache/limiter behavior;
45. no scheduler/task/thread/background behavior;
46. no purchase, auto-buy, login, Cookie scraping, CAPTCHA bypass, browser purchase, or marketplace-write behavior.

Also test false-like/mixed-case gate parsing, count property validation, runtime setup/cleanup ownership, printing after cleanup, and disabled direct-file/module entrypoints.

Use narrow fake clients/runtimes for behavior and one local `httpx.AsyncBaseTransport` for the real HTTP parser-to-Step-2F chain. Build real fixtures first and use test-only mutation solely to exercise malformed pre-network geometry. The risk-false branch may use a test-only otherwise-valid stricter `RiskFilterConfig`; production fixture defaults must not change.

## Validation and stop conditions

Run the required focused suites, full pytest, Ruff, Mypy for `app` and the new script, and whitespace/scope audits entirely offline. Record actual outcomes only after execution.

After validation inspect only whether inherited `STEAMDT_RUN_BUFF_LIVE_RECIPE_VALUATION_SMOKE` and `STEAMDT_API_KEY` are nonblank, and report yes/no without values. Never execute the real smoke automatically, even if both are present.

Stop without staging, committing, pushing, or beginning another step. Stop and report a blocker if implementation requires a protected-core change, exposes dynamic source provenance unavailable from the final DTO, or causes an eighth path to differ.
