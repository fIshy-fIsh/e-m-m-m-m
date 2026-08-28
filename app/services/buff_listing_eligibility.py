from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import cast

from app.services.buff_listing import (
    BuffListingValidationError,
    BuffTradableCandidate,
)


class BuffListingEligibilityValidationError(ValueError):
    """An eligibility value violated the safe business contract."""

    def __init__(self, *, field: str) -> None:
        super().__init__("invalid BUFF listing eligibility contract")
        self.field = field


@dataclass(frozen=True, kw_only=True, repr=False)
class BuffListingEligibilityFacts:
    """Explicit caller-supplied classification facts for one listing."""

    is_stattrak: bool
    is_souvenir: bool
    has_special_seed: bool

    def __post_init__(self) -> None:
        _validate_exact_bool(self.is_stattrak, field="is_stattrak")
        _validate_exact_bool(self.is_souvenir, field="is_souvenir")
        _validate_exact_bool(self.has_special_seed, field="has_special_seed")


@dataclass(frozen=True, kw_only=True, repr=False)
class BuffListingEligibilityPolicy:
    """Explicit controls for deciding whether a listing may reach a solver."""

    min_available_quantity: int = 1
    require_positive_price: bool = True
    require_float_value: bool = True
    allow_stattrak: bool = False
    allow_souvenir: bool = False
    allow_special_seed: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.min_available_quantity) is not int
            or self.min_available_quantity <= 0
        ):
            raise BuffListingEligibilityValidationError(
                field="min_available_quantity"
            )
        _validate_exact_bool(
            self.require_positive_price,
            field="require_positive_price",
        )
        _validate_exact_bool(
            self.require_float_value,
            field="require_float_value",
        )
        _validate_exact_bool(self.allow_stattrak, field="allow_stattrak")
        _validate_exact_bool(self.allow_souvenir, field="allow_souvenir")
        _validate_exact_bool(
            self.allow_special_seed,
            field="allow_special_seed",
        )


class BuffListingIneligibilityReason(StrEnum):
    """Stable reasons that a format-valid listing cannot enter a solver."""

    INSUFFICIENT_QUANTITY = "insufficient_quantity"
    NON_POSITIVE_PRICE = "non_positive_price"
    MISSING_FLOAT = "missing_float"
    STATTRAK_DISALLOWED = "stattrak_disallowed"
    SOUVENIR_DISALLOWED = "souvenir_disallowed"
    SPECIAL_SEED_DISALLOWED = "special_seed_disallowed"


@dataclass(frozen=True, kw_only=True, repr=False)
class BuffListingEligibilityDecision:
    """Immutable, self-validating eligibility result for one listing."""

    candidate: BuffTradableCandidate
    facts: BuffListingEligibilityFacts
    policy: BuffListingEligibilityPolicy
    reasons: tuple[BuffListingIneligibilityReason, ...]

    def __post_init__(self) -> None:
        candidate = _copy_candidate(self.candidate)
        facts = _copy_facts(self.facts)
        policy = _copy_policy(self.policy)
        reasons = _copy_reasons(self.reasons)
        expected_reasons = _collect_ineligibility_reasons(
            candidate,
            facts,
            policy,
        )
        if reasons != expected_reasons:
            raise BuffListingEligibilityValidationError(field="reasons")

        object.__setattr__(self, "candidate", candidate)
        object.__setattr__(self, "facts", facts)
        object.__setattr__(self, "policy", policy)
        object.__setattr__(self, "reasons", reasons)

    @property
    def is_eligible(self) -> bool:
        """Return whether no ineligibility reason applies."""

        return not self.reasons


def evaluate_buff_listing_eligibility(
    candidate: BuffTradableCandidate,
    facts: BuffListingEligibilityFacts,
    policy: BuffListingEligibilityPolicy,
) -> BuffListingEligibilityDecision:
    """Evaluate every listing rule in stable order without external work."""

    validated_candidate = _copy_candidate(candidate)
    validated_facts = _copy_facts(facts)
    validated_policy = _copy_policy(policy)
    reasons = _collect_ineligibility_reasons(
        validated_candidate,
        validated_facts,
        validated_policy,
    )
    return BuffListingEligibilityDecision(
        candidate=validated_candidate,
        facts=validated_facts,
        policy=validated_policy,
        reasons=reasons,
    )


def _collect_ineligibility_reasons(
    candidate: BuffTradableCandidate,
    facts: BuffListingEligibilityFacts,
    policy: BuffListingEligibilityPolicy,
) -> tuple[BuffListingIneligibilityReason, ...]:
    reasons: list[BuffListingIneligibilityReason] = []

    if candidate.available_quantity < policy.min_available_quantity:
        reasons.append(BuffListingIneligibilityReason.INSUFFICIENT_QUANTITY)
    if policy.require_positive_price and not _has_positive_price(candidate):
        reasons.append(BuffListingIneligibilityReason.NON_POSITIVE_PRICE)
    if policy.require_float_value and candidate.float_value is None:
        reasons.append(BuffListingIneligibilityReason.MISSING_FLOAT)
    if facts.is_stattrak and not policy.allow_stattrak:
        reasons.append(BuffListingIneligibilityReason.STATTRAK_DISALLOWED)
    if facts.is_souvenir and not policy.allow_souvenir:
        reasons.append(BuffListingIneligibilityReason.SOUVENIR_DISALLOWED)
    if facts.has_special_seed and not policy.allow_special_seed:
        reasons.append(BuffListingIneligibilityReason.SPECIAL_SEED_DISALLOWED)

    return tuple(reasons)


