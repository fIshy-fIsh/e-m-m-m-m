# ruff: noqa: I001
import os

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient
if __package__:
    from .steamdt_smoke_utils import (
        is_explicit_false,
        print_guard_exit,
        safe_error_message,
    )
else:
    from steamdt_smoke_utils import (
        is_explicit_false,
        print_guard_exit,
        safe_error_message,
    )


async def _run() -> None:
    environ = os.environ
    base_url = environ.get("STEAMDT_BASE_URL", "https://open.steamdt.com")
    api_key = environ.get("STEAMDT_API_KEY")
    market_hash_name = environ.get("STEAMDT_SMOKE_MARKET_HASH_NAME")

    if not is_explicit_false(environ, "STEAMDT_DRY_RUN"):
        print_guard_exit(print, "SteamDT avg smoke request skipped: STEAMDT_DRY_RUN is not false.")
        return
    if not api_key:
        print_guard_exit(print, "SteamDT avg smoke request skipped: STEAMDT_API_KEY is missing.")
        return
    if market_hash_name is None or not market_hash_name.strip():
        print_guard_exit(
            print,
            "SteamDT avg smoke request skipped: STEAMDT_SMOKE_MARKET_HASH_NAME is missing.",
        )
        return

    client = SteamDTHttpClient(
        SteamDTClientConfig(
            base_url=base_url,
            api_key=api_key,
            dry_run=False,
        )
    )

    try:
        result = await client.get_avg_price(market_hash_name.strip())
    except Exception as exc:
        print(f"SteamDT avg smoke request failed: {safe_error_message(exc, api_key=api_key)}")
        return

    print("smoke script: steamdt_avg_price_smoke")
    print("smoke mode: avg")
    print(f"market_hash_name: {result.market_hash_name}")
    print(f"avg_price_cny: {result.avg_price_cny}")
    platform_avg_prices = result.platform_avg_prices or {}
    print(f"platform_avg_prices count: {len(platform_avg_prices)}")
    print(f"platform_avg_prices summary: {platform_avg_prices}")


def main() -> None:
    """Run a manual official read-only SteamDT avg price smoke test.

    PowerShell example:
    $env:STEAMDT_API_KEY="your_api_key"
    $env:STEAMDT_DRY_RUN="false"
    $env:STEAMDT_SMOKE_MARKET_HASH_NAME="AK-47 | Redline (Field-Tested)"
    py -3.13 scripts/steamdt_avg_price_smoke.py

    Git Bash example:
    STEAMDT_API_KEY="your_api_key" \
    STEAMDT_DRY_RUN=false \
    STEAMDT_SMOKE_MARKET_HASH_NAME="AK-47 | Redline (Field-Tested)" \
    py -3.13 scripts/steamdt_avg_price_smoke.py
    """

    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    main()
