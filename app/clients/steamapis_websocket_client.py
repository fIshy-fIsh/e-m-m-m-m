from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedOK

from app.services.steamapis_listing import (
    SteamApisListingObservation,
    SteamApisMessageKind,
    parse_steamapis_message,
)

__all__ = (
    "SteamApisWebSocketClientError",
    "SteamApisWebSocketConfig",
    "SteamApisWebSocketClient",
)

_OFFICIAL_ENDPOINT = "wss://marketplaceapi.steamapis.com/ws/v2/offers"
_FIXED_ERROR_MESSAGE = "SteamApis WebSocket session failed"
_OPEN_TIMEOUT_SECONDS = 10
_MAX_MESSAGE_SIZE_BYTES = 1_048_576
_SUBSCRIPTION_MESSAGE = json.dumps(
    {
        "subscribeTo": ["Buff163"],
        "games": ["CS2"],
        "newFloorOnly": False,
    },
    separators=(",", ":"),
)


class SteamApisWebSocketClientError(RuntimeError):
    """A SteamApis WebSocket session failed without exposing transport details."""

    def __init__(self) -> None:
        super().__init__(_FIXED_ERROR_MESSAGE)


@dataclass(frozen=True, kw_only=True, repr=False)
class SteamApisWebSocketConfig:
    """Secret-bearing configuration for the fixed SteamApis offer endpoint."""

    api_key: str
    endpoint: str = _OFFICIAL_ENDPOINT

    def __post_init__(self) -> None:
        if type(self.api_key) is not str or not str.strip(str.__str__(self.api_key)):
            raise SteamApisWebSocketClientError from None
        if type(self.endpoint) is not str or self.endpoint != _OFFICIAL_ENDPOINT:
            raise SteamApisWebSocketClientError from None


class SteamApisWebSocketClient:
    """Open one read-only SteamApis session and stream parsed target observations."""

    def __init__(
        self,
        config: SteamApisWebSocketConfig,
        *,
        _connector: Callable[..., Any] | None = None,
    ) -> None:
        if type(config) is not SteamApisWebSocketConfig:
            raise SteamApisWebSocketClientError from None
        self._config = SteamApisWebSocketConfig(
            api_key=config.api_key,
            endpoint=config.endpoint,
        )
        self._connector = connect if _connector is None else _connector

    def __repr__(self) -> str:
        return "SteamApisWebSocketClient()"

    async def iter_observations(
        self,
    ) -> AsyncIterator[SteamApisListingObservation]:
        """Yield target observations from one confirmed subscription session."""

        try:
            uri = _build_connection_uri(self._config)
            connection = self._connector(
                uri,
                compression="deflate",
                open_timeout=_OPEN_TIMEOUT_SECONDS,
                max_size=_MAX_MESSAGE_SIZE_BYTES,
            )
            async with connection as websocket:
                await websocket.send(_SUBSCRIPTION_MESSAGE)
                subscribed = False
                async for frame in websocket:
                    if type(frame) is not str:
                        raise SteamApisWebSocketClientError from None
                    parsed = parse_steamapis_message(frame)
                    if parsed.kind is SteamApisMessageKind.SUBSCRIBED:
                        subscribed = True
                        continue
                    if parsed.kind is SteamApisMessageKind.IGNORED:
                        continue
                    if parsed.kind is SteamApisMessageKind.ERROR:
                        raise SteamApisWebSocketClientError from None
                    if parsed.kind is not SteamApisMessageKind.OFFER:
                        raise SteamApisWebSocketClientError from None
                    if not subscribed or parsed.offer is None:
                        raise SteamApisWebSocketClientError from None
                    yield parsed.offer
        except (MemoryError, asyncio.CancelledError):
            raise
        except ConnectionClosedOK:
            return
        except SteamApisWebSocketClientError:
            raise
        except Exception:
            raise SteamApisWebSocketClientError from None


def _build_connection_uri(config: SteamApisWebSocketConfig) -> str:
    return f"{config.endpoint}?{urlencode({'apiKey': config.api_key})}"
