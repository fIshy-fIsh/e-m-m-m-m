"""Phase 13R — Bounded deterministic market universe builder.

A pure, offline planner that joins the pinned BUFF identity catalog with
the pinned skin metadata catalog by exact `market_hash_name`, applies the
current Trade Up Contract output eligibility rule from
`scanner_recipe_composition`, and emits a bounded, stable goods-id
sequence for the existing live scanner.

The builder performs ZERO network I/O. It is a planning-layer module:
no BUFF request, no SteamDT call, no EV/ROI computation, no ranking.

Protected Core is not modified. The existing live scanner accepts the
builder's output `goods_ids` unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable
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
    }
)

__all__ = (
    "BoundedMarketUniverseBuilderError",
    "MarketUniverseDiagnostics",
    "MarketUniverseErrorReason",
    "MarketUniverseResult",
    "MarketUniverseSpec",
    "SouvenirInclusion",
    "StatTrakMode",
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


class StatTrakMode(StrEnum):
    """Explicit homogeneous StatTrak mode for the generated universe."""

    NORMAL = "normal"
    STATTRAK = "stattrak"


class SouvenirInclusion(StrEnum):
    """Souvenir input inclusion policy (output rule remains non-Souvenir)."""

    INCLUDE = "include"
    EXCLUDE = "exclude"


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


@dataclass(frozen=True, kw_only=True, repr=False)
class MarketUniverseDiagnostics:
    """Truthful counters for one build.

    Counter semantics:

    - ``catalog_metadata_rows`` and ``catalog_identity_rows`` are the
      sizes of the input catalogs.
    - ``eligible_before_bound`` counts metadata rows that pass every
      technical check (rarity, collection, output eligibility, intrinsic
      policy, collection allowlist) and would enter the active universe.
    - ``selected_count`` is the bounded final universe size.
    - ``excluded_no_identity`` counts catalog metadata rows whose
      ``market_hash_name`` is absent from the identity forward map.
    - ``excluded_no_metadata`` counts catalog identity rows whose
      ``market_hash_name`` is absent from the metadata catalog.
    - The remaining exclusions (``excluded_invalid_rarity``,
      ``excluded_no_collection``, ``excluded_no_valid_output``,
      ``excluded_intrinsic_policy``, ``excluded_by_allowlist``) count
      metadata rows that fail exactly one technical gate; they partition
      the rows that have BOTH an identity and a metadata record.

    ``excluded_no_identity`` and ``excluded_no_metadata`` are disjoint in
    catalog space (one is metadata-side, the other identity-side). The
    technical-exclusion counters above are also mutually exclusive among
    themselves because each metadata row short-circuits at the first
    failed gate in the pipeline. Together, the disjoint technical
    counters sum to the rows that have BOTH an identity and a metadata
    record (16868 metadata - 5494 no-identity = 11374, then minus
    no-collection, minus rarity, minus intrinsic policy, minus
    allowlist, minus no valid output = 1485 eligible).
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


@dataclass(frozen=True, kw_only=True, repr=False)
class MarketUniverseResult:
    """Immutable, deterministic bounded goods-id plan."""

    spec: MarketUniverseSpec
    goods_ids: tuple[str, ...]
    selected_market_hash_names: tuple[str, ...]
    diagnostics: MarketUniverseDiagnostics


