"""Deterministic JSON and Markdown reports for Phase 15A."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict
from fractions import Fraction
from pathlib import Path

from research.valuation_budget_calibration.corpus import (
    EMPTY_CACHE_FRESH_RUN_INTERPRETATION,
    REPLAY_PATTERNS,
    REPLAY_SEEDS,
    CalibrationCorpus,
    ReplayObservation,
    StructuralMaximum,
    build_calibration_corpus,
)
from research.valuation_budget_calibration.measurement import (
    QuantileSummary,
    summarize_quantiles,
)

RESULT_SCHEMA_VERSION = 1
REFERENCE_THRESHOLDS = (5, 10, 15, 20, 30, 60)
REPRESENTATIVENESS_MARKER = "PHASE15A_REPRESENTATIVENESS_LIMITATION"
DEFAULT_JSON_PATH = Path(__file__).with_name("results.json")
DEFAULT_MARKDOWN_PATH = Path(__file__).with_name("REPORT.md")


def build_report_payload(corpus: CalibrationCorpus) -> dict[str, object]:
    """Build the stable machine-readable Phase 15A result payload."""

    observations = corpus.observations
    values = [observation.run_unique_output_names for observation in observations]
    summary = summarize_quantiles(values)
    threshold_coverage = {
        str(threshold): _coverage(values, threshold)
        for threshold in REFERENCE_THRESHOLDS
    }
    rarity_groups: dict[str, list[ReplayObservation]] = defaultdict(list)
    mode_groups: dict[str, list[ReplayObservation]] = defaultdict(list)
    for observation in observations:
        rarity_groups[observation.input_rarity].append(observation)
        mode_groups["stattrak" if observation.stattrak else "normal"].append(
            observation
        )
    incremental = [
        observation.recipe_2_incremental_new_names
        for observation in observations
        if observation.recipe_2_incremental_new_names is not None
    ]
    overlaps = [
        observation.cross_recipe_overlap_count for observation in observations
    ]
    reuse_basis_points = [
        observation.reuse_ratio_numerator * 10_000
        // observation.reuse_ratio_denominator
        for observation in observations
    ]
    top = sorted(
        observations,
        key=lambda observation: (
            -observation.run_unique_output_names,
            observation.case_id,
        ),
    )[:10]
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "phase": "15A",
        "status": "offline_measurement_complete",
        "policy_status": "Phase 15B NOT STARTED / NOT AUTHORIZED",
        "representativeness_status": REPRESENTATIVENESS_MARKER,
        "measurement_definition": {
            "primary_metric": "run_unique_output_names",
            "definition": (
                "Count of distinct exact output_market_hash_name values across "
                "the ordered recipe candidates returned by current default "
                "scanner composition."
            ),
            "empty_cache_fresh_run_interpretation": (
                EMPTY_CACHE_FRESH_RUN_INTERPRETATION
            ),
            "enumeration": {
                "max_recipe_candidates_returned": 2,
                "max_candidate_states_explored": 256,
            },
            "quantile_method": {
                "name": "R-7 linear empirical quantile",
                "formula": (
                    "Sort x[0..N-1]; h=(N-1)*p; q=x[floor(h)] + "
                    "(h-floor(h))*(x[ceil(h)]-x[floor(h)])."
                ),
                "exact_arithmetic": "fractions.Fraction",
            },
            "reuse_ratio_formula": (
                "(sum(per_recipe_unique_counts) - run_unique_output_names) / "
                "sum(per_recipe_unique_counts); zero when the denominator is zero."
            ),
        },
        "corpus": {
            "definition": (
                "Repository-pinned normalized identity/metadata catalog census "
                "plus deterministic synthetic offer-order replays through the "
                "real cohort-depth universe builder, scanner composition, recipe "
                "solver, and trade-up output construction."
            ),
            "seeds": list(REPLAY_SEEDS),
            "ordering_patterns": list(REPLAY_PATTERNS),
            "observation_count": len(observations),
            "skipped_case_count": len(corpus.skipped_cases),
            "skipped_cases": [
                asdict(skipped) for skipped in corpus.skipped_cases
            ],
            "provenance": asdict(corpus.provenance),
            "structural_census_record_count": len(corpus.census),
        },
        "run_unique_output_names": {
            "summary": _summary_payload(summary),
            "by_input_rarity": {
                key: _group_payload(value)
                for key, value in sorted(rarity_groups.items())
            },
            "by_stattrak_mode": {
                key: _group_payload(value)
                for key, value in sorted(mode_groups.items())
            },
        },
        "recipe_2_incremental_new_names": _integer_distribution(incremental),
        "cross_recipe_overlap_count": _integer_distribution(overlaps),
        "cross_recipe_reuse_ratio_basis_points": {
            **_integer_distribution(reuse_basis_points),
            "unit": "basis_points",
        },
        "threshold_coverage": threshold_coverage,
        "structural_census": {
            "maximum": _structural_payload(corpus.structural_maximum),
            "default_cohort_depth_maximum": _structural_payload(
                corpus.default_universe_structural_maximum
            ),
            "records": [
                {
                    "input_rarity": record.input_rarity,
                    "stattrak": record.stattrak,
                    "collection_name": record.collection_name,
                    "input_identity_count": record.input_identity_count,
                    "output_unique_name_count": (
                        record.output_unique_name_count
                    ),
                }
                for record in corpus.census
            ],
        },
        "top_maximum_cardinality_cases": [
            _observation_payload(observation) for observation in top
        ],
        "observations": [
            _observation_payload(observation)
            for observation in observations
        ],
        "representativeness_limitations": [
            (
                "Pinned catalogs establish structural possibilities, not live "
                "listing availability, liquidity, or market frequency."
            ),
            (
                "Synthetic prices/floats only impose deterministic solver "
                "orderings; they are not sampled from BUFF or any market."
            ),
            (
                "The replay distribution is coverage evidence over designed "
                "scenarios, not a probability distribution of production runs."
            ),
            (
                "A market-frequency distribution requires timestamped, "
                "representative, policy-compliant listing snapshots with exact "
                "identity, price, float, StatTrak/Souvenir facts, sampling frame, "
                "and collection/rarity coverage."
            ),
        ],
        "analysis_only": {
            "reference_thresholds_are_not_policy": True,
            "budget_default_changed": False,
            "hard_max_changed": False,
            "cli_semantics_changed": False,
            "atomic_new_live_semantics_changed": False,
        },
    }


def render_json(payload: dict[str, object]) -> str:
    """Render canonical human-diffable JSON with one trailing newline."""

    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def render_markdown(payload: dict[str, object]) -> str:
    """Render the concise human Phase 15A report."""

    corpus = _mapping(payload["corpus"])
    metric = _mapping(payload["run_unique_output_names"])
    summary = _mapping(metric["summary"])
    coverage = _mapping(payload["threshold_coverage"])
    structural = _mapping(payload["structural_census"])
    maximum = _mapping(structural["maximum"])
    default_maximum = _mapping(structural["default_cohort_depth_maximum"])
    lines = [
        "# Phase 15A — Valuation Budget Calibration: Offline Measurement",
        "",
        f"**Status:** `{payload['status']}`",
        "",
        f"**Representativeness:** `{payload['representativeness_status']}`",
        "",
        f"**Policy:** `{payload['policy_status']}`",
        "",
        "## Measurement",
        "",
        "`run_unique_output_names` is the count of distinct exact "
        "`output_market_hash_name` values across the ordered recipe candidates "
        "returned by the current default scanner composition (`2 / 256`).",
        "",
        EMPTY_CACHE_FRESH_RUN_INTERPRETATION,
        "",
        "The replay corpus uses the repository-pinned normalized identity and "
        "metadata snapshots, current cohort-depth allocation, real scanner recipe "
        "composition, real recipe solver, and real trade-up output construction. "
        "Only listing price/float order is deterministic synthetic input.",
        "",
        "Quantiles use R-7: sort `x[0..N-1]`, `h=(N-1)p`, then "
        "`q=x[floor(h)] + (h-floor(h)) * (x[ceil(h)]-x[floor(h)])`. "
        "All calculations use exact rational arithmetic.",
        "",
        "Cross-recipe reuse ratio is "
        "`(sum(per-recipe unique counts) - run_unique_output_names) / "
        "sum(per-recipe unique counts)` (zero only for an empty denominator).",
        "",
        "## Corpus",
        "",
        f"- Observations: **{corpus['observation_count']}**",
        f"- Structural census records: **{corpus['structural_census_record_count']}**",
        f"- Skipped rarity/mode cases: **{corpus['skipped_case_count']}**",
        f"- Seeds: `{', '.join(str(value) for value in corpus['seeds'])}`",
        "- Ordering patterns: "
        + ", ".join(f"`{value}`" for value in corpus["ordering_patterns"]),
        "",
        "## Primary distribution (designed replay corpus)",
        "",
        "| min | P25 | P50 | P75 | P90 | P95 | max |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        "| "
        + " | ".join(
            _display_quantile(summary[key])
            for key in ("min", "p25", "p50", "p75", "p90", "p95", "max")
        )
        + " |",
        "",
        "## Reference-threshold coverage (analysis only, not policy)",
        "",
        "| Threshold | Count | Share |",
        "|---:|---:|---:|",
    ]
    for threshold in REFERENCE_THRESHOLDS:
        item = _mapping(coverage[str(threshold)])
        lines.append(
            f"| {threshold} | {item['count']} / {item['total']} | "
            f"{item['share_basis_points'] / 100:.2f}% |"
        )
    lines.extend(
        [
            "",
            "## Structural census",
            "",
            f"- Overall constructible 1–3 cohort maximum: "
            f"**{maximum['output_unique_name_count']}** "
            f"({maximum['input_rarity']}, {_mode_label(maximum['stattrak'])}; "
            f"{', '.join(maximum['collections'])}).",
            f"- Current default cohort-depth-universe maximum: "
            f"**{default_maximum['output_unique_name_count']}** "
            f"({default_maximum['input_rarity']}, "
            f"{_mode_label(default_maximum['stattrak'])}; "
            f"{', '.join(default_maximum['collections'])}).",
            "",
            "## Top maximum-cardinality replay cases",
            "",
            "| Cardinality | Rarity | Mode | Pattern | Seed | Participating collections |",
            "|---:|---|---|---|---:|---|",
        ]
    )
    for raw in payload["top_maximum_cardinality_cases"]:
        case = _mapping(raw)
        collections = sorted(
            {
                collection
                for recipe in case["participating_collections_by_recipe"]
                for collection in recipe
            }
        )
        lines.append(
            f"| {case['run_unique_output_names']} | {case['input_rarity']} | "
            f"{_mode_label(case['stattrak'])} | {case['ordering_pattern']} | "
            f"{case['seed']} | {', '.join(collections)} |"
        )
    lines.extend(
        [
            "",
            "## Representativeness limitations",
            "",
            f"`{REPRESENTATIVENESS_MARKER}`",
            "",
        ]
    )
    for limitation in payload["representativeness_limitations"]:
        lines.append(f"- {limitation}")
    lines.extend(
        [
            "",
            "The reported quantiles and threshold shares describe this designed "
            "offline replay corpus only. They must not be interpreted as expected "
            "production frequency. A defensible market-frequency distribution "
            "requires timestamped representative listing snapshots with a declared "
            "sampling frame and the exact identity/price/float/intrinsic facts.",
            "",
            "## Policy boundary",
            "",
            "Reference thresholds are analysis only. This phase changes no budget "
            "default, hard maximum, CLI semantics, atomic NEW-LIVE behavior, or "
            "production code. No final cap is recommended here.",
            "",
            "**Phase 15B: NOT STARTED / NOT AUTHORIZED.**",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(
    *,
    json_path: Path = DEFAULT_JSON_PATH,
    markdown_path: Path = DEFAULT_MARKDOWN_PATH,
) -> dict[str, object]:
    """Rebuild and atomically replace both deterministic report artifacts."""

    payload = build_report_payload(build_calibration_corpus())
    _atomic_write(json_path, render_json(payload))
    _atomic_write(markdown_path, render_markdown(payload))
    return payload


def main() -> int:
    payload = write_reports()
    corpus = _mapping(payload["corpus"])
    summary = _mapping(_mapping(payload["run_unique_output_names"])["summary"])
    print(
        "PHASE15A_OFFLINE_MEASUREMENT "
        f"N={corpus['observation_count']} "
        f"min={_display_quantile(summary['min'])} "
        f"p50={_display_quantile(summary['p50'])} "
        f"max={_display_quantile(summary['max'])}"
    )
    return 0


def _summary_payload(summary: QuantileSummary) -> dict[str, object]:
    return {
        "min": _fraction_payload(summary.minimum),
        "p25": _fraction_payload(summary.p25),
        "p50": _fraction_payload(summary.p50),
        "p75": _fraction_payload(summary.p75),
        "p90": _fraction_payload(summary.p90),
        "p95": _fraction_payload(summary.p95),
        "max": _fraction_payload(summary.maximum),
    }


def _fraction_payload(value: Fraction) -> dict[str, int]:
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
    }


def _group_payload(observations: Sequence[ReplayObservation]) -> dict[str, object]:
    values = [observation.run_unique_output_names for observation in observations]
    return {
        "count": len(values),
        "summary": _summary_payload(summarize_quantiles(values)),
    }


def _integer_distribution(values: Sequence[int]) -> dict[str, object]:
    if not values:
        return {"count": 0, "summary": None, "histogram": {}}
    histogram: dict[str, int] = defaultdict(int)
    for value in values:
        histogram[str(value)] += 1
    return {
        "count": len(values),
        "summary": _summary_payload(summarize_quantiles(values)),
        "histogram": dict(
            sorted(histogram.items(), key=lambda item: int(item[0]))
        ),
    }


def _coverage(values: Sequence[int], threshold: int) -> dict[str, int]:
    count = sum(value <= threshold for value in values)
    return {
        "count": count,
        "total": len(values),
        "share_basis_points": count * 10_000 // len(values),
    }


def _structural_payload(value: StructuralMaximum) -> dict[str, object]:
    return asdict(value)


def _observation_payload(value: ReplayObservation) -> dict[str, object]:
    return asdict(value)


def _display_quantile(value: object) -> str:
    quantile = _mapping(value)
    numerator = int(quantile["numerator"])
    denominator = int(quantile["denominator"])
    if denominator == 1:
        return str(numerator)
    return f"{numerator / denominator:.2f} ({numerator}/{denominator})"


def _mode_label(stattrak: object) -> str:
    return "StatTrak" if stattrak is True else "normal"


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("report payload member must be a mapping")
    return value


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
