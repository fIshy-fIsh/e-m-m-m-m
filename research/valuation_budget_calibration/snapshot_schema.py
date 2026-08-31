"""Strict immutable schema-v1 model for representative listing snapshots."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any, NoReturn

from research.valuation_budget_calibration.snapshot_protocol import (
    DEFAULT_CANDIDATE_STATES,
    DEFAULT_RECIPE_CANDIDATES,
    PROTOCOL_ID,
    SCHEMA_VERSION,
    TARGET_COHORT_COUNT,
    TARGET_GOODS_COUNT,
    ObservationSpec,
    build_snapshot_id,
    parse_utc_timestamp,
    scheduled_timestamp,
    validate_campaign_id,
)

_FIXED_ERROR = "invalid representative snapshot schema"
_DECIMAL_PATTERN = re.compile(r"(?:0|[1-9]\d*)(?:\.\d+)?")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
_SAFE_REFERENCE_PATTERN = re.compile(r"[^\s\x00-\x1f\x7f]{1,200}")
_SECRET_KEY_PATTERN = re.compile(
    r"(?:authorization|cookie|set[-_]?cookie|api[-_]?key|access[-_]?token|"
    r"refresh[-_]?token|session[-_]?token|password|secret|credential|"
    r"seller|account|personal|headers?|query[-_]?string|raw[-_]?payload)",
    re.IGNORECASE,
)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(
        r"(?:authorization|cookie|set-cookie|x-api-key)\s*:",
        re.IGNORECASE,
    ),
    re.compile(r"(?:^|[?&])[A-Za-z0-9_.~-]{1,64}=[^\s&]{1,}"),
    re.compile(r"(?:bearer|basic)\s+[A-Za-z0-9._~+/-]{8,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)

TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "protocol_id",
        "campaign_id",
        "snapshot_id",
        "nominal_slot_utc",
        "scheduled_for_utc",
        "observed_at_utc",
        "capture_completed_at_utc",
        "timestamp_source",
        "observation_status",
        "stratum",
        "provenance",
        "universe",
        "acquisition_summary",
        "pages",
    }
)
STRATUM_KEYS = frozenset(
    {"input_rarity", "stattrak_mode", "souvenir_inclusion"}
)
PROVENANCE_KEYS = frozenset(
    {
        "collector_git_commit",
        "identity_snapshot_path",
        "identity_snapshot_sha256",
        "metadata_snapshot_path",
        "metadata_snapshot_sha256",
        "universe_config",
        "enumeration_config",
    }
)
UNIVERSE_CONFIG_KEYS = frozenset(
    {"cap", "allocation_strategy", "target_cohort_count", "souvenir_inclusion"}
)
ENUMERATION_CONFIG_KEYS = frozenset(
    {"max_recipe_candidates_returned", "max_candidate_states_explored"}
)
UNIVERSE_KEYS = frozenset(
    {
        "target_goods_count",
        "actual_goods_count",
        "selected_cohort_count",
        "planned_goods",
    }
)
PLANNED_GOOD_KEYS = frozenset(
    {
        "goods_id",
        "universe_rank",
        "market_hash_name",
        "rarity",
        "stattrak",
        "souvenir",
        "cohort_collection",
        "cohort_allocated_slot",
    }
)
PAGE_KEYS = frozenset(
    {
        "goods_id",
        "universe_rank",
        "cohort_collection",
        "cohort_rarity",
        "cohort_stattrak",
        "acquisition_status",
        "failure_reason",
        "failure_detail_code",
        "listing_count",
        "listings",
    }
)
LISTING_KEYS = frozenset(
    {
        "listing_reference",
        "listing_reference_kind",
        "asset_reference",
        "goods_id",
        "market_hash_name",
        "price_cny",
        "paintwear",
        "paintseed",
        "stattrak",
        "souvenir",
        "rarity",
        "collection_name",
        "source",
        "identity_status",
        "intrinsic_status",
        "metadata_status",
        "candidate_status",
        "replay_status",
        "rejection_reason",
    }
)
SUMMARY_KEYS = frozenset(
    {
        "pages_requested",
        "pages_completed",
        "pages_nonempty",
        "pages_empty",
        "pages_failed",
        "listings_received",
        "identity_resolved",
        "identity_unresolved",
        "intrinsic_resolved",
        "intrinsic_unresolved",
        "metadata_resolved",
        "metadata_not_found",
        "metadata_not_attempted",
        "candidate_accepted",
        "candidate_rejected",
        "replay_included",
        "replay_excluded",
        "reason_counts",
    }
)

SAFE_REASONS = frozenset(
    {
        "MISSED_OBSERVATION",
        "UNIVERSE_PLANNING_FAILED",
        "UNIVERSE_NOT_EXACTLY_TEN",
        "LISTING_FETCH_FAILED",
        "LISTING_RESPONSE_INVALID",
        "LISTING_REFERENCE_INVALID",
        "LISTING_PRICE_INVALID",
        "PAINTWEAR_INVALID_OR_MISSING",
        "ASSET_REFERENCE_INVALID",
        "IDENTITY_UNRESOLVED",
        "IDENTITY_CONFLICT",
        "INTRINSIC_UNRESOLVED",
        "INTRINSIC_CONFLICT",
        "METADATA_NOT_FOUND",
        "LISTING_REJECTED",
        "SNAPSHOT_PARTIAL",
        "SNAPSHOT_ACQUISITION_FAILED",
        "SNAPSHOT_SCHEMA_INVALID",
        "PROVENANCE_MISMATCH",
    }
)
SAFE_DETAIL_CODES = frozenset(
    {
        "request_failed",
        "response_not_json",
        "response_schema_invalid",
        "anonymous_access_unavailable",
        "items_missing",
        "listing_id_invalid",
        "price_invalid",
        "paintwear_invalid",
        "asset_id_invalid",
        "paintseed_invalid",
        "resolver_goods_id_mismatch",
        "listing_goods_id_mismatch",
        "market_hash_name_conflict",
        "missing_price",
        "invalid_float",
        "missing_asset_id",
        "unsupported_source",
        "intrinsic_flag_invalid",
        "market_hash_name_unresolved",
        "metadata_not_found",
        "intrinsic_flag_unresolved",
    }
)


class SnapshotSchemaError(ValueError):
    """Strict schema validation failed without retaining rejected values."""

    def __init__(self, *, reason: str) -> None:
        super().__init__(_FIXED_ERROR)
        self.reason = reason


class SecretMaterialError(SnapshotSchemaError):
    """Persisted content looked like prohibited secret/request material."""


class ObservationStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID_FOR_CALIBRATION"


class PageStatus(StrEnum):
    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY_PAGE"
    FETCH_FAILED = "FETCH_FAILED"
    PARSE_FAILED = "PARSE_FAILED"
    BINDING_FAILED = "BINDING_FAILED"


@dataclass(frozen=True, kw_only=True)
class SnapshotStratum:
    input_rarity: str
    stattrak_mode: str
    souvenir_inclusion: str

    def to_payload(self) -> dict[str, object]:
        return {
            "input_rarity": self.input_rarity,
            "stattrak_mode": self.stattrak_mode,
            "souvenir_inclusion": self.souvenir_inclusion,
        }


@dataclass(frozen=True, kw_only=True)
class SnapshotProvenance:
    collector_git_commit: str
    identity_snapshot_path: str
    identity_snapshot_sha256: str
    metadata_snapshot_path: str
    metadata_snapshot_sha256: str

    def to_payload(self) -> dict[str, object]:
        return {
            "collector_git_commit": self.collector_git_commit,
            "identity_snapshot_path": self.identity_snapshot_path,
            "identity_snapshot_sha256": self.identity_snapshot_sha256,
            "metadata_snapshot_path": self.metadata_snapshot_path,
            "metadata_snapshot_sha256": self.metadata_snapshot_sha256,
            "universe_config": {
                "cap": TARGET_GOODS_COUNT,
                "allocation_strategy": "cohort-depth",
                "target_cohort_count": TARGET_COHORT_COUNT,
                "souvenir_inclusion": "include",
            },
            "enumeration_config": {
                "max_recipe_candidates_returned": DEFAULT_RECIPE_CANDIDATES,
                "max_candidate_states_explored": DEFAULT_CANDIDATE_STATES,
            },
        }


@dataclass(frozen=True, kw_only=True)
class SnapshotPlannedGood:
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
class SnapshotListing:
    listing_reference: str
    listing_reference_kind: str
    asset_reference: str
    goods_id: str
    market_hash_name: str | None
    price_cny: str
    paintwear: str
    paintseed: int | None
    stattrak: bool | None
    souvenir: bool | None
    rarity: str | None
    collection_name: str | None
    source: str
    identity_status: str
    intrinsic_status: str
    metadata_status: str
    candidate_status: str
    replay_status: str
    rejection_reason: str | None

    def to_payload(self) -> dict[str, object]:
        return {
            "listing_reference": self.listing_reference,
            "listing_reference_kind": self.listing_reference_kind,
            "asset_reference": self.asset_reference,
            "goods_id": self.goods_id,
            "market_hash_name": self.market_hash_name,
            "price_cny": self.price_cny,
            "paintwear": self.paintwear,
            "paintseed": self.paintseed,
            "stattrak": self.stattrak,
            "souvenir": self.souvenir,
            "rarity": self.rarity,
            "collection_name": self.collection_name,
            "source": self.source,
            "identity_status": self.identity_status,
            "intrinsic_status": self.intrinsic_status,
            "metadata_status": self.metadata_status,
            "candidate_status": self.candidate_status,
            "replay_status": self.replay_status,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True, kw_only=True)
class SnapshotPage:
    goods_id: str
    universe_rank: int
    cohort_collection: str
    cohort_rarity: str
    cohort_stattrak: bool
    acquisition_status: PageStatus
    failure_reason: str | None
    failure_detail_code: str | None
    listings: tuple[SnapshotListing, ...]

    @property
    def listing_count(self) -> int:
        return len(self.listings)

    def to_payload(self) -> dict[str, object]:
        return {
            "goods_id": self.goods_id,
            "universe_rank": self.universe_rank,
            "cohort_collection": self.cohort_collection,
            "cohort_rarity": self.cohort_rarity,
            "cohort_stattrak": self.cohort_stattrak,
            "acquisition_status": self.acquisition_status.value,
            "failure_reason": self.failure_reason,
            "failure_detail_code": self.failure_detail_code,
            "listing_count": self.listing_count,
            "listings": [listing.to_payload() for listing in self.listings],
        }


@dataclass(frozen=True, kw_only=True)
class AcquisitionSummary:
    pages_requested: int
    pages_completed: int
    pages_nonempty: int
    pages_empty: int
    pages_failed: int
    listings_received: int
    identity_resolved: int
    identity_unresolved: int
    intrinsic_resolved: int
    intrinsic_unresolved: int
    metadata_resolved: int
    metadata_not_found: int
    metadata_not_attempted: int
    candidate_accepted: int
    candidate_rejected: int
    replay_included: int
    replay_excluded: int
    reason_counts: tuple[tuple[str, int], ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "pages_requested": self.pages_requested,
            "pages_completed": self.pages_completed,
            "pages_nonempty": self.pages_nonempty,
            "pages_empty": self.pages_empty,
            "pages_failed": self.pages_failed,
            "listings_received": self.listings_received,
            "identity_resolved": self.identity_resolved,
            "identity_unresolved": self.identity_unresolved,
            "intrinsic_resolved": self.intrinsic_resolved,
            "intrinsic_unresolved": self.intrinsic_unresolved,
            "metadata_resolved": self.metadata_resolved,
            "metadata_not_found": self.metadata_not_found,
            "metadata_not_attempted": self.metadata_not_attempted,
            "candidate_accepted": self.candidate_accepted,
            "candidate_rejected": self.candidate_rejected,
            "replay_included": self.replay_included,
            "replay_excluded": self.replay_excluded,
            "reason_counts": dict(self.reason_counts),
        }


@dataclass(frozen=True, kw_only=True)
class RepresentativeSnapshot:
    campaign_id: str
    snapshot_id: str
    nominal_slot_utc: str
    scheduled_for_utc: str
    observed_at_utc: str
    capture_completed_at_utc: str
    observation_status: ObservationStatus
    stratum: SnapshotStratum
    provenance: SnapshotProvenance
    selected_cohort_count: int
    planned_goods: tuple[SnapshotPlannedGood, ...]
    acquisition_summary: AcquisitionSummary
    pages: tuple[SnapshotPage, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "protocol_id": PROTOCOL_ID,
            "campaign_id": self.campaign_id,
            "snapshot_id": self.snapshot_id,
            "nominal_slot_utc": self.nominal_slot_utc,
            "scheduled_for_utc": self.scheduled_for_utc,
            "observed_at_utc": self.observed_at_utc,
            "capture_completed_at_utc": self.capture_completed_at_utc,
            "timestamp_source": "collector_host_utc_clock",
            "observation_status": self.observation_status.value,
            "stratum": self.stratum.to_payload(),
            "provenance": self.provenance.to_payload(),
            "universe": {
                "target_goods_count": TARGET_GOODS_COUNT,
                "actual_goods_count": len(self.planned_goods),
                "selected_cohort_count": self.selected_cohort_count,
                "planned_goods": [item.to_payload() for item in self.planned_goods],
            },
            "acquisition_summary": self.acquisition_summary.to_payload(),
            "pages": [page.to_payload() for page in self.pages],
        }


def load_snapshot(path: Path) -> RepresentativeSnapshot:
    return parse_snapshot_bytes(path.read_bytes())


def parse_snapshot_bytes(value: bytes) -> RepresentativeSnapshot:
    if type(value) is not bytes:
        raise SnapshotSchemaError(reason="invalid_json_bytes")
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        raise SnapshotSchemaError(reason="invalid_json_bytes") from None
    try:
        payload = json.loads(
            text,
            parse_float=_reject_json_number,
            parse_constant=_reject_json_number,
            object_pairs_hook=_unique_object,
        )
    except SnapshotSchemaError:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError):
        raise SnapshotSchemaError(reason="invalid_json") from None
    return parse_snapshot_payload(payload)


def parse_snapshot_payload(value: object) -> RepresentativeSnapshot:
    payload = _object(value, keys=TOP_LEVEL_KEYS)
    if _exact_int(payload["schema_version"]) != SCHEMA_VERSION:
        _fail("unsupported_schema_version")
    if _exact_string(payload["protocol_id"]) != PROTOCOL_ID:
        _fail("unsupported_protocol_id")

    try:
        campaign_id = validate_campaign_id(payload["campaign_id"])
    except ValueError:
        _fail("campaign_id_invalid")
    nominal = _timestamp(payload["nominal_slot_utc"])
    stratum_payload = _object(payload["stratum"], keys=STRATUM_KEYS)
    stratum = SnapshotStratum(
        input_rarity=_exact_string(stratum_payload["input_rarity"]),
        stattrak_mode=_one_of(
            stratum_payload["stattrak_mode"], {"normal", "stattrak"}
        ),
        souvenir_inclusion=_one_of(
            stratum_payload["souvenir_inclusion"], {"include"}
        ),
    )
    try:
        spec = ObservationSpec(
            campaign_id=campaign_id,
            nominal_slot_utc=nominal,
            input_rarity=stratum.input_rarity,
            stattrak_mode=stratum.stattrak_mode,
        )
    except ValueError:
        _fail("stratum_invalid")
    snapshot_id = _exact_string(payload["snapshot_id"])
    if snapshot_id != build_snapshot_id(spec):
        _fail("snapshot_id_mismatch")
    scheduled = _timestamp(payload["scheduled_for_utc"])
    if scheduled != scheduled_timestamp(spec):
        _fail("scheduled_timestamp_mismatch")
    observed = _timestamp(payload["observed_at_utc"])
    completed = _timestamp(payload["capture_completed_at_utc"])
    if parse_utc_timestamp(completed) < parse_utc_timestamp(observed):
        _fail("timestamp_order_invalid")
    if _exact_string(payload["timestamp_source"]) != "collector_host_utc_clock":
        _fail("timestamp_source_invalid")
    status = _enum(payload["observation_status"], ObservationStatus)

    provenance = _parse_provenance(payload["provenance"])
    universe = _object(payload["universe"], keys=UNIVERSE_KEYS)
    if _exact_int(universe["target_goods_count"]) != TARGET_GOODS_COUNT:
        _fail("target_goods_count_invalid")
    planned_values = _exact_list(universe["planned_goods"])
    planned_goods = tuple(
        _parse_planned_good(item, index=index)
        for index, item in enumerate(planned_values)
    )
    if (
        _exact_int(universe["actual_goods_count"]) != len(planned_goods)
        or len(planned_goods) != TARGET_GOODS_COUNT
    ):
        _fail("planned_goods_count_invalid")
    selected_cohort_count = _exact_int(universe["selected_cohort_count"])
    if selected_cohort_count != TARGET_COHORT_COUNT:
        _fail("selected_cohort_count_invalid")
    if len({item.goods_id for item in planned_goods}) != TARGET_GOODS_COUNT:
        _fail("duplicate_planned_goods")

    page_values = _exact_list(payload["pages"])
    pages = tuple(
        _parse_page(item, index=index) for index, item in enumerate(page_values)
    )
    if len(pages) != TARGET_GOODS_COUNT:
        _fail("page_count_invalid")
    if len({page.goods_id for page in pages}) != TARGET_GOODS_COUNT:
        _fail("duplicate_page_goods")
    for planned, page in zip(planned_goods, pages, strict=True):
        if (
            planned.goods_id != page.goods_id
            or planned.universe_rank != page.universe_rank
            or planned.cohort_collection != page.cohort_collection
            or planned.rarity != page.cohort_rarity
            or planned.stattrak is not page.cohort_stattrak
        ):
            _fail("page_plan_alignment_invalid")
        for listing in page.listings:
            if (
                listing.market_hash_name != planned.market_hash_name
                or listing.stattrak is not planned.stattrak
                or listing.souvenir is not planned.souvenir
                or listing.rarity != planned.rarity
                or listing.collection_name != planned.cohort_collection
            ):
                _fail("listing_plan_alignment_invalid")

    all_listings = tuple(
        listing for page in pages for listing in page.listings
    )
    references = tuple(item.listing_reference for item in all_listings)
    if len(references) != len(set(references)):
        _fail("duplicate_listing_reference")

    summary = _parse_summary(payload["acquisition_summary"])
    _validate_summary(summary=summary, pages=pages)
    _validate_status(
        status=status,
        planned_goods=planned_goods,
        pages=pages,
        listings=all_listings,
    )

    result = RepresentativeSnapshot(
        campaign_id=campaign_id,
        snapshot_id=snapshot_id,
        nominal_slot_utc=nominal,
        scheduled_for_utc=scheduled,
        observed_at_utc=observed,
        capture_completed_at_utc=completed,
        observation_status=status,
        stratum=stratum,
        provenance=provenance,
        selected_cohort_count=selected_cohort_count,
        planned_goods=planned_goods,
        acquisition_summary=summary,
        pages=pages,
    )
    payload_roundtrip = result.to_payload()
    scan_for_secret_material(payload_roundtrip)
    if payload_roundtrip != payload:
        _fail("payload_not_canonical")
    return result


def canonical_snapshot_bytes(snapshot: RepresentativeSnapshot) -> bytes:
    payload = snapshot.to_payload()
    scan_for_secret_material(payload)
    validated = parse_snapshot_payload(payload)
    return (
        json.dumps(
            validated.to_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def scan_for_secret_material(value: object) -> None:
    """Fail closed on prohibited persisted key/value shapes without echoing data."""

    def visit(item: object) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                if type(key) is not str or _SECRET_KEY_PATTERN.search(key):
                    raise SecretMaterialError(reason="secret_material_detected")
                visit(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                visit(nested)
        elif type(item) is str:
            if any(pattern.search(item) for pattern in _SECRET_VALUE_PATTERNS):
                raise SecretMaterialError(reason="secret_material_detected")
        elif item is not None and type(item) not in (bool, int):
            raise SecretMaterialError(reason="unsupported_persisted_type")

    visit(value)


def canonical_decimal(value: Decimal) -> str:
    if type(value) is not Decimal or not value.is_finite():
        raise SnapshotSchemaError(reason="decimal_invalid")
    rendered = format(value, "f")
    return _decimal_string(rendered, minimum=None, maximum=None)


def _parse_provenance(value: object) -> SnapshotProvenance:
    payload = _object(value, keys=PROVENANCE_KEYS)
    universe = _object(payload["universe_config"], keys=UNIVERSE_CONFIG_KEYS)
    if (
        _exact_int(universe["cap"]) != TARGET_GOODS_COUNT
        or _exact_string(universe["allocation_strategy"]) != "cohort-depth"
        or _exact_int(universe["target_cohort_count"]) != TARGET_COHORT_COUNT
        or _exact_string(universe["souvenir_inclusion"]) != "include"
    ):
        _fail("universe_config_invalid")
    enumeration = _object(
        payload["enumeration_config"], keys=ENUMERATION_CONFIG_KEYS
    )
    if (
        _exact_int(enumeration["max_recipe_candidates_returned"])
        != DEFAULT_RECIPE_CANDIDATES
        or _exact_int(enumeration["max_candidate_states_explored"])
        != DEFAULT_CANDIDATE_STATES
    ):
        _fail("enumeration_config_invalid")
    commit = _exact_string(payload["collector_git_commit"])
    if _COMMIT_PATTERN.fullmatch(commit) is None:
        _fail("collector_commit_invalid")
    identity_hash = _exact_string(payload["identity_snapshot_sha256"])
    metadata_hash = _exact_string(payload["metadata_snapshot_sha256"])
    if (
        _SHA256_PATTERN.fullmatch(identity_hash) is None
        or _SHA256_PATTERN.fullmatch(metadata_hash) is None
    ):
        _fail("snapshot_hash_invalid")
    return SnapshotProvenance(
        collector_git_commit=commit,
        identity_snapshot_path=_relative_path(payload["identity_snapshot_path"]),
        identity_snapshot_sha256=identity_hash,
        metadata_snapshot_path=_relative_path(payload["metadata_snapshot_path"]),
        metadata_snapshot_sha256=metadata_hash,
    )


def _parse_planned_good(value: object, *, index: int) -> SnapshotPlannedGood:
    payload = _object(value, keys=PLANNED_GOOD_KEYS)
    rank = _nonnegative_int(payload["universe_rank"])
    if rank != index:
        _fail("planned_goods_order_invalid")
    return SnapshotPlannedGood(
        goods_id=_reference(payload["goods_id"]),
        universe_rank=rank,
        market_hash_name=_exact_string(payload["market_hash_name"]),
        rarity=_exact_string(payload["rarity"]),
        stattrak=_exact_bool(payload["stattrak"]),
        souvenir=_exact_bool(payload["souvenir"]),
        cohort_collection=_exact_string(payload["cohort_collection"]),
        cohort_allocated_slot=_nonnegative_int(payload["cohort_allocated_slot"]),
    )


def _parse_page(value: object, *, index: int) -> SnapshotPage:
    payload = _object(value, keys=PAGE_KEYS)
    rank = _nonnegative_int(payload["universe_rank"])
    if rank != index:
        _fail("page_order_invalid")
    status = _enum(payload["acquisition_status"], PageStatus)
    listing_values = _exact_list(payload["listings"])
    listings = tuple(_parse_listing(item) for item in listing_values)
    if _nonnegative_int(payload["listing_count"]) != len(listings):
        _fail("listing_count_invalid")
    failure_reason = _nullable_reason(payload["failure_reason"])
    detail = _nullable_detail(payload["failure_detail_code"])
    if status is PageStatus.SUCCESS:
        if not listings or failure_reason is not None or detail is not None:
            _fail("page_status_invalid")
    elif status is PageStatus.EMPTY:
        if listings or failure_reason is not None or detail is not None:
            _fail("page_status_invalid")
    else:
        if listings or failure_reason is None:
            _fail("page_status_invalid")
    goods_id = _reference(payload["goods_id"])
    if any(listing.goods_id != goods_id for listing in listings):
        _fail("listing_goods_id_mismatch")
    return SnapshotPage(
        goods_id=goods_id,
        universe_rank=rank,
        cohort_collection=_exact_string(payload["cohort_collection"]),
        cohort_rarity=_exact_string(payload["cohort_rarity"]),
        cohort_stattrak=_exact_bool(payload["cohort_stattrak"]),
        acquisition_status=status,
        failure_reason=failure_reason,
        failure_detail_code=detail,
        listings=listings,
    )


def _parse_listing(value: object) -> SnapshotListing:
    payload = _object(value, keys=LISTING_KEYS)
    listing = SnapshotListing(
        listing_reference=_reference(payload["listing_reference"]),
        listing_reference_kind=_one_of(
            payload["listing_reference_kind"],
            {"anonymous_item_id_compatibility"},
        ),
        asset_reference=_reference(payload["asset_reference"]),
        goods_id=_reference(payload["goods_id"]),
        market_hash_name=_nullable_string(payload["market_hash_name"]),
        price_cny=_decimal_string(
            payload["price_cny"], minimum=Decimal("0"), maximum=None
        ),
        paintwear=_decimal_string(
            payload["paintwear"], minimum=Decimal("0"), maximum=Decimal("1")
        ),
        paintseed=_nullable_nonnegative_int(payload["paintseed"]),
        stattrak=_nullable_bool(payload["stattrak"]),
        souvenir=_nullable_bool(payload["souvenir"]),
        rarity=_nullable_string(payload["rarity"]),
        collection_name=_nullable_string(payload["collection_name"]),
        source=_one_of(payload["source"], {"buff"}),
        identity_status=_one_of(
            payload["identity_status"], {"RESOLVED", "UNRESOLVED"}
        ),
        intrinsic_status=_one_of(
            payload["intrinsic_status"],
            {"RESOLVED", "UNRESOLVED", "CONFLICT"},
        ),
        metadata_status=_one_of(
            payload["metadata_status"],
            {"RESOLVED", "NOT_FOUND", "NOT_ATTEMPTED"},
        ),
        candidate_status=_one_of(
            payload["candidate_status"],
            {"ACCEPTED", "REJECTED", "NOT_ATTEMPTED"},
        ),
        replay_status=_one_of(
            payload["replay_status"], {"INCLUDED", "EXCLUDED"}
        ),
        rejection_reason=_nullable_reason(payload["rejection_reason"]),
    )
    _validate_listing_status(listing)
    return listing


def _parse_summary(value: object) -> AcquisitionSummary:
    payload = _object(value, keys=SUMMARY_KEYS)
    reasons_payload = payload["reason_counts"]
    if type(reasons_payload) is not dict:
        _fail("reason_counts_invalid")
    reasons: list[tuple[str, int]] = []
    for key, count in reasons_payload.items():
        if key not in SAFE_REASONS:
            _fail("reason_code_invalid")
        reasons.append((key, _nonnegative_int(count)))
    if reasons != sorted(reasons):
        _fail("reason_counts_order_invalid")
    counts = {
        key: _nonnegative_int(payload[key])
        for key in SUMMARY_KEYS
        if key != "reason_counts"
    }
    return AcquisitionSummary(
        **counts,
        reason_counts=tuple(reasons),
    )


def _validate_summary(
    *,
    summary: AcquisitionSummary,
    pages: tuple[SnapshotPage, ...],
) -> None:
    listings = tuple(listing for page in pages for listing in page.listings)
    expected = {
        "pages_requested": TARGET_GOODS_COUNT,
        "pages_completed": sum(
            page.acquisition_status in (PageStatus.SUCCESS, PageStatus.EMPTY)
            for page in pages
        ),
        "pages_nonempty": sum(
            page.acquisition_status is PageStatus.SUCCESS for page in pages
        ),
        "pages_empty": sum(
            page.acquisition_status is PageStatus.EMPTY for page in pages
        ),
        "pages_failed": sum(
            page.acquisition_status
            in (
                PageStatus.FETCH_FAILED,
                PageStatus.PARSE_FAILED,
                PageStatus.BINDING_FAILED,
            )
            for page in pages
        ),
        "listings_received": len(listings),
        "identity_resolved": sum(
            listing.identity_status == "RESOLVED" for listing in listings
        ),
        "identity_unresolved": sum(
            listing.identity_status == "UNRESOLVED" for listing in listings
        ),
        "intrinsic_resolved": sum(
            listing.intrinsic_status == "RESOLVED" for listing in listings
        ),
        "intrinsic_unresolved": sum(
            listing.intrinsic_status != "RESOLVED" for listing in listings
        ),
        "metadata_resolved": sum(
            listing.metadata_status == "RESOLVED" for listing in listings
        ),
        "metadata_not_found": sum(
            listing.metadata_status == "NOT_FOUND" for listing in listings
        ),
        "metadata_not_attempted": sum(
            listing.metadata_status == "NOT_ATTEMPTED" for listing in listings
        ),
        "candidate_accepted": sum(
            listing.candidate_status == "ACCEPTED" for listing in listings
        ),
        "candidate_rejected": sum(
            listing.candidate_status == "REJECTED" for listing in listings
        ),
        "replay_included": sum(
            listing.replay_status == "INCLUDED" for listing in listings
        ),
        "replay_excluded": sum(
            listing.replay_status == "EXCLUDED" for listing in listings
        ),
    }
    for key, value in expected.items():
        if getattr(summary, key) != value:
            _fail("acquisition_summary_mismatch")
    if (
        summary.pages_completed + summary.pages_failed != summary.pages_requested
        or summary.pages_nonempty + summary.pages_empty != summary.pages_completed
        or summary.identity_resolved + summary.identity_unresolved
        != summary.listings_received
        or summary.intrinsic_resolved + summary.intrinsic_unresolved
        != summary.listings_received
        or summary.metadata_resolved
        + summary.metadata_not_found
        + summary.metadata_not_attempted
        != summary.listings_received
        or summary.candidate_accepted + summary.candidate_rejected
        > summary.listings_received
        or summary.replay_included + summary.replay_excluded
        != summary.listings_received
    ):
        _fail("acquisition_summary_mismatch")

    expected_reasons: dict[str, int] = {}
    for page in pages:
        if page.failure_reason is not None:
            expected_reasons[page.failure_reason] = (
                expected_reasons.get(page.failure_reason, 0) + 1
            )
        for listing in page.listings:
            if listing.rejection_reason is not None:
                expected_reasons[listing.rejection_reason] = (
                    expected_reasons.get(listing.rejection_reason, 0) + 1
                )
    if summary.reason_counts != tuple(sorted(expected_reasons.items())):
        _fail("reason_counts_mismatch")


def _validate_status(
    *,
    status: ObservationStatus,
    planned_goods: tuple[SnapshotPlannedGood, ...],
    pages: tuple[SnapshotPage, ...],
    listings: tuple[SnapshotListing, ...],
) -> None:
    if len(planned_goods) != TARGET_GOODS_COUNT:
        _fail("observation_status_invalid")
    page_statuses = {page.acquisition_status for page in pages}
    all_included = all(
        listing.identity_status == "RESOLVED"
        and listing.intrinsic_status == "RESOLVED"
        and listing.metadata_status == "RESOLVED"
        and listing.candidate_status == "ACCEPTED"
        and listing.replay_status == "INCLUDED"
        and listing.rejection_reason is None
        for listing in listings
    )
    if status is ObservationStatus.COMPLETE:
        if not page_statuses <= {PageStatus.SUCCESS, PageStatus.EMPTY} or not all_included:
            _fail("observation_status_invalid")
    elif status is ObservationStatus.PARTIAL:
        if (
            not page_statuses
            & {PageStatus.FETCH_FAILED, PageStatus.PARSE_FAILED}
            or PageStatus.BINDING_FAILED in page_statuses
            or not all_included
        ):
            _fail("observation_status_invalid")
    else:
        if (
            PageStatus.BINDING_FAILED not in page_statuses
            and all_included
            and page_statuses <= {PageStatus.SUCCESS, PageStatus.EMPTY}
        ):
            _fail("observation_status_invalid")


def _validate_listing_status(listing: SnapshotListing) -> None:
    resolved_fields = (
        listing.market_hash_name,
        listing.rarity,
        listing.collection_name,
    )
    if listing.identity_status == "RESOLVED":
        if listing.market_hash_name is None:
            _fail("listing_status_invalid")
    elif any(value is not None for value in resolved_fields) or any(
        value is not None for value in (listing.stattrak, listing.souvenir)
    ):
        _fail("listing_status_invalid")
    if listing.intrinsic_status == "RESOLVED":
        if type(listing.stattrak) is not bool or type(listing.souvenir) is not bool:
            _fail("listing_status_invalid")
    elif listing.stattrak is not None or listing.souvenir is not None:
        _fail("listing_status_invalid")
    if listing.metadata_status == "RESOLVED":
        if listing.rarity is None or listing.collection_name is None:
            _fail("listing_status_invalid")
    elif listing.rarity is not None or listing.collection_name is not None:
        _fail("listing_status_invalid")
    if listing.replay_status == "INCLUDED":
        if (
            listing.identity_status != "RESOLVED"
            or listing.intrinsic_status != "RESOLVED"
            or listing.metadata_status != "RESOLVED"
            or listing.candidate_status != "ACCEPTED"
            or listing.rejection_reason is not None
        ):
            _fail("listing_status_invalid")
    elif listing.rejection_reason is None:
        _fail("listing_status_invalid")


def _object(value: object, *, keys: frozenset[str]) -> dict[str, Any]:
    if type(value) is not dict or frozenset(value) != keys:
        _fail("object_keys_invalid")
    return value


def _exact_list(value: object) -> list[Any]:
    if type(value) is not list:
        _fail("list_type_invalid")
    return value


def _exact_string(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail("string_invalid")
    return value


def _reference(value: object) -> str:
    result = _exact_string(value)
    if _SAFE_REFERENCE_PATTERN.fullmatch(result) is None:
        _fail("reference_invalid")
    return result


def _relative_path(value: object) -> str:
    result = _exact_string(value)
    if (
        "\\" in result
        or result.startswith("/")
        or result.startswith("../")
        or "/../" in result
        or re.match(r"^[A-Za-z]:", result)
    ):
        _fail("provenance_path_invalid")
    return result


def _nullable_string(value: object) -> str | None:
    return None if value is None else _exact_string(value)


def _exact_int(value: object) -> int:
    if type(value) is not int:
        _fail("integer_invalid")
    return value


def _nonnegative_int(value: object) -> int:
    result = _exact_int(value)
    if result < 0:
        _fail("integer_invalid")
    return result


def _nullable_nonnegative_int(value: object) -> int | None:
    return None if value is None else _nonnegative_int(value)


def _exact_bool(value: object) -> bool:
    if type(value) is not bool:
        _fail("boolean_invalid")
    return value


def _nullable_bool(value: object) -> bool | None:
    return None if value is None else _exact_bool(value)


def _timestamp(value: object) -> str:
    result = _exact_string(value)
    parse_utc_timestamp(result)
    return result


def _one_of(value: object, options: set[str]) -> str:
    result = _exact_string(value)
    if result not in options:
        _fail("enum_invalid")
    return result


def _enum(value: object, enum_type: type[Any]) -> Any:
    result = _exact_string(value)
    try:
        return enum_type(result)
    except ValueError:
        _fail("enum_invalid")


def _decimal_string(
    value: object,
    *,
    minimum: Decimal | None,
    maximum: Decimal | None,
) -> str:
    if type(value) is not str or _DECIMAL_PATTERN.fullmatch(value) is None:
        _fail("decimal_invalid")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        _fail("decimal_invalid")
    if not parsed.is_finite():
        _fail("decimal_invalid")
    if minimum is not None and parsed < minimum:
        _fail("decimal_invalid")
    if minimum == 0 and maximum is None and parsed <= 0:
        _fail("decimal_invalid")
    if maximum is not None and parsed > maximum:
        _fail("decimal_invalid")
    return value


def _nullable_reason(value: object) -> str | None:
    if value is None:
        return None
    result = _exact_string(value)
    if result not in SAFE_REASONS:
        _fail("reason_code_invalid")
    return result


def _nullable_detail(value: object) -> str | None:
    if value is None:
        return None
    result = _exact_string(value)
    if result not in SAFE_DETAIL_CODES:
        _fail("detail_code_invalid")
    return result


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotSchemaError(reason="duplicate_json_key")
        result[key] = value
    return result


def _reject_json_number(value: str) -> NoReturn:
    _ = value
    raise SnapshotSchemaError(reason="json_number_invalid")


def _fail(reason: str) -> NoReturn:
    raise SnapshotSchemaError(reason=reason)
