# Phase 13B Step 2B — Requirements

## Purpose and evidence boundary

Provide a standalone, explicitly enabled compatibility probe for one anonymous, read-only request:

```text
GET https://buff.163.com/api/market/goods/sell_order
?game=csgo
&goods_id=<explicit inherited nonsecret ID>
&page_num=1
&sort_by=default
```

This is a research-only empirical schema probe. It is not official BUFF OpenAPI, a production provider, a scanner, a stable future contract, or evidence that anonymous access will remain available. It performs no login, session, Cookie, API-key, browser, CAPTCHA/risk-control bypass, transaction, purchase preview, or purchase action. If anonymous compatibility is unavailable, it fails closed without circumvention.

The smoke verifies only whether the current response exposes one first concrete sell-order item with:

```text
items[0].id
items[0].price
items[0].asset_info.paintwear
```

Optional presence probes are limited to `asset_info.assetid` and `asset_info.paintseed`. No concrete market value is printed or retained as a production fixture.

## Allowed scope

New:

- `scripts/run_live_buff_anonymous_sell_order_schema_smoke.py`
- `tests/test_live_buff_anonymous_sell_order_schema_smoke.py`
- `docs/BUFF_ANONYMOUS_READONLY_NOTES.md`
- `specs/2026-08-20-buff-anonymous-sell-order-schema-smoke/plan.md`
- `specs/2026-08-20-buff-anonymous-sell-order-schema-smoke/requirements.md`
- `specs/2026-08-20-buff-anonymous-sell-order-schema-smoke/validation.md`

Modified:

- `.env.example`

No other path may change. In particular, do not modify or complete `BuffHttpClient`, Phase 12 BUFF domain/parser/qualification/adapters, `CandidateListing`, solver, engine, SteamDT, SteamApis, valuation, EV/risk, scheduler, Redis, Discord, database, Docker, dependencies, or application settings.

## Reused Phase 12 semantics

The existing Phase 12 identifier contract is exact string, stripped, nonblank; it does not require digits-only goods IDs. There is no public standalone scalar validator, and `BuffListingObservation` cannot truthfully be built from the limited probed fields without inventing market name, quantity, and observation semantics. The smoke therefore owns narrow scalar validation matching those existing nonblank-string and Decimal/range semantics, while leaving protected Phase 12 core unchanged.

It must not invoke qualification, facts lookup, eligibility, candidate adaptation, scanner, solver, EV/ROI, or risk.

## Public/CLI contract

```python
async def async_main(
    environ: Mapping[str, str] | None = None,
    *,
    printer: Callable[[str], None] = print,
    runtime_factory: BuffAnonymousSchemaSmokeRuntimeFactory | None = None,
) -> int: ...


def main() -> None: ...
```

It supports direct-file and `python -m` execution and accepts no CLI arguments. Endpoint, method, query, User-Agent, headers, page, and schema paths are fixed constants rather than operator-configurable values.

## Environment and guards

Add exactly:

```text
BUFF_RUN_ANONYMOUS_SELL_ORDER_SCHEMA_SMOKE=false
BUFF_READONLY_SMOKE_GOODS_ID=
```

Only stripped case-insensitive `true` enables the dedicated gate. Strict order is:

```text
gate
→ goods-ID presence
→ goods-ID validation
→ runtime construction
→ one request
```

The mapping is supplied explicitly or inherited from the current process. The script does not load `.env`, application settings, files, history, browser state, credentials, or another provider.

Gate disabled exits zero before reading goods ID or constructing runtime:

```text
live_smoke_executed: no
reason: opt_in_disabled
BUFF requests sent: 0
```

Enabled with absent/blank goods ID exits one before runtime:

```text
live_smoke_executed: no
reason: goods_id_missing
BUFF requests sent: 0
```

Goods ID validation accepts only exact `str`; it is stripped and must remain nonblank. Non-string values are invalid and map to `goods_id_invalid`. There is no digits-only restriction. The value is never inferred, parsed from a URL, looked up, or printed.

## Anonymous HTTP runtime

The default runtime owns exactly one `httpx.AsyncClient` configured with:

```text
base_url = https://buff.163.com
timeout = 10.0
follow_redirects = False
trust_env = False
User-Agent = cs2-tradeup-readonly-schema-smoke/1.0
Accept = application/json
```

It has no auth object or Cookie jar and adds no Cookie, Authorization, Proxy-Authorization, API-key, Device-Id, CSRF, Origin, Referer, X-Requested-With, signature, nonce, session, fingerprint, or browser-emulation header.

