# Phase 13H-0 — Synthetic Trade-up Pipeline Integration — Requirements

## Goal

Prove that the future production pipeline can be exercised end-to-end using **synthetic/offline inputs only**, without invoking any BUFF, SteamDT, or SteamApis live source and without implementing an identity resolver.

The pipeline target is:

```text
Synthetic Listing Fixture
    ↓
TradeUpInputCandidate
    ↓
Trade-up Engine
    ↓
EV / ROI / Risk evaluation
    ↓
Synthetic Pipeline Result
```

This phase does **not**:

- resolve `market_hash_name ↔ BUFF goods_id`;
- add a BUFF endpoint, mapping, or fixture that purports to be live;
- connect SteamApis or any external provider;
- modify the existing trade-up engine, recipe solver, valuation service, risk filter, or any live provider;
- wire a scanner, scheduler, or purchase flow.

## Public API

`app/services/trade_up_pipeline.py` exports exactly:

```python
TradeUpInputMetadata
TradeUpInputMetadataResolver
InMemoryTradeUpInputMetadataResolver
candidates_to_input_items
```

### Metadata DTO

```python
@dataclass(frozen=True, kw_only=True, repr=False)
class TradeUpInputMetadata:
    market_hash_name: str
    collection_name: str
    rarity: str
    min_float: float
    max_float: float
```

This is **synthetic-only** data. It is not derived from any live source. It must not be shared across phases without re-evaluation.

### Resolver protocol

```python
class TradeUpInputMetadataResolver(Protocol):
    def resolve(self, market_hash_name: str) -> TradeUpInputMetadata | None: ...
```

`None` represents unresolved metadata. Resolvers must not perform network I/O, file I/O, environment reads, or live queries.

### In-memory synthetic resolver

```python
class InMemoryTradeUpInputMetadataResolver:
    def __init__(self, mapping: Mapping[str, TradeUpInputMetadata]) -> None: ...
    def resolve(self, market_hash_name: str) -> TradeUpInputMetadata | None: ...
```

The in-memory resolver is the only implementation in this phase. It exists for offline tests only. It must not be wired into production scans, schedulers, or live pipelines.

### Adapter

```python
def candidates_to_input_items(
    candidates: Iterable[TradeUpInputCandidate],
    metadata_resolver: TradeUpInputMetadataResolver,
) -> list[InputItem]:
```

Contract:

- Iterates `candidates` once.
- Skips candidates whose `market_hash_name is None` (explicit unresolved marker).
- Skips candidates whose `market_hash_name` is not in the resolver.
- Preserves candidate order in the returned list.
- Converts each surviving candidate to one `InputItem` using the existing project `InputItem` model.
- Sets `actual_float = float(candidate.paintwear)` (existing engine boundary).
- Sets `stattrak=False`, `souvenir=False` (resolver does not yet expose these).
- The adapter does not mask or substitute price; it passes `price_cny` through as-is.
- The adapter does not perform any arithmetic, EV/ROI, or risk computation.

## Required tests

- The adapter converts a homogeneous group of ten synthetic candidates into ten `InputItem` objects.
- The adapter skips candidates whose `market_hash_name` is `None`.
- The adapter skips candidates whose `market_hash_name` is not in the resolver.
- The full pipeline call (`calculate_tradeup_results` → `calculate_opportunity_metrics` → `evaluate_opportunity`) executes without raising for a constructed synthetic fixture.
- The synthetic pipeline result is structurally valid (existing DTO invariants).
- The adapter does not import the live BUFF client/provider/smokes, SteamApis modules, or any I/O modules.

## Architecture decision

`solve_recipes` and `value_live_recipes` are not reused here because they depend on the live BUFF cost provider. The synthetic pipeline uses `calculate_tradeup_results` directly with the engine's existing inputs and demonstrates that `TradeUpInputCandidate` can flow into the engine. A future identity-resolved phase can introduce a `BuffListing → TradeUpInputCandidate` adapter and wire the full `value_live_recipes` chain.

## Protected scope

Do not modify `TradeUpInputCandidate`, `BuffItemIdentity`, `BuffItemIdentityResolver`, `BuffListing`, the anonymous BUFF client/provider/smokes, Phase 12 BUFF, SteamDT, SteamApis, metadata, scanner, solver, trade-up engine, valuation, EV/ROI/risk, pipeline, scheduler, config, dependencies, or any live smoke.

## Allowed files

- `app/services/trade_up_pipeline.py`
- `tests/test_trade_up_pipeline.py`
- `specs/2026-08-21-synthetic-trade-up-pipeline-integration/{plan,requirements,validation}.md`
- minimal AI context handoff update

## Validation

```bash
py -3.13 -m pytest tests/test_trade_up_pipeline.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
git diff --check
git diff --name-only
git status --short
```

No live request, no SteamApis, no purchase, no market write, no live provider.
