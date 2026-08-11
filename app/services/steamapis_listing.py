from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

_TARGET_MARKETPLACE = "Buff163"
_TARGET_GAME = "CS2"
_FIXED_ERROR_MESSAGE = "invalid SteamApis market message"
_IGNORE_REASONS = frozenset(
    {
        "missing_price_cny",
        "missing_float",
        "other_marketplace",
        "other_game",
    }
)
_REASON_CODES = frozenset(
    {
        "invalid_json",
        "invalid_envelope",
        "invalid_offer",
        "invalid_timestamp",
        "invalid_price",
        "invalid_float",
        "invalid_sticker",
        "unsupported_event",
    }
)
_OFFER_ENVELOPE_FIELDS = frozenset(
    {"type", "eventType", "marketplace", "game", "timestamp", "data"}
)
_OFFER_DATA_FIELDS = frozenset(
    {
        "name",
        "purchaseLink",
        "priceUSD",
        "priceEUR",
        "priceCNY",
        "priceRUB",
        "daysTradeLocked",
        "foundAt",
        "inspectLink",
        "float",
        "paintIndex",
        "paintSeed",
        "stickers",
    }
)
_STICKER_FIELDS = frozenset({"name", "wear", "slot"})


class SteamApisListingEventType(StrEnum):
    """Documented SteamApis offer event types supported by this boundary."""

    ADDED = "Added"
    UPDATED = "Updated"


class SteamApisMessageKind(StrEnum):
    """Stable project outcomes for one SteamApis market message."""

    SUBSCRIBED = "subscribed"
    OFFER = "offer"
    IGNORED = "ignored"
    ERROR = "error"


class SteamApisListingParseError(ValueError):
    """A SteamApis market message violated the safe parsing contract."""

    def __init__(self, *, reason_code: str) -> None:
        super().__init__(_FIXED_ERROR_MESSAGE)
        if type(reason_code) is not str or reason_code not in _REASON_CODES:
            raise ValueError(_FIXED_ERROR_MESSAGE)
        self.reason_code = reason_code


class _SteamApisParseFailure(Exception):
    __slots__ = ("reason_code",)

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code


class _DuplicateJsonKeyError(ValueError):
    pass


@dataclass(frozen=True, kw_only=True, repr=False)
class SteamApisSticker:
    """Retained CS2 sticker fields from one SteamApis offer."""

    name: str
    wear: Decimal
    slot: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _domain_string(self.name, "invalid_sticker"))
        _domain_decimal(self.wear, reason_code="invalid_sticker", minimum=Decimal("0"))
        if self.wear > 1:
            raise _public_error("invalid_sticker")
        _domain_nonnegative_int(self.slot, reason_code="invalid_sticker")


@dataclass(frozen=True, kw_only=True, repr=False)
class SteamApisListingObservation:
    """Immutable target-market offer observation without provider raw data."""

    source_offer_id: str
    event_type: SteamApisListingEventType
    marketplace: str
    game: str
    market_hash_name: str
    purchase_link: str
    inspect_link: str | None
    price_cny: Decimal
    float_value: Decimal
    paint_index: int | None
    paint_seed: int | None
    days_trade_locked: int | None
    found_at: datetime
    message_timestamp: datetime
    stickers: tuple[SteamApisSticker, ...]

    def __post_init__(self) -> None:
        source_offer_id = _domain_source_offer_id(self.source_offer_id)
        if type(self.event_type) is not SteamApisListingEventType:
            raise _public_error("unsupported_event")
        marketplace = _domain_string(self.marketplace, "invalid_offer")
        game = _domain_string(self.game, "invalid_offer")
        if marketplace != _TARGET_MARKETPLACE or game != _TARGET_GAME:
            raise _public_error("invalid_offer")
        market_hash_name = _domain_string(self.market_hash_name, "invalid_offer")
        purchase_link = _domain_string(self.purchase_link, "invalid_offer")
        inspect_link = _domain_optional_string(self.inspect_link, "invalid_offer")
        _domain_decimal(
            self.price_cny,
            reason_code="invalid_price",
            minimum=Decimal("0"),
            minimum_inclusive=False,
        )
        _domain_decimal(
            self.float_value,
            reason_code="invalid_float",
            minimum=Decimal("0"),
        )
        if self.float_value > 1:
            raise _public_error("invalid_float")
        _domain_optional_nonnegative_int(self.paint_index, reason_code="invalid_offer")
        _domain_optional_nonnegative_int(self.paint_seed, reason_code="invalid_offer")
        _domain_optional_nonnegative_int(
            self.days_trade_locked,
            reason_code="invalid_offer",
        )
        found_at = _domain_utc_datetime(self.found_at)
        message_timestamp = _domain_utc_datetime(self.message_timestamp)
        stickers = _copy_sticker_tuple(self.stickers)
        expected_source_offer_id = make_steamapis_source_offer_id(
            marketplace,
            game,
            purchase_link,
        )
        if source_offer_id != expected_source_offer_id:
            raise _public_error("invalid_offer")

        object.__setattr__(self, "source_offer_id", source_offer_id)
        object.__setattr__(self, "marketplace", marketplace)
        object.__setattr__(self, "game", game)
        object.__setattr__(self, "market_hash_name", market_hash_name)
        object.__setattr__(self, "purchase_link", purchase_link)
        object.__setattr__(self, "inspect_link", inspect_link)
        object.__setattr__(self, "found_at", found_at)
        object.__setattr__(self, "message_timestamp", message_timestamp)
        object.__setattr__(self, "stickers", stickers)


