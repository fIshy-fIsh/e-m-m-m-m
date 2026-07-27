from __future__ import annotations

import ast
import asyncio
from collections.abc import Coroutine
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from app.services.buff_listing import BuffTradableCandidate
from app.services.buff_listing_eligibility import (
    BuffListingEligibilityDecision,
    BuffListingEligibilityFacts,
    BuffListingEligibilityPolicy,
    BuffListingIneligibilityReason,
    evaluate_buff_listing_eligibility,
)
from app.services.buff_listing_facts import (
    BuffListingFactsLookupResult,
    BuffListingFactsLookupStatus,
)
from app.services.buff_listing_qualification import (
    BuffListingQualificationResult,
    BuffListingQualificationService,
    BuffListingQualificationStatus,
    BuffListingQualificationValidationError,
)

MODULE_PATH = Path("app/services/buff_listing_qualification.py")
_DEFAULT_DECISION = object()


def _run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def _candidate(**changes: object) -> BuffTradableCandidate:
    values: dict[str, object] = {
        "listing_id": "qualification-listing-001",
        "goods_id": "qualification-goods-001",
        "market_hash_name": "Synthetic Qualification Item",
        "buy_price_cny": Decimal("12.50"),
        "available_quantity": 2,
        "float_value": Decimal("0.15"),
        "wear_name": "Field-Tested",
        "paint_seed": 661,
        "observed_at": datetime(2026, 7, 25, 12, tzinfo=UTC),
    }
    values.update(changes)
    return BuffTradableCandidate(**values)  # type: ignore[arg-type]


def _facts(**changes: object) -> BuffListingEligibilityFacts:
    values: dict[str, object] = {
        "is_stattrak": False,
        "is_souvenir": False,
        "has_special_seed": False,
    }
    values.update(changes)
    return BuffListingEligibilityFacts(**values)  # type: ignore[arg-type]


def _policy(**changes: object) -> BuffListingEligibilityPolicy:
    values: dict[str, object] = {
        "min_available_quantity": 1,
        "require_positive_price": True,
        "require_float_value": True,
        "allow_stattrak": False,
        "allow_souvenir": False,
        "allow_special_seed": False,
    }
    values.update(changes)
    return BuffListingEligibilityPolicy(**values)  # type: ignore[arg-type]


def _lookup(
    candidate: BuffTradableCandidate,
    *,
    facts: BuffListingEligibilityFacts | None = None,
) -> BuffListingFactsLookupResult:
    return BuffListingFactsLookupResult(
        status=(
            BuffListingFactsLookupStatus.MISSING
            if facts is None
            else BuffListingFactsLookupStatus.FOUND
        ),
        listing_id=candidate.listing_id,
        market_hash_name=candidate.market_hash_name,
        facts=facts,
    )


def _decision(
    candidate: BuffTradableCandidate,
    facts: BuffListingEligibilityFacts,
    policy: BuffListingEligibilityPolicy,
) -> BuffListingEligibilityDecision:
    return evaluate_buff_listing_eligibility(candidate, facts, policy)


