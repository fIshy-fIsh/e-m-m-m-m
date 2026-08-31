from __future__ import annotations

import ast
from fractions import Fraction
from pathlib import Path

import pytest

from app.services.recipe_solver import RecipeEnumerationConfig
from research.valuation_budget_calibration.corpus import (
    DEFAULT_ENUMERATION_CONFIG,
    EMPTY_CACHE_FRESH_RUN_INTERPRETATION,
    INPUT_RARITIES,
    REPLAY_PATTERNS,
    REPLAY_SEEDS,
    CalibrationCorpus,
    build_calibration_corpus,
)
from research.valuation_budget_calibration.measurement import (
    empirical_r7_quantile,
    measure_output_name_sequences,
    summarize_quantiles,
)
from research.valuation_budget_calibration.report import (
    DEFAULT_JSON_PATH,
    DEFAULT_MARKDOWN_PATH,
    REPRESENTATIVENESS_MARKER,
    build_report_payload,
    render_json,
    render_markdown,
)

CALIBRATION_ROOT = Path("research/valuation_budget_calibration")
CALIBRATION_SOURCES = (
    CALIBRATION_ROOT / "__init__.py",
    CALIBRATION_ROOT / "measurement.py",
    CALIBRATION_ROOT / "corpus.py",
    CALIBRATION_ROOT / "report.py",
)
FORBIDDEN_IMPORT_PREFIXES = (
    "app.api",
    "app.cache",
    "app.db",
    "app.jobs",
    "app.services.buff_client",
    "app.services.buff_listing",
    "app.services.live_recipe_valuation",
    "app.services.metadata_provider",
    "app.services.live_metadata_catalog",
    "app.services.price_cache",
    "app.services.price_provider",
    "app.services.redis",
    "app.services.steamapis",
    "app.services.steamdt",
    "app.webhook",
    "aiohttp",
    "httpx",
    "requests",
    "socket",
    "urllib",
)
FORBIDDEN_CALL_NAMES = (
    "getenv",
    "urlopen",
    "request",
    "requests",
    "socket",
)


@pytest.fixture(scope="module")
def corpus() -> CalibrationCorpus:
    return build_calibration_corpus()


def test_exact_name_dedup_and_recipe_2_incremental_new_semantics() -> None:
    result = measure_output_name_sequences(
        (
            ("Output A", "Output A", "Output B"),
            ("Output B", "Output C", "Output C"),
        )
    )

    assert result.per_recipe_unique_names == (
        ("Output A", "Output B"),
        ("Output B", "Output C"),
    )
    assert result.run_unique_names == ("Output A", "Output B", "Output C")
    assert result.run_unique_output_names == 3
    assert result.cross_recipe_overlap_count == 1
    assert result.recipe_2_incremental_new_names == 1
    assert result.reuse_ratio == Fraction(1, 4)


def test_empirical_r7_quantile_method_uses_exact_linear_interpolation() -> None:
    values = (5, 10, 20, 40)

    assert empirical_r7_quantile(values, Fraction(0, 1)) == 5
    assert empirical_r7_quantile(values, Fraction(1, 4)) == Fraction(35, 4)
    assert empirical_r7_quantile(values, Fraction(1, 2)) == 15
    assert empirical_r7_quantile(values, Fraction(3, 4)) == 25
    assert empirical_r7_quantile(values, Fraction(9, 10)) == 34
    assert empirical_r7_quantile(values, Fraction(19, 20)) == 37
    assert empirical_r7_quantile(values, Fraction(1, 1)) == 40
    assert summarize_quantiles(values).p50 == 15


def test_default_measurement_enumeration_is_exactly_two_by_256() -> None:
    assert DEFAULT_ENUMERATION_CONFIG == RecipeEnumerationConfig()
    assert DEFAULT_ENUMERATION_CONFIG.max_recipe_candidates_returned == 2
    assert DEFAULT_ENUMERATION_CONFIG.max_candidate_states_explored == 256


