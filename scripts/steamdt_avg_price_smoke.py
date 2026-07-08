import os

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient


async def _run() -> None:
    base_url = os.getenv("STEAMDT_BASE_URL", "https://open.steamdt.com")
    api_key = os.getenv("STEAMDT_API_KEY")
    dry_run = os.getenv("STEAMDT_DRY_RUN", "true").lower() != "false"
    market_hash_name = os.getenv("STEAMDT_SMOKE_MARKET_HASH_NAME")

    if dry_run:
        print("SteamDT avg smoke request skipped: STEAMDT_DRY_RUN is not false.")
        return
    if not api_key:
        print("SteamDT avg smoke request skipped: STEAMDT_API_KEY is missing.")
        return
    if not market_hash_name:
        print("SteamDT avg smoke request skipped: STEAMDT_SMOKE_MARKET_HASH_NAME is missing.")
        return

    client = SteamDTHttpClient(
        SteamDTClientConfig(
            base_url=base_url,
            api_key=api_key,
            dry_run=False,
        )
    )

    try:
        result = await client.get_avg_price(market_hash_name)
    except Exception as exc:
        print(f"SteamDT avg smoke request failed: {exc}")
        return

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
