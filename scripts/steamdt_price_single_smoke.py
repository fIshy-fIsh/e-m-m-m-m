import os

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient


async def _run() -> None:
    base_url = os.getenv("STEAMDT_BASE_URL", "https://open.steamdt.com")
    api_key = os.getenv("STEAMDT_API_KEY")
    dry_run = os.getenv("STEAMDT_DRY_RUN", "true").lower() != "false"
    market_hash_name = os.getenv("STEAMDT_SMOKE_MARKET_HASH_NAME")

    if dry_run:
        print("SteamDT smoke request skipped: STEAMDT_DRY_RUN is not false.")
        return
    if not api_key:
        print("SteamDT smoke request skipped: STEAMDT_API_KEY is missing.")
        return
    if not market_hash_name:
        print("SteamDT smoke request skipped: STEAMDT_SMOKE_MARKET_HASH_NAME is missing.")
        return

    client = SteamDTHttpClient(
        SteamDTClientConfig(
            base_url=base_url,
            api_key=api_key,
            dry_run=False,
        )
    )

    try:
        quote = await client.get_price_single(market_hash_name)
    except Exception as exc:
        print(f"SteamDT smoke request failed: {exc}")
        return

    raw = quote.raw or {}
    platform_prices = raw.get("platform_prices", [])
    print(f"market_hash_name: {quote.market_hash_name}")
    print(f"selected price_cny: {quote.price_cny}")
    print(f"source: {quote.source}")
    print(f"selected_strategy: {raw.get('selected_strategy')}")
    print(f"reason_codes: {raw.get('reason_codes')}")
    selected_platform = None
    if platform_prices:
        selected_platform = min(
            (
                item.get("platform")
                for item in platform_prices
                if isinstance(item, dict) and item.get("platform") is not None
            ),
            default=None,
        )
    print(f"selected_platform: {selected_platform}")
    print(f"candidate count: {len(platform_prices)}")



def main() -> None:
    """Run a manual official read-only SteamDT price-single smoke test.

    PowerShell example:
    $env:STEAMDT_API_KEY="your_api_key"
    $env:STEAMDT_DRY_RUN="false"
    $env:STEAMDT_SMOKE_MARKET_HASH_NAME="AK-47 | Redline (Field-Tested)"
    py -3.13 scripts/steamdt_price_single_smoke.py

    Git Bash example:
    STEAMDT_API_KEY="your_api_key" \
    STEAMDT_DRY_RUN=false \
    STEAMDT_SMOKE_MARKET_HASH_NAME="AK-47 | Redline (Field-Tested)" \
    py -3.13 scripts/steamdt_price_single_smoke.py
    """

    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    main()
