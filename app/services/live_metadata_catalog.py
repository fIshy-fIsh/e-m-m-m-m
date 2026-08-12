from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from app.services.market_scan_service import CandidateListing
from app.services.metadata_models import SkinMetadata
from app.services.steamapis_candidate_adapter import (
    adapt_steamapis_listing_to_candidate,
)
from app.services.steamapis_offer_pool import SteamApisOfferPoolSnapshot

_FIXED_ERROR_MESSAGE = "invalid live metadata catalog contract"
_SOURCE = "steamapis:buff163"

__all__ = (
    "LiveMetadataCatalogError",
    "LiveCandidateRejectionReason",
    "LiveSolverBucketKey",
    "LiveCandidateBinding",
    "LiveCandidateRejection",
    "LiveSolverBucket",
    "LiveCandidateClassification",
    "SkinMetadataCatalog",
    "classify_steamapis_snapshot",
)


class LiveMetadataCatalogError(ValueError):
    """A value or operation violated the live metadata catalog contract."""

    def __init__(self) -> None:
        super().__init__(_FIXED_ERROR_MESSAGE)


class LiveCandidateRejectionReason(StrEnum):
    """Stable structural rejection reasons for one live candidate."""

    METADATA_NOT_FOUND = "metadata_not_found"
    MISSING_COLLECTION = "missing_collection"
    CANDIDATE_FLOAT_MISSING = "candidate_float_missing"
    FLOAT_OUTSIDE_SKIN_RANGE = "float_outside_skin_range"


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveSolverBucketKey:
    """Solver-compatible live grouping dimensions."""

    input_rarity: str
    stattrak: bool
    souvenir: bool

    def __post_init__(self) -> None:
        try:
            _validate_nonblank_string(self.input_rarity)
            _validate_exact_bool(self.stattrak)
            _validate_exact_bool(self.souvenir)
        except MemoryError:
            raise
        except Exception:
            raise LiveMetadataCatalogError from None


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveCandidateBinding:
    """One live candidate bound to detached exact metadata."""

    source_offer_id: str
    candidate: CandidateListing
    skin_metadata: SkinMetadata

    def __post_init__(self) -> None:
        try:
            source_offer_id = _validate_source_offer_id(self.source_offer_id)
            candidate = _copy_candidate(self.candidate)
            skin_metadata = _copy_skin_metadata(self.skin_metadata)
            expected_id = f"{_SOURCE}:{source_offer_id}"
            if (
                candidate.goods_id != expected_id
                or candidate.listing_id != expected_id
                or candidate.source != _SOURCE
                or candidate.market_hash_name != skin_metadata.market_hash_name
                or skin_metadata.collection_name is None
                or candidate.float_value is None
                or not skin_metadata.min_float
                <= candidate.float_value
                <= skin_metadata.max_float
            ):
                raise LiveMetadataCatalogError
            object.__setattr__(self, "source_offer_id", source_offer_id)
            object.__setattr__(self, "candidate", candidate)
            object.__setattr__(self, "skin_metadata", skin_metadata)
        except MemoryError:
            raise
        except Exception:
            raise LiveMetadataCatalogError from None


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveCandidateRejection:
    """Redacted structural rejection for one source offer."""

    source_offer_id: str
    reason_code: LiveCandidateRejectionReason

    def __post_init__(self) -> None:
        try:
            source_offer_id = _validate_source_offer_id(self.source_offer_id)
            if type(self.reason_code) is not LiveCandidateRejectionReason:
                raise LiveMetadataCatalogError
            object.__setattr__(self, "source_offer_id", source_offer_id)
        except MemoryError:
            raise
        except Exception:
            raise LiveMetadataCatalogError from None


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveSolverBucket:
    """Immutable ordered candidates for one solver-compatible group."""

    key: LiveSolverBucketKey
    bindings: tuple[LiveCandidateBinding, ...]
    affected_collections: frozenset[str]

    def __post_init__(self) -> None:
        try:
            key = _copy_bucket_key(self.key)
            if type(self.bindings) is not tuple or not self.bindings:
                raise LiveMetadataCatalogError
            bindings = tuple(_copy_binding(binding) for binding in self.bindings)
            if type(self.affected_collections) is not frozenset:
                raise LiveMetadataCatalogError
            collections = frozenset(
                _validate_exact_string(collection)
                for collection in self.affected_collections
            )
            expected_collections: set[str] = set()
            for binding in bindings:
                if _binding_bucket_key(binding) != key:
                    raise LiveMetadataCatalogError
                collection_name = binding.skin_metadata.collection_name
                if collection_name is None:
                    raise LiveMetadataCatalogError
                expected_collections.add(collection_name)
            if collections != frozenset(expected_collections):
                raise LiveMetadataCatalogError
            object.__setattr__(self, "key", key)
            object.__setattr__(self, "bindings", bindings)
            object.__setattr__(self, "affected_collections", collections)
        except MemoryError:
            raise
        except Exception:
            raise LiveMetadataCatalogError from None


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveCandidateClassification:
    """Complete immutable classification of one live pool snapshot."""

    eligible: tuple[LiveCandidateBinding, ...]
    rejected: tuple[LiveCandidateRejection, ...]
    buckets: tuple[LiveSolverBucket, ...]

    def __post_init__(self) -> None:
        try:
            if type(self.eligible) is not tuple:
                raise LiveMetadataCatalogError
            if type(self.rejected) is not tuple:
                raise LiveMetadataCatalogError
            if type(self.buckets) is not tuple:
                raise LiveMetadataCatalogError
            eligible = tuple(_copy_binding(binding) for binding in self.eligible)
            rejected = tuple(_copy_rejection(rejection) for rejection in self.rejected)
            buckets = tuple(_copy_bucket(bucket) for bucket in self.buckets)
            source_offer_ids = [
                *(binding.source_offer_id for binding in eligible),
                *(rejection.source_offer_id for rejection in rejected),
            ]
            if len(source_offer_ids) != len(set(source_offer_ids)):
                raise LiveMetadataCatalogError
            expected_buckets = _build_buckets(eligible)
            if buckets != expected_buckets:
                raise LiveMetadataCatalogError
            object.__setattr__(self, "eligible", eligible)
            object.__setattr__(self, "rejected", rejected)
            object.__setattr__(self, "buckets", buckets)
        except MemoryError:
            raise
        except Exception:
            raise LiveMetadataCatalogError from None

    @property
    def affected_collections(self) -> frozenset[str]:
        """Return all collections whose live candidate universe changed."""

        return frozenset(
            collection
            for bucket in self.buckets
            for collection in bucket.affected_collections
        )