@dataclass(frozen=True, kw_only=True, repr=False)
class SteamApisParsedMessage:
    """One validated SteamApis protocol or business outcome."""

    kind: SteamApisMessageKind
    offer: SteamApisListingObservation | None = None
    ignore_reason: str | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not SteamApisMessageKind:
            raise _public_error("invalid_envelope")

        offer: SteamApisListingObservation | None
        ignore_reason: str | None
        if self.kind is SteamApisMessageKind.OFFER:
            if type(self.offer) is not SteamApisListingObservation:
                raise _public_error("invalid_offer")
            if self.ignore_reason is not None:
                raise _public_error("invalid_envelope")
            offer = _copy_observation(self.offer)
            ignore_reason = None
        elif self.kind is SteamApisMessageKind.IGNORED:
            if self.offer is not None:
                raise _public_error("invalid_envelope")
            if (
                type(self.ignore_reason) is not str
                or self.ignore_reason not in _IGNORE_REASONS
            ):
                raise _public_error("invalid_envelope")
            offer = None
            ignore_reason = str.__str__(self.ignore_reason)
        else:
            if self.offer is not None or self.ignore_reason is not None:
                raise _public_error("invalid_envelope")
            offer = None
            ignore_reason = None

        object.__setattr__(self, "offer", offer)
        object.__setattr__(self, "ignore_reason", ignore_reason)


