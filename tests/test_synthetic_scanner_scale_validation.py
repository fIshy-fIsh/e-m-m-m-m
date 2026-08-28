from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pytest

import app.services.trade_up_pipeline as pipeline_module
from app.services.trade_up_pipeline import (
    SyntheticBasket,
    SyntheticBasketConfig,
    SyntheticScaleCase,
    build_synthetic_basket,
    compare_partition_paths,
    drive_enrichment_path,
    drive_pipeline_path,
)
from app.services.tradeup_engine import InputItem

PIPELINE_FORBIDDEN_TOKENS = (
    "buff_listing",
    "buff_listing_provider",
    "buff_item_identity",
    "buff_client",
    "steamapis",
    "steamdt",
    "os.environ",
    "open(",
    "json",
    "purchase",
    "scanner",
    "scheduler",
    "aiohttp",
    "websockets",
)

TEST_FORBIDDEN_IMPORTS = (
    "app.services.buff_listing",
    "app.services.buff_item_identity",
    "app.services.buff_client",
    "app.services.steamdt",
    "app.services.steamapis",
    "app.services.live_recipe_valuation",
    "app.services.metadata_provider",
    "app.services.live_metadata_catalog",
    "app.services.market_scan_service",
    "app.jobs.scheduler",
    "app.api",
    "app.db",
    "app.cache",
    "app.webhook",
    "app.services.scanner",
)

PROTECTED_CORE_FILES = (
    "app/services/tradeup_engine.py",
    "app/services/recipe_solver.py",
    "app/services/ev_service.py",
    "app/services/risk_filter.py",
    "app/services/valuation_service.py",
    "app/services/live_recipe_valuation.py",
    "app/services/metadata_models.py",
    "app/services/metadata_provider.py",
    "app/services/metadata_service.py",
    "app/services/live_metadata_catalog.py",
    "app/services/buff_listing.py",
    "app/services/buff_listing_parser.py",
    "app/services/buff_listing_facts.py",
    "app/services/buff_listing_eligibility.py",
    "app/services/buff_listing_qualification.py",
    "app/services/buff_listing_solver_adapter.py",
    "app/services/buff_client.py",
    "app/services/trade_up_input_enrichment.py",
    "app/services/trade_up_input_candidate.py",
)


@dataclass(frozen=True, kw_only=True)
class SyntheticValidationReport:
    """Test-local aggregation of counters and reproducibility for one case."""

    label: str
    seed: int
    pipeline_kept_count: int
    pipeline_skip_histogram: dict[str, int]
    enrichment_kept_count: int
    enrichment_rejected_count: int
    enrichment_rejection_histogram: dict[str, int]
    recipes_built: int
    recipes_attempted: int
    recipes_rejected_by_engine: tuple[str, ...]
    risk_passed: int
    risk_rejected: int
    risk_reason_histogram: dict[str, int]
    recipe_hashes: tuple[str, ...] = field(default_factory=tuple)
    partition_agreement: bool = False


def _small_config() -> SyntheticBasketConfig:
    return SyntheticBasketConfig(
        label="SMALL",
        seed=11,
        collections=("Synthetic Collection A",),
        inputs_per_collection=10,
        price_cny_min=Decimal("10.00"),
        price_cny_max=Decimal("20.00"),
    )


def _mixed_config() -> SyntheticBasketConfig:
    return SyntheticBasketConfig(
        label="MIXED",
        seed=23,
        collections=("Synthetic Collection A", "Synthetic Collection B"),
        inputs_per_collection=10,
        price_cny_min=Decimal("10.00"),
        price_cny_max=Decimal("25.00"),
        unresolved_ratio=0.2,
        missing_metadata_ratio=0.1,
    )


def _dirty_config() -> SyntheticBasketConfig:
    return SyntheticBasketConfig(
        label="DIRTY",
        seed=37,
        collections=("Synthetic Collection A", "Synthetic Collection B"),
        inputs_per_collection=10,
        price_cny_min=Decimal("5.00"),
        price_cny_max=Decimal("30.00"),
        unresolved_ratio=0.5,
        missing_metadata_ratio=0.3,
    )