class SkinMetadataCatalog:
    """Detached exact-name metadata catalog with immutable indexes."""

    __slots__ = ("_metadata_by_bucket", "_metadata_by_name")

    def __init__(self, *, skins: Sequence[SkinMetadata]) -> None:
        try:
            if not isinstance(skins, Sequence) or isinstance(
                skins,
                (str, bytes, bytearray),
            ):
                raise LiveMetadataCatalogError
            source_skins = tuple(skins)
            if not source_skins:
                raise LiveMetadataCatalogError
            copied_skins = tuple(_copy_skin_metadata(skin) for skin in source_skins)
            metadata_by_name: dict[str, SkinMetadata] = {}
            metadata_by_bucket: dict[
                LiveSolverBucketKey,
                list[SkinMetadata],
            ] = {}
            for skin in copied_skins:
                if skin.market_hash_name in metadata_by_name:
                    raise LiveMetadataCatalogError
                metadata_by_name[skin.market_hash_name] = skin
                key = _skin_bucket_key(skin)
                metadata_by_bucket.setdefault(key, []).append(skin)
            immutable_buckets = {
                key: tuple(
                    sorted(
                        bucket_skins,
                        key=lambda bucket_skin: bucket_skin.market_hash_name,
                    )
                )
                for key, bucket_skins in metadata_by_bucket.items()
            }
            self._metadata_by_name = MappingProxyType(metadata_by_name)
            self._metadata_by_bucket = MappingProxyType(immutable_buckets)
        except MemoryError:
            raise
        except Exception:
            raise LiveMetadataCatalogError from None

    def get_by_market_hash_name(
        self,
        market_hash_name: str,
    ) -> SkinMetadata | None:
        """Return detached metadata for one exact case-sensitive name."""

        try:
            if type(market_hash_name) is not str:
                raise LiveMetadataCatalogError
            skin = self._metadata_by_name.get(str.__str__(market_hash_name))
            return None if skin is None else _copy_skin_metadata(skin)
        except MemoryError:
            raise
        except Exception:
            raise LiveMetadataCatalogError from None

    def get_by_solver_bucket_key(
        self,
        key: LiveSolverBucketKey,
    ) -> tuple[SkinMetadata, ...]:
        """Return detached metadata for one exact solver-mode key."""

        try:
            copied_key = _copy_bucket_key(key)
            skins = self._metadata_by_bucket.get(copied_key, ())
            return tuple(_copy_skin_metadata(skin) for skin in skins)
        except MemoryError:
            raise
        except Exception:
            raise LiveMetadataCatalogError from None


