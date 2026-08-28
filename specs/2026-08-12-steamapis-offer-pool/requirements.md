# Phase 13A Step 2C — Requirements

## Scope

Step 2C implements only this local state boundary:

```text
SteamApisListingObservation
→ deterministic ingest/update
→ bounded in-memory pool
→ TTL expiry
→ immutable snapshot
→ source_offer_id provenance lookup
→ optional CandidateListing projection through Step 2B
```

The approved changed paths are exactly:

```text
README.md
app/services/steamapis_offer_pool.py
docs/STEAMAPIS_MARKET_DATA_NOTES.md
specs/2026-08-12-steamapis-offer-pool/plan.md
specs/2026-08-12-steamapis-offer-pool/requirements.md
specs/2026-08-12-steamapis-offer-pool/validation.md
tests/test_steamapis_offer_pool.py
```

## Public API

The module exports only:

```python
class SteamApisOfferPoolError(ValueError): ...

@dataclass(frozen=True, kw_only=True, repr=False)
class SteamApisOfferPoolSnapshot:
    observations: tuple[SteamApisListingObservation, ...]

class SteamApisOfferPool:
    def __init__(
        self,
        *,
        max_size: int,
        ttl: timedelta,
        now: Callable[[], datetime] = ...,
    ) -> None: ...

    def ingest(self, observation: SteamApisListingObservation) -> None: ...
    def snapshot(self) -> SteamApisOfferPoolSnapshot: ...
    def get_observation(
        self,
        source_offer_id: str,
    ) -> SteamApisListingObservation | None: ...
    def get_purchase_link(self, source_offer_id: str) -> str | None: ...
    def snapshot_candidates(self) -> tuple[CandidateListing, ...]: ...
```

There is no write-result enum, alternate projection helper, delete/clear/purge API, reverse index, runtime factory, or background service.

## Constructor and clock

- `max_size` is an exact positive builtin `int`; booleans and subclasses are invalid.
- `ttl` is an exact positive `timedelta`.
- `now` is callable and must return an exact aware `datetime`; aware results normalize to UTC.
- The constructor validates one `now()` result but stores only the callable.
- Every eviction-capable public operation obtains exactly one fresh clock result before mutating pool state.
- Invalid clock calls fail before TTL eviction or other state mutation.
- No future-timestamp rejection, monotonic clock requirement, or rollback policy is invented.

## Source of truth and defensive validation

- The only internal state is `dict[str, SteamApisListingObservation]` keyed by project-owned `source_offer_id`.
- `CandidateListing` is never stored or cached.
- Purchase links remain fields of observations; there is no parallel link mapping or reverse index.
- `ingest()` accepts only the exact `SteamApisListingObservation` type.
- Ingest reconstructs a fresh observation through the existing public constructor using every field, detecting tampering without reparsing JSON or copying private Step 2A rules.
- Frozen observations and their immutable nested values need no meaningless deep copy when returned in a new tuple.

## Added and Updated ingest semantics

- Added and Updated may both insert a previously unseen `source_offer_id`.
- Event type does not determine ordering.
- For an existing source ID:
  - newer `message_timestamp` replaces the stored observation;
  - older `message_timestamp` is ignored without error;
  - equal timestamp plus equal full observation is an idempotent no-op;
  - equal timestamp plus any differing observation field fails closed with the fixed pool error and preserves current state.
- `ingest()` returns `None` on every successful path.

## TTL

Expiry is exactly:

```text
now - observation.message_timestamp >= ttl
```

- Expiry is inclusive at the exact TTL boundary.
- Existing expired entries are removed lazily by `ingest()`, `snapshot()`, `get_observation()`, and `get_purchase_link()`.
- `snapshot_candidates()` receives the same behavior through its single `snapshot()` call.
- An incoming observation already expired at ingest time is ignored and not stored.
- TTL is a project-owned local stale-data policy, not evidence of a SteamApis or BUFF removal event.
- The documented contract currently contains no Removed/Deleted event.

## Capacity

After an accepted insert or replacement, the pool repeatedly evicts the minimum:

```text
(observation.message_timestamp, observation.source_offer_id)
```

until `len(pool) <= max_size`.

This means oldest message time first, then lexical-ascending source ID at a timestamp tie. TTL eviction happens before capacity eviction. Price, float, market name, trade lock, and opportunity quality do not influence retention.

## Snapshot

- The result is frozen, keyword-only, repr-suppressed, and backed by a new tuple.
- It does not expose the internal dictionary.
- Order is ascending by:
  1. `market_hash_name`
  2. `price_cny`
  3. `float_value`
  4. `message_timestamp`
  5. `source_offer_id`
- Different source IDs are never deduplicated, even with the same market name.
- A retained snapshot does not change after later ingest.
- Snapshot does not classify metadata, filter rarity/collection/ROI/trade lock, or invoke the solver.

## Provenance lookup

- Lookups accept one exact lowercase 64-character hexadecimal source ID.
- Valid unknown or expired IDs return `None`.
- `get_observation()` returns the retained immutable observation.
- `get_purchase_link()` returns its opaque purchase link.
- Neither method parses, requests, opens, logs, canonicalizes, or reverse-indexes a URL.

## Candidate projection

`snapshot_candidates()` is the only public projection path:

```text
snapshot observations
→ adapt_steamapis_listing_to_candidate(observation)
→ tuple
```

- It calls `snapshot()` once and uses the existing Step 2B adapter exactly once per observation.
- Candidate order matches snapshot observation order.
- Candidate mappings are not copied into the pool.
- Ordinary adapter failure becomes the fixed pool error, and no partial tuple is returned.
- It does not load metadata, filter trade lock, run recipes, or perform valuation.

## Trade lock

`days_trade_locked` remains unchanged on the observation. `None` is not interpreted as zero. Step 2C applies no eligibility policy; later live eligibility/evaluation work must define that rule explicitly.

## Error and redaction policy

Every pool error has exactly:

```text
invalid SteamApis offer pool contract
```

Ordinary input, invariant, clock, snapshot, and adapter errors are wrapped with suppressed chaining. Public text/repr contains no source ID, purchase link, inspect link, market name, price, float, paint seed, raw data, credential, token, Cookie, or nested exception text. `MemoryError` and all non-`Exception` control flow propagate unchanged.

## Explicit exclusions

Step 2C adds no WebSocket dependency/client, SteamApis connection, BUFF connection or Phase 12 module change, metadata loading, recipe solver execution, SteamDT call, Redis connection, pipeline, scheduler, FastAPI, Discord, Docker/database behavior, environment access, background task/thread, browser action, automatic login, Cookie extraction, captcha/risk-control bypass, or purchase behavior. It is not production-ready and stops before Step 2D.
