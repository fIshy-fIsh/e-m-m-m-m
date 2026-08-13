from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.clients.steamapis_websocket_client import SteamApisWebSocketClient
from app.services.steamapis_offer_pool import SteamApisOfferPool

__all__ = (
    "SteamApisOfferSessionError",
    "SteamApisOfferSessionResult",
    "run_steamapis_offer_session",
)

_FIXED_ERROR_MESSAGE = "SteamApis offer session failed"


class SteamApisOfferSessionError(RuntimeError):
    """A foreground SteamApis offer session failed without exposing details."""

    def __init__(self) -> None:
        super().__init__(_FIXED_ERROR_MESSAGE)


@dataclass(frozen=True, kw_only=True, repr=False)
class SteamApisOfferSessionResult:
    """Safe completion count for one normally completed offer session."""

    observations_consumed: int

    def __post_init__(self) -> None:
        try:
            if (
                type(self.observations_consumed) is not int
                or self.observations_consumed < 0
            ):
                raise SteamApisOfferSessionError
        except MemoryError:
            raise
        except Exception:
            raise SteamApisOfferSessionError from None


async def run_steamapis_offer_session(
    *,
    client: SteamApisWebSocketClient,
    pool: SteamApisOfferPool,
) -> SteamApisOfferSessionResult:
    """Ingest one client session sequentially into the caller-owned offer pool."""

    try:
        observations_consumed = 0
        async for observation in client.iter_observations():
            pool.ingest(observation)
            observations_consumed += 1
        return SteamApisOfferSessionResult(
            observations_consumed=observations_consumed,
        )
    except (MemoryError, asyncio.CancelledError):
        raise
    except Exception:
        raise SteamApisOfferSessionError from None
