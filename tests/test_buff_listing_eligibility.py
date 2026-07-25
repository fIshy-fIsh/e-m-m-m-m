import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import get_type_hints

import pytest

import app.services.buff_listing_eligibility as eligibility_module
from app.services.buff_listing import BuffTradableCandidate
from app.services.buff_listing_eligibility import (
    BuffListingEligibilityDecision,
    BuffListingEligibilityFacts,
    BuffListingEligibilityPolicy,
    BuffListingEligibilityValidationError,
    BuffListingIneligibilityReason,
    evaluate_buff_listing_eligibility,
)

OBSERVED_AT = datetime(2026, 7, 24, 12, tzinfo=UTC)


def _candidate(**changes: object) -> BuffTradableCandidate:
    values: dict[str, object] = {
        "listing_id": "listing-001",
        "market_hash_name": "AK-47 | Redline (Field-Tested)",
        "buy_price_cny": Decimal("123.4500"),
        "available_quantity": 1,
        "float_value": Decimal("0.234500"),
        "wear_name": "Field-Tested",
        "paint_seed": 321,
        "observed_at": OBSERVED_AT,
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
    values: dict[str, object] = {}
    values.update(changes)
    return BuffListingEligibilityPolicy(**values)  # type: ignore[arg-type]


def _evaluate(
    *,
    candidate: BuffTradableCandidate | None = None,
    facts: BuffListingEligibilityFacts | None = None,
    policy: BuffListingEligibilityPolicy | None = None,
) -> BuffListingEligibilityDecision:
    return evaluate_buff_listing_eligibility(
        candidate or _candidate(),
        facts or _facts(),
        policy or _policy(),
    )


def _assert_validation_error(
    exc_info: pytest.ExceptionInfo[BuffListingEligibilityValidationError],
    *,
    field: str,
) -> None:
    error = exc_info.value
    assert str(error) == "invalid BUFF listing eligibility contract"
    assert error.field == field
    assert error.__cause__ is None


def test_facts_have_exact_public_fields() -> None:
    assert [field.name for field in fields(BuffListingEligibilityFacts)] == [
        "is_stattrak",
        "is_souvenir",
        "has_special_seed",
    ]


def test_facts_accept_exact_boolean_values() -> None:
    assert _facts(
        is_stattrak=True,
        is_souvenir=True,
        has_special_seed=True,
    ) == BuffListingEligibilityFacts(
        is_stattrak=True,
        is_souvenir=True,
        has_special_seed=True,
    )


@pytest.mark.parametrize("field", ["is_stattrak", "is_souvenir", "has_special_seed"])
@pytest.mark.parametrize("value", [0, 1, "true", None, Decimal("1")])
def test_facts_reject_non_exact_booleans(field: str, value: object) -> None:
    with pytest.raises(BuffListingEligibilityValidationError) as exc_info:
        _facts(**{field: value})

    _assert_validation_error(exc_info, field=field)


def test_policy_has_exact_fields_and_defaults() -> None:
    policy = _policy()

    assert [field.name for field in fields(BuffListingEligibilityPolicy)] == [
        "min_available_quantity",
        "require_positive_price",
        "require_float_value",
        "allow_stattrak",
        "allow_souvenir",
        "allow_special_seed",
    ]
    assert policy.min_available_quantity == 1
    assert policy.require_positive_price is True
    assert policy.require_float_value is True
    assert policy.allow_stattrak is False
    assert policy.allow_souvenir is False
    assert policy.allow_special_seed is False


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, "1", Decimal("1"), None])
def test_policy_rejects_invalid_minimum_quantity(value: object) -> None:
    with pytest.raises(BuffListingEligibilityValidationError) as exc_info:
        _policy(min_available_quantity=value)

    _assert_validation_error(exc_info, field="min_available_quantity")


@pytest.mark.parametrize(
    "field",
    [
        "require_positive_price",
        "require_float_value",
        "allow_stattrak",
        "allow_souvenir",
        "allow_special_seed",
    ],
)
@pytest.mark.parametrize("value", [0, 1, "false", None])
def test_policy_rejects_non_exact_boolean_flags(field: str, value: object) -> None:
    with pytest.raises(BuffListingEligibilityValidationError) as exc_info:
        _policy(**{field: value})

    _assert_validation_error(exc_info, field=field)


