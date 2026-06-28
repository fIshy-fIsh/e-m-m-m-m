import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.clients.metadata_client import MetadataClient, MetadataClientConfig
from app.services.metadata_provider import ByMykelMetadataProvider, LocalJsonMetadataProvider

FIXTURE_PATH = Path("tests/fixtures/metadata/sample_skins.json")



def test_local_json_metadata_provider_reads_fixture() -> None:
    provider = LocalJsonMetadataProvider(FIXTURE_PATH)

    skins = asyncio.run(provider.fetch_skins())

    assert len(skins) >= 2
    assert skins[0].market_hash_name



def test_local_json_metadata_provider_calls_normalize() -> None:
    provider = LocalJsonMetadataProvider(FIXTURE_PATH)

    with patch("app.services.metadata_provider.normalize_skins") as mock_normalize:
        mock_normalize.return_value = []

        skins = asyncio.run(provider.fetch_skins())

    assert skins == []
    mock_normalize.assert_called_once()



def test_metadata_client_fetch_raw_skins_with_mocked_http_response() -> None:
    config = MetadataClientConfig(
        base_url="https://example.test",
        timeout_seconds=1.0,
        max_retries=0,
        rate_limit_per_minute=60,
    )
    client = MetadataClient(config)
    payload = [
        {
            "market_hash_name": "AK-47 | Redline",
            "rarity": "Classified",
            "min_float": 0.1,
            "max_float": 0.7,
        }
    ]

    response = httpx.Response(200, json=payload)
    request = httpx.Request("GET", "https://example.test/skins.json")
    response.request = request

    with patch("httpx.AsyncClient") as mock_async_client_class:
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__.return_value = mock_async_client
        mock_async_client.get.return_value = response
        mock_async_client_class.return_value = mock_async_client

        result = asyncio.run(client.fetch_raw_skins())

    assert result == payload



def test_bymykel_metadata_provider_uses_mocked_client() -> None:
    mocked_client = AsyncMock()
    mocked_client.fetch_raw_skins.return_value = [
        {
            "market_hash_name": "AK-47 | Redline (Field-Tested)",
            "name": "AK-47 | Redline (Field-Tested)",
            "rarity": "Classified",
            "collection_name": "Collection Alpha",
            "min_float": 0.10,
            "max_float": 0.70,
        }
    ]
    provider = ByMykelMetadataProvider(mocked_client)

    skins = asyncio.run(provider.fetch_skins())

    assert len(skins) == 1
    mocked_client.fetch_raw_skins.assert_awaited_once()



def test_metadata_client_http_error_raises_runtime_error() -> None:
    config = MetadataClientConfig(
        base_url="https://example.test",
        timeout_seconds=1.0,
        max_retries=0,
        rate_limit_per_minute=60,
    )
    client = MetadataClient(config)

    with patch("httpx.AsyncClient") as mock_async_client_class:
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__.return_value = mock_async_client
        mock_async_client.get.side_effect = httpx.HTTPStatusError(
            "boom",
            request=httpx.Request("GET", "https://example.test/skins.json"),
            response=httpx.Response(500),
        )
        mock_async_client_class.return_value = mock_async_client

        with pytest.raises(RuntimeError, match="failed to fetch raw metadata skins"):
            asyncio.run(client.fetch_raw_skins())



def test_metadata_client_timeout_raises_runtime_error() -> None:
    config = MetadataClientConfig(
        base_url="https://example.test",
        timeout_seconds=1.0,
        max_retries=0,
        rate_limit_per_minute=60,
    )
    client = MetadataClient(config)

    with patch("httpx.AsyncClient") as mock_async_client_class:
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__.return_value = mock_async_client
        mock_async_client.get.side_effect = httpx.ReadTimeout("timeout")
        mock_async_client_class.return_value = mock_async_client

        with pytest.raises(RuntimeError, match="failed to fetch raw metadata skins"):
            asyncio.run(client.fetch_raw_skins())