class FakeFactsProvider:
    def __init__(
        self,
        result: object,
        *,
        error: BaseException | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[BuffTradableCandidate] = []

    async def lookup_facts(self, candidate: BuffTradableCandidate) -> object:
        self.calls.append(candidate)
        if self.error is not None:
            raise self.error
        return self.result


class CountingEvaluator:
    def __init__(
        self,
        result: object = _DEFAULT_DECISION,
        *,
        error: BaseException | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[
            tuple[
                BuffTradableCandidate,
                BuffListingEligibilityFacts,
                BuffListingEligibilityPolicy,
            ]
        ] = []

    def __call__(
        self,
        candidate: BuffTradableCandidate,
        facts: BuffListingEligibilityFacts,
        policy: BuffListingEligibilityPolicy,
    ) -> BuffListingEligibilityDecision:
        self.calls.append((candidate, facts, policy))
        if self.error is not None:
            raise self.error
        if self.result is _DEFAULT_DECISION:
            return evaluate_buff_listing_eligibility(candidate, facts, policy)
        return cast(BuffListingEligibilityDecision, self.result)


def _result(
    *,
    candidate: BuffTradableCandidate | None = None,
    facts: BuffListingEligibilityFacts | None = None,
    policy: BuffListingEligibilityPolicy | None = None,
) -> BuffListingQualificationResult:
    candidate = _candidate() if candidate is None else candidate
    policy = _policy() if policy is None else policy
    lookup = _lookup(candidate, facts=facts)
    decision = None if facts is None else _decision(candidate, facts, policy)
    return BuffListingQualificationResult(
        candidate=candidate,
        policy=policy,
        lookup_result=lookup,
        decision=decision,
    )


def _assert_validation_error(
    action: Any,
    *,
    field: str,
) -> BuffListingQualificationValidationError:
    with pytest.raises(BuffListingQualificationValidationError) as captured:
        action()
    error = captured.value
    assert str(error) == "invalid BUFF listing qualification contract"
    assert error.field == field
    assert error.__cause__ is None
    return error


def test_status_vocabulary_is_exact() -> None:
    assert [(status.name, status.value) for status in BuffListingQualificationStatus] == [
        ("QUALIFIED", "qualified"),
        ("REJECTED", "rejected"),
        ("MISSING_FACTS", "missing_facts"),
    ]


def test_result_has_exact_stored_fields_and_derived_status() -> None:
    assert [field.name for field in fields(BuffListingQualificationResult)] == [
        "candidate",
        "policy",
        "lookup_result",
        "decision",
    ]
    assert "status" not in BuffListingQualificationResult.__dataclass_fields__


def test_result_rejects_constructor_status() -> None:
    with pytest.raises(TypeError):
        BuffListingQualificationResult(  # type: ignore[call-arg]
            candidate=_candidate(),
            policy=_policy(),
            lookup_result=_lookup(_candidate()),
            decision=None,
            status=BuffListingQualificationStatus.MISSING_FACTS,
        )


@pytest.mark.parametrize(
    ("facts", "candidate_changes", "expected"),
    [
        (None, {}, BuffListingQualificationStatus.MISSING_FACTS),
        (_facts(), {}, BuffListingQualificationStatus.QUALIFIED),
        (
            _facts(is_stattrak=True),
            {},
            BuffListingQualificationStatus.REJECTED,
        ),
        (
            _facts(),
            {"available_quantity": 0},
            BuffListingQualificationStatus.REJECTED,
        ),
    ],
)
def test_result_derives_three_outcomes(
    facts: BuffListingEligibilityFacts | None,
    candidate_changes: dict[str, object],
    expected: BuffListingQualificationStatus,
) -> None:
    assert _result(candidate=_candidate(**candidate_changes), facts=facts).status is expected


def test_result_is_frozen_keyword_only_and_repr_safe() -> None:
    result = _result()
    with pytest.raises(FrozenInstanceError):
        result.decision = None  # type: ignore[misc]
    with pytest.raises(TypeError):
        BuffListingQualificationResult(  # type: ignore[misc]
            result.candidate,
            result.policy,
            result.lookup_result,
            result.decision,
        )
    rendered = repr(result)
    assert "BuffListingQualificationResult object" in rendered
    assert "qualification-listing-001" not in rendered


def test_result_defensively_snapshots_complete_state() -> None:
    candidate = _candidate()
    facts = _facts()
    policy = _policy()
    lookup = _lookup(candidate, facts=facts)
    decision = _decision(candidate, facts, policy)

    result = BuffListingQualificationResult(
        candidate=candidate,
        policy=policy,
        lookup_result=lookup,
        decision=decision,
    )

    assert result.candidate == candidate and result.candidate is not candidate
    assert result.policy == policy and result.policy is not policy
    assert result.lookup_result == lookup and result.lookup_result is not lookup
    assert result.lookup_result.facts == facts
    assert result.lookup_result.facts is not facts
    assert result.decision == decision and result.decision is not decision
    assert result.decision is not None
    assert result.decision.candidate is not decision.candidate
    assert result.decision.facts is not decision.facts
    assert result.decision.policy is not decision.policy


@pytest.mark.parametrize(
    "status",
    [BuffListingFactsLookupStatus.FOUND, BuffListingFactsLookupStatus.MISSING],
)
def test_result_rejects_contradictory_lookup_and_decision(
    status: BuffListingFactsLookupStatus,
) -> None:
    candidate = _candidate()
    facts = _facts()
    lookup = _lookup(
        candidate,
        facts=(
            facts if status is BuffListingFactsLookupStatus.FOUND else None
        ),
    )
    decision = (
        None
        if status is BuffListingFactsLookupStatus.FOUND
        else _decision(candidate, facts, _policy())
    )
    _assert_validation_error(
        lambda: BuffListingQualificationResult(
            candidate=candidate,
            policy=_policy(),
            lookup_result=lookup,
            decision=decision,
        ),
        field="decision",
    )


@pytest.mark.parametrize("field", ["listing_id", "market_hash_name"])
def test_result_rejects_lookup_identity_mismatch(field: str) -> None:
    candidate = _candidate()
    lookup = _lookup(candidate)
    object.__setattr__(lookup, field, "another-identity")
    _assert_validation_error(
        lambda: BuffListingQualificationResult(
            candidate=candidate,
            policy=_policy(),
            lookup_result=lookup,
            decision=None,
        ),
        field="lookup_result",
    )


@pytest.mark.parametrize("component", ["candidate", "facts", "policy"])
def test_result_rejects_decision_state_mismatch(component: str) -> None:
    candidate = _candidate()
    facts = _facts()
    policy = _policy()
    lookup = _lookup(candidate, facts=facts)
    decision = _decision(candidate, facts, policy)
    replacement: object
    if component == "candidate":
        replacement = _candidate(available_quantity=3)
    elif component == "facts":
        replacement = _facts(is_souvenir=True)
    else:
        replacement = _policy(allow_souvenir=True)
    object.__setattr__(decision, component, replacement)
    _assert_validation_error(
        lambda: BuffListingQualificationResult(
            candidate=candidate,
            policy=policy,
            lookup_result=lookup,
            decision=decision,
        ),
        field="decision",
    )


def test_service_rejects_missing_or_noncallable_provider_capability() -> None:
    class MissingProvider:
        pass

    class NonCallableProvider:
        lookup_facts = 7

    for provider in (MissingProvider(), NonCallableProvider()):
        _assert_validation_error(
            lambda provider=provider: BuffListingQualificationService(provider),  # type: ignore[arg-type]
            field="provider",
        )


def test_provider_property_is_not_invoked_during_construction() -> None:
    class PropertyProvider:
        getter_calls = 0

        @property
        def lookup_facts(self) -> object:
            self.getter_calls += 1
            raise RuntimeError("Cookie=dummy-secret")

    provider = PropertyProvider()
    _assert_validation_error(
        lambda: BuffListingQualificationService(provider),  # type: ignore[arg-type]
        field="provider",
    )
    assert provider.getter_calls == 0


def test_callable_provider_descriptor_is_rejected_without_binding() -> None:
    class CallableDescriptor:
        get_calls = 0

        def __get__(self, instance: object, owner: type[object]) -> object:
            self.get_calls += 1
            raise RuntimeError("Cookie=dummy-secret")

        def __call__(self) -> None:
            raise AssertionError("descriptor must not be treated as a method")

    descriptor = CallableDescriptor()

    class DescriptorProvider:
        lookup_facts = descriptor

    _assert_validation_error(
        lambda: BuffListingQualificationService(DescriptorProvider()),  # type: ignore[arg-type]
        field="provider",
    )
    assert descriptor.get_calls == 0


def test_builtin_provider_descriptor_is_rejected() -> None:
    class DescriptorProvider:
        lookup_facts = list.append

    _assert_validation_error(
        lambda: BuffListingQualificationService(DescriptorProvider()),  # type: ignore[arg-type]
        field="provider",
    )


def test_service_rejects_noncallable_evaluator() -> None:
    candidate = _candidate()
    provider = FakeFactsProvider(_lookup(candidate))
    _assert_validation_error(
        lambda: BuffListingQualificationService(
            provider,  # type: ignore[arg-type]
            evaluator=cast(Any, 7),
        ),
        field="evaluator",
    )


def test_evaluator_call_property_is_rejected_without_binding() -> None:
    class PropertyEvaluator:
        get_calls = 0

        @property
        def __call__(self) -> object:
            self.get_calls += 1
            raise RuntimeError("Bearer dummy-secret")

    candidate = _candidate()
    evaluator = PropertyEvaluator()
    _assert_validation_error(
        lambda: BuffListingQualificationService(
            FakeFactsProvider(_lookup(candidate)),  # type: ignore[arg-type]
            evaluator=cast(Any, evaluator),
        ),
        field="evaluator",
    )
    assert evaluator.get_calls == 0


def test_builtin_evaluator_descriptor_is_rejected() -> None:
    class DescriptorEvaluator:
        __call__ = list.append

    candidate = _candidate()
    _assert_validation_error(
        lambda: BuffListingQualificationService(
            FakeFactsProvider(_lookup(candidate)),  # type: ignore[arg-type]
            evaluator=cast(Any, DescriptorEvaluator()),
        ),
        field="evaluator",
    )


def test_evaluator_selection_does_not_invoke_truthiness() -> None:
    class FalseyEvaluator(CountingEvaluator):
        def __bool__(self) -> bool:
            raise AssertionError("truthiness must not be inspected")

    candidate = _candidate()
    facts = _facts()
    evaluator = FalseyEvaluator()
    service = BuffListingQualificationService(
        FakeFactsProvider(_lookup(candidate, facts=facts)),  # type: ignore[arg-type]
        evaluator=evaluator,
    )
    result = _run(service.qualify(candidate, _policy()))
    assert result.status is BuffListingQualificationStatus.QUALIFIED


def test_found_eligible_qualifies_with_single_calls_and_original_values() -> None:
    candidate = _candidate()
    facts = _facts()
    policy = _policy()
    lookup = _lookup(candidate, facts=facts)
    provider = FakeFactsProvider(lookup)
    evaluator = CountingEvaluator()
    service = BuffListingQualificationService(
        provider,  # type: ignore[arg-type]
        evaluator=evaluator,
    )

    result = _run(service.qualify(candidate, policy))

    assert result.status is BuffListingQualificationStatus.QUALIFIED
    assert len(provider.calls) == 1
    assert len(evaluator.calls) == 1
    assert provider.calls[0] == candidate and provider.calls[0] is not candidate
    assert provider.calls[0].goods_id == "qualification-goods-001"
    evaluated_candidate, evaluated_facts, evaluated_policy = evaluator.calls[0]
    assert evaluated_candidate == candidate and evaluated_candidate is not candidate
    assert evaluated_candidate.goods_id == "qualification-goods-001"
    assert evaluated_facts == facts and evaluated_facts is not facts
    assert evaluated_policy == policy and evaluated_policy is not policy
    assert result.lookup_result == lookup and result.lookup_result is not lookup
    assert result.candidate.goods_id == "qualification-goods-001"
    assert result.decision is not None
    assert result.decision.candidate.goods_id == "qualification-goods-001"


def test_found_ineligible_rejects_and_preserves_all_reasons() -> None:
    candidate = _candidate(
        buy_price_cny=Decimal("0"),
        available_quantity=0,
        float_value=None,
    )
    facts = _facts(is_stattrak=True, is_souvenir=True, has_special_seed=True)
    policy = _policy()
    provider = FakeFactsProvider(_lookup(candidate, facts=facts))

    result = _run(
        BuffListingQualificationService(provider).qualify(  # type: ignore[arg-type]
            candidate,
            policy,
        )
    )

    assert result.status is BuffListingQualificationStatus.REJECTED
    assert result.candidate.goods_id == "qualification-goods-001"
    assert result.decision is not None
    assert result.decision.candidate.goods_id == "qualification-goods-001"
    assert result.decision.reasons == (
        BuffListingIneligibilityReason.INSUFFICIENT_QUANTITY,
        BuffListingIneligibilityReason.NON_POSITIVE_PRICE,
        BuffListingIneligibilityReason.MISSING_FLOAT,
        BuffListingIneligibilityReason.STATTRAK_DISALLOWED,
        BuffListingIneligibilityReason.SOUVENIR_DISALLOWED,
        BuffListingIneligibilityReason.SPECIAL_SEED_DISALLOWED,
    )


def test_missing_facts_skips_evaluator_and_creates_no_facts() -> None:
    candidate = _candidate()
    provider = FakeFactsProvider(_lookup(candidate))
    evaluator = CountingEvaluator()
    result = _run(
        BuffListingQualificationService(
            provider,  # type: ignore[arg-type]
            evaluator=evaluator,
        ).qualify(candidate, _policy())
    )

    assert result.status is BuffListingQualificationStatus.MISSING_FACTS
    assert result.candidate.goods_id == "qualification-goods-001"
    assert result.lookup_result.facts is None
    assert result.decision is None
    assert len(provider.calls) == 1
    assert evaluator.calls == []


def test_default_evaluator_is_used() -> None:
    candidate = _candidate()
    facts = _facts(is_souvenir=True)
    result = _run(
        BuffListingQualificationService(
            FakeFactsProvider(_lookup(candidate, facts=facts))  # type: ignore[arg-type]
        ).qualify(candidate, _policy())
    )
    assert result.status is BuffListingQualificationStatus.REJECTED
    assert result.decision is not None
    assert result.decision.reasons == (
        BuffListingIneligibilityReason.SOUVENIR_DISALLOWED,
    )


def test_legacy_null_goods_id_is_preserved_through_qualification() -> None:
    candidate = _candidate(goods_id=None)
    facts = _facts()
    result = _run(
        BuffListingQualificationService(
            FakeFactsProvider(_lookup(candidate, facts=facts))  # type: ignore[arg-type]
        ).qualify(candidate, _policy())
    )

    assert result.candidate.goods_id is None
    assert result.decision is not None
    assert result.decision.candidate.goods_id is None


def test_repeated_qualification_is_deterministic_and_fresh() -> None:
    candidate = _candidate()
    facts = _facts()
    service = BuffListingQualificationService(
        FakeFactsProvider(_lookup(candidate, facts=facts))  # type: ignore[arg-type]
    )

    first = _run(service.qualify(candidate, _policy()))
    second = _run(service.qualify(candidate, _policy()))

    assert first == second
    assert first is not second
    assert first.candidate is not second.candidate
    assert first.lookup_result is not second.lookup_result
    assert first.decision is not second.decision


@pytest.mark.parametrize(
    ("name", "paint_seed", "facts"),
    [
        ("StatTrak™ Souvenir Synthetic", 661, _facts()),
        ("Plain Item", None, _facts(has_special_seed=True)),
    ],
)
def test_qualification_does_not_infer_facts(
    name: str,
    paint_seed: int | None,
    facts: BuffListingEligibilityFacts,
) -> None:
    candidate = _candidate(market_hash_name=name, paint_seed=paint_seed)
    result = _run(
        BuffListingQualificationService(
            FakeFactsProvider(_lookup(candidate, facts=facts))  # type: ignore[arg-type]
        ).qualify(candidate, _policy())
    )
    expected = (
        BuffListingQualificationStatus.REJECTED
        if facts.has_special_seed
        else BuffListingQualificationStatus.QUALIFIED
    )
    assert result.status is expected


@pytest.mark.parametrize("input_name", ["candidate", "policy"])
def test_service_rejects_invalid_inputs_before_provider_call(input_name: str) -> None:
    candidate = _candidate()
    provider = FakeFactsProvider(_lookup(candidate))
    service = BuffListingQualificationService(provider)  # type: ignore[arg-type]
    if input_name == "candidate":
        invalid_candidate: object = object()
        invalid_policy: object = _policy()
    else:
        invalid_candidate = candidate
        invalid_policy = object()

    def action() -> None:
        _run(
            service.qualify(
                cast(Any, invalid_candidate),
                cast(Any, invalid_policy),
            )
        )

    _assert_validation_error(action, field=input_name)
    assert provider.calls == []


def test_exact_candidate_and_policy_subclasses_are_rejected() -> None:
    class CandidateSubclass(BuffTradableCandidate):
        pass

    class PolicySubclass(BuffListingEligibilityPolicy):
        pass

    candidate = _candidate()
    provider = FakeFactsProvider(_lookup(candidate))
    service = BuffListingQualificationService(provider)  # type: ignore[arg-type]
    candidate_subclass = CandidateSubclass(
        **{field.name: getattr(candidate, field.name) for field in fields(candidate)}
    )
    policy = _policy()
    policy_subclass = PolicySubclass(
        **{field.name: getattr(policy, field.name) for field in fields(policy)}
    )

    _assert_validation_error(
        lambda: _run(service.qualify(candidate_subclass, policy)),
        field="candidate",
    )
    _assert_validation_error(
        lambda: _run(service.qualify(candidate, policy_subclass)),
        field="policy",
    )
    assert provider.calls == []


@pytest.mark.parametrize("returned", [None, object(), "found", 1])
def test_invalid_provider_return_fails_closed_without_evaluation(
    returned: object,
) -> None:
    candidate = _candidate()
    evaluator = CountingEvaluator()
    service = BuffListingQualificationService(
        FakeFactsProvider(returned),  # type: ignore[arg-type]
        evaluator=evaluator,
    )
    _assert_validation_error(
        lambda: _run(service.qualify(candidate, _policy())),
        field="lookup_result",
    )
    assert evaluator.calls == []


def test_lookup_result_subclass_is_rejected() -> None:
    class LookupSubclass(BuffListingFactsLookupResult):
        pass

    candidate = _candidate()
    lookup = LookupSubclass(
        status=BuffListingFactsLookupStatus.MISSING,
        listing_id=candidate.listing_id,
        market_hash_name=candidate.market_hash_name,
        facts=None,
    )
    evaluator = CountingEvaluator()
    service = BuffListingQualificationService(
        FakeFactsProvider(lookup),  # type: ignore[arg-type]
        evaluator=evaluator,
    )
    _assert_validation_error(
        lambda: _run(service.qualify(candidate, _policy())),
        field="lookup_result",
    )
    assert evaluator.calls == []


@pytest.mark.parametrize("field", ["listing_id", "market_hash_name"])
def test_provider_query_identity_mismatch_fails_before_evaluation(field: str) -> None:
    candidate = _candidate()
    lookup = _lookup(candidate, facts=_facts())
    object.__setattr__(lookup, field, "wrong-query-identity")
    evaluator = CountingEvaluator()
    service = BuffListingQualificationService(
        FakeFactsProvider(lookup),  # type: ignore[arg-type]
        evaluator=evaluator,
    )
    _assert_validation_error(
        lambda: _run(service.qualify(candidate, _policy())),
        field="lookup_result",
    )
    assert evaluator.calls == []


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("status", "found"),
        ("facts", None),
        ("listing_id", "   "),
        ("market_hash_name", 7),
    ],
)
def test_tampered_lookup_fails_closed(
    attribute: str,
    value: object,
) -> None:
    candidate = _candidate()
    lookup = _lookup(candidate, facts=_facts())
    object.__setattr__(lookup, attribute, value)
    evaluator = CountingEvaluator()
    service = BuffListingQualificationService(
        FakeFactsProvider(lookup),  # type: ignore[arg-type]
        evaluator=evaluator,
    )
    _assert_validation_error(
        lambda: _run(service.qualify(candidate, _policy())),
        field="lookup_result",
    )
    assert evaluator.calls == []


