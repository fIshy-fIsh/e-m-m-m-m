from __future__ import annotations

import ast
import asyncio
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from inspect import Parameter, signature
from pathlib import Path
from typing import get_type_hints

import pytest

import app.services.live_metadata_catalog as catalog_module
from app.services.live_metadata_catalog import (
    LiveCandidateBinding,
    LiveCandidateClassification,
    LiveCandidateRejection,
    LiveCandidateRejectionReason,
    LiveMetadataCatalogError,
    LiveSolverBucket,
    LiveSolverBucketKey,
    SkinMetadataCatalog,
    classify_steamapis_snapshot,
)
from app.services.market_scan_service import CandidateListing
from app.services.metadata_models import SkinMetadata
from app.services.steamapis_listing import (
    SteamApisListingEventType,
    SteamApisListingObservation,
    make_steamapis_source_offer_id,
)
from app.services.steamapis_offer_pool import SteamApisOfferPoolSnapshot

BASE_TIME = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
PURCHASE_LINK = "https://example.invalid/manual/dummy-token"
INSPECT_LINK = "steam://rungame/730/dummy-inspect"
MARKET_NAME = "AK-47 | Synthetic (Field-Tested)"
MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "live_metadata_catalog.py"
)


def _skin(
    *,
    market_hash_name: str = MARKET_NAME,
    rarity: str = "Restricted",
    collection_name: str | None = "Collection Alpha",
    min_float: float = 0.0,
    max_float: float = 1.0,
    stattrak: bool = False,
    souvenir: bool = False,
    raw: dict[str, object] | None = None,
) -> SkinMetadata:
    return SkinMetadata(
        market_hash_name=market_hash_name,
        name=market_hash_name,
        weapon="AK-47",
        rarity=rarity,
        category="Rifle",
        collection_name=collection_name,
        min_float=min_float,
        max_float=max_float,
        stattrak=stattrak,
        souvenir=souvenir,
        paint_index=675,
        raw={"dummy": "payload"} if raw is None else raw,
    )


def _observation(
    *,
    suffix: str = "one",
    market_hash_name: str = MARKET_NAME,
    float_value: Decimal = Decimal("0.25"),
    price_cny: Decimal = Decimal("123.45"),
    message_timestamp: datetime = BASE_TIME,
    days_trade_locked: int | None = None,
) -> SteamApisListingObservation:
    purchase_link = f"{PURCHASE_LINK}/{suffix}"
    return SteamApisListingObservation(
        source_offer_id=make_steamapis_source_offer_id(
            "Buff163",
            "CS2",
            purchase_link,
        ),
        event_type=SteamApisListingEventType.ADDED,
        marketplace="Buff163",
        game="CS2",
        market_hash_name=market_hash_name,
        purchase_link=purchase_link,
        inspect_link=INSPECT_LINK,
        price_cny=price_cny,
        float_value=float_value,
        paint_index=675,
        paint_seed=42,
        days_trade_locked=days_trade_locked,
        found_at=message_timestamp - timedelta(minutes=1),
        message_timestamp=message_timestamp,
        stickers=(),
    )


def _snapshot(*observations: SteamApisListingObservation) -> SteamApisOfferPoolSnapshot:
    return SteamApisOfferPoolSnapshot(observations=tuple(observations))


def _candidate(
    observation: SteamApisListingObservation,
    *,
    float_value: float | None = 0.25,
) -> CandidateListing:
    source_local_id = f"steamapis:buff163:{observation.source_offer_id}"
    return CandidateListing(
        goods_id=source_local_id,
        listing_id=source_local_id,
        market_hash_name=observation.market_hash_name,
        price_cny=observation.price_cny,
        float_value=float_value,
        paint_seed=observation.paint_seed,
        inspect_link=observation.inspect_link,
        source="steamapis:buff163",
        scanned_at=observation.message_timestamp,
        raw=None,
    )


def _classify(
    observations: tuple[SteamApisListingObservation, ...],
    skins: list[SkinMetadata],
) -> LiveCandidateClassification:
    return classify_steamapis_snapshot(
        _snapshot(*observations),
        SkinMetadataCatalog(skins=skins),
    )


