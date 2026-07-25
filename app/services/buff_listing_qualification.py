from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import cast

from app.services.buff_listing import BuffTradableCandidate
from app.services.buff_listing_eligibility import (
    BuffListingEligibilityDecision,
    BuffListingEligibilityFacts,
    BuffListingEligibilityPolicy,
    evaluate_buff_listing_eligibility,
)
from app.services.buff_listing_facts import (
    BuffListingFactsLookupResult,
    BuffListingFactsLookupStatus,
    BuffListingFactsProvider,
)

_Evaluator = Callable[
    [
        BuffTradableCandidate,
        BuffListingEligibilityFacts,
        BuffListingEligibilityPolicy,
    ],
    BuffListingEligibilityDecision,
]


class BuffListingQualificationStatus(StrEnum):
    """Stable outcome of one listing qualification attempt."""

    QUALIFIED = "qualified"
    REJECTED = "rejected"
    MISSING_FACTS = "missing_facts"


class BuffListingQualificationValidationError(ValueError):
    """A qualification value violated the safe orchestration contract."""

    def __init__(self, *, field: str) -> None:
        super().__init__("invalid BUFF listing qualification contract")
        self.field = field


@dataclass(frozen=True, kw_only=True, repr=False)
class BuffListingQualificationResult:
    """Immutable qualification state assembled from existing contracts."""

    candidate: BuffTradableCandidate
    policy: BuffListingEligibilityPolicy
    lookup_result: BuffListingFactsLookupResult
    decision: BuffListingEligibilityDecision | None

    def __post_init__(self) -> None:
        candidate = _copy_candidate(self.candidate)
        policy = _copy_policy(self.policy)
        lookup_result = _copy_lookup_result(self.lookup_result)
        _validate_lookup_identity(candidate, lookup_result)

        if lookup_result.status is BuffListingFactsLookupStatus.MISSING:
            if self.decision is not None:
                raise _validation_error(field="decision")
            decision = None
        else:
            if self.decision is None:
                raise _validation_error(field="decision")
            decision = _copy_decision(self.decision)
            _validate_decision(
                decision,
                candidate=candidate,
                facts=cast(BuffListingEligibilityFacts, lookup_result.facts),
                policy=policy,
            )

        object.__setattr__(self, "candidate", candidate)
        object.__setattr__(self, "policy", policy)
        object.__setattr__(self, "lookup_result", lookup_result)
        object.__setattr__(self, "decision", decision)

    @property
    def status(self) -> BuffListingQualificationStatus:
        """Derive the three-way outcome from validated immutable state."""

        if self.decision is None:
            return BuffListingQualificationStatus.MISSING_FACTS
        if self.decision.is_eligible:
            return BuffListingQualificationStatus.QUALIFIED
        return BuffListingQualificationStatus.REJECTED


class BuffListingQualificationService:
    """Compose one explicit facts lookup with the existing evaluator."""

    def __init__(
        self,
        provider: BuffListingFactsProvider,
        *,
        evaluator: _Evaluator | None = None,
    ) -> None:
        _validate_provider_capability(provider)
        selected_evaluator = (
            evaluate_buff_listing_eligibility if evaluator is None else evaluator
        )
        if not callable(selected_evaluator) or not _has_static_call_capability(
            selected_evaluator
        ):
            raise _validation_error(field="evaluator")
        self._provider = provider
        self._evaluator = selected_evaluator

    async def qualify(
        self,
        candidate: BuffTradableCandidate,
        policy: BuffListingEligibilityPolicy,
    ) -> BuffListingQualificationResult:
        """Qualify one candidate without retry, fallback, or external wiring."""

        authoritative_candidate = _copy_candidate(candidate)
        authoritative_policy = _copy_policy(policy)

        provider_candidate = _copy_candidate(authoritative_candidate)
        raw_lookup_result = await self._provider.lookup_facts(provider_candidate)

        lookup_result = _copy_lookup_result(raw_lookup_result)
        _validate_lookup_identity(authoritative_candidate, lookup_result)
        if lookup_result.status is BuffListingFactsLookupStatus.MISSING:
            return BuffListingQualificationResult(
                candidate=authoritative_candidate,
                policy=authoritative_policy,
                lookup_result=lookup_result,
                decision=None,
            )

        evaluator_candidate = _copy_candidate(authoritative_candidate)
        evaluator_facts = _copy_facts(
            cast(BuffListingEligibilityFacts, lookup_result.facts)
        )
        evaluator_policy = _copy_policy(authoritative_policy)
        raw_decision = self._evaluator(
            evaluator_candidate,
            evaluator_facts,
            evaluator_policy,
        )

        decision = _copy_decision(raw_decision)
        _validate_decision(
            decision,
            candidate=authoritative_candidate,
            facts=cast(BuffListingEligibilityFacts, lookup_result.facts),
            policy=authoritative_policy,
        )
        return BuffListingQualificationResult(
            candidate=authoritative_candidate,
            policy=authoritative_policy,
            lookup_result=lookup_result,
            decision=decision,
        )