def test_reason_vocabulary_and_order_are_stable() -> None:
    assert [(reason.name, reason.value) for reason in BuffListingIneligibilityReason] == [
        ("INSUFFICIENT_QUANTITY", "insufficient_quantity"),
        ("NON_POSITIVE_PRICE", "non_positive_price"),
        ("MISSING_FLOAT", "missing_float"),
        ("STATTRAK_DISALLOWED", "stattrak_disallowed"),
        ("SOUVENIR_DISALLOWED", "souvenir_disallowed"),
        ("SPECIAL_SEED_DISALLOWED", "special_seed_disallowed"),
    ]


def test_public_models_are_keyword_only() -> None:
    with pytest.raises(TypeError):
        BuffListingEligibilityFacts(False, False, False)  # type: ignore[misc]
    with pytest.raises(TypeError):
        BuffListingEligibilityPolicy(1)  # type: ignore[misc]


def test_facts_and_policy_are_immutable() -> None:
    facts = _facts()
    policy = _policy()

    with pytest.raises(FrozenInstanceError):
        facts.is_stattrak = True  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        policy.min_available_quantity = 2  # type: ignore[misc]


def test_quantity_zero_is_ineligible_by_default() -> None:
    decision = _evaluate(candidate=_candidate(available_quantity=0))

    assert decision.reasons == (
        BuffListingIneligibilityReason.INSUFFICIENT_QUANTITY,
    )


def test_quantity_below_custom_threshold_is_ineligible() -> None:
    decision = _evaluate(
        candidate=_candidate(available_quantity=2),
        policy=_policy(min_available_quantity=3),
    )

    assert decision.reasons == (
        BuffListingIneligibilityReason.INSUFFICIENT_QUANTITY,
    )


@pytest.mark.parametrize("quantity", [3, 4])
def test_quantity_at_or_above_threshold_is_eligible(quantity: int) -> None:
    assert _evaluate(
        candidate=_candidate(available_quantity=quantity),
        policy=_policy(min_available_quantity=3),
    ).is_eligible


def test_zero_price_is_ineligible_when_positive_price_is_required() -> None:
    decision = _evaluate(candidate=_candidate(buy_price_cny=Decimal("0")))

    assert decision.reasons == (
        BuffListingIneligibilityReason.NON_POSITIVE_PRICE,
    )


def test_zero_price_is_allowed_when_positive_price_rule_is_disabled() -> None:
    assert _evaluate(
        candidate=_candidate(buy_price_cny=Decimal("0")),
        policy=_policy(require_positive_price=False),
    ).is_eligible


def test_missing_float_is_ineligible_when_float_is_required() -> None:
    decision = _evaluate(candidate=_candidate(float_value=None))

    assert decision.reasons == (BuffListingIneligibilityReason.MISSING_FLOAT,)


def test_missing_float_is_allowed_when_requirement_is_disabled() -> None:
    assert _evaluate(
        candidate=_candidate(float_value=None),
        policy=_policy(require_float_value=False),
    ).is_eligible


@pytest.mark.parametrize(
    ("fact_field", "policy_field", "reason"),
    [
        (
            "is_stattrak",
            "allow_stattrak",
            BuffListingIneligibilityReason.STATTRAK_DISALLOWED,
        ),
        (
            "is_souvenir",
            "allow_souvenir",
            BuffListingIneligibilityReason.SOUVENIR_DISALLOWED,
        ),
        (
            "has_special_seed",
            "allow_special_seed",
            BuffListingIneligibilityReason.SPECIAL_SEED_DISALLOWED,
        ),
    ],
)
def test_explicit_classification_is_disallowed_by_default(
    fact_field: str,
    policy_field: str,
    reason: BuffListingIneligibilityReason,
) -> None:
    decision = _evaluate(facts=_facts(**{fact_field: True}))

    assert decision.reasons == (reason,)
    assert getattr(decision.policy, policy_field) is False


@pytest.mark.parametrize(
    ("fact_field", "policy_field"),
    [
        ("is_stattrak", "allow_stattrak"),
        ("is_souvenir", "allow_souvenir"),
        ("has_special_seed", "allow_special_seed"),
    ],
)
def test_explicit_classification_can_be_allowed(
    fact_field: str,
    policy_field: str,
) -> None:
    assert _evaluate(
        facts=_facts(**{fact_field: True}),
        policy=_policy(**{policy_field: True}),
    ).is_eligible


