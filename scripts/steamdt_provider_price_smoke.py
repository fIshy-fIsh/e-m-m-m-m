import asyncio
import os
import re
from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient
from app.clients.steamdt_price_selection import SteamDTPriceSelectionConfig
from app.services.price_provider import (
    PriceLookupResult,
    PriceQuote,
    SteamDTPriceProvider,
    SteamDTPriceProviderConfig,
)

MAX_PROVIDER_SMOKE_BATCH_NAMES = 10


def parse_bool_env(
    environ: Mapping[str, str],
    name: str,
    *,
    default: bool = False,
) -> bool:
    """Return true only when an env flag is explicitly set to true."""

    raw_value = environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() == "true"


def parse_market_hash_names(raw_value: str | None) -> list[str]:
    """Parse comma-separated market hash names for manual smoke input."""

    if raw_value is None:
        return []
    return list(dict.fromkeys(name.strip() for name in raw_value.split(",") if name.strip()))


def _parse_decimal_env(environ: Mapping[str, str], name: str, default: str) -> Decimal:
    raw_value = environ.get(name, default).strip()
    try:
        return Decimal(raw_value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a valid decimal value") from exc


def _parse_int_env(environ: Mapping[str, str], name: str, default: str) -> int:
    raw_value = environ.get(name, default).strip()
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid integer value") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be greater than or equal to 0")
    return parsed


def build_provider_config_from_env(
    environ: Mapping[str, str],
) -> SteamDTPriceProviderConfig:
    """Build provider and selector config from smoke-script environment variables."""

    selection_config = SteamDTPriceSelectionConfig(
        max_price_to_avg_ratio=_parse_decimal_env(
            environ,
            "STEAMDT_MAX_PRICE_TO_AVG_RATIO",
            "1.50",
        ),
        fallback_to_lowest_positive=parse_bool_env(
            environ,
            "STEAMDT_AVG_SANITY_FALLBACK_TO_LOWEST_POSITIVE",
        ),
    )
    return SteamDTPriceProviderConfig(
        selection_config=selection_config,
        enable_avg_sanity_check=parse_bool_env(
            environ,
            "STEAMDT_ENABLE_AVG_SANITY_CHECK",
        ),
        fail_closed_on_avg_error=True,
        max_avg_requests_per_batch=_parse_int_env(
            environ,
            "STEAMDT_PROVIDER_MAX_AVG_REQUESTS_PER_BATCH",
            "10",
        ),
    )


def summarize_price_quote(quote: PriceQuote) -> list[str]:
    """Return safe summary lines for one provider quote without raw payload dumps."""

    raw = quote.raw or {}
    platform_prices = raw.get("platform_prices", [])
    candidate_count = len(platform_prices) if isinstance(platform_prices, list) else 0
    return [
        f"market_hash_name: {quote.market_hash_name}",
        f"price_cny: {quote.price_cny}",
        f"source: {quote.source}",
        f"selected_strategy: {raw.get('selected_strategy')}",
        f"reason_codes: {raw.get('reason_codes')}",
        f"selected_platform: {raw.get('selected_platform')}",
        f"candidate_count: {candidate_count}",
    ]


def summarize_price_lookup_result(
    result: PriceLookupResult,
    *,
    api_key: str | None = None,
) -> list[str]:
    """Return safe summary lines for a provider batch lookup result."""

    lines = [
        f"quote count: {len(result.quotes)}",
        f"missing count: {len(result.missing)}",
        f"errors count: {len(result.errors)}",
    ]
    for quote in result.quotes.values():
        raw = quote.raw or {}
        platform_prices = raw.get("platform_prices", [])
        candidate_count = len(platform_prices) if isinstance(platform_prices, list) else 0
        lines.append(
            "quote: "
            f"market_hash_name={quote.market_hash_name}, "
            f"price_cny={quote.price_cny}, "
            f"source={quote.source}, "
            f"selected_strategy={raw.get('selected_strategy')}, "
            f"reason_codes={raw.get('reason_codes')}, "
            f"selected_platform={raw.get('selected_platform')}, "
            f"candidate_count={candidate_count}"
        )
    lines.append(f"missing names: {result.missing}")
    lines.append(
        "errors summary: "
        f"{[_redact_message(error, api_key=api_key) for error in result.errors]}"
    )
    return lines


