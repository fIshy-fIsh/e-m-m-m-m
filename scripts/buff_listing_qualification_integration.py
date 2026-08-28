from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Never, Protocol

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.buff_listing import (
    BuffListingObservation,
    BuffTradableCandidate,
    normalize_buff_listing,
)
from app.services.buff_listing_eligibility import BuffListingEligibilityPolicy
from app.services.buff_listing_facts import (
    BuffListingFactsRecord,
    OfflineBuffListingFactsProvider,
    load_buff_listing_facts_fixture,
)
from app.services.buff_listing_parser import load_buff_listing_fixture
from app.services.buff_listing_qualification import (
    BuffListingQualificationResult,
    BuffListingQualificationService,
    BuffListingQualificationStatus,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LISTINGS_FIXTURE = (
    _PROJECT_ROOT / "tests" / "fixtures" / "buff" / "qualification_listings_v2.json"
)
DEFAULT_FACTS_FIXTURE = (
    _PROJECT_ROOT / "tests" / "fixtures" / "buff" / "qualification_facts_v1.json"
)

_SENSITIVE_MARKERS = (
    "api key",
    "api-key",
    "api_key",
    "apikey",
    "auth",
    "basic ",
    "bearer",
    "cookie",
    "credential",
    "password",
    "secret",
    "session",
    "token",
    "www.",
)
_URI_PATTERN = re.compile(r"[a-z][a-z0-9+.-]*:", re.IGNORECASE)
_DOMAIN_PATTERN = re.compile(
    r"(?:^|[^\w-])[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}(?:$|[^\w-])",
    re.IGNORECASE,
)
_SENSITIVE_PUNCTUATION = frozenset("=/%@;\\")


class _QualificationService(Protocol):
    async def qualify(
        self,
        candidate: BuffTradableCandidate,
        policy: BuffListingEligibilityPolicy,
    ) -> BuffListingQualificationResult:
        """Qualify one candidate."""


class _QualificationServiceFactory(Protocol):
    def __call__(
        self,
        provider: OfflineBuffListingFactsProvider,
    ) -> _QualificationService:
        """Construct the qualification service."""


@dataclass(frozen=True, kw_only=True, repr=False)
class BuffListingQualificationIntegrationOptions:
    listings_fixture: Path
    facts_fixture: Path


class BuffListingQualificationIntegrationCliError(ValueError):
    """The manual command arguments violated the safe CLI contract."""


class BuffListingQualificationIntegrationError(RuntimeError):
    """A fixed integration stage failed without exposing nested details."""

    def __init__(self, *, stage: str) -> None:
        super().__init__("offline BUFF qualification integration failed")
        self.stage = stage


@dataclass(frozen=True, kw_only=True, repr=False)
class BuffListingQualificationRunResult:
    """Immutable ordered output of one complete offline integration run."""

    ordered_candidates: tuple[BuffTradableCandidate, ...]
    ordered_qualification_results: tuple[BuffListingQualificationResult, ...]

    def __post_init__(self) -> None:
        if type(self.ordered_candidates) is not tuple or type(
            self.ordered_qualification_results
        ) is not tuple:
            raise BuffListingQualificationIntegrationError(stage="run_result")
        if len(self.ordered_candidates) != len(self.ordered_qualification_results):
            raise BuffListingQualificationIntegrationError(stage="run_result")
        for candidate, result in zip(
            self.ordered_candidates,
            self.ordered_qualification_results,
            strict=True,
        ):
            if (
                type(candidate) is not BuffTradableCandidate
                or type(result) is not BuffListingQualificationResult
                or result.candidate != candidate
            ):
                raise BuffListingQualificationIntegrationError(stage="run_result")

    @property
    def total_count(self) -> int:
        return len(self.ordered_qualification_results)

    @property
    def qualified_count(self) -> int:
        return self._count(BuffListingQualificationStatus.QUALIFIED)

    @property
    def rejected_count(self) -> int:
        return self._count(BuffListingQualificationStatus.REJECTED)

    @property
    def missing_facts_count(self) -> int:
        return self._count(BuffListingQualificationStatus.MISSING_FACTS)

    def _count(self, status: BuffListingQualificationStatus) -> int:
        return sum(result.status is status for result in self.ordered_qualification_results)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise BuffListingQualificationIntegrationCliError from None


async def run_qualification_integration(
    listings_fixture: Path,
    facts_fixture: Path,
    *,
    listing_loader: Callable[[Path], tuple[BuffListingObservation, ...]] = (
        load_buff_listing_fixture
    ),
    normalizer: Callable[[BuffListingObservation], BuffTradableCandidate] = (
        normalize_buff_listing
    ),
    facts_loader: Callable[[Path], tuple[BuffListingFactsRecord, ...]] = (
        load_buff_listing_facts_fixture
    ),
    provider_factory: Callable[
        [Sequence[BuffListingFactsRecord]], OfflineBuffListingFactsProvider
    ] = OfflineBuffListingFactsProvider,
    policy_factory: Callable[[], BuffListingEligibilityPolicy] = (
        BuffListingEligibilityPolicy
    ),
    service_factory: _QualificationServiceFactory = BuffListingQualificationService,
) -> BuffListingQualificationRunResult:
    """Run the real offline qualification chain in deterministic input order."""

    observations = _call_stage("listing_fixture", listing_loader, listings_fixture)
    candidates = tuple(
        _call_stage("normalization", normalizer, observation)
        for observation in observations
    )
    records = _call_stage("facts_fixture", facts_loader, facts_fixture)
    provider = _call_stage("provider", provider_factory, records)
    policy = _call_stage("policy", policy_factory)
    service = _call_stage("service", service_factory, provider)

    results: list[BuffListingQualificationResult] = []
    for candidate in candidates:
        try:
            result = await service.qualify(candidate, policy)
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception:
            raise BuffListingQualificationIntegrationError(
                stage="qualification"
            ) from None
        _validate_qualification_result(candidate, result)
        results.append(result)

    return BuffListingQualificationRunResult(
        ordered_candidates=candidates,
        ordered_qualification_results=tuple(results),
    )


async def async_main(
    argv: Sequence[str] | None = None,
    *,
    printer: Callable[[str], None] = print,
) -> int:
    """Parse options, execute the offline chain, and print one safe summary."""

    try:
        options = parse_options(argv)
        _validate_fixture_paths(options)
    except BuffListingQualificationIntegrationCliError:
        _print_failure(printer, "input")
        return 2

    try:
        result = await run_qualification_integration(
            options.listings_fixture,
            options.facts_fixture,
        )
        summary_lines = _build_summary_lines(result)
    except (MemoryError, asyncio.CancelledError):
        raise
    except BuffListingQualificationIntegrationError as exc:
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
) -> BuffListingQualificationIntegrationOptions:
    """Parse the two fixture path options without reading either file."""

    parser = _ArgumentParser(
        prog="buff_listing_qualification_integration",
        description="Run the fully offline BUFF listing qualification chain.",
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
    return BuffListingQualificationIntegrationOptions(
        listings_fixture=namespace.listings_fixture,
        facts_fixture=namespace.facts_fixture,
    )


def _validate_fixture_paths(
    options: BuffListingQualificationIntegrationOptions,
) -> None:
    try:
        valid = options.listings_fixture.is_file() and options.facts_fixture.is_file()
    except OSError:
        valid = False
    if not valid:
        raise BuffListingQualificationIntegrationCliError from None


def _validate_qualification_result(
    candidate: BuffTradableCandidate,
    result: object,
) -> None:
    if (
        type(result) is not BuffListingQualificationResult
        or result.candidate != candidate
    ):
        raise BuffListingQualificationIntegrationError(stage="qualification")


def _call_stage[T](
    stage: str,
    operation: Callable[..., T],
    *args: object,
) -> T:
    try:
        return operation(*args)
    except MemoryError:
        raise
    except Exception:
        raise BuffListingQualificationIntegrationError(stage=stage) from None


def _build_summary_lines(
    result: BuffListingQualificationRunResult,
) -> tuple[str, ...]:
    lines = [
        "Mode: offline-fixture",
        f"Listings: {result.total_count}",
        f"Qualified: {result.qualified_count}",
        f"Rejected: {result.rejected_count}",
        f"Missing facts: {result.missing_facts_count}",
    ]
    for index, qualification in enumerate(result.ordered_qualification_results):
        reasons = (
            ()
            if qualification.decision is None
            else tuple(reason.value for reason in qualification.decision.reasons)
        )
        lines.extend(
            [
                f"Listing {index}:",
                "  Market name: "
                f"{render_safe_buff_candidate_market_name(qualification.candidate)}",
                f"  Qualification status: {qualification.status.value}",
                "  Rejection reasons: "
                f"{', '.join(reasons) if reasons else 'none'}",
                f"  Facts status: {qualification.lookup_result.status.value}",
            ]
        )
    lines.extend(
        [
            "BUFF requests sent: 0",
            "SteamDT requests sent: 0",
            "Redis used: no",
        ]
    )
    return tuple(lines)


def render_safe_buff_candidate_market_name(
    candidate: BuffTradableCandidate,
) -> str:
    """Render one candidate market name without exposing sensitive content."""

    value = candidate.market_hash_name
    lowered = value.casefold()
    if (
        candidate.listing_id.casefold() in lowered
        or (
            candidate.goods_id is not None
            and candidate.goods_id.casefold() in lowered
        )
        or any(marker in lowered for marker in _SENSITIVE_MARKERS)
        or any(character in value for character in _SENSITIVE_PUNCTUATION)
        or _URI_PATTERN.search(value) is not None
        or _DOMAIN_PATTERN.search(value) is not None
    ):
        value = "[REDACTED]"
    return json.dumps(value, ensure_ascii=True)


def _print_failure(printer: Callable[[str], None], stage: str) -> None:
    safe_stage = stage if stage in _SAFE_FAILURE_STAGES else "internal"
    printer(f"Offline BUFF qualification failed: {safe_stage}")
    printer("BUFF requests sent: 0")
    printer("SteamDT requests sent: 0")
    printer("Redis used: no")


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
        "run_result",
        "internal",
    }
)


def main() -> None:
    """Run the manual offline BUFF qualification integration command."""

    try:
        exit_code = asyncio.run(async_main())
    except KeyboardInterrupt:
        exit_code = 130
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