def test_all_applicable_reasons_are_retained_in_fixed_order() -> None:
    decision = _evaluate(
        candidate=_candidate(
            available_quantity=0,
            buy_price_cny=Decimal("0"),
            float_value=None,
        ),
        facts=_facts(
            is_stattrak=True,
            is_souvenir=True,
            has_special_seed=True,
        ),
    )

    assert decision.reasons == tuple(BuffListingIneligibilityReason)
    assert decision.is_eligible is False


def test_eligible_decision_has_no_reasons() -> None:
    decision = _evaluate()

    assert decision.reasons == ()
    assert decision.is_eligible is True


def test_evaluation_is_deterministic() -> None:
    candidate = _candidate(available_quantity=0, float_value=None)
    facts = _facts(is_souvenir=True)
    policy = _policy()

    assert evaluate_buff_listing_eligibility(
        candidate, facts, policy
    ) == evaluate_buff_listing_eligibility(candidate, facts, policy)


def test_evaluation_does_not_modify_inputs() -> None:
    candidate = _candidate()
    facts = _facts()
    policy = _policy()

    decision = evaluate_buff_listing_eligibility(candidate, facts, policy)

    assert decision.candidate == candidate
    assert decision.facts == facts
    assert decision.policy == policy
    assert decision.candidate is not candidate
    assert decision.facts is not facts
    assert decision.policy is not policy


def test_candidate_fields_do_not_infer_facts_and_non_utc_candidate_fails_closed() -> None:
    decision = _evaluate(
        candidate=_candidate(
            market_hash_name="StatTrak™ Souvenir AK-47 | dummy-secret",
            paint_seed=661,
        ),
        facts=_facts(
            is_stattrak=False,
            is_souvenir=False,
            has_special_seed=False,
        ),
    )

    assert decision.is_eligible

    candidate = _candidate()
    object.__setattr__(
        candidate,
        "observed_at",
        datetime(2026, 7, 24, 20, tzinfo=timezone(timedelta(hours=8))),
    )
    with pytest.raises(BuffListingEligibilityValidationError) as exc_info:
        _evaluate(candidate=candidate)
    _assert_validation_error(exc_info, field="candidate")


def test_explicit_special_seed_fact_does_not_require_a_paint_seed() -> None:
    decision = _evaluate(
        candidate=_candidate(paint_seed=None),
        facts=_facts(has_special_seed=True),
    )

    assert decision.reasons == (
        BuffListingIneligibilityReason.SPECIAL_SEED_DISALLOWED,
    )


def test_decision_defensively_copies_nonempty_reason_tuple() -> None:
    reasons = (BuffListingIneligibilityReason.INSUFFICIENT_QUANTITY,)

    decision = BuffListingEligibilityDecision(
        candidate=_candidate(available_quantity=0),
        facts=_facts(),
        policy=_policy(),
        reasons=reasons,
    )

    assert decision.reasons == reasons
    assert decision.reasons is not reasons


def test_decision_is_immutable_and_eligibility_is_read_only() -> None:
    decision = _evaluate()

    with pytest.raises(FrozenInstanceError):
        decision.reasons = ()  # type: ignore[misc]
    with pytest.raises((AttributeError, FrozenInstanceError)):
        decision.is_eligible = False  # type: ignore[misc]


@pytest.mark.parametrize(
    "reasons",
    [
        [BuffListingIneligibilityReason.INSUFFICIENT_QUANTITY],
        ("insufficient_quantity",),
        (BuffListingIneligibilityReason.INSUFFICIENT_QUANTITY,) * 2,
        type(
            "HostileTuple",
            (tuple,),
            {
                "__iter__": lambda self: (_ for _ in ()).throw(
                    OSError("Cookie=dummy-secret")
                )
            },
        )((BuffListingIneligibilityReason.INSUFFICIENT_QUANTITY,)),
    ],
)
def test_decision_rejects_invalid_reason_containers_or_members(
    reasons: object,
) -> None:
    with pytest.raises(BuffListingEligibilityValidationError) as exc_info:
        BuffListingEligibilityDecision(
            candidate=_candidate(available_quantity=0),
            facts=_facts(),
            policy=_policy(),
            reasons=reasons,  # type: ignore[arg-type]
        )

    _assert_validation_error(exc_info, field="reasons")