def test_tampered_nested_lookup_facts_fail_closed() -> None:
    candidate = _candidate()
    facts = _facts()
    lookup = _lookup(candidate, facts=facts)
    assert lookup.facts is not None
    object.__setattr__(lookup.facts, "is_stattrak", 1)
    evaluator = CountingEvaluator()
    service = BuffListingQualificationService(
        FakeFactsProvider(lookup),  # type: ignore[arg-type]
        evaluator=evaluator,
    )
    _assert_validation_error(
        lambda: _run(service.qualify(candidate, _policy())),
        field="lookup_result",
    )
    assert evaluator.calls == []


@pytest.mark.parametrize("returned", [None, object(), "decision", 1])
def test_invalid_evaluator_return_fails_closed(returned: object) -> None:
    candidate = _candidate()
    facts = _facts()
    service = BuffListingQualificationService(
        FakeFactsProvider(_lookup(candidate, facts=facts)),  # type: ignore[arg-type]
        evaluator=CountingEvaluator(returned),
    )
    _assert_validation_error(
        lambda: _run(service.qualify(candidate, _policy())),
        field="decision",
    )


def test_decision_subclass_is_rejected() -> None:
    class DecisionSubclass(BuffListingEligibilityDecision):
        pass

    candidate = _candidate()
    facts = _facts()
    policy = _policy()
    base = _decision(candidate, facts, policy)
    decision = DecisionSubclass(
        candidate=base.candidate,
        facts=base.facts,
        policy=base.policy,
        reasons=base.reasons,
    )
    service = BuffListingQualificationService(
        FakeFactsProvider(_lookup(candidate, facts=facts)),  # type: ignore[arg-type]
        evaluator=CountingEvaluator(decision),
    )
    _assert_validation_error(
        lambda: _run(service.qualify(candidate, policy)),
        field="decision",
    )


