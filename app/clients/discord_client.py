import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


class DiscordWebhookError(RuntimeError):
    """Raised when a Discord webhook request fails."""


@dataclass(frozen=True, repr=False)
class DiscordWebhookConfig:
    """Configuration for Discord webhook delivery."""

    webhook_url: str | None
    timeout_seconds: float = 10.0
    max_retries: int = 3
    dry_run: bool = True
    mention_user_id: str | None = None
    mention_role_id: str | None = None

    def __post_init__(self) -> None:
        if not self.dry_run and not self.webhook_url:
            raise ValueError("webhook_url is required when dry_run is False")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        if self.max_retries < 0:
            raise ValueError("max_retries must be greater than or equal to 0")

    def __repr__(self) -> str:
        return (
            "DiscordWebhookConfig("
            f"webhook_url={self._redacted_webhook_url()}, "
            f"timeout_seconds={self.timeout_seconds}, "
            f"max_retries={self.max_retries}, "
            f"dry_run={self.dry_run}, "
            f"mention_user_id={self.mention_user_id!r}, "
            f"mention_role_id={self.mention_role_id!r}"
            ")"
        )

    def _redacted_webhook_url(self) -> str | None:
        if not self.webhook_url:
            return None
        return "[REDACTED]"


@dataclass(frozen=True)
class AlertDispatchResult:
    """Result returned after attempting to dispatch a Discord alert."""

    sent: bool
    dry_run: bool
    status_code: int | None
    message: str
    dedupe_key: str | None = None


class DiscordWebhookClient:
    """Discord webhook client with dry-run, timeout, retry, and error handling."""

    def __init__(self, config: DiscordWebhookConfig) -> None:
        self.config = config

    async def send_payload(self, payload: dict[str, Any]) -> AlertDispatchResult:
        """Send a Discord webhook payload or short-circuit in dry-run mode."""

        if self.config.dry_run:
            return AlertDispatchResult(
                sent=True,
                dry_run=True,
                status_code=None,
                message="Dry run: payload not sent",
            )

        webhook_url = self.config.webhook_url
        if webhook_url is None:
            raise DiscordWebhookError("Discord webhook URL is missing")

        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                    response = await client.post(webhook_url, json=payload)
                    if not 200 <= response.status_code < 300:
                        raise DiscordWebhookError(
                            f"Discord webhook request failed with status {response.status_code}"
                        )
                    return AlertDispatchResult(
                        sent=True,
                        dry_run=False,
                        status_code=response.status_code,
                        message="Discord webhook sent successfully",
                    )
            except (httpx.HTTPError, DiscordWebhookError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    raise DiscordWebhookError(
                        "Discord webhook dispatch failed for [REDACTED URL]"
                    ) from exc
                await asyncio.sleep(2**attempt * 0.1)

        raise DiscordWebhookError(
            "Discord webhook dispatch failed for [REDACTED URL]"
        ) from last_error