def test_public_api_fields_and_reason_codes_are_exact() -> None:
    assert catalog_module.__all__ == (
        "LiveMetadataCatalogError",
        "LiveCandidateRejectionReason",
        "LiveSolverBucketKey",
        "LiveCandidateBinding",
        "LiveCandidateRejection",
        "LiveSolverBucket",
        "LiveCandidateClassification",
        "SkinMetadataCatalog",
        "classify_steamapis_snapshot",
    )
    assert [field.name for field in fields(LiveSolverBucketKey)] == [
        "input_rarity",
        "stattrak",
        "souvenir",
    ]
    assert [field.name for field in fields(LiveCandidateBinding)] == [
        "source_offer_id",
        "candidate",
        "skin_metadata",
    ]
    assert [field.name for field in fields(LiveCandidateRejection)] == [
        "source_offer_id",
        "reason_code",
    ]
    assert [field.name for field in fields(LiveSolverBucket)] == [
        "key",
        "bindings",
        "affected_collections",
    ]
    assert [field.name for field in fields(LiveCandidateClassification)] == [
        "eligible",
        "rejected",
        "buckets",
    ]
    assert tuple(reason.value for reason in LiveCandidateRejectionReason) == (
        "metadata_not_found",
        "missing_collection",
        "candidate_float_missing",
        "float_outside_skin_range",
    )


def test_public_signatures_and_type_hints_are_exact() -> None:
    constructor = list(signature(SkinMetadataCatalog).parameters.values())
    assert [parameter.name for parameter in constructor] == ["skins"]
    assert constructor[0].kind is Parameter.KEYWORD_ONLY
    assert get_type_hints(SkinMetadataCatalog.get_by_market_hash_name) == {
        "market_hash_name": str,
        "return": SkinMetadata | None,
    }
    assert get_type_hints(SkinMetadataCatalog.get_by_solver_bucket_key) == {
        "key": LiveSolverBucketKey,
        "return": tuple[SkinMetadata, ...],
    }
    assert get_type_hints(classify_steamapis_snapshot) == {
        "snapshot": SteamApisOfferPoolSnapshot,
        "catalog": SkinMetadataCatalog,
        "return": LiveCandidateClassification,
    }


def test_public_dtos_are_frozen_keyword_only_and_repr_safe() -> None:
    observation = _observation()
    classification = _classify((observation,), [_skin()])
    binding = classification.eligible[0]
    rejection = LiveCandidateRejection(
        source_offer_id=observation.source_offer_id,
        reason_code=LiveCandidateRejectionReason.METADATA_NOT_FOUND,
    )

    with pytest.raises(TypeError):
        LiveSolverBucketKey("Restricted", False, False)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        binding.source_offer_id = "0" * 64  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        rejection.reason_code = (  # type: ignore[misc]
            LiveCandidateRejectionReason.MISSING_COLLECTION
        )
    for value in (
        binding,
        rejection,
        classification.buckets[0],
        classification,
    ):
        rendered = repr(value)
        assert observation.source_offer_id not in rendered
        assert observation.purchase_link not in rendered
        assert observation.inspect_link not in rendered
        assert observation.market_hash_name not in rendered
        assert str(observation.price_cny) not in rendered


def test_catalog_valid_construction_exact_lookup_and_no_raw() -> None:
    source = _skin()
    catalog = SkinMetadataCatalog(skins=[source])

    found = catalog.get_by_market_hash_name(MARKET_NAME)

    assert found is not None
    assert found == replace(source, raw=None)
    assert found is not source
    assert found.raw is None
    assert catalog.get_by_market_hash_name("ak-47 | Synthetic (Field-Tested)") is None
    assert catalog.get_by_market_hash_name("missing") is None


@pytest.mark.parametrize("skins", [[], (), "not-a-sequence", None])
def test_catalog_rejects_empty_or_invalid_source(skins: object) -> None:
    with pytest.raises(LiveMetadataCatalogError) as exc_info:
        SkinMetadataCatalog(skins=skins)  # type: ignore[arg-type]

    assert str(exc_info.value) == "invalid live metadata catalog contract"