def _validate_provider_capability(provider: object) -> None:
    try:
        capability = inspect.getattr_static(provider, "lookup_facts")
    except AttributeError:
        raise _validation_error(field="provider") from None
    if type(capability) in (staticmethod, classmethod):
        capability = capability.__func__
    if not _is_static_callable(capability):
        raise _validation_error(field="provider")


def _has_static_call_capability(value: object) -> bool:
    if inspect.isfunction(value):
        return True
    try:
        capability = inspect.getattr_static(type(value), "__call__")
    except AttributeError:
        return False
    if type(capability) in (staticmethod, classmethod):
        capability = capability.__func__
    return _is_static_callable(capability)


def _is_static_callable(value: object) -> bool:
    return inspect.isfunction(value)


def _copy_candidate(candidate: object) -> BuffTradableCandidate:
    if type(candidate) is not BuffTradableCandidate:
        raise _validation_error(field="candidate")
    try:
        return BuffTradableCandidate(
            listing_id=_copy_string(
                _stored_attribute(candidate, "listing_id", field="candidate"),
                field="candidate",
            ),
            market_hash_name=_copy_string(
                _stored_attribute(candidate, "market_hash_name", field="candidate"),
                field="candidate",
            ),
            buy_price_cny=_copy_decimal(
                _stored_attribute(candidate, "buy_price_cny", field="candidate"),
                field="candidate",
            ),
            available_quantity=cast(
                int,
                _stored_attribute(
                    candidate,
                    "available_quantity",
                    field="candidate",
                ),
            ),
            float_value=_copy_optional_decimal(
                _stored_attribute(candidate, "float_value", field="candidate"),
                field="candidate",
            ),
            wear_name=_copy_optional_string(
                _stored_attribute(candidate, "wear_name", field="candidate"),
                field="candidate",
            ),
            paint_seed=cast(
                int | None,
                _stored_attribute(candidate, "paint_seed", field="candidate"),
            ),
            observed_at=_copy_datetime(
                _stored_attribute(candidate, "observed_at", field="candidate"),
                field="candidate",
            ),
        )
    except MemoryError:
        raise
    except Exception:
        raise _validation_error(field="candidate") from None


def _copy_policy(policy: object) -> BuffListingEligibilityPolicy:
    if type(policy) is not BuffListingEligibilityPolicy:
        raise _validation_error(field="policy")
    try:
        return BuffListingEligibilityPolicy(
            min_available_quantity=cast(
                int,
                _stored_attribute(
                    policy,
                    "min_available_quantity",
                    field="policy",
                ),
            ),
            require_positive_price=cast(
                bool,
                _stored_attribute(
                    policy,
                    "require_positive_price",
                    field="policy",
                ),
            ),
            require_float_value=cast(
                bool,
                _stored_attribute(
                    policy,
                    "require_float_value",
                    field="policy",
                ),
            ),
            allow_stattrak=cast(
                bool,
                _stored_attribute(policy, "allow_stattrak", field="policy"),
            ),
            allow_souvenir=cast(
                bool,
                _stored_attribute(policy, "allow_souvenir", field="policy"),
            ),
            allow_special_seed=cast(
                bool,
                _stored_attribute(
                    policy,
                    "allow_special_seed",
                    field="policy",
                ),
            ),
        )
    except MemoryError:
        raise
    except Exception:
        raise _validation_error(field="policy") from None


def _copy_facts(facts: object) -> BuffListingEligibilityFacts:
    if type(facts) is not BuffListingEligibilityFacts:
        raise _validation_error(field="lookup_result")
    try:
        return BuffListingEligibilityFacts(
            is_stattrak=cast(
                bool,
                _stored_attribute(facts, "is_stattrak", field="lookup_result"),
            ),
            is_souvenir=cast(
                bool,
                _stored_attribute(facts, "is_souvenir", field="lookup_result"),
            ),
            has_special_seed=cast(
                bool,
                _stored_attribute(
                    facts,
                    "has_special_seed",
                    field="lookup_result",
                ),
            ),
        )
    except MemoryError:
        raise
    except Exception:
        raise _validation_error(field="lookup_result") from None


def _copy_lookup_result(value: object) -> BuffListingFactsLookupResult:
    if type(value) is not BuffListingFactsLookupResult:
        raise _validation_error(field="lookup_result")
    try:
        status = _stored_attribute(value, "status", field="lookup_result")
        facts = _stored_attribute(value, "facts", field="lookup_result")
        return BuffListingFactsLookupResult(
            status=cast(BuffListingFactsLookupStatus, status),
            listing_id=_copy_string(
                _stored_attribute(value, "listing_id", field="lookup_result"),
                field="lookup_result",
            ),
            market_hash_name=_copy_string(
                _stored_attribute(
                    value,
                    "market_hash_name",
                    field="lookup_result",
                ),
                field="lookup_result",
            ),
            facts=None if facts is None else _copy_facts(facts),
        )
    except MemoryError:
        raise
    except Exception:
        raise _validation_error(field="lookup_result") from None


