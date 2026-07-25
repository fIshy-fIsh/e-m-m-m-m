from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Protocol, cast

from app.services.buff_listing import BuffTradableCandidate
from app.services.buff_listing_eligibility import (
    BuffListingEligibilityFacts,
    BuffListingEligibilityValidationError,
)

BUFF_LISTING_FACTS_SCHEMA_VERSION = 1
BUFF_LISTING_FACTS_SOURCE = "buff"

_TOP_LEVEL_FIELDS = frozenset({"schema_version", "source", "records"})
_RECORD_FIELDS = frozenset(
    {
        "listing_id",
        "market_hash_name",
        "is_stattrak",
        "is_souvenir",
        "has_special_seed",
    }
)


class BuffListingFactsCause(StrEnum):
    """Stable classifications for safe facts-boundary failures."""

    JSON_DECODE = "json_decode"
    FILE_READ = "file_read"
    FIXTURE_SCHEMA = "fixture_schema"
    DOMAIN_VALIDATION = "domain_validation"
    DUPLICATE_IDENTITY = "duplicate_identity"
    LISTING_ID_COLLISION = "listing_id_collision"


class BuffListingFactsValidationError(ValueError):
    """A listing-facts value violated the safe business contract."""

    def __init__(self, *, field: str, cause: BuffListingFactsCause) -> None:
        super().__init__("invalid BUFF listing facts contract")
        self.field = field
        self.cause = cause


class BuffListingFactsParseError(ValueError):
    """A project-owned facts fixture violated its safe parsing contract."""

    def __init__(
        self,
        *,
        field: str,
        cause: BuffListingFactsCause,
        record_index: int | None = None,
    ) -> None:
        super().__init__("invalid BUFF listing facts fixture")
        self.field = field
        self.cause = cause
        self.record_index = record_index


class _DuplicateJsonKeyError(ValueError):
    pass


class _FactsParseFailure(Exception):
    __slots__ = ("cause", "field", "record_index")

    def __init__(
        self,
        *,
        field: str,
        cause: BuffListingFactsCause,
        record_index: int | None = None,
    ) -> None:
        self.field = field
        self.cause = cause
        self.record_index = record_index


@dataclass(frozen=True, kw_only=True, repr=False)
class BuffListingFactsRecord:
    """Explicit project-owned classification metadata for one listing."""

    listing_id: str
    market_hash_name: str
    is_stattrak: bool
    is_souvenir: bool
    has_special_seed: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "listing_id",
            _canonical_identity(self.listing_id, field="listing_id"),
        )
        object.__setattr__(
            self,
            "market_hash_name",
            _canonical_identity(
                self.market_hash_name,
                field="market_hash_name",
            ),
        )
        _validate_exact_bool(self.is_stattrak, field="is_stattrak")
        _validate_exact_bool(self.is_souvenir, field="is_souvenir")
        _validate_exact_bool(
            self.has_special_seed,
            field="has_special_seed",
        )


class BuffListingFactsLookupStatus(StrEnum):
    """Stable outcomes for one explicit facts lookup."""

    FOUND = "found"
    MISSING = "missing"


@dataclass(frozen=True, kw_only=True, repr=False)
class BuffListingFactsLookupResult:
    """Immutable facts result bound to the normalized queried identity."""

    status: BuffListingFactsLookupStatus
    listing_id: str
    market_hash_name: str
    facts: BuffListingEligibilityFacts | None

    def __post_init__(self) -> None:
        if type(self.status) is not BuffListingFactsLookupStatus:
            raise _validation_error(field="status")
        listing_id = _canonical_identity(self.listing_id, field="listing_id")
        market_hash_name = _canonical_identity(
            self.market_hash_name,
            field="market_hash_name",
        )
        if self.status is BuffListingFactsLookupStatus.FOUND:
            if self.facts is None:
                raise _validation_error(field="facts")
            facts = _copy_facts(self.facts)
        else:
            if self.facts is not None:
                raise _validation_error(field="facts")
            facts = None

        object.__setattr__(self, "listing_id", listing_id)
        object.__setattr__(self, "market_hash_name", market_hash_name)
        object.__setattr__(self, "facts", facts)


class BuffListingFactsProvider(Protocol):
    """Read-only boundary for explicit listing classification facts."""

    async def lookup_facts(
        self,
        candidate: BuffTradableCandidate,
    ) -> BuffListingFactsLookupResult:
        """Look up facts without defining transport or metadata inference."""