The only client operation sends one bodyless GET to exact path `/api/market/goods/sell_order` with exactly these ordered query pairs:

```text
game=csgo
goods_id=<validated exact value>
page_num=1
sort_by=default
```

It adds no `page_size`, paintwear/paintseed filters, price sort, generic filter/search, second page, alternate endpoint, retry, backoff, sleep, redirect, fallback, proxy rotation, User-Agent rotation, task, thread, subprocess, or background work.

## Hard request budget and request contract

A pre-send event hook validates before transport:

- exact GET;
- exact HTTPS host, default port, and path;
- exact ordered query pairs;
- empty request body;
- exact fixed User-Agent and Accept;
- no sensitive/auth/browser/session headers;
- no URL userinfo.

The runtime distinguishes attempt-hook count, dispatched outbound count, and a budget-exceeded flag. Attempt one increments dispatched count and may reach transport. Attempt two sets the budget flag and raises before transport, so maximum actual outbound attempts is one.

Success requires exact valid state `(attempted=1, dispatched=1, budget_exceeded=False)`. Any invalid/unreadable state, a second attempted send, zero dispatched requests after candidate success, or dispatched count greater than one maps to `request_count_invalid`. A request-contract violation is an ordinary fixed failure and exposes no URL/query/value.

## Response handling and precedence

An ordinary transport/client exception or any non-2xx HTTP response maps to `request_failed`. No retry occurs. Status, exception, URL, headers, and body are not printed.

Decode response bytes using strict JSON rules:

- fractional JSON numbers parse directly to `Decimal`;
- nonstandard bare `NaN`/Infinity constants are rejected;
- malformed or non-JSON bytes map to `response_not_json`;
- valid JSON whose top level is not an exact object maps to `response_schema_invalid`.

Then validate in this order:

1. `code` must be exact string `OK`; any other/missing/wrong value maps to `anonymous_access_unavailable` and no provider message is rendered.
2. `data` must be an object; otherwise `response_schema_invalid`.
3. `data.items` must exist and be an exact list; otherwise `items_missing`.
4. Empty list maps to `no_items`; no second page is requested.
5. Inspect exactly `items[0]`; it must be an object or map to `response_schema_invalid`.
6. Validate required fields, then optional presence. Never iterate, search for a valid item, inspect item two, or fall forward.

## First-item fields

### `id`

`id` must be present as an exact nonblank `str`, stripped locally. Missing, null, blank, integer, boolean, float/Decimal, container, or other type maps to `listing_id_missing`. This matches the existing Phase 12 listing-ID string contract and avoids inventing a live integer-ID mapping. Output contains only `listing_id_present: yes` on success.

Third-party behavior evidence associates `items[].id` with `sell_order_id`; this probe verifies only current compatibility and does not claim official BUFF semantics or permanence.

### `price`

Accept exact string, exact `Decimal`, or exact `int` excluding `bool`. Strings must be nonblank and already trimmed. Parse directly to `Decimal` without a binary-float round trip. Require finite and strictly greater than zero. Invalid, missing, null, zero, negative, nonfinite, bool, float, or container maps to `price_invalid`.

Output contains only `price_valid: yes` on success.

### `asset_info.paintwear`

`asset_info` must be an object. `paintwear` accepts exact string, exact `Decimal`, or exact `int` excluding `bool`, under the same direct Decimal rules. Require finite inclusive `[0,1]`. Missing/null/invalid type, nonfinite, negative, or greater than one maps to `paintwear_invalid`.

Output contains only `paintwear_valid: yes` on success. No alternate field, wear inference, or external enrichment is allowed.

### Optional passive presence

For `asset_info.assetid` and `asset_info.paintseed`:

- absent or null → `no`;
- any present non-null value → `yes`.

They are not parsed, required, printed, used as identity, or sent elsewhere. Unknown fields and all later items are ignored.

## Exact success summary

After successful cleanup, print exactly:

```text
live_smoke_executed: yes
result: success
anonymous_request: yes
cookie_used: no
login_used: no
page_num: 1
item_list_present: yes
listing_item_present: yes
listing_id_present: yes
price_valid: yes
paintwear_valid: yes
asset_id_present: yes|no
paintseed_present: yes|no
BUFF requests sent: 1
```

Never output goods ID, listing ID, price, float, seller/account/asset ID, market name, URL/query, response body, BUFF message, headers, cookies, object repr, exception type/message/cause, or traceback.

## Failure allowlist

The complete permitted reason set is:

```text
opt_in_disabled
goods_id_missing
goods_id_invalid
runtime_failed
request_failed
anonymous_access_unavailable
response_not_json
response_schema_invalid
items_missing
no_items
listing_id_missing
price_invalid
paintwear_invalid
request_count_invalid
close_failed
```

No other reason may be emitted. Enabled failures print only:

```text
live_smoke_executed: yes|no
result: failed            # omitted only for gate/missing/invalid local guards
reason: <allowlisted reason>
BUFF requests sent: <nonnegative integer | unavailable>
```

Gate and local goods-ID guards use `live_smoke_executed: no`; runtime and later failures use `yes` except runtime creation failure, which uses `no` because no request runtime became available. Exact output variants are locked in tests.

A readable budget violation overrides an ordinary body failure with `request_count_invalid`. Candidate success with any state other than exact one dispatched request also maps there. An ordinary close failure overrides pending ordinary success/failure with `close_failed`.

## Lifecycle and exception policy

All enabled output is buffered until cleanup. An assigned runtime is closed exactly once in `finally`; printer invocation starts only afterward.

- Ordinary close failure replaces pending output with fixed `close_failed`.
- `MemoryError` and `asyncio.CancelledError` are explicitly rethrown.
- `KeyboardInterrupt`, `SystemExit`, and other direct `BaseException` values propagate naturally.
- Body process-control still triggers cleanup and produces no summary.
- Ordinary cleanup failure does not suppress an active process-control value.
- Process-control cleanup failure propagates under normal `finally` semantics.

## No-evasion and read-only guarantees

Production smoke source contains no randomization, proxy configuration/rotation, retry/backoff/sleep, Cookie/session handling, login, API key, Device-Id, CSRF, Referer spoofing, X-Requested-With, browser automation, purchase/buy-preview/auto-buy, CAPTCHA or Cloudflare/risk-control bypass, scrape loop, second page, solver, valuation, EV/ROI/risk, scheduler, cache/Redis, database, Discord, or marketplace write.

If the anonymous endpoint rejects the request, `anonymous_access_unavailable` or `request_failed` is final; the smoke does not add browser-like state or try again.

## Offline tests

Automated pytest performs zero real network and covers all requested requirements:

1. gate off → zero network;
2. missing goods ID → zero network;
3. invalid goods ID → zero network;
4. exactly one GET;
5. exact endpoint path;
6. `game=csgo`;
7. `page_num=1`;
8. `sort_by=default`;
9. no page size;
10. no float filters;
11. no paintseed filters;
12. no retry;
13. redirects disabled;
14. fixed nonrandom User-Agent;
15. no Cookie;
16. no auth header;
17. no Device-Id;
18. no CSRF;
19. valid `code=OK` and valid first item succeeds;
20. non-OK code → anonymous unavailable;
21. non-JSON → safe failure;
22. missing/wrong `data.items` → failure;
23. empty items → no items;
24. missing/invalid item ID → failure;
25. valid Decimal price;
26. zero price → failure;
27. negative price → failure;
28. nonfinite price → failure;
29. valid paintwear including boundaries;
30. paintwear below zero → failure;
31. paintwear above one → failure;
32. optional asset ID absent → success;
33. optional paint seed absent → success;
34. no raw JSON output;
35. no goods ID output;
36. no listing ID output;
37. no price output;
38. no float output;
39. no BUFF message output;
40. second request blocked before transport;
41. close failure → safe reason;
42. MemoryError propagates;
43. CancelledError propagates;
44. KeyboardInterrupt propagates;
45. SystemExit propagates;
46. no purchase-related imports/calls;
47. no login/Cookie code;
48. no proxy/User-Agent rotation;
49. no retry/backoff;
50. no live network in pytest.

Additional tests cover normalized gate variants, exact public signature/constants, first-item-only behavior, fixed allowlist, request-state validation/precedence, runtime construction cleanup, printer-after-close, disabled direct/module entrypoints, strict redaction, protected reverse imports, and exact `.env.example` declarations.

Use fake runtimes and one local `httpx.AsyncBaseTransport`; an autouse socket/DNS guard fails every accidental socket path.

## Documentation and stop conditions

`docs/BUFF_ANONYMOUS_READONLY_NOTES.md` records only the empirical research contract and its limitations. Existing `BUFF_API_NOTES.md` remains the authority for unresolved official/production mapping questions.

All implementation and validation remain offline. After validation, inspect only nonblank inherited presence of the gate and goods ID, report yes/no without values, and never execute the smoke automatically.

Stop without staging, committing, pushing, or beginning another step. Stop if implementation requires protected-core changes, adds an eighth path, or needs any authentication/evasion behavior.