def test_decision_rejects_foreign_reason_enum() -> None:
    class ForeignReason(StrEnum):
        INSUFFICIENT_QUANTITY = "insufficient_quantity"

    with pytest.raises(BuffListingEligibilityValidationError) as exc_info:
        BuffListingEligibilityDecision(
            candidate=_candidate(available_quantity=0),
            facts=_facts(),
            policy=_policy(),
            reasons=(ForeignReason.INSUFFICIENT_QUANTITY,),  # type: ignore[arg-type]
        )

    _assert_validation_error(exc_info, field="reasons")


@pytest.mark.parametrize(
    "reasons",
    [
        (),
        (BuffListingIneligibilityReason.NON_POSITIVE_PRICE,),
        (
            BuffListingIneligibilityReason.NON_POSITIVE_PRICE,
            BuffListingIneligibilityReason.INSUFFICIENT_QUANTITY,
        ),
    ],
)
def test_decision_rejects_missing_extra_or_reordered_reasons(
    reasons: tuple[BuffListingIneligibilityReason, ...],
) -> None:
    with pytest.raises(BuffListingEligibilityValidationError) as exc_info:
        BuffListingEligibilityDecision(
            candidate=_candidate(
                available_quantity=0,
                buy_price_cny=Decimal("0"),
            ),
            facts=_facts(),
            policy=_policy(),
            reasons=reasons,
        )

    _assert_validation_error(exc_info, field="reasons")


def test_evaluator_rejects_invalidly_tampered_candidate() -> None:
    candidate = _candidate()
    object.__setattr__(candidate, "available_quantity", True)

    with pytest.raises(BuffListingEligibilityValidationError) as exc_info:
        _evaluate(candidate=candidate)

    _assert_validation_error(exc_info, field="candidate")


def test_evaluator_rejects_invalidly_tampered_facts() -> None:
    facts = _facts()
    object.__setattr__(facts, "is_stattrak", 1)

    with pytest.raises(BuffListingEligibilityValidationError) as exc_info:
        _evaluate(facts=facts)

    _assert_validation_error(exc_info, field="facts")


def test_evaluator_rejects_invalidly_tampered_policy() -> None:
    policy = _policy()
    object.__setattr__(policy, "min_available_quantity", 0)

    with pytest.raises(BuffListingEligibilityValidationError) as exc_info:
        _evaluate(policy=policy)

    _assert_validation_error(exc_info, field="policy")


def test_public_repr_and_errors_do_not_leak_candidate_data() -> None:
    secret = "Cookie=Bearer-password-dummy-secret"
    candidate = _candidate(listing_id=secret, market_hash_name=secret)
    facts = _facts(is_stattrak=True)
    policy = _policy()
    decision = evaluate_buff_listing_eligibility(candidate, facts, policy)

    rendered = " ".join(
        [repr(candidate), repr(facts), repr(policy), repr(decision)]
    )
    assert secret not in rendered

    object.__setattr__(candidate, "available_quantity", secret)
    with pytest.raises(BuffListingEligibilityValidationError) as exc_info:
        _evaluate(candidate=candidate)
    error_rendered = str(exc_info.value) + repr(exc_info.value)
    assert secret not in error_rendered
    assert "Cookie" not in error_rendered
    assert "Bearer" not in error_rendered
    assert "password" not in error_rendered


def test_hostile_decimal_subclass_is_detached_before_evaluation() -> None:
    class HostileDecimal(Decimal):
        def __le__(self, other: object) -> bool:
            raise RuntimeError("Cookie=dummy-secret")

    price = HostileDecimal("1.2300")
    candidate = _candidate(buy_price_cny=price)

    decision = _evaluate(candidate=candidate)

    assert decision.is_eligible
    assert decision.candidate.buy_price_cny == Decimal("1.2300")
    assert type(decision.candidate.buy_price_cny) is Decimal
    assert decision.candidate.buy_price_cny is not price