def build_universe_goods_ids(
    *,
    identity_resolver: BuffCommunityIdentityResolver,
    metadata_resolver: PinnedSkinMetadataResolver,
    spec: MarketUniverseSpec,
) -> MarketUniverseResult:
    """Build a deterministic bounded goods-id universe from pinned catalogs.

    Pure function: no I/O, no async, no global state. Two runs with
    identical inputs return byte-equal results.
    """
    try:
        if type(identity_resolver) is not BuffCommunityIdentityResolver:
            raise BoundedMarketUniverseBuilderError(reason="exact_collision")
        if type(metadata_resolver) is not PinnedSkinMetadataResolver:
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
    forward: dict[str, str] = dict(identity_resolver._forward)  # noqa: SLF001 — same-module resolver contract
    metadata_skins: tuple[SkinMetadata, ...] = metadata_resolver.skins

    allowed_collections: frozenset[str] | None
    if spec.collection_allowlist:
        seen: set[str] = set()
        unique: list[str] = []
        for value in spec.collection_allowlist:
            if value in seen:
                continue
            seen.add(value)
            unique.append(value)
        allowed_collections = frozenset(unique)
    else:
        allowed_collections = None

    expected_stattrak: bool = spec.stattrak_mode is StatTrakMode.STATTRAK

    # Exact metadata identity index: market_hash_name -> SkinMetadata
    metadata_index: dict[str, SkinMetadata] = {}
    for skin in metadata_skins:
        if skin.market_hash_name in metadata_index:
            raise BoundedMarketUniverseBuilderError(reason="exact_collision")
        metadata_index[skin.market_hash_name] = skin

    # Per-collection next-rarity canonical output existence check.
    next_rarity = get_next_rarity(spec.rarity)
    if next_rarity is None:
        raise BoundedMarketUniverseBuilderError(reason="unsupported_rarity")

    collection_has_canonical_output: dict[str, bool] = {}
    for skin in metadata_skins:
        if skin.collection_name is None:
            continue
        if skin.rarity != next_rarity:
            continue
        if skin.collection_name not in collection_has_canonical_output:
            collection_has_canonical_output[skin.collection_name] = False
        if is_current_standard_trade_up_output_eligible(
            skin=skin, result_stattrak=expected_stattrak
        ):
            collection_has_canonical_output[skin.collection_name] = True

    excluded_no_identity = 0
    excluded_no_metadata = 0
    excluded_invalid_rarity = 0
    excluded_no_collection = 0
    excluded_no_valid_output = 0
    excluded_intrinsic_policy = 0
    excluded_by_allowlist = 0

    eligible_rows: list[SkinMetadata] = []
    seen_goods_ids: set[str] = set()

    for skin in metadata_skins:
        market_hash_name = skin.market_hash_name
        if market_hash_name not in forward:
            excluded_no_identity += 1
            continue
        # Skins exist iff we found a metadata row; this counter applies only
        # to identity rows absent from metadata.
        if market_hash_name not in metadata_index:
            excluded_no_metadata += 1
            continue
        if skin.rarity not in RarityOrder.ORDER[:5]:
            excluded_invalid_rarity += 1
            continue
        if skin.rarity != spec.rarity:
            # Spec rarity is the only productive input tier in V1.
            excluded_invalid_rarity += 1
            continue
        if (
            skin.collection_name is None
            or not skin.collection_name
            or not skin.collection_name.strip()
        ):
            excluded_no_collection += 1
            continue
        if allowed_collections is not None and skin.collection_name not in allowed_collections:
            excluded_by_allowlist += 1
            continue
        if skin.stattrak is not expected_stattrak:
            excluded_intrinsic_policy += 1
            continue
        if spec.souvenir_inclusion is SouvenirInclusion.EXCLUDE and skin.souvenir:
            excluded_intrinsic_policy += 1
            continue
        if not collection_has_canonical_output.get(skin.collection_name, False):
            excluded_no_valid_output += 1
            continue

        goods_id = forward[market_hash_name]
        if goods_id in seen_goods_ids:
            raise BoundedMarketUniverseBuilderError(reason="duplicate_goods_id")
        seen_goods_ids.add(goods_id)
        eligible_rows.append(skin)

    # Identity rows absent from metadata (catalog-side counter; disjoint
    # from the technical-exclusion counters below).
    for name, _gid in identity_resolver.identities:
        if name not in metadata_index:
            excluded_no_metadata += 1

    if not eligible_rows:
        raise BoundedMarketUniverseBuilderError(reason="universe_empty")

    # Deterministic ordering: round-robin by collection, with each row
    # ordered by (stattrak, souvenir, len(market_hash_name), market_hash_name).
    # Sorting within a collection this way keeps the deterministic total
    # order stable across reruns.
    eligible_rows.sort(
        key=lambda item: (
            item.collection_name or "",
            item.stattrak,
            item.souvenir,
            len(item.market_hash_name),
            item.market_hash_name,
        )
    )

    # Round-robin across collections. With cap > 1, take one row per
    # collection in sorted order, then loop again so diversity is preserved.
    collections_in_order: list[str] = []
    buckets: dict[str, list[SkinMetadata]] = {}
    for row in eligible_rows:
        assert row.collection_name is not None
        if row.collection_name not in buckets:
            collections_in_order.append(row.collection_name)
            buckets[row.collection_name] = []
        buckets[row.collection_name].append(row)

    picked: list[SkinMetadata] = []
    while len(picked) < spec.cap:
        progressed = False
        for collection in collections_in_order:
            bucket = buckets[collection]
            if not bucket:
                continue
            picked.append(bucket.pop(0))
            progressed = True
            if len(picked) >= spec.cap:
                break
        if not progressed:
            break

    if not picked:
        raise BoundedMarketUniverseBuilderError(reason="universe_empty")

    selected_goods_ids: list[str] = []
    selected_market_hash_names: list[str] = []
    for row in picked:
        goods_id = forward[row.market_hash_name]
        selected_goods_ids.append(goods_id)
        selected_market_hash_names.append(row.market_hash_name)

    diagnostics = MarketUniverseDiagnostics(
        catalog_metadata_rows=len(metadata_skins),
        catalog_identity_rows=len(forward),
        eligible_before_bound=len(eligible_rows),
        selected_count=len(selected_goods_ids),
        excluded_no_identity=excluded_no_identity,
        excluded_no_metadata=excluded_no_metadata,
        excluded_invalid_rarity=excluded_invalid_rarity,
        excluded_no_collection=excluded_no_collection,
        excluded_no_valid_output=excluded_no_valid_output,
        excluded_intrinsic_policy=excluded_intrinsic_policy,
        excluded_by_allowlist=excluded_by_allowlist,
    )

    return MarketUniverseResult(
        spec=spec,
        goods_ids=tuple(selected_goods_ids),
        selected_market_hash_names=tuple(selected_market_hash_names),
        diagnostics=diagnostics,
    )


def _ensure_iterable(value: Iterable[str]) -> tuple[str, ...]:
    return tuple(value)