# Phase 13D-0 — Requirements

## Audit conclusion

No committed evidence establishes a canonical BUFF `market_hash_name ↔ goods_id` mapping.

- Anonymous sell-order requests receive goods ID from caller context; the response parser does not extract it.
- `BuffListing.market_hash_name` remains `None` because no live name field was verified.
- Phase 12 paired fixtures are synthetic internal contracts.
- Legacy `BuffGoodsInfo` live mapping remains unimplemented.
- SteamDT platform IDs remain opaque and explicitly unverified as BUFF goods IDs.
- SteamApis compatibility identities are explicitly not authoritative BUFF IDs.

Therefore Path B applies: abstraction only, no mapping implementation or provider integration.

## Public API

`app/services/buff_item_identity.py` exports exactly:

```python
BuffItemIdentityValidationError
BuffItemIdentity
BuffItemIdentityResolver
```

### Validation error

`BuffItemIdentityValidationError(ValueError)` has fixed text:

```text
invalid BUFF item identity contract
```

It exposes only `.field`, whose value is one of:

```text
market_hash_name
goods_id
```

It never includes a rejected value, payload, URL, provider text, or nested exception.

### Resolved identity

```python
@dataclass(frozen=True, kw_only=True, repr=False)
class BuffItemIdentity:
    market_hash_name: str
    goods_id: str
```

Both values must be exact built-in strings, nonempty, already trimmed, case-preserving, and retained unchanged. Internal whitespace and punctuation remain significant. Goods ID is not restricted to digits. No normalization, coercion, case-folding, parsing, hashing, or derivation occurs.

The DTO validates scalar shape only; it does not prove the semantic truth of a pair.

### Resolver protocol

```python
class BuffItemIdentityResolver(Protocol):
    async def resolve(
        self,
        market_hash_name: str,
    ) -> BuffItemIdentity | None: ...
```

A future verified implementation may return one exact resolved identity. `None` is the normal unresolved outcome. The protocol owns no lifecycle, transport, config, cache, retry, fallback, batch, reverse lookup, discovery, or mapping data.

Phase 13D-0 adds no concrete resolver, always-unresolved implementation, dictionary, fixture, parser, loader, factory, environment variable, or endpoint.

## Tests

Tests use inline clearly synthetic strings only and cover:

- exact exports, field order, annotations, signatures, async protocol method;
- keyword-only, frozen, equality, repr-suppressed DTO behavior;
- case/internal-whitespace/punctuation preservation and nonnumeric IDs;
- rejection of blank, padded, wrong built-in type, subclass, bool/int, and coercible values;
- fixed safe error text and field without rejected-value or exception-context leakage;
- a test-local structural resolver returning `None` as a normal result;
- exact query preservation;
- static proof of no concrete resolver, map, fixture, I/O, client/provider, SteamDT, SteamApis, metadata, config, scanner, solver, valuation, cache, runtime, or purchase dependency.

## Documentation

Documentation must state that the current listing provider consumes externally known goods ID and does not resolve names. The authoritative mapping source, cardinality, conflict rules, lifecycle/freshness, and provenance remain TODOs. No endpoint or response field is guessed.

## Protected scope

Do not modify any existing application module, including `BuffListing`, anonymous client/provider/smokes, Phase 12 BUFF code/fixtures, legacy BUFF client, SteamDT, SteamApis, metadata, scanner, solver, valuation, EV/risk, pipeline, scheduler, config, `.env.example`, dependencies, or deployment.

## Allowed files

New:

- `app/services/buff_item_identity.py`
- `tests/test_buff_item_identity.py`
- `specs/2026-08-21-buff-item-identity-contract/plan.md`
- `specs/2026-08-21-buff-item-identity-contract/requirements.md`
- `specs/2026-08-21-buff-item-identity-contract/validation.md`

Modified:

- `docs/BUFF_ANONYMOUS_READONLY_NOTES.md`
- `docs/BUFF_API_NOTES.md`

No other path may differ.