class OfflineBuffListingFactsProvider:
    """Deterministic in-memory facts provider built from validated records."""

    def __init__(self, records: Sequence[BuffListingFactsRecord]) -> None:
        if not isinstance(records, Sequence) or isinstance(
            records,
            (str, bytes, bytearray),
        ):
            raise _validation_error(field="records")
        try:
            raw_records = tuple(records)
        except MemoryError:
            raise
        except Exception:
            raise _validation_error(field="records") from None
        try:
            copied_records = tuple(_copy_record(record) for record in raw_records)
        except MemoryError:
            raise
        except Exception:
            raise _validation_error(field="records") from None
        index = _build_provider_index(copied_records)
        self._records_by_listing_id = MappingProxyType(index)

    async def lookup_facts(
        self,
        candidate: BuffTradableCandidate,
    ) -> BuffListingFactsLookupResult:
        listing_id, market_hash_name = _copy_candidate_identity(candidate)
        record = self._records_by_listing_id.get(listing_id)
        if record is None or record.market_hash_name != market_hash_name:
            return BuffListingFactsLookupResult(
                status=BuffListingFactsLookupStatus.MISSING,
                listing_id=listing_id,
                market_hash_name=market_hash_name,
                facts=None,
            )
        return BuffListingFactsLookupResult(
            status=BuffListingFactsLookupStatus.FOUND,
            listing_id=listing_id,
            market_hash_name=market_hash_name,
            facts=_record_facts(record),
        )


def parse_buff_listing_facts_fixture(
    payload: Mapping[str, object],
) -> tuple[BuffListingFactsRecord, ...]:
    """Parse one project-owned facts fixture mapping without performing I/O."""

    try:
        trusted_payload = _snapshot_fixture_payload(payload)
    except MemoryError:
        raise
    except Exception:
        raise BuffListingFactsParseError(
            field="payload",
            cause=BuffListingFactsCause.FIXTURE_SCHEMA,
        ) from None

    try:
        return _parse_fixture(trusted_payload)
    except _FactsParseFailure as exc:
        if type(exc) is not _FactsParseFailure:
            raise BuffListingFactsParseError(
                field="payload",
                cause=BuffListingFactsCause.FIXTURE_SCHEMA,
            ) from None
        raise BuffListingFactsParseError(
            field=exc.field,
            cause=exc.cause,
            record_index=exc.record_index,
        ) from None
    except MemoryError:
        raise
    except Exception:
        raise BuffListingFactsParseError(
            field="payload",
            cause=BuffListingFactsCause.FIXTURE_SCHEMA,
        ) from None