@pytest.mark.parametrize("component", ["candidate", "facts", "policy"])
def test_evaluator_decision_mismatch_fails_closed(component: str) -> None:
    candidate = _candidate()
    facts = _facts()
    policy = _policy()
    decision = _decision(candidate, facts, policy)
    if component == "candidate":
        replacement: object = _candidate(available_quantity=4)
    elif component == "facts":
        replacement = _facts(is_stattrak=True)
    else:
        replacement = _policy(allow_stattrak=True)
    object.__setattr__(decision, component, replacement)
    service = BuffListingQualificationService(
        FakeFactsProvider(_lookup(candidate, facts=facts)),  # type: ignore[arg-type]
        evaluator=CountingEvaluator(decision),
    )
    _assert_validation_error(
        lambda: _run(service.qualify(candidate, policy)),
        field="decision",
    )


def test_tampered_decision_reasons_fail_closed() -> None:
    candidate = _candidate()
    facts = _facts()
    policy = _policy()
    decision = _decision(candidate, facts, policy)
    object.__setattr__(
        decision,
        "reasons",
        (BuffListingIneligibilityReason.MISSING_FLOAT,),
    )
    service = BuffListingQualificationService(
        FakeFactsProvider(_lookup(candidate, facts=facts)),  # type: ignore[arg-type]
        evaluator=CountingEvaluator(decision),
    )
    _assert_validation_error(
        lambda: _run(service.qualify(candidate, policy)),
        field="decision",
    )


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("Cookie=dummy-secret"),
        ValueError("Bearer dummy-token"),
        MemoryError("password=dummy-password"),
        asyncio.CancelledError("redis://dummy-secret"),
    ],
)
def test_provider_errors_propagate_by_identity(error: BaseException) -> None:
    candidate = _candidate()
    evaluator = CountingEvaluator()
    service = BuffListingQualificationService(
        FakeFactsProvider(_lookup(candidate), error=error),  # type: ignore[arg-type]
        evaluator=evaluator,
    )
    with pytest.raises(type(error)) as captured:
        _run(service.qualify(candidate, _policy()))
    assert captured.value is error
    assert evaluator.calls == []


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("Cookie=dummy-secret"),
        ValueError("Bearer dummy-token"),
        MemoryError("password=dummy-password"),
        asyncio.CancelledError("redis://dummy-secret"),
    ],
)
def test_evaluator_errors_propagate_by_identity(error: BaseException) -> None:
    candidate = _candidate()
    facts = _facts()
    evaluator = CountingEvaluator(error=error)
    service = BuffListingQualificationService(
        FakeFactsProvider(_lookup(candidate, facts=facts)),  # type: ignore[arg-type]
        evaluator=evaluator,
    )
    with pytest.raises(type(error)) as captured:
        _run(service.qualify(candidate, _policy()))
    assert captured.value is error
    assert len(evaluator.calls) == 1


