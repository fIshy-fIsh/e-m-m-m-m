import os

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient


async def _run() -> None:
    base_url = os.getenv("STEAMDT_BASE_URL", "https://open.steamdt.com")
    api_key = os.getenv("STEAMDT_API_KEY")
    dry_run = os.getenv("STEAMDT_DRY_RUN", "true").lower() != "false"
    market_hash_names_raw = os.getenv("STEAMDT_SMOKE_MARKET_HASH_NAMES")

    if dry_run:
        print("SteamDT batch smoke request skipped: STEAMDT_DRY_RUN is not false.")
        return
    if not api_key:
        print("SteamDT batch smoke request skipped: STEAMDT_API_KEY is missing.")
        return
    if not market_hash_names_raw:
        print("SteamDT batch smoke request skipped: STEAMDT_SMOKE_MARKET_HASH_NAMES is missing.")
        return

    names = [name.strip() for name in market_hash_names_raw.split(",") if name.strip()]
    if not names:
        print("SteamDT batch smoke request skipped: no valid market hash names were provided.")
        return
    if len(names) > 10:
        print("SteamDT batch smoke request skipped: maximum 10 market hash names are allowed.")
        return

    client = SteamDTHttpClient(
        SteamDTClientConfig(
            base_url=base_url,
            api_key=api_key,
            dry_run=False,
        )
    )

    try:
        result = await client.get_price_batch(names)
    except Exception as exc:
        print(f"SteamDT batch smoke request failed: {exc}")
        return

    print(f"requested count: {len(names)}")
    print(f"quote count: {len(result.quotes)}")
    print(f"missing count: {len(result.missing)}")
    for quote in result.quotes.values():
        raw = quote.raw or {}
        platform_prices = raw.get("platform_prices", [])
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
        print(
            f"quote: market_hash_name={quote.market_hash_name}, "
            f"price_cny={quote.price_cny}, "
            f"source={quote.source}, "
            f"selected_strategy={raw.get('selected_strategy')}, "
            f"reason_codes={raw.get('reason_codes')}, "
            f"selected_platform={selected_platform}, "
            f"candidate_count={len(platform_prices)}"
        )
    print(f"missing names: {result.missing}")



def main() -> None:
    """Run a manual official read-only SteamDT price-batch smoke test.

    PowerShell example:
    $env:STEAMDT_API_KEY="your_api_key"
    $env:STEAMDT_DRY_RUN="false"
    $env:STEAMDT_SMOKE_MARKET_HASH_NAMES=
    "AK-47 | Redline (Field-Tested),AWP | Asiimov (Field-Tested)"
    py -3.13 scripts/steamdt_price_batch_smoke.py

    Git Bash example:
    STEAMDT_API_KEY="your_api_key" \
    STEAMDT_DRY_RUN=false \
    STEAMDT_SMOKE_MARKET_HASH_NAMES=
    "AK-47 | Redline (Field-Tested),AWP | Asiimov (Field-Tested)" \
    py -3.13 scripts/steamdt_price_batch_smoke.py
    """

    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    main()