def test_catalog_rejects_duplicate_exact_name_without_last_wins() -> None:
    duplicate = _skin(collection_name="Collection Beta", min_float=0.1)

    with pytest.raises(LiveMetadataCatalogError):
        SkinMetadataCatalog(skins=[_skin(), duplicate])


def test_catalog_allows_case_distinct_names() -> None:
    upper = _skin(market_hash_name="Case Name")
    lower = _skin(market_hash_name="case name", collection_name="Collection Beta")
    catalog = SkinMetadataCatalog(skins=[upper, lower])

    assert catalog.get_by_market_hash_name("Case Name") == replace(upper, raw=None)
    assert catalog.get_by_market_hash_name("case name") == replace(lower, raw=None)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("market_hash_name", True),
        ("rarity", 1),
        ("name", 1),
        ("collection_name", False),
        ("min_float", Decimal("0")),
        ("min_float", float("nan")),
        ("max_float", float("inf")),
        ("stattrak", 1),
        ("souvenir", 0),
        ("paint_index", 1.0),
    ],
)
def test_catalog_rejects_unsafe_metadata_primitives(
    field_name: str,
    invalid_value: object,
) -> None:
    skin = _skin()
    object.__setattr__(skin, field_name, invalid_value)

    with pytest.raises(LiveMetadataCatalogError):
        SkinMetadataCatalog(skins=[skin])


def test_catalog_accepts_finite_ordered_bounds_outside_unit_interval() -> None:
    source = _skin(min_float=-0.5, max_float=1.5)

    found = SkinMetadataCatalog(skins=[source]).get_by_market_hash_name(MARKET_NAME)

    assert found is not None
    assert (found.min_float, found.max_float) == (-0.5, 1.5)


def test_catalog_is_detached_from_source_list_record_and_raw_mutation() -> None:
    raw = {"nested": "original"}
    source = _skin(raw=raw)
    source_list = [source]
    catalog = SkinMetadataCatalog(skins=source_list)

    source_list.clear()
    raw["nested"] = "changed"
    object.__setattr__(source, "rarity", "Covert")

    found = catalog.get_by_market_hash_name(MARKET_NAME)
    assert found is not None
    assert found.rarity == "Restricted"
    assert found.raw is None


def test_catalog_lookup_returns_fresh_values_after_return_tampering() -> None:
    catalog = SkinMetadataCatalog(skins=[_skin()])
    first = catalog.get_by_market_hash_name(MARKET_NAME)
    assert first is not None
    object.__setattr__(first, "rarity", "Covert")

    second = catalog.get_by_market_hash_name(MARKET_NAME)

    assert second is not None
    assert second.rarity == "Restricted"
    assert second is not first


def test_catalog_solver_bucket_index_is_deterministic_and_exact() -> None:
    zulu = _skin(market_hash_name="Zulu")
    alpha = _skin(market_hash_name="Alpha", collection_name=None)
    other = _skin(market_hash_name="Beta", stattrak=True)
    first = SkinMetadataCatalog(skins=[zulu, other, alpha])
    second = SkinMetadataCatalog(skins=[alpha, zulu, other])
    key = LiveSolverBucketKey(
        input_rarity="Restricted",
        stattrak=False,
        souvenir=False,
    )

    assert tuple(
        skin.market_hash_name for skin in first.get_by_solver_bucket_key(key)
    ) == ("Alpha", "Zulu")
    assert first.get_by_solver_bucket_key(key) == second.get_by_solver_bucket_key(key)
    assert first.get_by_solver_bucket_key(
        LiveSolverBucketKey(
            input_rarity="Covert",
            stattrak=False,
            souvenir=False,
        )
    ) == ()


@pytest.mark.parametrize(
    "method_call",
    [
        lambda catalog: catalog.get_by_market_hash_name(1),
        lambda catalog: catalog.get_by_solver_bucket_key("Restricted"),
    ],
)
def test_catalog_lookup_rejects_invalid_public_inputs(method_call: object) -> None:
    catalog = SkinMetadataCatalog(skins=[_skin()])

    with pytest.raises(LiveMetadataCatalogError):
        method_call(catalog)  # type: ignore[operator]


