# Phase 13A Step 2H — Requirements

## Scope

Implement only this read-only chain:

```text
official SteamApis WebSocket contract
→ one WebSocket session
→ one fixed subscription
→ existing parse_steamapis_message()
→ async SteamApisListingObservation stream
```

The client is offline-testable and opens no connection unless its iterator is consumed by a caller. Tests use an injected fake connector and never use DNS or sockets.

## Official contract checked 2026-08-13

- Endpoint: `wss://marketplaceapi.steamapis.com/ws/v2/offers`.
- Authentication: `apiKey` query parameter.
- Permission: the API key requires `websocketAccess`.
- Compression: the server requires `permessage-deflate`.
- Limit: each API key permits at most two concurrent connections.
- Fixed subscription:

```json
{"subscribeTo":["Buff163"],"games":["CS2"],"newFloorOnly":false}
```

- Documented message types: `subscribed`, `offer`, `error`.
- Supported offer events: `Added`, `Updated`.
- The current official reference lists `Buff163` and `CS2`.

## Dependency

- Add only `websockets>=17,<18`.
- Use `websockets.asyncio.client.connect`.
- Explicitly pass `compression="deflate"`, `open_timeout=10`, and `max_size=1_048_576`.
- Retain the selected library's defaults for ping interval/timeouts, close timeout, and receive queue.
- Do not manually add `Sec-WebSocket-Extensions`.
- No lock file exists or is updated.

## Public API

`app/clients/steamapis_websocket_client.py` exports only:

```python
SteamApisWebSocketClientError
SteamApisWebSocketConfig
SteamApisWebSocketClient
```

The config is a frozen, keyword-only, repr-hidden dataclass containing an API key and the fixed official endpoint. It accepts only an exact nonblank built-in API-key string and only the exact official endpoint.

The client exposes:

```python
async def iter_observations(
    self,
) -> AsyncIterator[SteamApisListingObservation]:
    ...
```

A narrow connector injection point may exist for offline tests. Production defaults to the real `websockets` asyncio connector.

## API-key and error safety

- The key enters only through constructor/config input.
- Build the query with standards-based URL encoding.
- Do not read environment variables or user files.
- Do not hardcode, log, or document a real key.
- Config/client repr must not contain the key.
- No error may expose the key, complete URI, query string, raw frame, server error text, or underlying exception text.
- Ordinary connection, handshake, context-entry, send, receive, parser, protocol, and abnormal-close failures raise one fixed unchained error:

```text
SteamApis WebSocket session failed
```

- `MemoryError`, `KeyboardInterrupt`, `asyncio.CancelledError`, and other non-`Exception` `BaseException` values propagate unchanged.

## Session behavior

- Build one encoded URI and call the connector exactly once.
- Enter one WebSocket connection context.
- Send the fixed subscription exactly once with standard JSON serialization.
- Parse every exact text frame with the unchanged `parse_steamapis_message()` function.
- Do not decode binary frames; fail closed.
- Require a parser `SUBSCRIBED` outcome before yielding any offer.
- The Step 2A parser deliberately discards subscribed confirmation fields, so this client gates on the parsed kind only and does not parse raw JSON a second time to verify confirmation fields.
- After subscription, yield only parser-provided `SteamApisListingObservation` values, preserving receive order.
- Safely ignore parser `IGNORED` outcomes.
- Convert parser `ERROR`, unknown/malformed messages, offer-before-subscribed, and impossible parser results to the fixed client error.
- A normal close or normal receive-loop completion ends the async iterator.
- An abnormal close raises the fixed client error.

## Explicit exclusions

Do not implement:

- reconnect or retry;
- `async for connect(...)` automatic reconnection;
- sleep, backoff, second connection, task, thread, scheduler, singleton, runtime manager, service locator, or factory;
- live smoke or real SteamApis connection;
- offer-pool writes, candidate adaptation, metadata, construction, solver, valuation, EV, or risk;
- SteamDT, BUFF, Redis, Discord, PostgreSQL, FastAPI, Docker, browser, login, marketplace writes, or purchases;
- arbitrary endpoint, marketplace, game, or subscription injection;
- `all`, additional marketplace/game scopes, BUFF credentials, or seller/account data;
- parser/schema duplication, source-ID re-hashing, or purchase-link parsing.

The SteamDT batch currency blocker remains fully in force. Step 2G is not resumed. Step 2I is not started.

## Allowed files

- `app/clients/steamapis_websocket_client.py`
- `tests/test_steamapis_websocket_client.py`
- `README.md`
- `docs/STEAMAPIS_MARKET_DATA_NOTES.md`
- `specs/2026-08-13-steamapis-websocket-client/plan.md`
- `specs/2026-08-13-steamapis-websocket-client/requirements.md`
- `specs/2026-08-13-steamapis-websocket-client/validation.md`
- `pyproject.toml`

All Step 2A–2F services, SteamDT modules, Phase 12 BUFF modules, `.env.example`, config, Redis, scheduler, Discord, FastAPI, Docker, and database files remain unchanged.