def classify_steamapis_snapshot(
    snapshot: SteamApisOfferPoolSnapshot,
    catalog: SkinMetadataCatalog,
) -> LiveCandidateClassification:
    """Classify one immutable pool snapshot without running the solver."""

    try:
        if type(snapshot) is not SteamApisOfferPoolSnapshot:
            raise LiveMetadataCatalogError
        if type(catalog) is not SkinMetadataCatalog:
            raise LiveMetadataCatalogError
        validated_snapshot = SteamApisOfferPoolSnapshot(
            observations=snapshot.observations,
        )
        eligible: list[LiveCandidateBinding] = []
        rejected: list[LiveCandidateRejection] = []
        seen_source_offer_ids: set[str] = set()
        for observation in validated_snapshot.observations:
            source_offer_id = _validate_source_offer_id(observation.source_offer_id)
            if source_offer_id in seen_source_offer_ids:
                raise LiveMetadataCatalogError
            seen_source_offer_ids.add(source_offer_id)
            candidate = _copy_candidate(
                adapt_steamapis_listing_to_candidate(observation)
            )
            if candidate.market_hash_name is None:
                raise LiveMetadataCatalogError
            skin = catalog.get_by_market_hash_name(candidate.market_hash_name)
            reason_code = _classify_rejection(candidate, skin)
            if reason_code is not None:
                rejected.append(
                    LiveCandidateRejection(
                        source_offer_id=source_offer_id,
                        reason_code=reason_code,
                    )
                )
                continue
            if skin is None:
                raise LiveMetadataCatalogError
            eligible.append(
                LiveCandidateBinding(
                    source_offer_id=source_offer_id,
                    candidate=candidate,
                    skin_metadata=skin,
                )
            )
        eligible_tuple = tuple(eligible)
        return LiveCandidateClassification(
            eligible=eligible_tuple,
            rejected=tuple(rejected),
            buckets=_build_buckets(eligible_tuple),
        )
    except MemoryError:
        raise
    except Exception:
        raise LiveMetadataCatalogError from None


def _classify_rejection(
    candidate: CandidateListing,
    skin: SkinMetadata | None,
) -> LiveCandidateRejectionReason | None:
    if skin is None:
        return LiveCandidateRejectionReason.METADATA_NOT_FOUND
    if skin.collection_name is None:
        return LiveCandidateRejectionReason.MISSING_COLLECTION
    if candidate.float_value is None:
        return LiveCandidateRejectionReason.CANDIDATE_FLOAT_MISSING
    if not skin.min_float <= candidate.float_value <= skin.max_float:
        return LiveCandidateRejectionReason.FLOAT_OUTSIDE_SKIN_RANGE
    return None


def _build_buckets(
    bindings: tuple[LiveCandidateBinding, ...],
) -> tuple[LiveSolverBucket, ...]:
    grouped: dict[LiveSolverBucketKey, list[LiveCandidateBinding]] = {}
    for binding in bindings:
        key = _binding_bucket_key(binding)
        grouped.setdefault(key, []).append(binding)
    return tuple(
        LiveSolverBucket(
            key=key,
            bindings=tuple(grouped[key]),
            affected_collections=frozenset(
                binding.skin_metadata.collection_name
                for binding in grouped[key]
                if binding.skin_metadata.collection_name is not None
            ),
        )
        for key in sorted(grouped, key=_bucket_sort_key)
    )


def _copy_skin_metadata(value: object) -> SkinMetadata:
    if type(value) is not SkinMetadata:
        raise LiveMetadataCatalogError
    market_hash_name = _validate_nonblank_string(value.market_hash_name)
    name = _validate_optional_string(value.name)
    weapon = _validate_optional_string(value.weapon)
    rarity = _validate_nonblank_string(value.rarity)
    category = _validate_optional_string(value.category)
    collection_name = _validate_optional_string(value.collection_name)
    min_float = _validate_finite_float(value.min_float)
    max_float = _validate_finite_float(value.max_float)
    if min_float >= max_float:
        raise LiveMetadataCatalogError
    _validate_exact_bool(value.stattrak)
    _validate_exact_bool(value.souvenir)
    paint_index = value.paint_index
    if paint_index is not None and type(paint_index) is not int:
        raise LiveMetadataCatalogError
    return SkinMetadata(
        market_hash_name=market_hash_name,
        name=name,
        weapon=weapon,
        rarity=rarity,
        category=category,
        collection_name=collection_name,
        min_float=min_float,
        max_float=max_float,
        stattrak=value.stattrak,
        souvenir=value.souvenir,
        paint_index=paint_index,
        raw=None,
    )


