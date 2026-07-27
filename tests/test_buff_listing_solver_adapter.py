import ast
import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

import app.services.buff_listing_solver_adapter as adapter_module
from app.services.buff_listing import BuffTradableCandidate
from app.services.buff_listing_eligibility import (
    BuffListingEligibilityDecision,
    BuffListingEligibilityFacts,
    BuffListingEligibilityPolicy,
    BuffListingIneligibilityReason,
)
from app.services.buff_listing_facts import (
    BuffListingFactsLookupResult,
    BuffListingFactsLookupStatus,
)
from app.services.buff_listing_qualification import BuffListingQualificationResult
from app.services.buff_listing_solver_adapter import (
    BuffListingSolverAdapterError,
    adapt_qualified_buff_listing,
)
from app.services.market_scan_service import CandidateListing

OBSERVED_AT = datetime(2026, 7, 27, 8, 15, tzinfo=UTC)


def _candidate(**changes: object) -> BuffTradableCandidate:
    values: dict[str, object] = {
        "listing_id": "listing-dummy-secret",
        "goods_id": "goods-dummy-secret",
        "market_hash_name": "AK-47 | Synthetic (Field-Tested)",
        "buy_price_cny": Decimal("123.4500000000000000000000001"),
        "available_quantity": 2,
        "float_value": Decimal("0.173400"),
        "wear_name": "Field-Tested",
        "paint_seed": 42,
        "observed_at": OBSERVED_AT,
    }
    values.update(changes)
    return BuffTradableCandidate(**values)  # type: ignore[arg-type]


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


def _facts() -> BuffListingEligibilityFacts:
    return BuffListingEligibilityFacts(
        is_stattrak=False,
        is_souvenir=False,
        has_special_seed=False,
    )


def _found_lookup(
    candidate: BuffTradableCandidate,
    facts: BuffListingEligibilityFacts,
) -> BuffListingFactsLookupResult:
    return BuffListingFactsLookupResult(
        status=BuffListingFactsLookupStatus.FOUND,
        listing_id=candidate.listing_id,
        market_hash_name=candidate.market_hash_name,
        facts=facts,
    )


def _qualified_result(
    *,
    candidate: BuffTradableCandidate | None = None,
    policy: BuffListingEligibilityPolicy | None = None,
) -> BuffListingQualificationResult:
    selected_candidate = candidate or _candidate()
    selected_policy = policy or _policy()
    facts = _facts()
    lookup_result = _found_lookup(selected_candidate, facts)
    decision = BuffListingEligibilityDecision(
        candidate=selected_candidate,
        facts=facts,
        policy=selected_policy,
        reasons=(),
    )
    return BuffListingQualificationResult(
        candidate=selected_candidate,
        policy=selected_policy,
        lookup_result=lookup_result,
        decision=decision,
    )


def _rejected_result() -> BuffListingQualificationResult:
    candidate = _candidate(available_quantity=0)
    policy = _policy()
    facts = _facts()
    return BuffListingQualificationResult(
        candidate=candidate,
        policy=policy,
        lookup_result=_found_lookup(candidate, facts),
        decision=BuffListingEligibilityDecision(
            candidate=candidate,
            facts=facts,
            policy=policy,
            reasons=(BuffListingIneligibilityReason.INSUFFICIENT_QUANTITY,),
        ),
    )


def _missing_facts_result() -> BuffListingQualificationResult:
    candidate = _candidate()
    return BuffListingQualificationResult(
        candidate=candidate,
        policy=_policy(),
        lookup_result=BuffListingFactsLookupResult(
            status=BuffListingFactsLookupStatus.MISSING,
            listing_id=candidate.listing_id,
            market_hash_name=candidate.market_hash_name,
            facts=None,
        ),
        decision=None,
    )


def test_adapts_qualified_result_to_existing_candidate_listing() -> None:
    result = _qualified_result()

    adapted = adapt_qualified_buff_listing(result)

    assert type(adapted) is CandidateListing
    assert adapted == CandidateListing(
        goods_id="goods-dummy-secret",
        listing_id="listing-dummy-secret",
        market_hash_name="AK-47 | Synthetic (Field-Tested)",
        price_cny=Decimal("123.4500000000000000000000001"),
        float_value=0.1734,
        paint_seed=42,
        inspect_link=None,
        source="buff",
        scanned_at=OBSERVED_AT,
        raw=None,
    )


