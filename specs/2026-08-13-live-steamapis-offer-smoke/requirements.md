# Phase 13A Step 2K — Requirements

## Purpose

Add one manual, explicit-opt-in, bounded-duration smoke proving that real SteamApis WebSocket offer observations can pass through the existing parser and foreground session runner into the existing in-memory offer pool.

The authoritative chain is:

```text
official SteamApis WebSocket
→ existing SteamApisWebSocketClient
→ existing Step 2A parser
→ existing run_steamapis_offer_session()
→ existing SteamApisOfferPool
→ one post-stop snapshot
→ aggregate-only safe summary
```

This step deliberately does not invoke Step 2J. Production metadata loading/composition and current recipe construction remain Step 2L work.

## Official provider contract

Only these official pages are authoritative for Step 2K:

- https://docs.steamapis.com/market-data/websocket
- https://docs.steamapis.com/market-data/websocket/offers
- https://docs.steamapis.com/market-data/reference

They document:

- endpoint `wss://marketplaceapi.steamapis.com/ws/v2/offers`;
- `apiKey` query authentication and required `websocketAccess` permission;
- required `permessage-deflate` compression;
- at most two concurrent connections per API key;
- required `subscribeTo` and `games` fields with optional default-false `newFloorOnly`;
- Added and Updated offer events;
- offer fields including `purchaseLink`, currency fields including `priceCNY`, `daysTradeLocked`, `foundAt`, and CS2 float/paint/sticker data.

The existing client and parser already implement the relevant fixed Buff163 + CS2 contract. Step 2K must not change or duplicate those modules.

## CLI contract

The command supports:

```bash
py -3.13 scripts/run_live_steamapis_offer_smoke.py --seconds 15
py -3.13 -m scripts.run_live_steamapis_offer_smoke --seconds 15
```

`--seconds`:

- is the only command option other than standard help;
- accepts a decimal integer only;
- defaults to `15`;
- accepts `5` through `60` inclusive;
- rejects zero, negatives, values below 5, values above 60, fractions, NaN, infinity, missing values, and malformed input;
- is validated before any environment access or collaborator construction.

Invalid CLI input prints only:

```text
live_smoke_executed: no
reason: invalid_duration
```

and exits with code 2 and zero network activity.

## Environment and explicit opt-in

The script reads only its inherited process environment. It must not load `.env`, read shell history, search user files, or prompt for a key.

Environment names:

```text
ENABLE_LIVE_STEAMAPIS_SMOKE
STEAMAPIS_API_KEY
```

Networking is enabled only when the gate value, after trimming whitespace and ignoring case, is exactly `true`. Every other value is safely disabled.

Guard ordering is strict:

1. validate CLI;
2. read the gate;
3. if disabled, exit 0 without reading the key;
4. only when enabled, read and strip the API key;
5. if the key is absent or blank, fail closed with nonzero exit and construct nothing;
6. only then build client and pool collaborators.

Gate disabled output:

```text
live_smoke_executed: no
reason: opt_in_disabled
```

Missing-key output:

```text
live_smoke_executed: no
reason: api_key_missing
```

The key must never be written to the repository, command line, output, repr, exception rendering, logs, files, databases, or docs.

## Existing client/session/pool authority

Step 2K instantiates but does not modify or duplicate:

- `SteamApisWebSocketConfig` and `SteamApisWebSocketClient`;
- `run_steamapis_offer_session()`;
- `SteamApisOfferPool`.

The existing client remains authoritative for endpoint pinning, API-key URI encoding, compression, open timeout, maximum message size, fixed subscription, SUBSCRIBED gating, parsing, normal close, abnormal failure, cancellation, and absence of retry/reconnect.

The existing session runner remains authoritative for one iterator, sequential pool ingestion, no rollback, normal result count, fixed ordinary failures, and cancellation propagation. The smoke ignores `observations_consumed` because timeout returns no session result and consumed events are not current retained observations.

The pool remains authoritative for identity, newer/older/equal-time behavior, TTL, capacity, and deterministic snapshots.

## Smoke-only pool composition

The script composes a process-local pool with:

```text
max_size = 5000
ttl = 10 minutes
```

These are manual smoke retention settings, not production scanner defaults.

The smoke uses no Redis, persistence, background purge, scheduler, database, or application configuration layer.

## Bounded session lifecycle

Exactly one `asyncio.timeout(seconds)` context wraps exactly one call to:

```python
await run_steamapis_offer_session(client=client, pool=pool)
```

The script must create no explicit task and use no retry, reconnect, second client, second iterator, second runner call, loop, backoff, sleep, thread, queue, executor, or scheduler.

When the timeout expires:

- cancellation propagates through the unchanged session runner/client;
- the WebSocket context unwinds and closes;
- the outer smoke recognizes actual timeout-context expiry as expected `stop_reason: timeout`;
- no reconnection occurs.