def _redact_message(message: str, *, api_key: str | None = None) -> str:
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    message = re.sub(
        r"Authorization\s*[:=]\s*Bearer\s+[^\s,;]+",
        "[REDACTED_AUTHORIZATION]",
        message,
        flags=re.IGNORECASE,
    )
    message = re.sub(
        r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}",
        "Bearer [REDACTED]",
        message,
    )
    if len(message) > 300:
        return f"{message[:300]}..."
    return message


def _safe_error_message(exc: Exception, *, api_key: str | None) -> str:
    """Format an exception without leaking API keys or Authorization headers."""

    message = _redact_message(str(exc), api_key=api_key)
    if not message:
        return type(exc).__name__
    return f"{type(exc).__name__}: {message}"


async def run_provider_smoke(
    environ: Mapping[str, str] | None = None,
    *,
    client_factory: Callable[[SteamDTClientConfig], Any] | None = None,
    provider_factory: Callable[[Any, SteamDTPriceProviderConfig], Any] | None = None,
    printer: Callable[[str], None] = print,
) -> int:
    """Run the manual provider smoke flow with injectable factories for tests."""

    environ = os.environ if environ is None else environ
    client_factory = client_factory or (lambda config: SteamDTHttpClient(config))
    provider_factory = provider_factory or (
        lambda client, config: SteamDTPriceProvider(client, config)
    )

    base_url = environ.get("STEAMDT_BASE_URL", "https://open.steamdt.com")
    api_key = environ.get("STEAMDT_API_KEY")
    dry_run = environ.get("STEAMDT_DRY_RUN", "true").strip().lower() != "false"
    batch_mode = parse_bool_env(environ, "STEAMDT_PROVIDER_BATCH_MODE")
    avg_sanity_enabled = parse_bool_env(environ, "STEAMDT_ENABLE_AVG_SANITY_CHECK")

    if dry_run:
        printer("SteamDT provider smoke request skipped: STEAMDT_DRY_RUN is not false.")
        return 0
    if not api_key:
        printer("SteamDT provider smoke request skipped: STEAMDT_API_KEY is missing.")
        return 0

    if batch_mode:
        names = parse_market_hash_names(environ.get("STEAMDT_SMOKE_MARKET_HASH_NAMES"))
        if not names:
            printer(
                "SteamDT provider batch smoke request skipped: "
                "STEAMDT_SMOKE_MARKET_HASH_NAMES is missing."
            )
            return 0
        if len(names) > MAX_PROVIDER_SMOKE_BATCH_NAMES:
            printer(
                "SteamDT provider batch smoke request skipped: "
                "maximum 10 market hash names are allowed."
            )
            return 0
    else:
        market_hash_name = environ.get("STEAMDT_SMOKE_MARKET_HASH_NAME")
        if market_hash_name is None or not market_hash_name.strip():
            printer(
                "SteamDT provider smoke request skipped: "
                "STEAMDT_SMOKE_MARKET_HASH_NAME is missing."
            )
            return 0
        names = [market_hash_name.strip()]

    try:
        provider_config = build_provider_config_from_env(environ)
    except ValueError as exc:
        printer(f"SteamDT provider smoke request skipped: {exc}")
        return 0

    client = client_factory(
        SteamDTClientConfig(
            base_url=base_url,
            api_key=api_key,
            dry_run=False,
        )
    )
    provider = provider_factory(client, provider_config)

    if batch_mode:
        try:
            result = await provider.get_prices(names)
        except Exception as exc:
            printer(
                "SteamDT provider batch smoke request failed: "
                f"{_safe_error_message(exc, api_key=api_key)}"
            )
            return 1
        printer("provider mode: batch")
        printer(f"requested count: {len(names)}")
        printer(f"avg sanity enabled: {avg_sanity_enabled}")
        for line in summarize_price_lookup_result(result, api_key=api_key):
            printer(line)
        return 0

    try:
        quote = await provider.get_price(names[0])
    except Exception as exc:
        printer(
            "SteamDT provider smoke request failed: "
            f"{_safe_error_message(exc, api_key=api_key)}"
        )
        return 1

    printer("provider mode: single")
    for line in summarize_price_quote(quote):
        printer(line)
    printer(f"avg sanity enabled: {avg_sanity_enabled}")
    return 0


def main() -> None:
    """Run a manual official read-only SteamDT provider smoke test.

    Default behavior is dry-run and does not make real SteamDT requests. Set
    STEAMDT_DRY_RUN=false and STEAMDT_API_KEY explicitly before manual use.
    """

    asyncio.run(run_provider_smoke())


if __name__ == "__main__":
    main()