def test_preserves_decimal_price_without_float_conversion() -> None:
    price = Decimal("123.4500000000000000000000001")

    adapted = adapt_qualified_buff_listing(
        _qualified_result(candidate=_candidate(buy_price_cny=price))
    )

    assert adapted.price_cny is price
    assert type(adapted.price_cny) is Decimal
    assert str(adapted.price_cny) == "123.4500000000000000000000001"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (Decimal("0"), 0.0),
        (Decimal("0.1234567890123456789"), float(Decimal("0.1234567890123456789"))),
        (Decimal("1"), 1.0),
    ],
)
def test_converts_decimal_float_once_at_legacy_boundary(
    source: Decimal,
    expected: float,
) -> None:
    adapted = adapt_qualified_buff_listing(
        _qualified_result(candidate=_candidate(float_value=source))
    )

    assert type(adapted.float_value) is float
    assert adapted.float_value == expected


@pytest.mark.parametrize("quantity", [3, 4])
def test_accepts_quantity_meeting_actual_policy_threshold(quantity: int) -> None:
    policy = _policy(min_available_quantity=3)
    result = _qualified_result(
        candidate=_candidate(available_quantity=quantity),
        policy=policy,
    )

    assert adapt_qualified_buff_listing(result).listing_id == result.candidate.listing_id


def test_repeated_adaptation_is_deterministic_and_independent() -> None:
    result = _qualified_result()

    first = adapt_qualified_buff_listing(result)
    second = adapt_qualified_buff_listing(result)

    assert first == second
    assert first is not second
    assert first is not result.candidate


def test_adaptation_does_not_mutate_qualification_result() -> None:
    result = _qualified_result()
    snapshot = BuffListingQualificationResult(
        candidate=result.candidate,
        policy=result.policy,
        lookup_result=result.lookup_result,
        decision=result.decision,
    )

    adapt_qualified_buff_listing(result)

    assert result == snapshot


@pytest.mark.parametrize(
    "invalid",
    [None, object(), "qualified", _candidate()],
)
def test_rejects_non_result_values_with_fixed_error(invalid: object) -> None:
    with pytest.raises(BuffListingSolverAdapterError) as exc_info:
        adapt_qualified_buff_listing(invalid)  # type: ignore[arg-type]

    assert str(exc_info.value) == "invalid BUFF listing solver adapter contract"
    assert repr(invalid) not in str(exc_info.value)


def test_rejects_result_subclass() -> None:
    class ResultSubclass(BuffListingQualificationResult):
        pass

    result = _qualified_result()
    subclassed = ResultSubclass(
        candidate=result.candidate,
        policy=result.policy,
        lookup_result=result.lookup_result,
        decision=result.decision,
    )

    with pytest.raises(BuffListingSolverAdapterError):
        adapt_qualified_buff_listing(subclassed)


@pytest.mark.parametrize(
    "result_factory",
    [_rejected_result, _missing_facts_result],
)
def test_rejected_and_missing_facts_results_fail_closed(
    result_factory: Callable[[], BuffListingQualificationResult],
) -> None:
    with pytest.raises(BuffListingSolverAdapterError):
        adapt_qualified_buff_listing(result_factory())


def test_legacy_null_goods_id_fails_closed() -> None:
    with pytest.raises(BuffListingSolverAdapterError):
        adapt_qualified_buff_listing(
            _qualified_result(candidate=_candidate(goods_id=None))
        )


def test_missing_float_fails_even_when_policy_permits_it() -> None:
    result = _qualified_result(
        candidate=_candidate(float_value=None),
        policy=_policy(require_float_value=False),
    )

    with pytest.raises(BuffListingSolverAdapterError):
        adapt_qualified_buff_listing(result)


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("candidate", "available_quantity", 0),
        ("candidate", "goods_id", None),
        ("candidate", "float_value", Decimal("NaN")),
        ("policy", "min_available_quantity", 3),
        ("lookup", "listing_id", "other-listing"),
        ("decision", "reasons", (BuffListingIneligibilityReason.MISSING_FLOAT,)),
    ],
)
def test_revalidates_tampered_qualification_snapshots(
    target: str,
    field: str,
    value: object,
) -> None:
    result = _qualified_result()
    nested = {
        "candidate": result.candidate,
        "policy": result.policy,
        "lookup": result.lookup_result,
        "decision": result.decision,
    }[target]
    assert nested is not None
    object.__setattr__(nested, field, value)

    with pytest.raises(BuffListingSolverAdapterError) as exc_info:
        adapt_qualified_buff_listing(result)

    assert str(exc_info.value) == "invalid BUFF listing solver adapter contract"