def test_empty_cache_fresh_run_interpretation_is_explicit() -> None:
    assert "empty persistent cache" in EMPTY_CACHE_FRESH_RUN_INTERPRETATION
    assert "fresh run memo" in EMPTY_CACHE_FRESH_RUN_INTERPRETATION
    assert "theoretical NEW-LIVE exact-name demand" in (
        EMPTY_CACHE_FRESH_RUN_INTERPRETATION
    )
    assert "successfully" in EMPTY_CACHE_FRESH_RUN_INTERPRETATION


def test_calibration_harness_has_no_network_client_cache_or_provider_imports() -> None:
    for path in CALIBRATION_SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports: list[str] = []
        calls: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.append(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)
        for imported in imports:
            assert not imported.startswith(FORBIDDEN_IMPORT_PREFIXES), (
                f"forbidden import {imported!r} in {path}"
            )
        for called in calls:
            assert called not in FORBIDDEN_CALL_NAMES, (
                f"forbidden call {called!r} in {path}"
            )


def test_corpus_exercises_required_structural_scenarios(
    corpus: CalibrationCorpus,
) -> None:
    observations = corpus.observations
    assert len(observations) == 192
    assert {observation.seed for observation in observations} == set(REPLAY_SEEDS)
    assert {
        observation.ordering_pattern for observation in observations
    } == set(REPLAY_PATTERNS)
    assert all(observation.recipe_count == 2 for observation in observations)
    assert all(
        observation.composition_states_explored <= 256
        for observation in observations
    )
    assert all(
        observation.universe_goods_id_count == 10
        for observation in observations
    )

    collection_counts = {
        len(
            {
                collection
                for recipe in observation.participating_collections_by_recipe
                for collection in recipe
            }
        )
        for observation in observations
    }
    assert collection_counts == {1, 2, 3}
    assert {observation.stattrak for observation in observations} == {False, True}
    assert {observation.input_rarity for observation in observations} == set(
        INPUT_RARITIES
    )
    assert min(
        observation.recipe_2_incremental_new_names or 0
        for observation in observations
    ) == 0
    assert max(
        observation.recipe_2_incremental_new_names or 0
        for observation in observations
    ) > 0
    reuse_ratios = {
        Fraction(
            observation.reuse_ratio_numerator,
            observation.reuse_ratio_denominator,
        )
        for observation in observations
    }
    assert max(reuse_ratios) == Fraction(1, 2)
    assert min(reuse_ratios) < Fraction(1, 5)


def test_structural_census_and_report_contain_required_evidence(
    corpus: CalibrationCorpus,
) -> None:
    payload = build_report_payload(corpus)
    metric = payload["run_unique_output_names"]
    assert isinstance(metric, dict)
    summary = metric["summary"]
    assert isinstance(summary, dict)

    assert len(corpus.census) == 439
    assert corpus.structural_maximum.output_unique_name_count == 120
    assert corpus.default_universe_structural_maximum.output_unique_name_count == 95
    assert summary == {
        "min": {"numerator": 5, "denominator": 1},
        "p25": {"numerator": 20, "denominator": 1},
        "p50": {"numerator": 59, "denominator": 2},
        "p75": {"numerator": 45, "denominator": 1},
        "p90": {"numerator": 75, "denominator": 1},
        "p95": {"numerator": 95, "denominator": 1},
        "max": {"numerator": 95, "denominator": 1},
    }
    assert payload["representativeness_status"] == REPRESENTATIVENESS_MARKER
    assert payload["policy_status"] == "Phase 15B NOT STARTED / NOT AUTHORIZED"


def test_committed_reports_regenerate_byte_for_byte(
    corpus: CalibrationCorpus,
) -> None:
    payload = build_report_payload(corpus)

    assert DEFAULT_JSON_PATH.read_text(encoding="utf-8") == render_json(payload)
    assert DEFAULT_MARKDOWN_PATH.read_text(encoding="utf-8") == render_markdown(
        payload
    )


def test_independent_corpus_rerun_is_deterministic(
    corpus: CalibrationCorpus,
) -> None:
    rerun = build_calibration_corpus()

    assert rerun == corpus
    assert render_json(build_report_payload(rerun)) == render_json(
        build_report_payload(corpus)
    )