def _has_positive_price(candidate: BuffTradableCandidate) -> bool:
    return candidate.buy_price_cny > 0


def _copy_candidate(candidate: object) -> BuffTradableCandidate:
    if not isinstance(candidate, BuffTradableCandidate):
        raise BuffListingEligibilityValidationError(field="candidate")
    try:
        return BuffTradableCandidate(
            listing_id=_copy_string(
                _stored_attribute(candidate, "listing_id", field="candidate")
            ),
            goods_id=_copy_optional_string(
                _stored_attribute(candidate, "goods_id", field="candidate")
            ),
            market_hash_name=_copy_string(
                _stored_attribute(candidate, "market_hash_name", field="candidate")
            ),
            buy_price_cny=_copy_decimal(
                _stored_attribute(candidate, "buy_price_cny", field="candidate")
            ),
            available_quantity=_stored_exact_int(
                candidate,
                "available_quantity",
                field="candidate",
            ),
            float_value=_copy_optional_decimal(
                _stored_attribute(candidate, "float_value", field="candidate")
            ),
            wear_name=_copy_optional_string(
                _stored_attribute(candidate, "wear_name", field="candidate")
            ),
            paint_seed=_stored_optional_exact_int(
                candidate,
                "paint_seed",
                field="candidate",
            ),
            observed_at=_copy_datetime(
                _stored_attribute(candidate, "observed_at", field="candidate")
            ),
        )
    except BuffListingEligibilityValidationError:
        raise
    except BuffListingValidationError:
        raise BuffListingEligibilityValidationError(field="candidate") from None


def _stored_attribute(value: object, name: str, *, field: str) -> object:
    try:
        storage = object.__getattribute__(value, "__dict__")
        return dict.__getitem__(storage, name)
    except (AttributeError, KeyError, TypeError):
        raise BuffListingEligibilityValidationError(field=field) from None


def _stored_exact_int(value: object, name: str, *, field: str) -> int:
    return cast(int, _stored_attribute(value, name, field=field))


def _stored_optional_exact_int(
    value: object,
    name: str,
    *,
    field: str,
) -> int | None:
    return cast(int | None, _stored_attribute(value, name, field=field))


def _stored_exact_bool(value: object, name: str, *, field: str) -> bool:
    return cast(bool, _stored_attribute(value, name, field=field))


def _copy_string(value: object) -> str:
    if not isinstance(value, str):
        raise BuffListingEligibilityValidationError(field="candidate")
    return str.__str__(value)


def _copy_optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _copy_string(value)


def _copy_decimal(value: object) -> Decimal:
    if not isinstance(value, Decimal):
        raise BuffListingEligibilityValidationError(field="candidate")
    try:
        return Decimal(value)
    except (ArithmeticError, RuntimeError, TypeError, ValueError):
        raise BuffListingEligibilityValidationError(field="candidate") from None


def _copy_optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return _copy_decimal(value)


def _copy_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise BuffListingEligibilityValidationError(field="candidate")
    if datetime.tzinfo.__get__(value) is not UTC:
        raise BuffListingEligibilityValidationError(field="candidate")
    return datetime(
        datetime.year.__get__(value),
        datetime.month.__get__(value),
        datetime.day.__get__(value),
        datetime.hour.__get__(value),
        datetime.minute.__get__(value),
        datetime.second.__get__(value),
        datetime.microsecond.__get__(value),
        tzinfo=UTC,
        fold=datetime.fold.__get__(value),
    )


def _copy_facts(facts: object) -> BuffListingEligibilityFacts:
    if not isinstance(facts, BuffListingEligibilityFacts):
        raise BuffListingEligibilityValidationError(field="facts")
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
        raise BuffListingEligibilityValidationError(field="facts") from None


def _copy_policy(policy: object) -> BuffListingEligibilityPolicy:
    if not isinstance(policy, BuffListingEligibilityPolicy):
        raise BuffListingEligibilityValidationError(field="policy")
    try:
        return BuffListingEligibilityPolicy(
            min_available_quantity=_stored_exact_int(
                policy,
                "min_available_quantity",
                field="policy",
            ),
            require_positive_price=_stored_exact_bool(
                policy,
                "require_positive_price",
                field="policy",
            ),
            require_float_value=_stored_exact_bool(
                policy,
                "require_float_value",
                field="policy",
            ),
            allow_stattrak=_stored_exact_bool(
                policy,
                "allow_stattrak",
                field="policy",
            ),
            allow_souvenir=_stored_exact_bool(
                policy,
                "allow_souvenir",
                field="policy",
            ),
            allow_special_seed=_stored_exact_bool(
                policy,
                "allow_special_seed",
                field="policy",
            ),
        )
    except BuffListingEligibilityValidationError:
        raise BuffListingEligibilityValidationError(field="policy") from None


def _copy_reasons(value: object) -> tuple[BuffListingIneligibilityReason, ...]:
    if type(value) is not tuple:
        raise BuffListingEligibilityValidationError(field="reasons")
    reasons = tuple(tuple.__iter__(value))
    if any(type(reason) is not BuffListingIneligibilityReason for reason in reasons):
        raise BuffListingEligibilityValidationError(field="reasons")
    if len(set(reasons)) != len(reasons):
        raise BuffListingEligibilityValidationError(field="reasons")
    return reasons


def _validate_exact_bool(value: object, *, field: str) -> None:
    if type(value) is not bool:
        raise BuffListingEligibilityValidationError(field=field)