def _copy_decision(value: object) -> BuffListingEligibilityDecision:
    if type(value) is not BuffListingEligibilityDecision:
        raise _validation_error(field="decision")
    try:
        return BuffListingEligibilityDecision(
            candidate=_copy_candidate(
                _stored_attribute(value, "candidate", field="decision")
            ),
            facts=_copy_decision_facts(
                _stored_attribute(value, "facts", field="decision")
            ),
            policy=_copy_decision_policy(
                _stored_attribute(value, "policy", field="decision")
            ),
            reasons=cast(
                tuple,
                _stored_attribute(value, "reasons", field="decision"),
            ),
        )
    except MemoryError:
        raise
    except Exception:
        raise _validation_error(field="decision") from None


def _copy_decision_facts(value: object) -> BuffListingEligibilityFacts:
    if type(value) is not BuffListingEligibilityFacts:
        raise _validation_error(field="decision")
    try:
        return BuffListingEligibilityFacts(
            is_stattrak=cast(
                bool,
                _stored_attribute(value, "is_stattrak", field="decision"),
            ),
            is_souvenir=cast(
                bool,
                _stored_attribute(value, "is_souvenir", field="decision"),
            ),
            has_special_seed=cast(
                bool,
                _stored_attribute(value, "has_special_seed", field="decision"),
            ),
        )
    except MemoryError:
        raise
    except Exception:
        raise _validation_error(field="decision") from None


def _copy_decision_policy(value: object) -> BuffListingEligibilityPolicy:
    if type(value) is not BuffListingEligibilityPolicy:
        raise _validation_error(field="decision")
    try:
        return BuffListingEligibilityPolicy(
            min_available_quantity=cast(
                int,
                _stored_attribute(
                    value,
                    "min_available_quantity",
                    field="decision",
                ),
            ),
            require_positive_price=cast(
                bool,
                _stored_attribute(
                    value,
                    "require_positive_price",
                    field="decision",
                ),
            ),
            require_float_value=cast(
                bool,
                _stored_attribute(value, "require_float_value", field="decision"),
            ),
            allow_stattrak=cast(
                bool,
                _stored_attribute(value, "allow_stattrak", field="decision"),
            ),
            allow_souvenir=cast(
                bool,
                _stored_attribute(value, "allow_souvenir", field="decision"),
            ),
            allow_special_seed=cast(
                bool,
                _stored_attribute(value, "allow_special_seed", field="decision"),
            ),
        )
    except MemoryError:
        raise
    except Exception:
        raise _validation_error(field="decision") from None


def _validate_lookup_identity(
    candidate: BuffTradableCandidate,
    lookup_result: BuffListingFactsLookupResult,
) -> None:
    if (
        lookup_result.listing_id != candidate.listing_id
        or lookup_result.market_hash_name != candidate.market_hash_name
    ):
        raise _validation_error(field="lookup_result")


def _validate_decision(
    decision: BuffListingEligibilityDecision,
    *,
    candidate: BuffTradableCandidate,
    facts: BuffListingEligibilityFacts,
    policy: BuffListingEligibilityPolicy,
) -> None:
    if (
        decision.candidate != candidate
        or decision.facts != facts
        or decision.policy != policy
    ):
        raise _validation_error(field="decision")


def _stored_attribute(value: object, name: str, *, field: str) -> object:
    try:
        storage = object.__getattribute__(value, "__dict__")
        return dict.__getitem__(storage, name)
    except (AttributeError, KeyError, TypeError):
        raise _validation_error(field=field) from None


def _copy_string(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise _validation_error(field=field)
    try:
        return str.__str__(value)
    except MemoryError:
        raise
    except Exception:
        raise _validation_error(field=field) from None


def _copy_optional_string(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _copy_string(value, field=field)


def _copy_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise _validation_error(field=field)
    try:
        return Decimal(value)
    except MemoryError:
        raise
    except Exception:
        raise _validation_error(field=field) from None


def _copy_optional_decimal(value: object, *, field: str) -> Decimal | None:
    if value is None:
        return None
    return _copy_decimal(value, field=field)


def _copy_datetime(value: object, *, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise _validation_error(field=field)
    try:
        if datetime.tzinfo.__get__(value) is not UTC:
            raise _validation_error(field=field)
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
    except MemoryError:
        raise
    except Exception:
        raise _validation_error(field=field) from None


def _validation_error(*, field: str) -> BuffListingQualificationValidationError:
    return BuffListingQualificationValidationError(field=field)
