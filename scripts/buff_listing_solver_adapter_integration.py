from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Never, Protocol

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.buff_listing_qualification import (
    BuffListingQualificationResult,
    BuffListingQualificationStatus,
)
from app.services.buff_listing_solver_adapter import adapt_qualified_buff_listing
from app.services.market_scan_service import CandidateListing
from scripts.buff_listing_qualification_integration import (
    DEFAULT_FACTS_FIXTURE,
    DEFAULT_LISTINGS_FIXTURE,
    BuffListingQualificationIntegrationError,
    BuffListingQualificationRunResult,
    render_safe_buff_candidate_market_name,
    run_qualification_integration,
)


class _QualificationRunner(Protocol):
    def __call__(
        self,
        listings_fixture: Path,
        facts_fixture: Path,
    ) -> Awaitable[BuffListingQualificationRunResult]:
        """Run one complete offline qualification integration."""


@dataclass(frozen=True, kw_only=True, repr=False)
class BuffListingSolverAdapterIntegrationOptions:
    listings_fixture: Path
    facts_fixture: Path


class BuffListingSolverAdapterIntegrationCliError(ValueError):
    """The command arguments violated the safe CLI contract."""


class BuffListingSolverAdapterIntegrationError(RuntimeError):
    """A fixed integration stage failed without exposing nested details."""

    def __init__(self, *, stage: str) -> None:
        super().__init__("offline BUFF solver adapter integration failed")
        self.stage = stage


@dataclass(frozen=True, kw_only=True, repr=False)
class BuffListingSolverAdapterIntegrationResult:
    """Immutable output of one complete offline adapter integration run."""

    qualification_run_result: BuffListingQualificationRunResult
    ordered_solver_candidates: tuple[CandidateListing, ...]

    def __post_init__(self) -> None:
        try:
            if (
                type(self.qualification_run_result)
                is not BuffListingQualificationRunResult
                or type(self.ordered_solver_candidates) is not tuple
                or any(
                    type(candidate) is not CandidateListing
                    for candidate in self.ordered_solver_candidates
                )
                or self.adapted_candidate_count != self.qualified_result_count
            ):
                raise BuffListingSolverAdapterIntegrationError(stage="run_result")

            qualified_results = _qualified_results(self.qualification_run_result)
            if any(
                not _candidate_matches_qualification(candidate, qualification)
                for qualification, candidate in zip(
                    qualified_results,
                    self.ordered_solver_candidates,
                    strict=True,
                )
            ):
                raise BuffListingSolverAdapterIntegrationError(stage="run_result")
        except MemoryError:
            raise
        except BuffListingSolverAdapterIntegrationError:
            raise
        except Exception:
            raise BuffListingSolverAdapterIntegrationError(
                stage="run_result"
            ) from None

    @property
    def qualification_total_count(self) -> int:
        return self.qualification_run_result.total_count

    @property
    def qualified_result_count(self) -> int:
        return self.qualification_run_result.qualified_count

    @property
    def adapted_candidate_count(self) -> int:
        return len(self.ordered_solver_candidates)

    @property
    def skipped_rejected_count(self) -> int:
        return self.qualification_run_result.rejected_count

    @property
    def skipped_missing_facts_count(self) -> int:
        return self.qualification_run_result.missing_facts_count


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise BuffListingSolverAdapterIntegrationCliError from None


async def run_solver_adapter_integration(
    listings_fixture: Path,
    facts_fixture: Path,
    *,
    qualification_runner: _QualificationRunner = run_qualification_integration,
    adapter: Callable[
        [BuffListingQualificationResult], CandidateListing
    ] = adapt_qualified_buff_listing,
) -> BuffListingSolverAdapterIntegrationResult:
    """Qualify once and adapt every qualified result in source order."""

    try:
        qualification_run = await qualification_runner(
            listings_fixture,
            facts_fixture,
        )
    except (MemoryError, asyncio.CancelledError):
        raise
    except BuffListingQualificationIntegrationError as exc:
        raise BuffListingSolverAdapterIntegrationError(
            stage=_safe_failure_stage(exc.stage)
        ) from None
    except Exception:
        raise BuffListingSolverAdapterIntegrationError(stage="qualification") from None

    if type(qualification_run) is not BuffListingQualificationRunResult:
        raise BuffListingSolverAdapterIntegrationError(stage="run_result")

    adapted: list[CandidateListing] = []
    for result in qualification_run.ordered_qualification_results:
        if result.status is BuffListingQualificationStatus.QUALIFIED:
            try:
                candidate = adapter(result)
            except MemoryError:
                raise
            except Exception:
                raise BuffListingSolverAdapterIntegrationError(
                    stage="adaptation"
                ) from None
            if type(candidate) is not CandidateListing or candidate.source != "buff":
                raise BuffListingSolverAdapterIntegrationError(stage="adaptation")
            adapted.append(candidate)
        elif result.status in {
            BuffListingQualificationStatus.REJECTED,
            BuffListingQualificationStatus.MISSING_FACTS,
        }:
            continue
        else:
            raise BuffListingSolverAdapterIntegrationError(stage="qualification")

    return BuffListingSolverAdapterIntegrationResult(
        qualification_run_result=qualification_run,
        ordered_solver_candidates=tuple(adapted),
    )


