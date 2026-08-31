"""Frozen Phase 15C representative-snapshot planning primitives."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.market_universe_builder import (
    BoundedMarketUniverseBuilderError,
    MarketUniverseResult,
    MarketUniverseSpec,
    SouvenirInclusion,
    StatTrakMode,
    UniverseAllocationStrategy,
    build_universe_goods_ids,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver

PROTOCOL_ID = "representative-listing-snapshot-v1"
SCHEMA_VERSION = 1
TARGET_GOODS_COUNT = 10
TARGET_COHORT_COUNT = 3
DEFAULT_RECIPE_CANDIDATES = 2
DEFAULT_CANDIDATE_STATES = 256
MINIMUM_REQUEST_START_INTERVAL_SECONDS = 2.0

PRODUCTIVE_STRATA: tuple[tuple[str, str], ...] = (
    ("Consumer Grade", "normal"),
    ("Industrial Grade", "normal"),
    ("Mil-Spec Grade", "normal"),
    ("Mil-Spec Grade", "stattrak"),
    ("Restricted", "normal"),
    ("Restricted", "stattrak"),
    ("Classified", "normal"),
    ("Classified", "stattrak"),
)

_CAMPAIGN_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{2,63}")
_UTC_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_FIXED_ERROR = "invalid representative snapshot protocol input"


class SnapshotProtocolError(ValueError):
    """A frozen protocol input or plan violated a deterministic contract."""

    def __init__(self, *, reason: str) -> None:
        super().__init__(_FIXED_ERROR)
        self.reason = reason


@dataclass(frozen=True, kw_only=True)
class ObservationSpec:
    campaign_id: str
    nominal_slot_utc: str
    input_rarity: str
    stattrak_mode: str

    def __post_init__(self) -> None:
        validate_campaign_id(self.campaign_id)
        parse_utc_timestamp(self.nominal_slot_utc)
        if (self.input_rarity, self.stattrak_mode) not in PRODUCTIVE_STRATA:
            raise SnapshotProtocolError(reason="unsupported_stratum")


@dataclass(frozen=True, kw_only=True)
class PlannedGood:
    goods_id: str
    universe_rank: int
    market_hash_name: str
    rarity: str
    stattrak: bool
    souvenir: bool
    cohort_collection: str
    cohort_allocated_slot: int

    def to_payload(self) -> dict[str, object]:
        return {
            "goods_id": self.goods_id,
            "universe_rank": self.universe_rank,
            "market_hash_name": self.market_hash_name,
            "rarity": self.rarity,
            "stattrak": self.stattrak,
            "souvenir": self.souvenir,
            "cohort_collection": self.cohort_collection,
            "cohort_allocated_slot": self.cohort_allocated_slot,
        }


@dataclass(frozen=True, kw_only=True)
class ObservationPlan:
    spec: ObservationSpec
    snapshot_id: str
    scheduled_for_utc: str
    jitter_minutes: int
    planned_goods: tuple[PlannedGood, ...]
    selected_cohort_count: int

    @property
    def goods_ids(self) -> tuple[str, ...]:
        return tuple(item.goods_id for item in self.planned_goods)


@dataclass(frozen=True, kw_only=True)
class PlanningFailure:
    spec: ObservationSpec
    snapshot_id: str
    scheduled_for_utc: str
    reason: str


PlanningResult = ObservationPlan | PlanningFailure


def validate_campaign_id(value: object) -> str:
    if type(value) is not str or _CAMPAIGN_ID_PATTERN.fullmatch(value) is None:
        raise SnapshotProtocolError(reason="invalid_campaign_id")
    return value


def parse_utc_timestamp(value: object) -> datetime:
    if type(value) is not str or _UTC_PATTERN.fullmatch(value) is None:
        raise SnapshotProtocolError(reason="invalid_utc_timestamp")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
    except ValueError:
        raise SnapshotProtocolError(reason="invalid_utc_timestamp") from None
    if format_utc_timestamp(parsed) != value:
        raise SnapshotProtocolError(reason="invalid_utc_timestamp")
    return parsed


def format_utc_timestamp(value: datetime) -> str:
    if type(value) is not datetime or value.tzinfo is None:
        raise SnapshotProtocolError(reason="invalid_utc_timestamp")
    normalized = value.astimezone(UTC)
    if normalized.microsecond != 0:
        raise SnapshotProtocolError(reason="invalid_utc_timestamp")
    return normalized.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_snapshot_id(spec: ObservationSpec) -> str:
    material = (
        f"{spec.campaign_id}|{spec.nominal_slot_utc}|"
        f"{spec.input_rarity}|{spec.stattrak_mode}"
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"snap-v1-{digest[:24]}"


def calculate_jitter_minutes(
    *,
    campaign_id: str,
    nominal_slot_utc: str,
) -> int:
    validate_campaign_id(campaign_id)
    parse_utc_timestamp(nominal_slot_utc)
    material = f"{campaign_id}|{nominal_slot_utc}".encode()
    value = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    return value % 21 - 10


def scheduled_timestamp(spec: ObservationSpec) -> str:
    nominal = parse_utc_timestamp(spec.nominal_slot_utc)
    jitter = calculate_jitter_minutes(
        campaign_id=spec.campaign_id,
        nominal_slot_utc=spec.nominal_slot_utc,
    )
    return format_utc_timestamp(nominal + timedelta(minutes=jitter))


def plan_observation(
    *,
    spec: ObservationSpec,
    identity_resolver: BuffCommunityIdentityResolver,
    metadata_resolver: PinnedSkinMetadataResolver,
) -> PlanningResult:
    """Build the frozen exact ten-goods plan without network activity."""

    snapshot_id = build_snapshot_id(spec)
    scheduled = scheduled_timestamp(spec)
    try:
        universe = build_universe_goods_ids(
            identity_resolver=identity_resolver,
            metadata_resolver=metadata_resolver,
            spec=MarketUniverseSpec(
                rarity=spec.input_rarity,
                stattrak_mode=(
                    StatTrakMode.STATTRAK
                    if spec.stattrak_mode == "stattrak"
                    else StatTrakMode.NORMAL
                ),
                souvenir_inclusion=SouvenirInclusion.INCLUDE,
                cap=TARGET_GOODS_COUNT,
                allocation_strategy=UniverseAllocationStrategy.COHORT_DEPTH,
                target_cohort_count=TARGET_COHORT_COUNT,
            ),
        )
    except BoundedMarketUniverseBuilderError:
        return PlanningFailure(
            spec=spec,
            snapshot_id=snapshot_id,
            scheduled_for_utc=scheduled,
            reason="UNIVERSE_PLANNING_FAILED",
        )

    if (
        len(universe.goods_ids) != TARGET_GOODS_COUNT
        or len(universe.selected_entries) != TARGET_GOODS_COUNT
        or universe.diagnostics.selected_cohort_count != TARGET_COHORT_COUNT
    ):
        return PlanningFailure(
            spec=spec,
            snapshot_id=snapshot_id,
            scheduled_for_utc=scheduled,
            reason="UNIVERSE_NOT_EXACTLY_TEN",
        )

    return ObservationPlan(
        spec=spec,
        snapshot_id=snapshot_id,
        scheduled_for_utc=scheduled,
        jitter_minutes=calculate_jitter_minutes(
            campaign_id=spec.campaign_id,
            nominal_slot_utc=spec.nominal_slot_utc,
        ),
        planned_goods=_planned_goods(universe),
        selected_cohort_count=universe.diagnostics.selected_cohort_count,
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _planned_goods(universe: MarketUniverseResult) -> tuple[PlannedGood, ...]:
    cohort_slots: dict[str, dict[str, int]] = {}
    for cohort in universe.diagnostics.selected_cohorts:
        cohort_slots[cohort.key.collection_name] = {
            entry.goods_id: slot
            for slot, entry in enumerate(cohort.selected_entries)
        }

    planned: list[PlannedGood] = []
    for rank, entry in enumerate(universe.selected_entries):
        slots = cohort_slots.get(entry.collection_name)
        if slots is None or entry.goods_id not in slots:
            raise SnapshotProtocolError(reason="universe_provenance_mismatch")
        planned.append(
            PlannedGood(
                goods_id=entry.goods_id,
                universe_rank=rank,
                market_hash_name=entry.market_hash_name,
                rarity=entry.rarity,
                stattrak=entry.stattrak,
                souvenir=entry.souvenir,
                cohort_collection=entry.collection_name,
                cohort_allocated_slot=slots[entry.goods_id],
            )
        )
    return tuple(planned)
