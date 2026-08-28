import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class MetadataClientConfig:
    base_url: str
    timeout_seconds: float
    max_retries: int
    rate_limit_per_minute: int


class MetadataClient:
    """HTTP client for fetching raw CS2 metadata payloads.

    This client intentionally returns raw JSON objects only. Field mapping and fallback
    rules belong in metadata_service, not in the client or trade-up engine layers.
    """

    def __init__(self, config: MetadataClientConfig) -> None:
        self.config = config
        self._minimum_interval_seconds = (
            60.0 / config.rate_limit_per_minute if config.rate_limit_per_minute > 0 else 0.0
        )
        self._last_request_monotonic = 0.0

    async def fetch_raw_skins(self) -> list[dict[str, Any]]:
        """Fetch raw skin metadata payloads with timeout, retry, and simple rate limiting."""

        await self._respect_rate_limit()

        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    base_url=self.config.base_url,
                    timeout=self.config.timeout_seconds,
                ) as client:
                    response = await client.get("/skins.json")
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, list):
                        raise ValueError("metadata API must return a list of skin objects")
                    if not all(isinstance(item, dict) for item in payload):
                        raise ValueError("metadata API items must be objects")
                    return payload
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    raise RuntimeError("failed to fetch raw metadata skins") from exc
                await asyncio.sleep(2**attempt * 0.1)

        raise RuntimeError("failed to fetch raw metadata skins") from last_error

    async def _respect_rate_limit(self) -> None:
        """Apply a simple minimum-interval gate between outgoing requests."""

        if self._minimum_interval_seconds <= 0:
            return

        now = asyncio.get_running_loop().time()
        elapsed = now - self._last_request_monotonic
        remaining = self._minimum_interval_seconds - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)
        self._last_request_monotonic = asyncio.get_running_loop().time()