async def async_main(
    argv: Sequence[str] | None = None,
    *,
    printer: Callable[[str], None] = print,
    qualification_runner: _QualificationRunner = run_qualification_integration,
    adapter: Callable[
        [BuffListingQualificationResult], CandidateListing
    ] = adapt_qualified_buff_listing,
) -> int:
    """Parse fixtures, run the offline integration, and print a safe summary."""

    try:
        options = parse_options(argv)
        _validate_fixture_paths(options)
    except BuffListingSolverAdapterIntegrationCliError:
        _print_failure(printer, "input")
        return 2

    try:
        result = await run_solver_adapter_integration(
            options.listings_fixture,
            options.facts_fixture,
            qualification_runner=qualification_runner,
            adapter=adapter,
        )
        summary_lines = _build_summary_lines(result)
    except (MemoryError, asyncio.CancelledError):
        raise
    except BuffListingSolverAdapterIntegrationError as exc:
        _print_failure(printer, exc.stage)
        return 1
    except Exception:
        _print_failure(printer, "internal")
        return 1

    for line in summary_lines:
        printer(line)
    return 0


def parse_options(
    argv: Sequence[str] | None = None,
) -> BuffListingSolverAdapterIntegrationOptions:
    """Parse fixture path options without reading either fixture."""

    parser = _ArgumentParser(
        prog="buff_listing_solver_adapter_integration",
        description="Adapt qualified offline BUFF listings without running recipes.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--listings-fixture",
        type=Path,
        default=DEFAULT_LISTINGS_FIXTURE,
    )
    parser.add_argument(
        "--facts-fixture",
        type=Path,
        default=DEFAULT_FACTS_FIXTURE,
    )
    namespace = parser.parse_args(argv)
    return BuffListingSolverAdapterIntegrationOptions(
        listings_fixture=namespace.listings_fixture,
        facts_fixture=namespace.facts_fixture,
    )


def _validate_fixture_paths(
    options: BuffListingSolverAdapterIntegrationOptions,
) -> None:
    try:
        valid = options.listings_fixture.is_file() and options.facts_fixture.is_file()
    except OSError:
        valid = False
    if not valid:
        raise BuffListingSolverAdapterIntegrationCliError from None


def _qualified_results(
    qualification_run: BuffListingQualificationRunResult,
) -> tuple[BuffListingQualificationResult, ...]:
    qualified: list[BuffListingQualificationResult] = []
    for result in qualification_run.ordered_qualification_results:
        if result.status is BuffListingQualificationStatus.QUALIFIED:
            qualified.append(result)
        elif result.status not in {
            BuffListingQualificationStatus.REJECTED,
            BuffListingQualificationStatus.MISSING_FACTS,
        }:
            raise BuffListingSolverAdapterIntegrationError(stage="run_result")
    return tuple(qualified)


def _candidate_matches_qualification(
    candidate: CandidateListing,
    qualification: BuffListingQualificationResult,
) -> bool:
    source = qualification.candidate
    return (
        candidate.goods_id == source.goods_id
        and candidate.listing_id == source.listing_id
        and candidate.market_hash_name == source.market_hash_name
        and candidate.price_cny == source.buy_price_cny
        and source.float_value is not None
        and candidate.float_value == float(source.float_value)
        and candidate.paint_seed == source.paint_seed
        and candidate.inspect_link is None
        and candidate.source == "buff"
        and candidate.scanned_at == source.observed_at
        and candidate.raw is None
    )


def _build_summary_lines(
    result: BuffListingSolverAdapterIntegrationResult,
) -> tuple[str, ...]:
    qualified_results = _qualified_results(result.qualification_run_result)
    if len(qualified_results) != result.adapted_candidate_count:
        raise BuffListingSolverAdapterIntegrationError(stage="run_result")

    lines = [
        "Mode: offline-fixture",
        f"Qualification results: {result.qualification_total_count}",
        f"Qualified results: {result.qualified_result_count}",
        f"Adapted solver candidates: {result.adapted_candidate_count}",
        f"Skipped rejected: {result.skipped_rejected_count}",
        f"Skipped missing facts: {result.skipped_missing_facts_count}",
    ]
    for index, (qualification, candidate) in enumerate(
        zip(
            qualified_results,
            result.ordered_solver_candidates,
            strict=True,
        )
    ):
        if candidate.source != "buff":
            raise BuffListingSolverAdapterIntegrationError(stage="run_result")
        lines.extend(
            [
                f"Adapted candidate {index}:",
                "  Market name: "
                f"{render_safe_buff_candidate_market_name(qualification.candidate)}",
                "  Source: buff",
                f"  Float present: {'yes' if candidate.float_value is not None else 'no'}",
            ]
        )
    lines.extend(
        [
            "Recipe solver executed: no",
            "BUFF requests sent: 0",
            "SteamDT requests sent: 0",
            "Redis used: no",
        ]
    )
    return tuple(lines)


def _print_failure(printer: Callable[[str], None], stage: str) -> None:
    printer(
        "Offline BUFF solver adapter integration failed: "
        f"{_safe_failure_stage(stage)}"
    )
    printer("Recipe solver executed: no")
    printer("BUFF requests sent: 0")
    printer("SteamDT requests sent: 0")
    printer("Redis used: no")


def _safe_failure_stage(stage: str) -> str:
    return stage if stage in _SAFE_FAILURE_STAGES else "internal"


_SAFE_FAILURE_STAGES = frozenset(
    {
        "input",
        "listing_fixture",
        "normalization",
        "facts_fixture",
        "provider",
        "policy",
        "service",
        "qualification",
        "adaptation",
        "run_result",
        "internal",
    }
)


def main() -> None:
    """Run the manual offline qualified-listing adapter integration."""

    try:
        exit_code = asyncio.run(async_main())
    except KeyboardInterrupt:
        exit_code = 130
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