def test_hostile_candidate_and_value_subclasses_are_detached() -> None:
    class HostileCandidate(BuffTradableCandidate):
        def __getattribute__(self, name: str) -> object:
            if name == "listing_id":
                raise OSError("Cookie=dummy-secret")
            return super().__getattribute__(name)

    class ExhaustedString(str):
        def strip(self, *args: object, **kwargs: object) -> str:
            raise MemoryError("password=dummy-secret")

    class HostileDatetime(datetime):
        def __getattribute__(self, name: str) -> object:
            if name in {"year", "month", "tzinfo", "fold"}:
                raise OSError("Cookie=dummy-secret")
            return super().__getattribute__(name)

    candidate = _candidate()
    object.__setattr__(candidate, "listing_id", ExhaustedString("listing-001"))
    object.__setattr__(
        candidate,
        "observed_at",
        HostileDatetime(2026, 7, 24, 12, tzinfo=UTC),
    )
    object.__setattr__(candidate, "__class__", HostileCandidate)

    decision = _evaluate(candidate=candidate)

    assert decision.is_eligible
    assert type(decision.candidate.listing_id) is str
    assert decision.candidate.listing_id == "listing-001"
    assert type(decision.candidate.observed_at) is datetime
    assert decision.candidate.observed_at == OBSERVED_AT


def test_hostile_timezone_is_rejected_without_executing_it() -> None:
    class HostileTimezone(tzinfo):
        def utcoffset(self, value: datetime | None) -> timedelta:
            raise MemoryError("password=dummy-secret")

        def dst(self, value: datetime | None) -> timedelta:
            return timedelta(0)

        def tzname(self, value: datetime | None) -> str:
            return "hostile"

    candidate = _candidate()
    object.__setattr__(
        candidate,
        "observed_at",
        datetime(2026, 7, 24, 12, tzinfo=HostileTimezone()),
    )

    with pytest.raises(BuffListingEligibilityValidationError) as exc_info:
        _evaluate(candidate=candidate)

    _assert_validation_error(exc_info, field="candidate")


def test_keyboard_interrupt_is_not_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(_candidate: object) -> BuffTradableCandidate:
        raise KeyboardInterrupt

    monkeypatch.setattr(eligibility_module, "_copy_candidate", interrupt)

    with pytest.raises(KeyboardInterrupt):
        _evaluate()


def test_public_api_annotations_are_explicit() -> None:
    annotations = get_type_hints(evaluate_buff_listing_eligibility)

    assert annotations == {
        "candidate": BuffTradableCandidate,
        "facts": BuffListingEligibilityFacts,
        "policy": BuffListingEligibilityPolicy,
        "return": BuffListingEligibilityDecision,
    }


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            module = node.module.casefold()
            names.add(module)
            names.update(f"{module}.{alias.name.casefold()}" for alias in node.names)
    return names


def test_module_has_no_external_or_runtime_wiring_imports() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "buff_listing_eligibility.py"
    )
    imported = _imported_names(module_path)
    forbidden = {
        "app.clients",
        "app.config",
        "asyncio",
        "fastapi",
        "httpx",
        "market_scan",
        "os",
        "pipeline",
        "provider",
        "recipe",
        "redis",
        "risk_filter",
        "scheduler",
        "steamdt",
        "threading",
        "valuation",
    }

    assert not any(
        fragment in name for name in imported for fragment in forbidden
    )


def test_module_has_no_io_env_async_task_or_thread_calls() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "buff_listing_eligibility.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
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

    assert not any(
        isinstance(node, (ast.AsyncFunctionDef, ast.Await)) for node in ast.walk(tree)
    )
    assert called_names.isdisjoint({"open", "print"})
    assert called_attributes.isdisjoint(
        {
            "create_task",
            "getenv",
            "read_bytes",
            "read_text",
            "request",
            "start",
            "write_bytes",
            "write_text",
        }
    )


def test_runtime_and_downstream_modules_do_not_reverse_import_eligibility() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = [
        root / "app" / "main.py",
        root / "app" / "config.py",
        root / "app" / "services" / "market_scan_service.py",
        root / "app" / "services" / "recipe_solver.py",
        root / "app" / "services" / "risk_filter.py",
        root / "app" / "services" / "price_provider.py",
        root / "app" / "services" / "valuation_service.py",
        root / "app" / "services" / "pipeline_service.py",
        root / "app" / "jobs" / "scheduler.py",
    ]

    for path in paths:
        assert "app.services.buff_listing_eligibility" not in _imported_names(path)