def test_keyboard_interrupt_from_provider_propagates_by_identity() -> None:
    candidate = _candidate()
    error = KeyboardInterrupt("dummy-secret")
    service = BuffListingQualificationService(
        FakeFactsProvider(_lookup(candidate), error=error)  # type: ignore[arg-type]
    )
    coroutine = service.qualify(candidate, _policy())
    with pytest.raises(KeyboardInterrupt) as captured:
        coroutine.send(None)
    assert captured.value is error


def test_keyboard_interrupt_from_evaluator_propagates_by_identity() -> None:
    candidate = _candidate()
    facts = _facts()
    error = KeyboardInterrupt("dummy-secret")
    service = BuffListingQualificationService(
        FakeFactsProvider(_lookup(candidate, facts=facts)),  # type: ignore[arg-type]
        evaluator=CountingEvaluator(error=error),
    )
    coroutine = service.qualify(candidate, _policy())
    with pytest.raises(KeyboardInterrupt) as captured:
        coroutine.send(None)
    assert captured.value is error


def test_validation_error_and_repr_are_fixed_and_redacted() -> None:
    secrets = (
        "dummy-listing-secret",
        "Cookie=dummy-cookie",
        "Bearer dummy-token",
        "redis://dummy-password@localhost",
        "password=dummy-password",
    )
    candidate = _candidate(
        listing_id=secrets[0],
        goods_id=secrets[4],
        market_hash_name=secrets[1],
    )
    lookup = _lookup(candidate)
    object.__setattr__(lookup, "market_hash_name", secrets[2])
    error = _assert_validation_error(
        lambda: BuffListingQualificationResult(
            candidate=candidate,
            policy=_policy(),
            lookup_result=lookup,
            decision=None,
        ),
        field="lookup_result",
    )
    rendered = f"{error!s} {error!r} {_result()!r}"
    assert all(secret not in rendered for secret in secrets)


