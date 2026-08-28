from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path

from app.services.buff_listing import (
    BuffListingObservation,
    BuffListingValidationError,
)

BUFF_LISTING_FIXTURE_SCHEMA_VERSION = 2
BUFF_LISTING_FIXTURE_SCHEMA_VERSION_V1 = 1
BUFF_LISTING_FIXTURE_SOURCE = "buff"
_SUPPORTED_SCHEMA_VERSIONS = frozenset(
    {BUFF_LISTING_FIXTURE_SCHEMA_VERSION_V1, BUFF_LISTING_FIXTURE_SCHEMA_VERSION}
)

_TOP_LEVEL_FIELDS = frozenset(
    {"schema_version", "source", "observed_at", "listings"}
)
_REQUIRED_LISTING_FIELDS_V1 = frozenset(
    {"listing_id", "market_hash_name", "price_cny", "quantity"}
)
_OPTIONAL_LISTING_FIELDS = frozenset(
    {"float_value", "wear_name", "paint_seed", "sticker_metadata"}
)
_LISTING_FIELDS_V1 = _REQUIRED_LISTING_FIELDS_V1 | _OPTIONAL_LISTING_FIELDS
_REQUIRED_LISTING_FIELDS_V2 = _REQUIRED_LISTING_FIELDS_V1 | {"goods_id"}
_LISTING_FIELDS_V2 = _LISTING_FIELDS_V1 | {"goods_id"}
_STICKER_FIELDS = frozenset({"key", "value"})


class BuffListingParseCause(StrEnum):
    """Stable failure classifications for the offline fixture boundary."""

    JSON_DECODE = "json_decode"
    FILE_READ = "file_read"
    FIXTURE_SCHEMA = "fixture_schema"
    DOMAIN_VALIDATION = "domain_validation"


class BuffListingParseError(ValueError):
    """A project-owned BUFF fixture violated its safe parsing contract."""

    def __init__(
        self,
        *,
        field: str,
        cause: BuffListingParseCause,
        record_index: int | None = None,
    ) -> None:
        super().__init__("invalid BUFF listing fixture")
        self.field = field
        self.cause = cause
        self.record_index = record_index


class _DuplicateJsonKeyError(ValueError):
    pass


def parse_buff_listing_fixture(
    payload: Mapping[str, object],
) -> tuple[BuffListingObservation, ...]:
    """Parse one project-owned fixture mapping without performing I/O."""

    try:
        return _parse_fixture(payload)
    except (BuffListingParseError, MemoryError):
        raise
    except Exception:
        raise BuffListingParseError(
            field="payload",
            cause=BuffListingParseCause.FIXTURE_SCHEMA,
        ) from None


