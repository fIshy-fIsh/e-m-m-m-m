"""Phase 13S — Pure bounded structural market-universe planning.

The planner joins pinned identity and metadata catalogs by exact
``market_hash_name`` and separates two responsibilities:

``catalog eligibility -> bounded allocation strategy``

``BREADTH`` preserves the Phase 13R collection round-robin byte-for-byte.
``COHORT_DEPTH`` concentrates the same finite goods-id budget into a small
number of collection-local allocation cohorts. Neither strategy inspects
live listings, prices, EV, ROI, risk, or any network state.

An allocation cohort is intentionally stricter than legal recipe
compatibility: ``(collection, input rarity, StatTrak mode)``. Collections may
legally mix, and normal/Souvenir inputs may mix under the May 2026 standard
contract rule. Souvenir therefore remains an entry fact, not a cohort key.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.services.buff_community_identity_resolver import BuffCommunityIdentityResolver
from app.services.metadata_models import RarityOrder, SkinMetadata
from app.services.metadata_service import get_next_rarity
from app.services.scanner_recipe_composition import (
    is_current_standard_trade_up_output_eligible,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver

_FIXED_ERROR = "invalid bounded market universe builder"
_ALLOWED_REASONS = frozenset(
    {
        "exact_collision",
        "unsupported_rarity",
        "collection_not_in_catalog",
        "duplicate_goods_id",
        "universe_empty",
        "universe_over_hard_max",
        "unsupported_allocation",
        "invalid_target_cohort_count",
    }
)

__all__ = (
    "BoundedMarketUniverseBuilderError",
    "MarketUniverseCohortAllocation",
    "MarketUniverseCohortKey",
    "MarketUniverseDiagnostics",
    "MarketUniverseEntry",
    "MarketUniverseErrorReason",
    "MarketUniverseResult",
    "MarketUniverseSpec",
    "SouvenirInclusion",
    "StatTrakMode",
    "UniverseAllocationStrategy",
    "build_universe_goods_ids",
)


class MarketUniverseErrorReason(StrEnum):
    """Closed vocabulary of builder failure reasons."""

    EXACT_COLLISION = "exact_collision"
    UNSUPPORTED_RARITY = "unsupported_rarity"
    COLLECTION_NOT_IN_CATALOG = "collection_not_in_catalog"
    DUPLICATE_GOODS_ID = "duplicate_goods_id"
    UNIVERSE_EMPTY = "universe_empty"
    UNIVERSE_OVER_HARD_MAX = "universe_over_hard_max"
    UNSUPPORTED_ALLOCATION = "unsupported_allocation"
    INVALID_TARGET_COHORT_COUNT = "invalid_target_cohort_count"


class StatTrakMode(StrEnum):
    """Explicit homogeneous StatTrak mode for the generated universe."""

    NORMAL = "normal"
    STATTRAK = "stattrak"


class SouvenirInclusion(StrEnum):
    """Souvenir input inclusion policy (output rule remains non-Souvenir)."""

    INCLUDE = "include"
    EXCLUDE = "exclude"


class UniverseAllocationStrategy(StrEnum):
    """Deterministic catalog-only allocation policies."""

    BREADTH = "breadth"
    COHORT_DEPTH = "cohort-depth"


class BoundedMarketUniverseBuilderError(ValueError):
    """A builder input or output violated the fixed contract."""

    def __init__(self, *, reason: str) -> None:
        if reason not in _ALLOWED_REASONS:
            raise ValueError("unsupported market universe error reason")
        super().__init__(_FIXED_ERROR)
        self.reason = reason


@dataclass(frozen=True, kw_only=True, repr=False)
class MarketUniverseSpec:
    """Validated, immutable specification for one bounded universe build."""

    rarity: str
    stattrak_mode: StatTrakMode
    souvenir_inclusion: SouvenirInclusion
    cap: int
    collection_allowlist: tuple[str, ...] = ()
    allocation_strategy: UniverseAllocationStrategy = (
        UniverseAllocationStrategy.BREADTH
    )
    target_cohort_count: int = 3

    def __post_init__(self) -> None:
        if type(self.rarity) is not str or not self.rarity:
            raise BoundedMarketUniverseBuilderError(reason="unsupported_rarity")
        if type(self.stattrak_mode) is not StatTrakMode:
            raise BoundedMarketUniverseBuilderError(reason="unsupported_rarity")
        if type(self.souvenir_inclusion) is not SouvenirInclusion:
            raise BoundedMarketUniverseBuilderError(reason="unsupported_rarity")
        if type(self.cap) is not int or self.cap < 1 or self.cap > 10:
            raise BoundedMarketUniverseBuilderError(
                reason="universe_over_hard_max"
            )
        if self.rarity not in RarityOrder.ORDER[:5]:
            raise BoundedMarketUniverseBuilderError(reason="unsupported_rarity")
        if not isinstance(self.collection_allowlist, tuple) or any(
            type(value) is not str or not value or value != value.strip()
            for value in self.collection_allowlist
        ):
            raise BoundedMarketUniverseBuilderError(
                reason="collection_not_in_catalog"
            )
        if type(self.allocation_strategy) is not UniverseAllocationStrategy:
            raise BoundedMarketUniverseBuilderError(
                reason="unsupported_allocation"
            )
        if (
            type(self.target_cohort_count) is not int
            or self.target_cohort_count < 1
            or self.target_cohort_count > 10
            or (
                self.allocation_strategy
                is UniverseAllocationStrategy.COHORT_DEPTH
                and self.target_cohort_count > self.cap
            )
        ):
            raise BoundedMarketUniverseBuilderError(
                reason="invalid_target_cohort_count"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class MarketUniverseEntry:
    """One exact identity/metadata record eligible for allocation."""

    goods_id: str
    market_hash_name: str
    collection_name: str
    rarity: str
    stattrak: bool
    souvenir: bool


@dataclass(frozen=True, kw_only=True, repr=False)
class MarketUniverseCohortKey:
    """Collection-local structural allocation key, not legal compatibility."""

    collection_name: str
    rarity: str
    stattrak: bool


@dataclass(frozen=True, kw_only=True, repr=False)
class MarketUniverseCohortAllocation:
    """Catalog-only capacity and allocation facts for one selected cohort."""

    key: MarketUniverseCohortKey
    catalog_capacity: int
    normal_identity_count: int
    souvenir_identity_count: int
    canonical_output_count: int
    allocated_slots: int
    selected_entries: tuple[MarketUniverseEntry, ...]


@dataclass(frozen=True, kw_only=True, repr=False)
class MarketUniverseDiagnostics:
    """Truthful catalog eligibility and structural allocation counters.

    ``catalog_capacity`` means exact eligible identities in the pinned
    catalogs under the effective spec. It is not live listing availability,
    market liquidity, or a profitability signal.

    Existing exclusion counters retain Phase 13R semantics. The technical
    counters partition metadata rows that have both identity and metadata,
    short-circuiting at the first failed gate. ``excluded_no_identity`` is
    metadata-side, while ``excluded_no_metadata`` is identity-side.
    """

    catalog_metadata_rows: int
    catalog_identity_rows: int
    eligible_before_bound: int
    selected_count: int
    excluded_no_identity: int
    excluded_no_metadata: int
    excluded_invalid_rarity: int
    excluded_no_collection: int
    excluded_no_valid_output: int
    excluded_intrinsic_policy: int
    excluded_by_allowlist: int
    allocation_strategy: UniverseAllocationStrategy
    target_cohort_count: int
    eligible_cohort_count: int
    selected_cohort_count: int
    selected_cohorts: tuple[MarketUniverseCohortAllocation, ...]


@dataclass(frozen=True, kw_only=True, repr=False)
class MarketUniverseResult:
    """Immutable, deterministic bounded goods-id plan."""

    spec: MarketUniverseSpec
    goods_ids: tuple[str, ...]
    selected_market_hash_names: tuple[str, ...]
    selected_entries: tuple[MarketUniverseEntry, ...]
    diagnostics: MarketUniverseDiagnostics


@dataclass(frozen=True, kw_only=True, repr=False)
class _EligibilityResult:
    entries: tuple[MarketUniverseEntry, ...]
    canonical_output_counts: dict[str, int]
    catalog_metadata_rows: int
    catalog_identity_rows: int
    excluded_no_identity: int
    excluded_no_metadata: int
    excluded_invalid_rarity: int
    excluded_no_collection: int
    excluded_no_valid_output: int
    excluded_intrinsic_policy: int
    excluded_by_allowlist: int


def build_universe_goods_ids(
    *,
    identity_resolver: BuffCommunityIdentityResolver,
    metadata_resolver: PinnedSkinMetadataResolver,
    spec: MarketUniverseSpec,
) -> MarketUniverseResult:
    """Build a deterministic bounded goods-id universe from pinned catalogs.

    Pure function: no I/O, no async, no global state. Two runs with identical
    inputs return byte-equal results.
    """
    try:
        if type(identity_resolver) is not BuffCommunityIdentityResolver:
            raise BoundedMarketUniverseBuilderError(reason="exact_collision")
        if type(metadata_resolver) is not PinnedSkinMetadataResolver:
            raise BoundedMarketUniverseBuilderError(reason="exact_collision")
        if type(spec) is not MarketUniverseSpec:
            raise BoundedMarketUniverseBuilderError(reason="exact_collision")
        return _build_universe(
            identity_resolver=identity_resolver,
            metadata_resolver=metadata_resolver,
            spec=spec,
        )
    except MemoryError:
        raise
    except BoundedMarketUniverseBuilderError:
        raise
    except Exception:
        raise BoundedMarketUniverseBuilderError(reason="exact_collision") from None


def _build_universe(
    *,
    identity_resolver: BuffCommunityIdentityResolver,
    metadata_resolver: PinnedSkinMetadataResolver,
    spec: MarketUniverseSpec,
) -> MarketUniverseResult:
    eligibility = _collect_eligible_entries(
        identity_resolver=identity_resolver,
        metadata_resolver=metadata_resolver,
        spec=spec,
    )
    if not eligibility.entries:
        raise BoundedMarketUniverseBuilderError(reason="universe_empty")

    cohorts = _group_entries_by_cohort(eligibility.entries)
    if spec.allocation_strategy is UniverseAllocationStrategy.BREADTH:
        picked = _allocate_breadth(eligibility.entries, cap=spec.cap)
    else:
        picked = _allocate_cohort_depth(
            cohorts,
            cap=spec.cap,
            target_cohort_count=spec.target_cohort_count,
        )
    if not picked:
        raise BoundedMarketUniverseBuilderError(reason="universe_empty")

    selected_cohorts = _build_selected_cohort_diagnostics(
        picked=picked,
        cohorts=cohorts,
        canonical_output_counts=eligibility.canonical_output_counts,
        strategy=spec.allocation_strategy,
    )
    diagnostics = MarketUniverseDiagnostics(
        catalog_metadata_rows=eligibility.catalog_metadata_rows,
        catalog_identity_rows=eligibility.catalog_identity_rows,
        eligible_before_bound=len(eligibility.entries),
        selected_count=len(picked),
        excluded_no_identity=eligibility.excluded_no_identity,
        excluded_no_metadata=eligibility.excluded_no_metadata,
        excluded_invalid_rarity=eligibility.excluded_invalid_rarity,
        excluded_no_collection=eligibility.excluded_no_collection,
        excluded_no_valid_output=eligibility.excluded_no_valid_output,
        excluded_intrinsic_policy=eligibility.excluded_intrinsic_policy,
        excluded_by_allowlist=eligibility.excluded_by_allowlist,
        allocation_strategy=spec.allocation_strategy,
        target_cohort_count=spec.target_cohort_count,
        eligible_cohort_count=len(cohorts),
        selected_cohort_count=len(selected_cohorts),
        selected_cohorts=selected_cohorts,
    )
    selected = tuple(picked)
    return MarketUniverseResult(
        spec=spec,
        goods_ids=tuple(entry.goods_id for entry in selected),
        selected_market_hash_names=tuple(
            entry.market_hash_name for entry in selected
        ),
        selected_entries=selected,
        diagnostics=diagnostics,
    )


def _collect_eligible_entries(
    *,
    identity_resolver: BuffCommunityIdentityResolver,
    metadata_resolver: PinnedSkinMetadataResolver,
    spec: MarketUniverseSpec,
) -> _EligibilityResult:
    forward: dict[str, str] = dict(identity_resolver._forward)  # noqa: SLF001 — concrete resolver catalog contract
    metadata_skins: tuple[SkinMetadata, ...] = metadata_resolver.skins

    allowed_collections: frozenset[str] | None
    if spec.collection_allowlist:
        allowed_collections = frozenset(spec.collection_allowlist)
    else:
        allowed_collections = None
    expected_stattrak = spec.stattrak_mode is StatTrakMode.STATTRAK

    metadata_index: dict[str, SkinMetadata] = {}
    for skin in metadata_skins:
        if skin.market_hash_name in metadata_index:
            raise BoundedMarketUniverseBuilderError(reason="exact_collision")
        metadata_index[skin.market_hash_name] = skin

    next_rarity = get_next_rarity(spec.rarity)
    if next_rarity is None:
        raise BoundedMarketUniverseBuilderError(reason="unsupported_rarity")

    canonical_output_counts: dict[str, int] = {}
    for skin in metadata_skins:
        collection_name = skin.collection_name
        if collection_name is None or skin.rarity != next_rarity:
            continue
        if is_current_standard_trade_up_output_eligible(
            skin=skin,
            result_stattrak=expected_stattrak,
        ):
            canonical_output_counts[collection_name] = (
                canonical_output_counts.get(collection_name, 0) + 1
            )

    excluded_no_identity = 0
    excluded_invalid_rarity = 0
    excluded_no_collection = 0
    excluded_no_valid_output = 0
    excluded_intrinsic_policy = 0
    excluded_by_allowlist = 0
    entries: list[MarketUniverseEntry] = []
    seen_goods_ids: set[str] = set()

    for skin in metadata_skins:
        market_hash_name = skin.market_hash_name
        if market_hash_name not in forward:
            excluded_no_identity += 1
            continue
        if skin.rarity not in RarityOrder.ORDER[:5] or skin.rarity != spec.rarity:
            excluded_invalid_rarity += 1
            continue
        collection_name = skin.collection_name
        if collection_name is None or not collection_name.strip():
            excluded_no_collection += 1
            continue
        if (
            allowed_collections is not None
            and collection_name not in allowed_collections
        ):
            excluded_by_allowlist += 1
            continue
        if skin.stattrak is not expected_stattrak:
            excluded_intrinsic_policy += 1
            continue
        if (
            spec.souvenir_inclusion is SouvenirInclusion.EXCLUDE
            and skin.souvenir
        ):
            excluded_intrinsic_policy += 1
            continue
        if canonical_output_counts.get(collection_name, 0) == 0:
            excluded_no_valid_output += 1
            continue

        goods_id = forward[market_hash_name]
        if goods_id in seen_goods_ids:
            raise BoundedMarketUniverseBuilderError(reason="duplicate_goods_id")
        seen_goods_ids.add(goods_id)
        entries.append(
            MarketUniverseEntry(
                goods_id=goods_id,
                market_hash_name=market_hash_name,
                collection_name=collection_name,
                rarity=skin.rarity,
                stattrak=skin.stattrak,
                souvenir=skin.souvenir,
            )
        )

    excluded_no_metadata = sum(
        1 for name, _goods_id in identity_resolver.identities
        if name not in metadata_index
    )
    return _EligibilityResult(
        entries=tuple(entries),
        canonical_output_counts=canonical_output_counts,
        catalog_metadata_rows=len(metadata_skins),
        catalog_identity_rows=len(forward),
        excluded_no_identity=excluded_no_identity,
        excluded_no_metadata=excluded_no_metadata,
        excluded_invalid_rarity=excluded_invalid_rarity,
        excluded_no_collection=excluded_no_collection,
        excluded_no_valid_output=excluded_no_valid_output,
        excluded_intrinsic_policy=excluded_intrinsic_policy,
        excluded_by_allowlist=excluded_by_allowlist,
    )


def _entry_breadth_key(
    entry: MarketUniverseEntry,
) -> tuple[str, bool, bool, int, str]:
    return (
        entry.collection_name,
        entry.stattrak,
        entry.souvenir,
        len(entry.market_hash_name),
        entry.market_hash_name,
    )


def _entry_identity_key(entry: MarketUniverseEntry) -> tuple[int, str]:
    return (len(entry.market_hash_name), entry.market_hash_name)


def _cohort_key(entry: MarketUniverseEntry) -> MarketUniverseCohortKey:
    return MarketUniverseCohortKey(
        collection_name=entry.collection_name,
        rarity=entry.rarity,
        stattrak=entry.stattrak,
    )


def _cohort_lexical_key(
    key: MarketUniverseCohortKey,
) -> tuple[str, str, bool]:
    return (key.collection_name, key.rarity, key.stattrak)


def _group_entries_by_cohort(
    entries: tuple[MarketUniverseEntry, ...],
) -> dict[MarketUniverseCohortKey, tuple[MarketUniverseEntry, ...]]:
    mutable: dict[MarketUniverseCohortKey, list[MarketUniverseEntry]] = {}
    for entry in entries:
        mutable.setdefault(_cohort_key(entry), []).append(entry)
    return {
        key: tuple(values)
        for key, values in mutable.items()
    }


def _allocate_breadth(
    entries: tuple[MarketUniverseEntry, ...],
    *,
    cap: int,
) -> list[MarketUniverseEntry]:
    """Preserve Phase 13R collection round-robin ordering exactly."""
    ordered = sorted(entries, key=_entry_breadth_key)
    collections_in_order: list[str] = []
    buckets: dict[str, list[MarketUniverseEntry]] = {}
    for entry in ordered:
        if entry.collection_name not in buckets:
            collections_in_order.append(entry.collection_name)
            buckets[entry.collection_name] = []
        buckets[entry.collection_name].append(entry)

    picked: list[MarketUniverseEntry] = []
    while len(picked) < cap:
        progressed = False
        for collection_name in collections_in_order:
            bucket = buckets[collection_name]
            if not bucket:
                continue
            picked.append(bucket.pop(0))
            progressed = True
            if len(picked) >= cap:
                break
        if not progressed:
            break
    return picked


def _interleave_intrinsic_categories(
    entries: tuple[MarketUniverseEntry, ...],
) -> tuple[MarketUniverseEntry, ...]:
    normal = sorted(
        (entry for entry in entries if not entry.souvenir),
        key=_entry_identity_key,
    )
    souvenir = sorted(
        (entry for entry in entries if entry.souvenir),
        key=_entry_identity_key,
    )
    result: list[MarketUniverseEntry] = []
    index = 0
    while index < len(normal) or index < len(souvenir):
        if index < len(normal):
            result.append(normal[index])
        if index < len(souvenir):
            result.append(souvenir[index])
        index += 1
    return tuple(result)


def _rank_cohorts(
    cohorts: dict[MarketUniverseCohortKey, tuple[MarketUniverseEntry, ...]],
) -> list[MarketUniverseCohortKey]:
    return sorted(
        cohorts,
        key=lambda key: (
            -len(cohorts[key]),
            *_cohort_lexical_key(key),
        ),
    )


def _allocate_cohort_depth(
    cohorts: dict[MarketUniverseCohortKey, tuple[MarketUniverseEntry, ...]],
    *,
    cap: int,
    target_cohort_count: int,
) -> list[MarketUniverseEntry]:
    ranked = _rank_cohorts(cohorts)[:target_cohort_count]
    ordered_entries = {
        key: _interleave_intrinsic_categories(cohorts[key])
        for key in ranked
    }
    allocations = {key: 0 for key in ranked}
    allocated = 0
    while allocated < cap:
        progressed = False
        for key in ranked:
            if allocations[key] >= len(ordered_entries[key]):
                continue
            allocations[key] += 1
            allocated += 1
            progressed = True
            if allocated >= cap:
                break
        if not progressed:
            break

    picked: list[MarketUniverseEntry] = []
    for key in ranked:
        picked.extend(ordered_entries[key][:allocations[key]])
    return picked


def _build_selected_cohort_diagnostics(
    *,
    picked: list[MarketUniverseEntry],
    cohorts: dict[MarketUniverseCohortKey, tuple[MarketUniverseEntry, ...]],
    canonical_output_counts: dict[str, int],
    strategy: UniverseAllocationStrategy,
) -> tuple[MarketUniverseCohortAllocation, ...]:
    selected_by_key: dict[
        MarketUniverseCohortKey, list[MarketUniverseEntry]
    ] = {}
    selected_key_order: list[MarketUniverseCohortKey] = []
    for entry in picked:
        key = _cohort_key(entry)
        if key not in selected_by_key:
            selected_by_key[key] = []
            selected_key_order.append(key)
        selected_by_key[key].append(entry)

    if strategy is UniverseAllocationStrategy.COHORT_DEPTH:
        selected_key_order = sorted(
            selected_key_order,
            key=lambda key: (
                -len(cohorts[key]),
                *_cohort_lexical_key(key),
            ),
        )

    result: list[MarketUniverseCohortAllocation] = []
    for key in selected_key_order:
        cohort_entries = cohorts[key]
        selected_entries = tuple(selected_by_key[key])
        normal_count = sum(not entry.souvenir for entry in cohort_entries)
        souvenir_count = len(cohort_entries) - normal_count
        result.append(
            MarketUniverseCohortAllocation(
                key=key,
                catalog_capacity=len(cohort_entries),
                normal_identity_count=normal_count,
                souvenir_identity_count=souvenir_count,
                canonical_output_count=canonical_output_counts.get(
                    key.collection_name, 0
                ),
                allocated_slots=len(selected_entries),
                selected_entries=selected_entries,
            )
        )
    return tuple(result)