def test_valid_observation_binds_existing_step2b_candidate_and_metadata() -> None:
    observation = _observation(days_trade_locked=None)

    classification = _classify((observation,), [_skin()])

    assert classification.rejected == ()
    assert len(classification.eligible) == 1
    binding = classification.eligible[0]
    assert binding.source_offer_id == observation.source_offer_id
    assert binding.candidate == _candidate(observation)
    assert binding.candidate.raw is None
    assert binding.skin_metadata == replace(_skin(), raw=None)
    assert binding.skin_metadata.raw is None
    assert observation.purchase_link not in repr(binding)


def test_metadata_not_found_is_explicit_and_not_silently_skipped() -> None:
    observation = _observation(market_hash_name="Unknown")

    classification = _classify((observation,), [_skin()])

    assert classification.eligible == ()
    assert classification.rejected == (
        LiveCandidateRejection(
            source_offer_id=observation.source_offer_id,
            reason_code=LiveCandidateRejectionReason.METADATA_NOT_FOUND,
        ),
    )


def test_missing_collection_is_rejected_without_name_inference() -> None:
    observation = _observation()

    classification = _classify(
        (observation,),
        [_skin(collection_name=None)],
    )

    assert classification.rejected[0].reason_code is (
        LiveCandidateRejectionReason.MISSING_COLLECTION
    )


def test_candidate_float_missing_is_typed_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation = _observation()
    monkeypatch.setattr(
        catalog_module,
        "adapt_steamapis_listing_to_candidate",
        lambda value: _candidate(value, float_value=None),
    )

    classification = _classify((observation,), [_skin()])

    assert classification.rejected[0].reason_code is (
        LiveCandidateRejectionReason.CANDIDATE_FLOAT_MISSING
    )


@pytest.mark.parametrize(
    ("float_value", "expected_eligible"),
    [
        (Decimal("0.10"), True),
        (Decimal("0.50"), True),
        (Decimal("0.90"), True),
        (Decimal("0.09"), False),
        (Decimal("0.91"), False),
    ],
)
def test_float_range_is_inclusive(
    float_value: Decimal,
    expected_eligible: bool,
) -> None:
    classification = _classify(
        (_observation(float_value=float_value),),
        [_skin(min_float=0.1, max_float=0.9)],
    )

    assert bool(classification.eligible) is expected_eligible
    if not expected_eligible:
        assert classification.rejected[0].reason_code is (
            LiveCandidateRejectionReason.FLOAT_OUTSIDE_SKIN_RANGE
        )


