import os
from decimal import Decimal, InvalidOperation

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient
from app.clients.steamdt_price_selection import SteamDTPriceSelectionConfig


def _env_flag(name: str, *, default: bool = False) -> bool:
    """Return true only when an env flag is explicitly set to true."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() == "true"


def _parse_decimal_env(name: str, default: str) -> Decimal:
    """Parse a Decimal env value for smoke-only configuration."""

    raw_value = os.getenv(name, default).strip()
    try:
        return Decimal(raw_value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a valid decimal value") from exc


def _safe_error_message(exc: Exception, *, api_key: str | None) -> str:
    """Format an exception without leaking a configured API key."""

    message = str(exc)
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    return message


async def _run() -> None:
    base_url = os.getenv("STEAMDT_BASE_URL", "https://open.steamdt.com")
    api_key = os.getenv("STEAMDT_API_KEY")
    dry_run = os.getenv("STEAMDT_DRY_RUN", "true").lower() != "false"
    market_hash_name = os.getenv("STEAMDT_SMOKE_MARKET_HASH_NAME")
    avg_sanity_enabled = _env_flag("STEAMDT_ENABLE_AVG_SANITY_CHECK")
    fallback_to_lowest_positive = _env_flag(
        "STEAMDT_AVG_SANITY_FALLBACK_TO_LOWEST_POSITIVE"
    )

    if dry_run:
        print("SteamDT smoke request skipped: STEAMDT_DRY_RUN is not false.")
        return
    if not api_key:
        print("SteamDT smoke request skipped: STEAMDT_API_KEY is missing.")
        return
    if not market_hash_name:
        print("SteamDT smoke request skipped: STEAMDT_SMOKE_MARKET_HASH_NAME is missing.")
        return

    max_price_to_avg_ratio: Decimal | None = None
    selection_config = None
    if avg_sanity_enabled:
        try:
            max_price_to_avg_ratio = _parse_decimal_env(
                "STEAMDT_MAX_PRICE_TO_AVG_RATIO",
                "1.50",
            )
            selection_config = SteamDTPriceSelectionConfig(
                max_price_to_avg_ratio=max_price_to_avg_ratio,
                fallback_to_lowest_positive=fallback_to_lowest_positive,
            )
        except ValueError as exc:
            print(f"SteamDT smoke request skipped: {exc}")
            return

    client = SteamDTHttpClient(
        SteamDTClientConfig(
            base_url=base_url,
            api_key=api_key,
            dry_run=False,
        )
    )

    avg_price_cny: Decimal | None = None
    if avg_sanity_enabled:
        try:
            avg_result = await client.get_avg_price(market_hash_name)
        except Exception as exc:
            print(
                "SteamDT avg sanity request failed; selection skipped: "
                f"{_safe_error_message(exc, api_key=api_key)}"
            )
            return
        avg_price_cny = avg_result.avg_price_cny

    try:
        quote = await client.get_price_single_with_selection(
            market_hash_name,
            selection_config=selection_config,
            avg_price_cny=avg_price_cny,
        )
    except Exception as exc:
        print(f"SteamDT smoke request failed: {_safe_error_message(exc, api_key=api_key)}")
        return

    raw = quote.raw or {}
    platform_prices = raw.get("platform_prices", [])
    print(f"market_hash_name: {quote.market_hash_name}")
    print(f"selected price_cny: {quote.price_cny}")
    print(f"source: {quote.source}")
    print(f"avg sanity enabled: {avg_sanity_enabled}")
    print(f"avg_price_cny: {avg_price_cny}")
    print(f"max_price_to_avg_ratio: {max_price_to_avg_ratio}")
    print(f"fallback_to_lowest_positive: {fallback_to_lowest_positive}")
    print(f"selected_strategy: {raw.get('selected_strategy')}")
    print(f"reason_codes: {raw.get('reason_codes')}")
    print(f"selected_platform: {raw.get('selected_platform')}")
    print(f"candidate_count: {len(platform_prices)}")


def main() -> None:
    """Run a manual official read-only SteamDT price-single smoke test.

    PowerShell example:
    $env:STEAMDT_API_KEY="your_api_key"
    $env:STEAMDT_DRY_RUN="false"
    $env:STEAMDT_SMOKE_MARKET_HASH_NAME="AK-47 | Redline (Field-Tested)"
    # Optional avg sanity check:
    $env:STEAMDT_ENABLE_AVG_SANITY_CHECK="true"
    $env:STEAMDT_MAX_PRICE_TO_AVG_RATIO="1.50"
    $env:STEAMDT_AVG_SANITY_FALLBACK_TO_LOWEST_POSITIVE="false"
    py -3.13 scripts/steamdt_price_single_smoke.py

    Git Bash example:
    STEAMDT_API_KEY="your_api_key" \
    STEAMDT_DRY_RUN=false \
    STEAMDT_SMOKE_MARKET_HASH_NAME="AK-47 | Redline (Field-Tested)" \
    STEAMDT_ENABLE_AVG_SANITY_CHECK=true \
    STEAMDT_MAX_PRICE_TO_AVG_RATIO=1.50 \
    STEAMDT_AVG_SANITY_FALLBACK_TO_LOWEST_POSITIVE=false \
    py -3.13 scripts/steamdt_price_single_smoke.py
    """

    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    main()