def test_revalidates_decision_candidate_consistency() -> None:
    result = _qualified_result()
    assert result.decision is not None
    object.__setattr__(result.decision, "candidate", _candidate(listing_id="other"))

    with pytest.raises(BuffListingSolverAdapterError):
        adapt_qualified_buff_listing(result)


def test_revalidates_decision_facts_and_policy_consistency() -> None:
    result = _qualified_result()
    assert result.decision is not None
    object.__setattr__(
        result.decision,
        "facts",
        BuffListingEligibilityFacts(
            is_stattrak=True,
            is_souvenir=False,
            has_special_seed=False,
        ),
    )

    with pytest.raises(BuffListingSolverAdapterError):
        adapt_qualified_buff_listing(result)


def test_candidate_listing_construction_failure_uses_fixed_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_construction(**_values: object) -> CandidateListing:
        raise RuntimeError("Cookie: dummy-secret Authorization: Bearer dummy-token")

    monkeypatch.setattr(adapter_module, "CandidateListing", fail_construction)

    with pytest.raises(BuffListingSolverAdapterError) as exc_info:
        adapt_qualified_buff_listing(_qualified_result())

    assert type(exc_info.value) is BuffListingSolverAdapterError
    assert str(exc_info.value) == "invalid BUFF listing solver adapter contract"
    assert "dummy-secret" not in str(exc_info.value)
    assert "dummy-token" not in repr(exc_info.value)


def test_candidate_listing_memory_error_propagates_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = MemoryError("resource-dummy-secret")

    def fail_construction(**_values: object) -> CandidateListing:
        raise expected

    monkeypatch.setattr(adapter_module, "CandidateListing", fail_construction)

    with pytest.raises(MemoryError) as exc_info:
        adapt_qualified_buff_listing(_qualified_result())

    assert exc_info.value is expected


@pytest.mark.parametrize("error", [asyncio.CancelledError(), KeyboardInterrupt()])
def test_candidate_listing_base_exceptions_propagate_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
) -> None:
    def fail_construction(**_values: object) -> CandidateListing:
        raise error

    monkeypatch.setattr(adapter_module, "CandidateListing", fail_construction)

    with pytest.raises(type(error)) as exc_info:
        adapt_qualified_buff_listing(_qualified_result())

    assert exc_info.value is error


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module.casefold())
    return modules


def test_adapter_has_no_direct_external_runtime_or_solver_imports() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "buff_listing_solver_adapter.py"
    )

    assert _imported_modules(module_path) == {
        "__future__",
        "math",
        "app.services.buff_listing_facts",
        "app.services.buff_listing_qualification",
        "app.services.market_scan_service",
    }


def test_adapter_has_no_external_runtime_or_solver_calls() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "buff_listing_solver_adapter.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    called_names = {
        node.func.id.casefold()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    forbidden_calls = {
        "lookup_facts",
        "evaluate_buff_listing_eligibility",
        "qualify",
        "solve_recipes",
        "create_task",
        "create_thread",
        "getenv",
        "open",
        "sleep",
    }

    assert called_names.isdisjoint(forbidden_calls)


def test_runtime_modules_do_not_reverse_import_adapter() -> None:
    project_root = Path(__file__).resolve().parents[1]
    runtime_paths = [
        project_root / "app" / "main.py",
        project_root / "app" / "config.py",
        project_root / "app" / "services" / "buff_listing.py",
        project_root / "app" / "services" / "buff_listing_parser.py",
        project_root / "app" / "services" / "buff_listing_facts.py",
        project_root / "app" / "services" / "buff_listing_eligibility.py",
        project_root / "app" / "services" / "buff_listing_qualification.py",
        project_root / "app" / "services" / "market_scan_service.py",
        project_root / "app" / "services" / "recipe_solver.py",
        project_root / "app" / "services" / "valuation_service.py",
        project_root / "app" / "services" / "pipeline_service.py",
        project_root / "app" / "jobs" / "scheduler.py",
    ]

    for path in runtime_paths:
        assert "app.services.buff_listing_solver_adapter" not in _imported_modules(path)