def test_rejection_precedence_checks_missing_collection_before_missing_float(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation = _observation()
    monkeypatch.setattr(
        catalog_module,
        "adapt_steamapis_listing_to_candidate",
        lambda value: _candidate(value, float_value=None),
    )

    classification = _classify(
        (observation,),
        [_skin(collection_name=None)],
    )

    assert classification.rejected[0].reason_code is (
        LiveCandidateRejectionReason.MISSING_COLLECTION
    )


def test_distinct_source_ids_with_same_name_are_preserved() -> None:
    first = _observation(suffix="one", price_cny=Decimal("100"))
    second = _observation(suffix="two", price_cny=Decimal("101"))

    classification = _classify((second, first), [_skin()])

    assert len(classification.eligible) == 2
    assert {binding.source_offer_id for binding in classification.eligible} == {
        first.source_offer_id,
        second.source_offer_id,
    }
    assert len(classification.buckets[0].bindings) == 2


def test_duplicate_source_id_in_supplied_snapshot_fails_closed() -> None:
    observation = _observation()
    snapshot = SteamApisOfferPoolSnapshot(observations=(observation,))
    object.__setattr__(snapshot, "observations", (observation, observation))

    with pytest.raises(LiveMetadataCatalogError):
        classify_steamapis_snapshot(snapshot, SkinMetadataCatalog(skins=[_skin()]))


def test_eligible_and_rejected_preserve_snapshot_subsequences() -> None:
    eligible_later = _observation(
        suffix="eligible-later",
        market_hash_name="Zulu",
        message_timestamp=BASE_TIME + timedelta(seconds=2),
    )
    rejected = _observation(
        suffix="rejected",
        market_hash_name="Middle",
        message_timestamp=BASE_TIME + timedelta(seconds=1),
    )
    eligible_first = _observation(
        suffix="eligible-first",
        market_hash_name="Alpha",
        message_timestamp=BASE_TIME,
    )
    snapshot = _snapshot(eligible_later, rejected, eligible_first)

    classification = classify_steamapis_snapshot(
        snapshot,
        SkinMetadataCatalog(
            skins=[
                _skin(market_hash_name="Zulu"),
                _skin(market_hash_name="Alpha"),
            ]
        ),
    )

    assert [binding.candidate.market_hash_name for binding in classification.eligible] == [
        "Alpha",
        "Zulu",
    ]
    assert [rejection.source_offer_id for rejection in classification.rejected] == [
        rejected.source_offer_id
    ]


def test_same_rarity_mode_across_collections_uses_one_bucket() -> None:
    alpha = _observation(suffix="alpha", market_hash_name="Alpha Input")
    beta = _observation(suffix="beta", market_hash_name="Beta Input")

    classification = _classify(
        (beta, alpha),
        [
            _skin(
                market_hash_name="Alpha Input",
                collection_name="Collection Alpha",
            ),
            _skin(
                market_hash_name="Beta Input",
                collection_name="Collection Beta",
            ),
        ],
    )

    assert len(classification.buckets) == 1
    bucket = classification.buckets[0]
    assert bucket.key == LiveSolverBucketKey(
        input_rarity="Restricted",
        stattrak=False,
        souvenir=False,
    )
    assert bucket.affected_collections == frozenset(
        {"Collection Alpha", "Collection Beta"}
    )
    assert classification.affected_collections == bucket.affected_collections
    assert bucket.bindings == classification.eligible


@pytest.mark.parametrize(
    ("field_name", "first_value", "second_value"),
    [
        ("rarity", "Restricted", "Classified"),
        ("stattrak", False, True),
        ("souvenir", False, True),
    ],
)
def test_each_solver_key_dimension_separates_buckets(
    field_name: str,
    first_value: object,
    second_value: object,
) -> None:
    first_skin = _skin(market_hash_name="Alpha")
    second_skin = _skin(market_hash_name="Beta")
    object.__setattr__(first_skin, field_name, first_value)
    object.__setattr__(second_skin, field_name, second_value)

    classification = _classify(
        (
            _observation(suffix="beta", market_hash_name="Beta"),
            _observation(suffix="alpha", market_hash_name="Alpha"),
        ),
        [second_skin, first_skin],
    )

    assert len(classification.buckets) == 2
    assert classification.buckets == tuple(
        sorted(
            classification.buckets,
            key=lambda bucket: (
                bucket.key.input_rarity,
                bucket.key.stattrak,
                bucket.key.souvenir,
            ),
        )
    )


def test_classification_is_empty_for_empty_snapshot() -> None:
    classification = classify_steamapis_snapshot(
        _snapshot(),
        SkinMetadataCatalog(skins=[_skin()]),
    )

    assert classification == LiveCandidateClassification(
        eligible=(),
        rejected=(),
        buckets=(),
    )
    assert classification.affected_collections == frozenset()


def test_adapter_is_reused_exactly_once_per_observation_in_snapshot_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _observation(suffix="first", market_hash_name="Alpha")
    second = _observation(suffix="second", market_hash_name="Beta")
    snapshot = _snapshot(second, first)
    calls: list[str] = []
    real_adapter = catalog_module.adapt_steamapis_listing_to_candidate

    def recording_adapter(
        observation: SteamApisListingObservation,
    ) -> CandidateListing:
        calls.append(observation.source_offer_id)
        return real_adapter(observation)

    monkeypatch.setattr(
        catalog_module,
        "adapt_steamapis_listing_to_candidate",
        recording_adapter,
    )

    classify_steamapis_snapshot(
        snapshot,
        SkinMetadataCatalog(
            skins=[_skin(market_hash_name="Alpha"), _skin(market_hash_name="Beta")]
        ),
    )

    assert calls == [observation.source_offer_id for observation in snapshot.observations]


def test_late_adapter_failure_is_atomic_fixed_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _observation(suffix="first", market_hash_name="Alpha")
    second = _observation(suffix="second", market_hash_name="Beta")
    real_adapter = catalog_module.adapt_steamapis_listing_to_candidate
    calls = 0

    def failing_adapter(
        observation: SteamApisListingObservation,
    ) -> CandidateListing:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError(
                f"{PURCHASE_LINK} {INSPECT_LINK} dummy-cookie dummy-api-key"
            )
        return real_adapter(observation)

    monkeypatch.setattr(
        catalog_module,
        "adapt_steamapis_listing_to_candidate",
        failing_adapter,
    )

    with pytest.raises(LiveMetadataCatalogError) as exc_info:
        _classify(
            (first, second),
            [_skin(market_hash_name="Alpha"), _skin(market_hash_name="Beta")],
        )

    assert str(exc_info.value) == "invalid live metadata catalog contract"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True
    rendered = repr(exc_info.value)
    for sensitive in (
        PURCHASE_LINK,
        INSPECT_LINK,
        "dummy-cookie",
        "dummy-api-key",
        first.source_offer_id,
        first.market_hash_name,
    ):
        assert sensitive not in rendered


@pytest.mark.parametrize(
    "expected",
    [MemoryError(), KeyboardInterrupt(), asyncio.CancelledError()],
    ids=["memory", "keyboard-interrupt", "cancelled"],
)
def test_classification_propagates_memory_and_control_flow_identity(
    monkeypatch: pytest.MonkeyPatch,
    expected: BaseException,
) -> None:
    observation = _observation()

    def fail(value: SteamApisListingObservation) -> CandidateListing:
        raise expected

    monkeypatch.setattr(
        catalog_module,
        "adapt_steamapis_listing_to_candidate",
        fail,
    )

    with pytest.raises(type(expected)) as exc_info:
        _classify((observation,), [_skin()])

    assert exc_info.value is expected


def test_public_result_constructors_reject_inconsistent_bucket_state() -> None:
    observation = _observation()
    classification = _classify((observation,), [_skin()])
    bucket = classification.buckets[0]

    with pytest.raises(LiveMetadataCatalogError):
        LiveSolverBucket(
            key=bucket.key,
            bindings=bucket.bindings,
            affected_collections=frozenset({"Wrong Collection"}),
        )
    with pytest.raises(LiveMetadataCatalogError):
        LiveCandidateClassification(
            eligible=classification.eligible,
            rejected=(),
            buckets=(),
        )


def test_module_has_exact_import_boundary() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )

    assert imports == {
        "__future__",
        "math",
        "collections.abc",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "types",
        "app.services.market_scan_service",
        "app.services.metadata_models",
        "app.services.steamapis_candidate_adapter",
        "app.services.steamapis_offer_pool",
    }