def _scale_cases() -> tuple[SyntheticScaleCase, ...]:
    out: list[SyntheticScaleCase] = []
    for config in (_small_config(), _mixed_config(), _dirty_config()):
        basket = build_synthetic_basket(config)
        expected_unresolved = sum(
            1 for c in basket.candidates if c.market_hash_name is None
        )
        expected_missing = sum(
            1
            for c in basket.candidates
            if c.market_hash_name is not None
            and c.market_hash_name not in basket.metadata
        )
        out.append(
            SyntheticScaleCase(
                label=config.label,
                basket=basket,
                expected_unresolved_count=expected_unresolved,
                expected_missing_metadata_count=expected_missing,
            )
        )
    return tuple(out)


def _input_item_signature(item: InputItem) -> tuple[object, ...]:
    return (
        item.market_hash_name,
        item.price_cny,
        Decimal(str(item.actual_float)),
        item.stattrak,
        item.souvenir,
    )


def _run_engine_pipeline(
    items: list[InputItem],
    collection_to_output: dict[str, list[tuple[str, Decimal, float, float]]],
) -> tuple[list, list[str], list[str]]:
    """Run the existing trade-up engine over one collection-bucket at a time.

    Returns (recipe_payloads, recipe_hashes, engine_rejection_substrings).
    `collection_to_output` maps a collection name to a list of
    (market_hash_name, price, min_float, max_float) tuples describing the
    output candidates for that collection.
    """

    from app.services.tradeup_engine import (
        OutputCandidate,
        TradeupResult,
        calculate_tradeup_results,
    )

    payloads: list[dict[str, object]] = []
    hashes: list[str] = []
    rejections: list[str] = []

    grouped: dict[str, list[InputItem]] = {}
    for item in items:
        grouped.setdefault(item.collection_name, []).append(item)

    for collection_name, bucket in grouped.items():
        if collection_name not in collection_to_output:
            rejections.append("MISSING_COLLECTION")
            continue
        outputs = [
            OutputCandidate(
                market_hash_name=name,
                collection_name=collection_name,
                rarity="Classified",
                min_float=min_float,
                max_float=max_float,
                estimated_price_cny=price,
            )
            for (name, price, min_float, max_float) in (
                collection_to_output[collection_name]
            )
        ]
        try:
            results = calculate_tradeup_results(bucket, {collection_name: outputs})
        except ValueError as exc:
            rejections.append(_classify_engine_error(str(exc)))
            continue
        recipe_hash = _compute_recipe_hash(bucket)
        hashes.append(recipe_hash)
        payloads.append(
            {
                "collection_name": collection_name,
                "results": list(results),
                "bucket_size": len(bucket),
            }
        )
        assert isinstance(results[0], TradeupResult)

    return payloads, hashes, rejections