def load_buff_listing_facts_fixture(
    path: Path,
) -> tuple[BuffListingFactsRecord, ...]:
    """Load one UTF-8 JSON facts fixture through the strict mapping parser."""

    if not isinstance(path, Path):
        raise BuffListingFactsParseError(
            field="path",
            cause=BuffListingFactsCause.FILE_READ,
        )
    try:
        serialized = path.read_text(encoding="utf-8")
    except MemoryError:
        raise
    except Exception:
        raise BuffListingFactsParseError(
            field="path",
            cause=BuffListingFactsCause.FILE_READ,
        ) from None

    try:
        payload = json.loads(
            serialized,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except MemoryError:
        raise
    except Exception:
        raise BuffListingFactsParseError(
            field="json",
            cause=BuffListingFactsCause.JSON_DECODE,
        ) from None

    return parse_buff_listing_facts_fixture(payload)


def _snapshot_fixture_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise TypeError
    if frozenset(payload) != _TOP_LEVEL_FIELDS:
        raise ValueError
    schema_version = payload["schema_version"]
    source = payload["source"]
    raw_records = payload["records"]
    if type(raw_records) is not list:
        return {
            "schema_version": schema_version,
            "source": source,
            "records": raw_records,
        }
    records_snapshot = tuple(list.__iter__(raw_records))
    copied_records: list[object] = []
    for raw_record in records_snapshot:
        if not isinstance(raw_record, Mapping):
            copied_records.append(raw_record)
            continue
        copied_records.append(dict(raw_record))
    return {
        "schema_version": schema_version,
        "source": source,
        "records": copied_records,
    }


def _parse_fixture(payload: object) -> tuple[BuffListingFactsRecord, ...]:
    if not isinstance(payload, Mapping):
        raise _parse_error(field="payload")
    _require_exact_fields(payload, _TOP_LEVEL_FIELDS, field="payload")

    schema_version = payload["schema_version"]
    if (
        type(schema_version) is not int
        or schema_version != BUFF_LISTING_FACTS_SCHEMA_VERSION
    ):
        raise _parse_error(field="schema_version")

    source = payload["source"]
    if type(source) is not str or source != BUFF_LISTING_FACTS_SOURCE:
        raise _parse_error(field="source")

    raw_records = payload["records"]
    if type(raw_records) is not list:
        raise _parse_error(field="records")
    raw_records_snapshot = tuple(list.__iter__(raw_records))

    records: list[BuffListingFactsRecord] = []
    seen_pairs: set[tuple[str, str]] = set()
    names_by_listing_id: dict[str, str] = {}
    for record_index, raw_record in enumerate(raw_records_snapshot):
        record = _parse_record(raw_record, record_index=record_index)
        _check_parsed_identity(
            record,
            record_index=record_index,
            seen_pairs=seen_pairs,
            names_by_listing_id=names_by_listing_id,
        )
        records.append(record)
    return tuple(records)


def _parse_record(
    raw_record: object,
    *,
    record_index: int,
) -> BuffListingFactsRecord:
    if not isinstance(raw_record, Mapping):
        raise _parse_error(field="records", record_index=record_index)
    _require_exact_fields(
        raw_record,
        _RECORD_FIELDS,
        field="records",
        record_index=record_index,
    )

    listing_id = _require_string(
        raw_record["listing_id"],
        field="listing_id",
        record_index=record_index,
    )
    market_hash_name = _require_string(
        raw_record["market_hash_name"],
        field="market_hash_name",
        record_index=record_index,
    )
    is_stattrak = _require_exact_bool(
        raw_record["is_stattrak"],
        field="is_stattrak",
        record_index=record_index,
    )
    is_souvenir = _require_exact_bool(
        raw_record["is_souvenir"],
        field="is_souvenir",
        record_index=record_index,
    )
    has_special_seed = _require_exact_bool(
        raw_record["has_special_seed"],
        field="has_special_seed",
        record_index=record_index,
    )

    try:
        return BuffListingFactsRecord(
            listing_id=listing_id,
            market_hash_name=market_hash_name,
            is_stattrak=is_stattrak,
            is_souvenir=is_souvenir,
            has_special_seed=has_special_seed,
        )
    except BuffListingFactsValidationError as exc:
        raise _FactsParseFailure(
            field=exc.field,
            cause=BuffListingFactsCause.DOMAIN_VALIDATION,
            record_index=record_index,
        ) from None


def _check_parsed_identity(
    record: BuffListingFactsRecord,
    *,
    record_index: int,
    seen_pairs: set[tuple[str, str]],
    names_by_listing_id: dict[str, str],
) -> None:
    pair = (record.listing_id, record.market_hash_name)
    if pair in seen_pairs:
        raise _FactsParseFailure(
            field="records",
            cause=BuffListingFactsCause.DUPLICATE_IDENTITY,
            record_index=record_index,
        )
    known_name = names_by_listing_id.get(record.listing_id)
    if known_name is not None and known_name != record.market_hash_name:
        raise _FactsParseFailure(
            field="records",
            cause=BuffListingFactsCause.LISTING_ID_COLLISION,
            record_index=record_index,
        )
    seen_pairs.add(pair)
    names_by_listing_id[record.listing_id] = record.market_hash_name


def _build_provider_index(
    records: tuple[BuffListingFactsRecord, ...],
) -> dict[str, BuffListingFactsRecord]:
    index: dict[str, BuffListingFactsRecord] = {}
    for record in records:
        known = index.get(record.listing_id)
        if known is not None:
            if known.market_hash_name == record.market_hash_name:
                raise _validation_error(
                    field="records",
                    cause=BuffListingFactsCause.DUPLICATE_IDENTITY,
                )
            raise _validation_error(
                field="records",
                cause=BuffListingFactsCause.LISTING_ID_COLLISION,
            )
        index[record.listing_id] = record
    return index


def _copy_record(record: object) -> BuffListingFactsRecord:
    if not isinstance(record, BuffListingFactsRecord):
        raise _validation_error(field="records")
    try:
        return BuffListingFactsRecord(
            listing_id=_stored_string(record, "listing_id", field="records"),
            market_hash_name=_stored_string(
                record,
                "market_hash_name",
                field="records",
            ),
            is_stattrak=_stored_exact_bool(
                record,
                "is_stattrak",
                field="records",
            ),
            is_souvenir=_stored_exact_bool(
                record,
                "is_souvenir",
                field="records",
            ),
            has_special_seed=_stored_exact_bool(
                record,
                "has_special_seed",
                field="records",
            ),
        )
    except BuffListingFactsValidationError:
        raise _validation_error(field="records") from None


def _record_facts(record: BuffListingFactsRecord) -> BuffListingEligibilityFacts:
    return BuffListingEligibilityFacts(
        is_stattrak=record.is_stattrak,
        is_souvenir=record.is_souvenir,
        has_special_seed=record.has_special_seed,
    )


def _copy_facts(facts: object) -> BuffListingEligibilityFacts:
    if not isinstance(facts, BuffListingEligibilityFacts):
        raise _validation_error(field="facts")
    try:
        return BuffListingEligibilityFacts(
            is_stattrak=_stored_exact_bool(
                facts,
                "is_stattrak",
                field="facts",
            ),
            is_souvenir=_stored_exact_bool(
                facts,
                "is_souvenir",
                field="facts",
            ),
            has_special_seed=_stored_exact_bool(
                facts,
                "has_special_seed",
                field="facts",
            ),
        )
    except BuffListingEligibilityValidationError:
        raise _validation_error(field="facts") from None


def _copy_candidate_identity(candidate: object) -> tuple[str, str]:
    if not isinstance(candidate, BuffTradableCandidate):
        raise _validation_error(field="candidate")
    try:
        listing_id = _canonical_identity(
            _stored_string(candidate, "listing_id", field="candidate"),
            field="candidate",
        )
        market_hash_name = _canonical_identity(
            _stored_string(candidate, "market_hash_name", field="candidate"),
            field="candidate",
        )
    except BuffListingFactsValidationError:
        raise _validation_error(field="candidate") from None
    return listing_id, market_hash_name


def _stored_attribute(value: object, name: str, *, field: str) -> object:
    try:
        storage = object.__getattribute__(value, "__dict__")
        return dict.__getitem__(storage, name)
    except (AttributeError, KeyError, TypeError):
        raise _validation_error(field=field) from None


def _stored_string(value: object, name: str, *, field: str) -> str:
    return cast(str, _stored_attribute(value, name, field=field))


def _stored_exact_bool(value: object, name: str, *, field: str) -> bool:
    stored = _stored_attribute(value, name, field=field)
    if type(stored) is not bool:
        raise _validation_error(field=field)
    return cast(bool, stored)


def _canonical_identity(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise _validation_error(field=field)
    try:
        detached = str.__str__(value)
        normalized = detached.strip()
    except Exception:
        raise _validation_error(field=field) from None
    if not normalized:
        raise _validation_error(field=field)
    return normalized


def _validate_exact_bool(value: object, *, field: str) -> None:
    if type(value) is not bool:
        raise _validation_error(field=field)


def _require_string(
    value: object,
    *,
    field: str,
    record_index: int,
) -> str:
    if not isinstance(value, str):
        raise _parse_error(field=field, record_index=record_index)
    return str.__str__(value)


def _require_exact_bool(
    value: object,
    *,
    field: str,
    record_index: int,
) -> bool:
    if type(value) is not bool:
        raise _parse_error(field=field, record_index=record_index)
    return cast(bool, value)


def _require_exact_fields(
    value: Mapping[object, object],
    allowed: frozenset[str],
    *,
    field: str,
    record_index: int | None = None,
) -> None:
    actual = frozenset(value)
    if actual == allowed:
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


def _validation_error(
    *,
    field: str,
    cause: BuffListingFactsCause = BuffListingFactsCause.DOMAIN_VALIDATION,
) -> BuffListingFactsValidationError:
    return BuffListingFactsValidationError(field=field, cause=cause)


def _parse_error(
    *,
    field: str,
    record_index: int | None = None,
) -> _FactsParseFailure:
    return _FactsParseFailure(
        field=field,
        cause=BuffListingFactsCause.FIXTURE_SCHEMA,
        record_index=record_index,
    )