def test_module_has_no_external_runtime_solver_or_inference_behavior() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_fragments = {
        "websocket",
        "httpx",
        "requests",
        "urllib",
        "socket",
        "redis",
        "steamdt",
        "buff_client",
        "metadata_provider",
        "metadata_service",
        "recipe_solver",
        "tradeup_engine",
        "construct_recipes",
        "solve_recipes",
        "calculate_adjusted_float",
        "ev_service",
        "risk_filter",
        "valuation",
        "pipeline",
        "scheduler",
        "discord",
        "fastapi",
        "sqlalchemy",
        "getenv",
        "environ",
        "urlparse",
        "webbrowser",
        "create_task",
        "thread",
        "sleep",
        "retry",
        "purchase(",
        "login(",
    }
    lowered = source.lower()
    assert not {fragment for fragment in forbidden_fragments if fragment in lowered}

    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not called_names.intersection(
        {"open", "exec", "eval", "compile", "getattr", "setattr"}
    )


def test_protected_runtime_modules_do_not_reverse_import_catalog() -> None:
    root = MODULE_PATH.parents[2]
    protected_paths = (
        root / "app" / "services" / "steamapis_listing.py",
        root / "app" / "services" / "steamapis_candidate_adapter.py",
        root / "app" / "services" / "steamapis_offer_pool.py",
        root / "app" / "services" / "recipe_solver.py",
        root / "app" / "services" / "pipeline_service.py",
    )

    for path in protected_paths:
        assert "live_metadata_catalog" not in path.read_text(encoding="utf-8")