def make_steamapis_source_offer_id(
    marketplace: str,
    game: str,
    purchase_link: str,
) -> str:
    """Build a project-owned source-local ID without parsing the purchase link."""

    canonical_marketplace = _domain_string(marketplace, "invalid_offer")
    canonical_game = _domain_string(game, "invalid_offer")
    canonical_purchase_link = _domain_string(purchase_link, "invalid_offer")
    preimage = (
        f"{canonical_marketplace}\x00{canonical_game}\x00{canonical_purchase_link}"
    )
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def parse_steamapis_message(payload: str) -> SteamApisParsedMessage:
    """Parse one documented SteamApis WebSocket JSON message without I/O."""

    if type(payload) is not str:
        raise _public_error("invalid_json")

    try:
        decoded = json.loads(
            payload,
            parse_float=Decimal,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except MemoryError:
        raise
    except Exception:
        raise _public_error("invalid_json") from None

    try:
        return _parse_message_object(decoded)
    except _SteamApisParseFailure as exc:
        raise _public_error(exc.reason_code) from None
    except SteamApisListingParseError:
        raise
    except MemoryError:
        raise
    except Exception:
        raise _public_error("invalid_envelope") from None


def _parse_message_object(decoded: object) -> SteamApisParsedMessage:
    if type(decoded) is not dict:
        raise _failure("invalid_envelope")
    message_type = _require_string_value(decoded.get("type"), "invalid_envelope")

    if message_type == SteamApisMessageKind.SUBSCRIBED.value:
        return SteamApisParsedMessage(kind=SteamApisMessageKind.SUBSCRIBED)
    if message_type == SteamApisMessageKind.ERROR.value:
        return SteamApisParsedMessage(kind=SteamApisMessageKind.ERROR)
    if message_type != SteamApisMessageKind.OFFER.value:
        raise _failure("invalid_envelope")
    return _parse_offer_message(decoded)


def _parse_offer_message(payload: dict[str, object]) -> SteamApisParsedMessage:
    _require_fields(payload, _OFFER_ENVELOPE_FIELDS, "invalid_envelope")
    event_type = _parse_event_type(payload["eventType"])
    marketplace = _require_string_value(payload["marketplace"], "invalid_envelope")
    game = _require_string_value(payload["game"], "invalid_envelope")
    data = payload["data"]
    if type(data) is not dict:
        raise _failure("invalid_offer")

    if marketplace != _TARGET_MARKETPLACE:
        return _ignored("other_marketplace")
    if game != _TARGET_GAME:
        return _ignored("other_game")

    _require_fields(data, _OFFER_DATA_FIELDS - {"priceCNY", "float"}, "invalid_offer")
    if "priceCNY" not in data or data["priceCNY"] is None:
        return _ignored("missing_price_cny")
    if "float" not in data or data["float"] is None:
        return _ignored("missing_float")

    _validate_discarded_prices(data)
    market_hash_name = _require_string_value(data["name"], "invalid_offer")
    purchase_link = _require_string_value(data["purchaseLink"], "invalid_offer")
    inspect_link = _optional_string_value(data["inspectLink"], "invalid_offer")
    price_cny = _require_decimal_value(
        data["priceCNY"],
        reason_code="invalid_price",
        minimum=Decimal("0"),
        minimum_inclusive=False,
    )
    float_value = _require_decimal_value(
        data["float"],
        reason_code="invalid_float",
        minimum=Decimal("0"),
        maximum=Decimal("1"),
    )
    paint_index = _optional_nonnegative_int_value(data["paintIndex"], "invalid_offer")
    paint_seed = _optional_nonnegative_int_value(data["paintSeed"], "invalid_offer")
    days_trade_locked = _optional_nonnegative_int_value(
        data["daysTradeLocked"],
        "invalid_offer",
    )
    found_at = _timestamp_value(data["foundAt"], milliseconds=False)
    message_timestamp = _timestamp_value(payload["timestamp"], milliseconds=True)
    stickers = _parse_stickers(data["stickers"])
    source_offer_id = make_steamapis_source_offer_id(
        _TARGET_MARKETPLACE,
        _TARGET_GAME,
        purchase_link,
    )

    offer = SteamApisListingObservation(
        source_offer_id=source_offer_id,
        event_type=event_type,
        marketplace=_TARGET_MARKETPLACE,
        game=_TARGET_GAME,
        market_hash_name=market_hash_name,
        purchase_link=purchase_link,
        inspect_link=inspect_link,
        price_cny=price_cny,
        float_value=float_value,
        paint_index=paint_index,
        paint_seed=paint_seed,
        days_trade_locked=days_trade_locked,
        found_at=found_at,
        message_timestamp=message_timestamp,
        stickers=stickers,
    )
    return SteamApisParsedMessage(kind=SteamApisMessageKind.OFFER, offer=offer)


def _validate_discarded_prices(data: dict[str, object]) -> None:
    _require_decimal_value(
        data["priceUSD"],
        reason_code="invalid_offer",
        minimum=Decimal("0"),
        minimum_inclusive=False,
    )
    for field in ("priceEUR", "priceRUB"):
        value = data[field]
        if value is None:
            continue
        _require_decimal_value(
            value,
            reason_code="invalid_offer",
            minimum=Decimal("0"),
            minimum_inclusive=False,
        )


def _parse_event_type(value: object) -> SteamApisListingEventType:
    if type(value) is not str:
        raise _failure("unsupported_event")
    try:
        return SteamApisListingEventType(value)
    except ValueError:
        raise _failure("unsupported_event") from None


def _parse_stickers(value: object) -> tuple[SteamApisSticker, ...]:
    if value is None:
        return ()
    if type(value) is not list:
        raise _failure("invalid_sticker")

    stickers: list[SteamApisSticker] = []
    for raw_sticker in tuple(list.__iter__(value)):
        if type(raw_sticker) is not dict:
            raise _failure("invalid_sticker")
        _require_fields(raw_sticker, _STICKER_FIELDS, "invalid_sticker")
        name = _require_string_value(raw_sticker["name"], "invalid_sticker")
        wear = _require_decimal_value(
            raw_sticker["wear"],
            reason_code="invalid_sticker",
            minimum=Decimal("0"),
            maximum=Decimal("1"),
        )
        slot = _require_nonnegative_int_value(raw_sticker["slot"], "invalid_sticker")
        stickers.append(SteamApisSticker(name=name, wear=wear, slot=slot))
    return tuple(stickers)


def _ignored(reason: str) -> SteamApisParsedMessage:
    return SteamApisParsedMessage(
        kind=SteamApisMessageKind.IGNORED,
        ignore_reason=reason,
    )


def _require_fields(
    payload: dict[str, object],
    required_fields: frozenset[str],
    reason_code: str,
) -> None:
    if not required_fields.issubset(payload):
        raise _failure(reason_code)


def _require_string_value(value: object, reason_code: str) -> str:
    if type(value) is not str:
        raise _failure(reason_code)
    canonical = str.strip(str.__str__(value))
    if not canonical:
        raise _failure(reason_code)
    return canonical


def _optional_string_value(value: object, reason_code: str) -> str | None:
    if value is None:
        return None
    return _require_string_value(value, reason_code)


def _require_decimal_value(
    value: object,
    *,
    reason_code: str,
    minimum: Decimal,
    maximum: Decimal | None = None,
    minimum_inclusive: bool = True,
) -> Decimal:
    if type(value) is int:
        decimal_value = Decimal(value)
    elif type(value) is Decimal:
        decimal_value = value
    else:
        raise _failure(reason_code)
    if not decimal_value.is_finite():
        raise _failure(reason_code)
    if minimum_inclusive:
        if decimal_value < minimum:
            raise _failure(reason_code)
    elif decimal_value <= minimum:
        raise _failure(reason_code)
    if maximum is not None and decimal_value > maximum:
        raise _failure(reason_code)
    return decimal_value


def _require_nonnegative_int_value(value: object, reason_code: str) -> int:
    if type(value) is not int or value < 0:
        raise _failure(reason_code)
    return value


def _optional_nonnegative_int_value(value: object, reason_code: str) -> int | None:
    if value is None:
        return None
    return _require_nonnegative_int_value(value, reason_code)


def _timestamp_value(value: object, *, milliseconds: bool) -> datetime:
    if type(value) is int:
        numeric_value = Decimal(value)
    elif type(value) is Decimal:
        numeric_value = value
    else:
        raise _failure("invalid_timestamp")
    if not numeric_value.is_finite() or numeric_value < 0:
        raise _failure("invalid_timestamp")
    seconds = numeric_value / Decimal(1000) if milliseconds else numeric_value
    try:
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        whole_seconds = int(seconds)
        microseconds = int((seconds - Decimal(whole_seconds)) * Decimal(1_000_000))
        return epoch + timedelta(seconds=whole_seconds, microseconds=microseconds)
    except (OverflowError, OSError, TypeError, ValueError):
        raise _failure("invalid_timestamp") from None


def _reject_duplicate_json_keys(
    pairs: Sequence[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> object:
    raise ValueError


def _copy_sticker_tuple(value: object) -> tuple[SteamApisSticker, ...]:
    if type(value) is not tuple:
        raise _public_error("invalid_sticker")
    copied: list[SteamApisSticker] = []
    for sticker in value:
        if type(sticker) is not SteamApisSticker:
            raise _public_error("invalid_sticker")
        copied.append(
            SteamApisSticker(
                name=sticker.name,
                wear=sticker.wear,
                slot=sticker.slot,
            )
        )
    return tuple(copied)


def _copy_observation(value: SteamApisListingObservation) -> SteamApisListingObservation:
    return SteamApisListingObservation(
        source_offer_id=value.source_offer_id,
        event_type=value.event_type,
        marketplace=value.marketplace,
        game=value.game,
        market_hash_name=value.market_hash_name,
        purchase_link=value.purchase_link,
        inspect_link=value.inspect_link,
        price_cny=value.price_cny,
        float_value=value.float_value,
        paint_index=value.paint_index,
        paint_seed=value.paint_seed,
        days_trade_locked=value.days_trade_locked,
        found_at=value.found_at,
        message_timestamp=value.message_timestamp,
        stickers=value.stickers,
    )


def _domain_string(value: object, reason_code: str) -> str:
    if type(value) is not str:
        raise _public_error(reason_code)
    canonical = str.strip(str.__str__(value))
    if not canonical:
        raise _public_error(reason_code)
    return canonical


def _domain_optional_string(value: object, reason_code: str) -> str | None:
    if value is None:
        return None
    return _domain_string(value, reason_code)


def _domain_decimal(
    value: object,
    *,
    reason_code: str,
    minimum: Decimal,
    minimum_inclusive: bool = True,
) -> None:
    if type(value) is not Decimal or not value.is_finite():
        raise _public_error(reason_code)
    if minimum_inclusive:
        if value < minimum:
            raise _public_error(reason_code)
    elif value <= minimum:
        raise _public_error(reason_code)


def _domain_nonnegative_int(value: object, *, reason_code: str) -> None:
    if type(value) is not int or value < 0:
        raise _public_error(reason_code)


def _domain_optional_nonnegative_int(value: object, *, reason_code: str) -> None:
    if value is not None:
        _domain_nonnegative_int(value, reason_code=reason_code)


def _domain_utc_datetime(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise _public_error("invalid_timestamp")
    return value.astimezone(UTC)


def _domain_source_offer_id(value: object) -> str:
    if type(value) is not str:
        raise _public_error("invalid_offer")
    source_offer_id = str.__str__(value)
    if len(source_offer_id) != 64 or any(
        character not in "0123456789abcdef" for character in source_offer_id
    ):
        raise _public_error("invalid_offer")
    return source_offer_id


def _failure(reason_code: str) -> _SteamApisParseFailure:
    return _SteamApisParseFailure(reason_code)


def _public_error(reason_code: str) -> SteamApisListingParseError:
    return SteamApisListingParseError(reason_code=reason_code)