def _imported_names(tree: ast.AST) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.add(module)
            imported.update(f"{module}.{alias.name}" for alias in node.names)
    return imported


def test_qualification_module_has_no_forbidden_imports() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported = _imported_names(tree)
    forbidden_fragments = {
        "client",
        "config",
        "fastapi",
        "httpx",
        "metadata",
        "pipeline",
        "price_provider",
        "redis",
        "risk",
        "scanner",
        "scheduler",
        "solver",
        "steamdt",
        "valuation",
    }
    assert not {
        name
        for name in imported
        if any(fragment in name.lower() for fragment in forbidden_fragments)
    }
    assert "os" not in imported
    assert "threading" not in imported


def test_qualification_module_has_no_forbidden_calls_or_background_work() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    forbidden = {
        "create_task",
        "getenv",
        "open",
        "parse_buff_listing_facts_fixture",
        "read_text",
        "run_in_executor",
        "sleep",
        "start",
        "to_thread",
        "write_text",
    }
    assert called_names.isdisjoint(forbidden)
    assert called_attributes.isdisjoint(forbidden)


def test_runtime_and_lower_layers_do_not_reverse_import_qualification() -> None:
    paths = [
        Path("app/main.py"),
        Path("app/config.py"),
        Path("app/services/buff_listing.py"),
        Path("app/services/buff_listing_parser.py"),
        Path("app/services/buff_listing_facts.py"),
        Path("app/services/buff_listing_eligibility.py"),
        Path("app/services/market_scan_service.py"),
        Path("app/services/recipe_solver.py"),
        Path("app/services/risk_filter.py"),
        Path("app/services/metadata_provider.py"),
        Path("app/services/price_provider.py"),
        Path("app/services/valuation_service.py"),
        Path("app/services/pipeline_service.py"),
        Path("app/jobs/scheduler.py"),
    ]
    for path in paths:
        assert "buff_listing_qualification" not in path.read_text(encoding="utf-8")
