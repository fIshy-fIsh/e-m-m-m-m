# Phase 13A Step 2I — Requirements

## Scope

Connect only the existing Step 2H WebSocket observation stream to the existing Step 2C offer pool:

```text
SteamApisWebSocketClient.iter_observations()
→ SteamApisListingObservation
→ SteamApisOfferPool.ingest()
```

The runner is one single-session, foreground, sequential, offline-testable bridge. It performs no live connection, reconnect, retry, background work, downstream analysis, alerting, persistence, or trade action.

## Existing authoritative contracts

- The WebSocket client owns endpoint/authentication, compression, subscription, SUBSCRIBED gating, text-frame parsing, observation construction, receive order, normal close, and transport/parser failure behavior.
- The offer pool owns observation reconstruction, Added/Updated acceptance, message-time ordering, equal-time conflict handling, TTL eviction, capacity eviction, retained provenance, and pool errors.
- The runner must not reproduce or override either boundary.

## Public API

```python
class SteamApisOfferSessionError(RuntimeError):
    ...

@dataclass(frozen=True, kw_only=True, repr=False)
class SteamApisOfferSessionResult:
    observations_consumed: int

async def run_steamapis_offer_session(
    *,
    client: SteamApisWebSocketClient,
    pool: SteamApisOfferPool,
) -> SteamApisOfferSessionResult:
    ...
```

The result must contain no observation, snapshot, source ID, market name, link, price, float, seed, raw payload, or candidate data. `observations_consumed` must be an exact nonnegative built-in integer; booleans, integer subclasses, non-integers, and negatives fail with the session error.

The function retains concrete public type annotations but does not impose exact-class runtime checks or add a Protocol/framework. Collaborators are exercised through their established method contracts.

## Authoritative flow

The implementation must perform exactly:

```text
observations_consumed = 0
call client.iter_observations() once
for each yielded observation in order:
    call pool.ingest(observation) synchronously
    increment only after ingest returns normally
return the count after normal iterator completion
```

It must not:

- parse or validate frames;
- inspect Added/Updated, timestamps, source IDs, links, or economic fields;
- hash identity, deduplicate, apply TTL, or enforce capacity itself;
- call `snapshot()` or any pool lookup before, during, or after ingest;
- retain a second pool or observation list;
- create a new client or pool;
- call the iterator a second time;
- parallelize ingestion.

## Count definition

`observations_consumed` is the number of observations that:

1. were yielded by the client; and
2. were handed to `pool.ingest()` whose call returned normally.

An older, identical equal-time, already-expired, or capacity-evicted observation still counts because the authoritative pool handled it successfully. The count is not named or interpreted as inserted, accepted, retained, mutated, unique, or final pool size because `ingest()` returns no write-status contract.

## Completion and failure

Natural iterator completion and Step 2H normal close return the accumulated count, including zero for an empty confirmed session.

All ordinary `Exception` failures at the session boundary, including `SteamApisWebSocketClientError`, `SteamApisOfferPoolError`, and unexpected collaborator exceptions, become one unchained fixed error:

```text
SteamApis offer session failed
```

The error must not expose nested exception text, API keys, URI/query values, source IDs, purchase or inspect links, market names, price/float/seed values, raw payloads, or collaborator details.

The runner must not catch `MemoryError`, `asyncio.CancelledError`, `KeyboardInterrupt`, or other non-`Exception` `BaseException` values. They propagate unchanged.

If earlier observations were successfully ingested and a later client or pool operation fails:

- no partial `SteamApisOfferSessionResult` is returned;
- all earlier successful pool mutations and policy-driven evictions remain;
- the runner performs no rollback, transaction, copy, clear, replacement, or replay;
- the failing observation is not included in any returned count because there is no result.

## Sequential and lifecycle boundaries

The runner is strictly foreground and sequential:

```text
await next observation
→ synchronous pool.ingest()
→ await next observation
```

It must contain no task, thread, queue, gather, executor, worker, scheduler, sleep, timeout, retry, backoff, reconnect loop, or background manager.

## Architecture exclusions

Production runner imports are limited to standard-library support, `SteamApisWebSocketClient`, and `SteamApisOfferPool`. It must not import or invoke:

- the Step 2A parser or source-ID helpers;
- candidate adapter or candidate projection;
- live metadata, construction, recipe solver, valuation, EV, or risk;
- SteamDT or any price provider;
- BUFF, Redis, Discord, FastAPI, scheduler, database, Docker, config, environment, logging, browser, login, marketplace writes, or purchase behavior.

## Offline integration acceptance

At least one test must use the real WebSocket client, injected fake connector/context/WebSocket, real Step 2A parser path, real offer pool, and real runner with:

```text
SUBSCRIBED
Added A at t1
Updated A at t2
Added B at t3
older Updated A at t0
normal close
```

It must return `observations_consumed == 4`; retain A at t2 and B; ignore the older A for retention; use parser-generated source identity; preserve opaque purchase-link provenance only in the pool observation; use one connection/subscription; and perform zero network I/O.

Equal-time conflicting content must be allowed to reach the pool, become the fixed session error, return no partial result, preserve the first retained version, and perform no rollback or runner-side guess.

## Documentation and file scope

Allowed changed paths are exactly:

```text
app/services/steamapis_offer_session.py
tests/test_steamapis_offer_session.py
README.md
docs/STEAMAPIS_MARKET_DATA_NOTES.md
specs/2026-08-13-steamapis-offer-session/plan.md
specs/2026-08-13-steamapis-offer-session/requirements.md
specs/2026-08-13-steamapis-offer-session/validation.md
```

The WebSocket client, parser, offer pool, candidate adapter, metadata/construction/valuation/solver/engine/risk modules, every SteamDT/BUFF/Redis/Discord/runtime/config/database file, `pyproject.toml`, and prior feature specs/tests remain unchanged.

## Persistent blockers and stop boundary

Official SteamDT documentation still does not establish that batch `sellPrice` / `biddingPrice` are CNY/RMB. Step 2G remains blocked, no SteamDT or `PriceQuote.price_cny` semantic changes are permitted, and no UI currency display may be promoted into an OpenAPI contract.

This work makes no real SteamApis, SteamDT, BUFF, Redis, Discord, or PostgreSQL connection, creates no live smoke, remains not production-ready, performs no automatic purchase, and stops before commit, push, or Step 2J.