def _compute_recipe_hash(items: list[InputItem]) -> str:
    import hashlib

    sorted_items = sorted(
        items,
        key=lambda item: (
            item.market_hash_name,
            item.actual_float,
            item.price_cny,
        ),
    )
    source = "|".join(
        f"{item.market_hash_name}::{item.collection_name}::{item.actual_float}::"
        f"{item.price_cny}::{item.stattrak}::{item.souvenir}"
        for item in sorted_items
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _classify_engine_error(message: str) -> str:
    lowered = message.casefold()
    if "same rarity" in lowered:
        return "MIXED_RARITY"
    if "stattrak" in lowered:
        return "MIXED_STATTRAK"
    if "souvenir" in lowered:
        return "MIXED_SOUVENIR"
    if "missing output candidates" in lowered:
        return "MISSING_COLLECTION"
    return "ENGINE_VALIDATION_OTHER"


def _evaluate_ev_and_risk(
    payloads: list[dict[str, object]],
    recipes_attempted: int,
) -> tuple[int, int, dict[str, int]]:
    from app.services.ev_service import calculate_opportunity_metrics
    from app.services.risk_filter import RiskFilterConfig, evaluate_opportunity

    risk_config = RiskFilterConfig(
        min_roi=Decimal("0"),
        min_expected_profit_cny=Decimal("0"),
        max_worst_case_loss_pct=Decimal("1"),
        min_profit_probability=0.0,
        max_input_total_cost_cny=Decimal("999999"),
    )
    risk_passed = 0
    risk_rejected = 0
    risk_histogram: Counter[str] = Counter()
    for payload in payloads:
        results = payload["results"]
        assert isinstance(results, list)
        bucket: list[InputItem] = [
            item
            for item in [
                InputItem(
                    market_hash_name=_dummy_name(),
                    collection_name=str(payload["collection_name"]),
                    rarity="Restricted",
                    actual_float=0.1,
                    min_float=0.0,
                    max_float=1.0,
                    price_cny=Decimal("1"),
                )
                for _ in range(int(payload["bucket_size"]))
            ]
        ]
        metrics = calculate_opportunity_metrics(
            input_items=bucket,
            tradeup_results=results,
            sell_fee_rate=Decimal("0.05"),
        )
        decision = evaluate_opportunity(
            metrics=metrics,
            input_items=bucket,
            config=risk_config,
            paint_seeds=None,
        )
        if decision.passed:
            risk_passed += 1
        else:
            risk_rejected += 1
        risk_histogram.update(decision.reason_codes)
    return risk_passed, risk_rejected, dict(risk_histogram)


_dummy_counter = 0


def _dummy_name() -> str:
    global _dummy_counter
    _dummy_counter += 1
    return f"recompute-bucket-{_dummy_counter}"


def _build_output_catalog(
    basket: SyntheticBasket,
) -> dict[str, list[tuple[str, Decimal, float, float]]]:
    catalog: dict[str, list[tuple[str, Decimal, float, float]]] = {}
    for collection_name, metadata in basket.metadata.items():
        catalog[metadata.collection_name] = [
            (
                f"Synthetic Output | {collection_name} (Target)",
                Decimal("60.00"),
                0.0,
                1.0,
            )
        ]
    return catalog


def _drive_case(case: SyntheticScaleCase) -> SyntheticValidationReport:
    pipeline_items, pipeline_skips = drive_pipeline_path(case.basket)
    enrichment_result = drive_enrichment_path(case.basket)
    comparison = compare_partition_paths(
        pipeline_items, pipeline_skips, enrichment_result
    )

    signatures = sorted(
        _input_item_signature(item) for item in pipeline_items
    )
    enrichment_signatures = sorted(
        _input_item_signature(enriched.input_item)
        for enriched in enrichment_result.enriched
    )
    assert signatures == enrichment_signatures, (
        f"{case.label}: partition signatures diverged between paths"
    )

    catalog = _build_output_catalog(case.basket)
    enriched_items = [
        enriched.input_item for enriched in enrichment_result.enriched
    ]
    payloads, hashes, engine_rejections = _run_engine_pipeline(
        enriched_items, catalog
    )
    recipes_attempted = len(
        {item.collection_name for item in enriched_items}
    )
    risk_passed, risk_rejected, risk_histogram = _evaluate_ev_and_risk(
        payloads, recipes_attempted
    )

    return SyntheticValidationReport(
        label=case.label,
        seed=case.basket.config.seed,
        pipeline_kept_count=comparison.pipeline_kept_count,
        pipeline_skip_histogram=dict(comparison.pipeline_skip_histogram),
        enrichment_kept_count=comparison.enrichment_kept_count,
        enrichment_rejected_count=comparison.enrichment_rejected_count,
        enrichment_rejection_histogram={
            reason.name: count
            for reason, count in comparison.enrichment_rejection_histogram.items()
        },
        recipes_built=len(payloads),
        recipes_attempted=recipes_attempted,
        recipes_rejected_by_engine=tuple(engine_rejections),
        risk_passed=risk_passed,
        risk_rejected=risk_rejected,
        risk_reason_histogram=risk_histogram,
        recipe_hashes=tuple(hashes),
        partition_agreement=comparison.partition_agreement,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_public_api_is_exact() -> None:
    assert pipeline_module.__all__ == (
        "TradeUpInputMetadata",
        "TradeUpInputMetadataResolver",
        "InMemoryTradeUpInputMetadataResolver",
        "candidates_to_input_items",
        "SyntheticBasketConfig",
        "SyntheticBasket",
        "SyntheticScaleCase",
        "build_synthetic_basket",
        "drive_pipeline_path",
        "drive_enrichment_path",
        "compare_partition_paths",
    )


def test_synthetic_basket_is_deterministic() -> None:
    basket_a = build_synthetic_basket(_small_config())
    basket_b = build_synthetic_basket(_small_config())
    assert [c.listing_id for c in basket_a.candidates] == [
        c.listing_id for c in basket_b.candidates
    ]
    assert tuple(basket_a.metadata.keys()) == tuple(basket_b.metadata.keys())
    assert tuple(basket_a.enrichment_metadata.keys()) == tuple(
        basket_b.enrichment_metadata.keys()
    )


def test_synthetic_basket_rejects_invalid_config() -> None:
    with pytest.raises(ValueError):
        SyntheticBasketConfig(
            label="",
            seed=0,
            collections=("Synthetic Collection A",),
            inputs_per_collection=10,
            price_cny_min=Decimal("10.00"),
            price_cny_max=Decimal("20.00"),
        )
    with pytest.raises(ValueError):
        SyntheticBasketConfig(
            label="BAD",
            seed=0,
            collections=("Synthetic Collection A",),
            inputs_per_collection=5,
            price_cny_min=Decimal("10.00"),
            price_cny_max=Decimal("20.00"),
        )
    with pytest.raises(ValueError):
        SyntheticBasketConfig(
            label="BAD",
            seed=0,
            collections=(),
            inputs_per_collection=10,
            price_cny_min=Decimal("10.00"),
            price_cny_max=Decimal("20.00"),
        )


def test_scale_cases_cover_required_scenarios() -> None:
    cases = {case.label: case for case in _scale_cases()}
    assert set(cases) == {"SMALL", "MIXED", "DIRTY"}
    small = cases["SMALL"]
    assert small.expected_unresolved_count == 0
    assert small.expected_missing_metadata_count == 0
    mixed = cases["MIXED"]
    assert mixed.expected_unresolved_count > 0
    assert mixed.expected_missing_metadata_count > 0
    dirty = cases["DIRTY"]
    assert dirty.expected_unresolved_count > 0


@pytest.mark.parametrize("label", ["SMALL", "MIXED", "DIRTY"])
def test_partition_agreement_across_two_paths(label: str) -> None:
    case = next(c for c in _scale_cases() if c.label == label)
    report = _drive_case(case)
    assert report.partition_agreement is True, (
        f"{label}: pipeline_kept={report.pipeline_kept_count} "
        f"enrichment_kept={report.enrichment_kept_count}"
    )


@pytest.mark.parametrize("label", ["SMALL", "MIXED"])
def test_two_path_kept_signatures_match(label: str) -> None:
    """Signature equality only holds when intrinsic flags are off.

    The 13H-0 pipeline predates the intrinsic-flag boundary and hard-codes
    stattrak=False / souvenir=False on the InputItem it builds. The 13I-3
    enrichment path preserves the candidate's intrinsic flags. To compare
    signatures the basket must keep intrinsic flags at their default.
    """
    case = next(c for c in _scale_cases() if c.label == label)
    pipeline_items, _ = drive_pipeline_path(case.basket)
    enrichment_result = drive_enrichment_path(case.basket)
    pipeline_sigs = sorted(
        _input_item_signature(item) for item in pipeline_items
    )
    enrichment_sigs = sorted(
        _input_item_signature(enriched.input_item)
        for enriched in enrichment_result.enriched
    )
    assert pipeline_sigs == enrichment_sigs
    assert pipeline_items and enrichment_result.enriched


def test_rejection_reasons_are_surfaced() -> None:
    cases = {case.label: case for case in _scale_cases()}
    mixed_report = _drive_case(cases["MIXED"])
    assert (
        mixed_report.enrichment_rejection_histogram.get("MARKET_HASH_NAME_UNRESOLVED", 0)
        > 0
    )
    assert (
        mixed_report.enrichment_rejection_histogram.get("METADATA_NOT_FOUND", 0) > 0
    )


def test_engine_compatibility_runs_without_exception() -> None:
    case = next(c for c in _scale_cases() if c.label == "SMALL")
    report = _drive_case(case)
    assert report.recipes_attempted >= 1
    assert isinstance(report.recipes_rejected_by_engine, tuple)


def test_ev_risk_outputs_are_reproducible() -> None:
    case = next(c for c in _scale_cases() if c.label == "SMALL")
    first = _drive_case(case)
    second = _drive_case(case)
    assert first.recipe_hashes == second.recipe_hashes
    assert first.risk_reason_histogram == second.risk_reason_histogram
    assert first.risk_passed == second.risk_passed
    assert first.risk_rejected == second.risk_rejected


def test_metric_accepted_candidates_is_positive() -> None:
    cases = {case.label: case for case in _scale_cases()}
    found = False
    for label in ("SMALL", "MIXED"):
        report = _drive_case(cases[label])
        accepted = report.enrichment_kept_count - len(report.recipes_rejected_by_engine)
        if accepted >= 1:
            found = True
            break
    assert found, "expected at least one case with accepted_candidates >= 1"


def test_metric_rejection_reasons_cover_all_buckets() -> None:
    reports = {case.label: _drive_case(case) for case in _scale_cases()}
    enrichment_codes: set[str] = set()
    for label in ("MIXED", "DIRTY"):
        enrichment_codes |= set(reports[label].enrichment_rejection_histogram.keys())
    assert "MARKET_HASH_NAME_UNRESOLVED" in enrichment_codes
    assert "METADATA_NOT_FOUND" in enrichment_codes


def test_metric_solver_compatibility_for_mixed_is_below_one() -> None:
    mixed_report = _drive_case(
        next(c for c in _scale_cases() if c.label == "MIXED")
    )
    if mixed_report.recipes_attempted:
        assert mixed_report.recipes_built <= mixed_report.recipes_attempted


def test_pipeline_module_has_no_live_or_external_dependencies() -> None:
    source = (
        Path(pipeline_module.__file__).read_text(encoding="utf-8").casefold()
    )
    for forbidden in PIPELINE_FORBIDDEN_TOKENS:
        assert forbidden not in source, (
            f"forbidden token {forbidden!r} found in trade_up_pipeline.py"
        )


def test_test_module_has_no_live_imports() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imported.append(node.module)
    for forbidden in TEST_FORBIDDEN_IMPORTS:
        for actual in imported:
            assert not actual.startswith(forbidden), (
                f"forbidden import {actual!r} starts with {forbidden!r}"
            )


def test_protected_core_files_are_not_modified() -> None:
    """Static guard: the scale-validation phase must not directly re-import
    Protected Core symbols at module top level.

    The test deliberately routes through `pipeline_module`'s public helpers
    plus lazy imports inside helper bodies. This guard ensures no top-level
    import re-exposes a Protected Core type to the test surface.
    """

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    top_level_imports: list[tuple[str, list[str]]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_imports.append(
                (
                    node.names[0].name if node.names else "",
                    [alias.asname or alias.name for alias in node.names],
                )
            )
        elif isinstance(node, ast.ImportFrom):
            top_level_imports.append(
                (
                    node.module or "",
                    [alias.asname or alias.name for alias in node.names],
                )
            )

    forbidden_symbols = (
        "TradeupResult",
        "OutputCandidate",
        "CandidateListing",
        "SkinMetadata",
        "BuffClient",
        "BuffSellOrder",
    )
    for _, names in top_level_imports:
        for symbol in forbidden_symbols:
            assert symbol not in names, (
                f"Protected Core symbol {symbol!r} imported at module level"
            )


def test_no_value_leakage_in_path_comparison_repr() -> None:
    case = next(c for c in _scale_cases() if c.label == "DIRTY")
    pipeline_items, pipeline_skips = drive_pipeline_path(case.basket)
    enrichment_result = drive_enrichment_path(case.basket)
    comparison = compare_partition_paths(
        pipeline_items, pipeline_skips, enrichment_result
    )
    rendered = repr(comparison)
    for candidate in case.basket.candidates:
        assert candidate.listing_id not in rendered
        assert candidate.goods_id not in rendered
        if candidate.market_hash_name is not None:
            assert candidate.market_hash_name not in rendered


def test_drive_case_pipeline_skip_histogram_matches_configured_ratios() -> None:
    case = next(c for c in _scale_cases() if c.label == "MIXED")
    report = _drive_case(case)
    expected_unresolved = case.expected_unresolved_count
    expected_missing = case.expected_missing_metadata_count
    actual_unresolved = report.pipeline_skip_histogram.get("unresolved", 0)
    actual_missing = report.pipeline_skip_histogram.get("missing_metadata", 0)
    assert actual_unresolved == expected_unresolved
    assert actual_missing == expected_missing
    assert report.enrichment_rejection_histogram.get(
        "MARKET_HASH_NAME_UNRESOLVED", 0
    ) == expected_unresolved
    assert report.enrichment_rejection_histogram.get(
        "METADATA_NOT_FOUND", 0
    ) == expected_missing