def _copy_candidate(value: object) -> CandidateListing:
    if type(value) is not CandidateListing:
        raise LiveMetadataCatalogError
    if type(value.goods_id) is not str or type(value.listing_id) is not str:
        raise LiveMetadataCatalogError
    if value.market_hash_name is not None and type(value.market_hash_name) is not str:
        raise LiveMetadataCatalogError
    if type(value.price_cny) is not Decimal or not value.price_cny.is_finite():
        raise LiveMetadataCatalogError
    if value.float_value is not None and (
        type(value.float_value) is not float or not math.isfinite(value.float_value)
    ):
        raise LiveMetadataCatalogError
    if value.paint_seed is not None and type(value.paint_seed) is not int:
        raise LiveMetadataCatalogError
    if value.inspect_link is not None and type(value.inspect_link) is not str:
        raise LiveMetadataCatalogError
    if type(value.source) is not str or type(value.scanned_at) is not datetime:
        raise LiveMetadataCatalogError
    if value.raw is not None:
        raise LiveMetadataCatalogError
    return CandidateListing(
        goods_id=str.__str__(value.goods_id),
        listing_id=str.__str__(value.listing_id),
        market_hash_name=value.market_hash_name,
        price_cny=value.price_cny,
        float_value=value.float_value,
        paint_seed=value.paint_seed,
        inspect_link=value.inspect_link,
        source=str.__str__(value.source),
        scanned_at=value.scanned_at,
        raw=None,
    )


def _copy_bucket_key(value: object) -> LiveSolverBucketKey:
    if type(value) is not LiveSolverBucketKey:
        raise LiveMetadataCatalogError
    return LiveSolverBucketKey(
        input_rarity=value.input_rarity,
        stattrak=value.stattrak,
        souvenir=value.souvenir,
    )


def _copy_binding(value: object) -> LiveCandidateBinding:
    if type(value) is not LiveCandidateBinding:
        raise LiveMetadataCatalogError
    return LiveCandidateBinding(
        source_offer_id=value.source_offer_id,
        candidate=value.candidate,
        skin_metadata=value.skin_metadata,
    )


def _copy_rejection(value: object) -> LiveCandidateRejection:
    if type(value) is not LiveCandidateRejection:
        raise LiveMetadataCatalogError
    return LiveCandidateRejection(
        source_offer_id=value.source_offer_id,
        reason_code=value.reason_code,
    )


def _copy_bucket(value: object) -> LiveSolverBucket:
    if type(value) is not LiveSolverBucket:
        raise LiveMetadataCatalogError
    return LiveSolverBucket(
        key=value.key,
        bindings=value.bindings,
        affected_collections=value.affected_collections,
    )


def _skin_bucket_key(skin: SkinMetadata) -> LiveSolverBucketKey:
    return LiveSolverBucketKey(
        input_rarity=skin.rarity,
        stattrak=skin.stattrak,
        souvenir=skin.souvenir,
    )


def _binding_bucket_key(binding: LiveCandidateBinding) -> LiveSolverBucketKey:
    return _skin_bucket_key(binding.skin_metadata)


def _bucket_sort_key(key: LiveSolverBucketKey) -> tuple[str, bool, bool]:
    return (key.input_rarity, key.stattrak, key.souvenir)


def _validate_nonblank_string(value: object) -> str:
    if type(value) is not str:
        raise LiveMetadataCatalogError
    canonical = str.__str__(value)
    if not canonical.strip():
        raise LiveMetadataCatalogError
    return canonical


def _validate_optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _validate_exact_string(value)


def _validate_exact_string(value: object) -> str:
    if type(value) is not str:
        raise LiveMetadataCatalogError
    return str.__str__(value)


def _validate_finite_float(value: object) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise LiveMetadataCatalogError
    return value


def _validate_exact_bool(value: object) -> None:
    if type(value) is not bool:
        raise LiveMetadataCatalogError


def _validate_source_offer_id(value: object) -> str:
    if type(value) is not str:
        raise LiveMetadataCatalogError
    source_offer_id = str.__str__(value)
    if len(source_offer_id) != 64 or any(
        character not in "0123456789abcdef" for character in source_offer_id
    ):
        raise LiveMetadataCatalogError
    return source_offer_id