A collaborator-raised `TimeoutError` that is not caused by expiry of the smoke timeout is an ordinary session failure.

If the stream completes normally before the deadline, the stop reason is `normal_close` and the script does not reopen it.

An ordinary setup or session failure prints only:

```text
live_smoke_executed: yes
result: failed
reason: session_failed
```

and exits nonzero without a post-success snapshot or retry.

`MemoryError`, external `asyncio.CancelledError`, `KeyboardInterrupt`, and other non-`Exception` process-control values propagate unchanged.

## One post-stop snapshot

After expected timeout or normal completion only:

```python
snapshot = pool.snapshot()
```

is called exactly once.

The snapshot retains its existing lazy TTL eviction. The script must not call pool getters, purchase-link APIs, candidate projection, Step 2J, classifier, metadata lookup, recipe construction, solver, valuation, or another snapshot.

The summary fields are derived only from the current snapshot:

- `retained_observations` — total current retained observations;
- `retained_added` — current observations whose event type is Added;
- `retained_updated` — current observations whose event type is Updated.

They are post-TTL/post-capacity current-state counts. They are not consumed, inserted, accepted, unique event volume, or final session-runner counts. The total must equal Added plus Updated.

An ordinary snapshot/summary failure prints a fixed `snapshot_failed` result, returns nonzero, and emits no partial counts. Process-control exceptions propagate.

## Success and output

A live attempt succeeds only when the unique current snapshot retains at least one observation.

Success output may contain only:

```text
live_smoke_executed: yes
result: success
stop_reason: timeout | normal_close
duration_seconds: N
retained_observations: N
retained_added: N
retained_updated: N
```

If retained count is zero, output the same aggregate stop/count context plus:

```text
result: failed
reason: no_retained_observations
```

and exit nonzero. Do not reconnect to try again.

Output must never include:

- API key, encoded URI, query string, or Authorization material;
- nested exception text, external error payload, raw frame, or raw JSON;
- purchase/inspect links;
- source, offer, listing, seller, or account IDs;
- market/item names;
- price, float, paint index/seed, stickers, trade locks, or timestamps.

The script writes no logfile, database record, cache entry, or other artifact.

## Exit matrix

| Condition | Exit code |
|---|---:|
| Gate absent or not exact normalized `true` | 0 |
| Gate enabled but key absent/blank | 1 |
| Invalid CLI duration/arguments | 2 |
| Expected stop and retained count > 0 | 0 |
| Expected stop and retained count = 0 | 1 |
| Ordinary setup/session/snapshot failure | 1 |
| Memory/cancellation/process-control exception | propagate |

## Automated tests and optional live run

Every pytest case is offline. Tests use explicit environment mappings and injected fakes; any subprocess test removes the live gate from its inherited environment. Automated validation must make zero real SteamApis, SteamDT, BUFF, Redis, Discord, or PostgreSQL requests/connections.

Only after all offline validation passes may one real smoke be run, at most once, and only when the current inherited shell already has both:

```text
ENABLE_LIVE_STEAMAPIS_SMOKE=true
STEAMAPIS_API_KEY=<nonblank>
```

The implementation must not prompt, discover, source, modify, or print either value. If either guard is absent, the real smoke is skipped and the final report states only which guard category was missing.

## Explicit exclusions

Step 2K does not:

- invoke `construct_live_recipes_from_pool()`, `construct_live_recipes()`, or `classify_steamapis_snapshot()`;
- load or compose production metadata;
- project candidates or invoke the solver;
- perform SteamDT valuation, EV, risk, alerts, runtime scheduling, persistence, or Redis work;
- call a direct BUFF API;
- automatically log in, collect cookies, bypass CAPTCHA/risk control, simulate a browser purchase, or buy anything;
- add retry, reconnect, background ownership, or production runtime wiring.

Step 2G remains blocked because official SteamDT documentation still does not establish that batch `sellPrice` / `biddingPrice` are CNY/RMB. No SteamDT module or `PriceQuote.price_cny` / `PriceProvider` currency semantic may change.

## Exact change scope

Exactly these eight paths may change:

```text
scripts/run_live_steamapis_offer_smoke.py
tests/test_live_steamapis_offer_smoke.py
.env.example
README.md
docs/STEAMAPIS_MARKET_DATA_NOTES.md
specs/2026-08-13-live-steamapis-offer-smoke/plan.md
specs/2026-08-13-live-steamapis-offer-smoke/requirements.md
specs/2026-08-13-live-steamapis-offer-smoke/validation.md
```

Protected client/parser/session/pool, Step 2J, metadata, solver, valuation, SteamDT, BUFF, Redis, config, dependencies, runtime, scheduler, Discord, FastAPI, Docker, and database files remain unchanged.

Stop with all changes unstaged, uncommitted, and unpushed. Do not begin Step 2L.
