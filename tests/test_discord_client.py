import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.clients.discord_client import (
    AlertDispatchResult,
    DiscordWebhookClient,
    DiscordWebhookConfig,
    DiscordWebhookError,
)


def test_discord_webhook_config_allows_empty_url_in_dry_run() -> None:
    config = DiscordWebhookConfig(webhook_url=None, dry_run=True)

    assert config.webhook_url is None



def test_discord_webhook_config_requires_url_when_not_dry_run() -> None:
    with pytest.raises(ValueError, match="webhook_url"):
        DiscordWebhookConfig(webhook_url=None, dry_run=False)



def test_discord_webhook_config_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        DiscordWebhookConfig(webhook_url=None, dry_run=True, timeout_seconds=0)



def test_discord_webhook_config_rejects_negative_retries() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        DiscordWebhookConfig(webhook_url=None, dry_run=True, max_retries=-1)



def test_discord_webhook_client_dry_run_returns_success_without_real_send() -> None:
    client = DiscordWebhookClient(DiscordWebhookConfig(webhook_url=None, dry_run=True))

    result = asyncio.run(client.send_payload({"content": "hello"}))

    assert result.sent is True
    assert result.dry_run is True
    assert result.status_code is None



def test_discord_webhook_client_sends_successfully_with_mocked_http() -> None:
    client = DiscordWebhookClient(
        DiscordWebhookConfig(
            webhook_url="https://discord.example/webhook",
            dry_run=False,
        )
    )
    response = httpx.Response(204)

    with patch("httpx.AsyncClient") as mock_async_client_class:
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__.return_value = mock_async_client
        mock_async_client.post.return_value = response
        mock_async_client_class.return_value = mock_async_client

        result = asyncio.run(client.send_payload({"content": "hello"}))

    assert isinstance(result, AlertDispatchResult)
    assert result.sent is True
    assert result.dry_run is False
    assert result.status_code == 204



def test_discord_webhook_client_raises_on_non_2xx_response() -> None:
    client = DiscordWebhookClient(
        DiscordWebhookConfig(
            webhook_url="https://discord.example/webhook",
            dry_run=False,
            max_retries=0,
        )
    )
    response = httpx.Response(500)

    with patch("httpx.AsyncClient") as mock_async_client_class:
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__.return_value = mock_async_client
        mock_async_client.post.return_value = response
        mock_async_client_class.return_value = mock_async_client

        with pytest.raises(DiscordWebhookError, match="dispatch failed"):
            asyncio.run(client.send_payload({"content": "hello"}))



def test_discord_webhook_client_error_does_not_leak_full_webhook_url() -> None:
    webhook_url = "https://discord.example/super-secret-webhook"
    client = DiscordWebhookClient(
        DiscordWebhookConfig(
            webhook_url=webhook_url,
            dry_run=False,
            max_retries=0,
        )
    )

    with patch("httpx.AsyncClient") as mock_async_client_class:
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__.return_value = mock_async_client
        mock_async_client.post.side_effect = httpx.ConnectError("boom")
        mock_async_client_class.return_value = mock_async_client

        with pytest.raises(DiscordWebhookError) as exc_info:
            asyncio.run(client.send_payload({"content": "hello"}))

    assert webhook_url not in str(exc_info.value)