def load_buff_listing_fixture(path: Path) -> tuple[BuffListingObservation, ...]:
    """Load one UTF-8 JSON fixture, then delegate to the mapping parser."""

    if not isinstance(path, Path):
        raise BuffListingParseError(
            field="path",
            cause=BuffListingParseCause.FILE_READ,
        )
    try:
        serialized = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise BuffListingParseError(
            field="path",
            cause=BuffListingParseCause.FILE_READ,
        ) from None

    try:
        payload = json.loads(
            serialized,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except MemoryError:
        raise
    except Exception:
        raise BuffListingParseError(
            field="json",
            cause=BuffListingParseCause.JSON_DECODE,
        ) from None

    return parse_buff_listing_fixture(payload)


def _parse_fixture(payload: object) -> tuple[BuffListingObservation, ...]:
    if not isinstance(payload, Mapping):
        raise _parse_error(field="payload")
    _require_exact_fields(payload, _TOP_LEVEL_FIELDS, field="payload")

    schema_version = payload["schema_version"]
    if (
        type(schema_version) is not int
        or schema_version not in _SUPPORTED_SCHEMA_VERSIONS
    ):
        raise _parse_error(field="schema_version")

    source = payload["source"]
    if source != BUFF_LISTING_FIXTURE_SOURCE or type(source) is not str:
        raise _parse_error(field="source")

    observed_at = _parse_observed_at(payload["observed_at"])
    raw_listings = payload["listings"]
    if not isinstance(raw_listings, Sequence) or isinstance(
        raw_listings,
        (str, bytes, bytearray),
    ):
        raise _parse_error(field="listings")

    observations: list[BuffListingObservation] = []
    for record_index, raw_record in enumerate(raw_listings):
        observations.append(
            _parse_listing_record(
                raw_record,
                schema_version=schema_version,
                record_index=record_index,
                observed_at=observed_at,
            )
        )
    return tuple(observations)


def _parse_listing_record(
    raw_record: object,
    *,
    schema_version: int,
    record_index: int,
    observed_at: datetime,
) -> BuffListingObservation:
    record_field = "listings"
    if not isinstance(raw_record, Mapping):
        raise _parse_error(field=record_field, record_index=record_index)
    allowed_fields, required_fields = _listing_fields(schema_version)
    _require_exact_fields(
        raw_record,
        allowed_fields,
        required=required_fields,
        field=record_field,
        record_index=record_index,
    )

    price_cny = _parse_decimal_string(
        raw_record["price_cny"],
        field="price_cny",
        record_index=record_index,
    )
    float_value = _parse_optional_decimal_string(
        raw_record.get("float_value"),
        field="float_value",
        record_index=record_index,
    )
    sticker_metadata = _parse_sticker_metadata(
        raw_record.get("sticker_metadata"),
        record_index=record_index,
    )

    try:
        return BuffListingObservation(
            listing_id=_require_string(
                raw_record["listing_id"],
                field="listing_id",
                record_index=record_index,
            ),
            goods_id=(
                None
                if schema_version == BUFF_LISTING_FIXTURE_SCHEMA_VERSION_V1
                else _require_string(
                    raw_record["goods_id"],
                    field="goods_id",
                    record_index=record_index,
                )
            ),
            market_hash_name=_require_string(
                raw_record["market_hash_name"],
                field="market_hash_name",
                record_index=record_index,
            ),
            price_cny=price_cny,
            quantity=_require_exact_nonnegative_int(
                raw_record["quantity"],
                field="quantity",
                record_index=record_index,
            ),
            float_value=float_value,
            wear_name=_require_optional_string(
                raw_record.get("wear_name"),
                field="wear_name",
                record_index=record_index,
            ),
            paint_seed=_require_optional_exact_nonnegative_int(
                raw_record.get("paint_seed"),
                field="paint_seed",
                record_index=record_index,
            ),
            sticker_metadata=sticker_metadata,
            observed_at=observed_at,
        )
    except BuffListingValidationError as exc:
        raise BuffListingParseError(
            field=exc.field,
            record_index=record_index,
            cause=BuffListingParseCause.DOMAIN_VALIDATION,
        ) from None


def _listing_fields(
    schema_version: int,
) -> tuple[frozenset[str], frozenset[str]]:
    if schema_version == BUFF_LISTING_FIXTURE_SCHEMA_VERSION_V1:
        return _LISTING_FIELDS_V1, _REQUIRED_LISTING_FIELDS_V1
    return _LISTING_FIELDS_V2, _REQUIRED_LISTING_FIELDS_V2


def _parse_observed_at(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise _parse_error(field="observed_at")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        raise _parse_error(field="observed_at") from None


def _parse_decimal_string(
    value: object,
    *,
    field: str,
    record_index: int,
) -> Decimal:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _parse_error(field=field, record_index=record_index)
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        raise _parse_error(field=field, record_index=record_index) from None


def _parse_optional_decimal_string(
    value: object,
    *,
    field: str,
    record_index: int,
) -> Decimal | None:
    if value is None:
        return None
    return _parse_decimal_string(
        value,
        field=field,
        record_index=record_index,
    )


def _parse_sticker_metadata(
    value: object,
    *,
    record_index: int,
) -> tuple[tuple[str, str], ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise _parse_error(field="sticker_metadata", record_index=record_index)

    pairs: list[tuple[str, str]] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            raise _parse_error(field="sticker_metadata", record_index=record_index)
        _require_exact_fields(
            entry,
            _STICKER_FIELDS,
            field="sticker_metadata",
            record_index=record_index,
        )
        pairs.append(
            (
                _require_string(
                    entry["key"],
                    field="sticker_metadata",
                    record_index=record_index,
                ),
                _require_string(
                    entry["value"],
                    field="sticker_metadata",
                    record_index=record_index,
                ),
            )
        )
    return tuple(pairs)


def _require_string(value: object, *, field: str, record_index: int) -> str:
    if not isinstance(value, str):
        raise _parse_error(field=field, record_index=record_index)
    return value


def _require_optional_string(
    value: object,
    *,
    field: str,
    record_index: int,
) -> str | None:
    if value is None:
        return None
    return _require_string(value, field=field, record_index=record_index)


def _require_exact_nonnegative_int(
    value: object,
    *,
    field: str,
    record_index: int,
) -> int:
    if type(value) is not int or value < 0:
        raise _parse_error(field=field, record_index=record_index)
    return value


def _require_optional_exact_nonnegative_int(
    value: object,
    *,
    field: str,
    record_index: int,
) -> int | None:
    if value is None:
        return None
    return _require_exact_nonnegative_int(
        value,
        field=field,
        record_index=record_index,
    )


def _require_exact_fields(
    value: Mapping[object, object],
    allowed: frozenset[str],
    *,
    field: str,
    record_index: int | None = None,
    required: frozenset[str] | None = None,
) -> None:
    actual = frozenset(value)
    required_fields = allowed if required is None else required
    if actual <= allowed and required_fields <= actual:
        return
    raise _parse_error(field=field, record_index=record_index)


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError
        result[key] = value
    return result


def _parse_error(
    *,
    field: str,
    record_index: int | None = None,
) -> BuffListingParseError:
    return BuffListingParseError(
        field=field,
        record_index=record_index,
        cause=BuffListingParseCause.FIXTURE_SCHEMA,
    )
