import re
from typing import Any

_REDACTED_AUTHORIZATION = "[REDACTED_AUTHORIZATION]"
_REDACTED_SECRET = "[REDACTED]"


def redact_steamdt_error_text(value: Any, *, api_key: str | None = None) -> str:
    """Return a short error string without API keys or Authorization headers."""

    message = "" if value is None else str(value)
    if api_key:
        message = message.replace(api_key, _REDACTED_SECRET)
    message = re.sub(
        r"Authorization\s*[:=]\s*Bearer\s+[^\s,;]+",
        _REDACTED_AUTHORIZATION,
        message,
        flags=re.IGNORECASE,
    )
    message = re.sub(
        r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}",
        "Bearer [REDACTED]",
        message,
    )
    if len(message) > 300:
        return f"{message[:300]}..."
    return message


class SteamDTError(RuntimeError):
    """Base class for sanitized SteamDT client errors."""

    def __init__(self, message: str, *, endpoint: str | None = None) -> None:
        self.endpoint = endpoint
        self.message = redact_steamdt_error_text(message)
        super().__init__(self.message)

    def __str__(self) -> str:
        parts = [self.__class__.__name__]
        if self.endpoint is not None:
            parts.append(f"endpoint={self.endpoint}")
        if self.message:
            parts.append(f"message={self.message}")
        return ": ".join(parts)


class SteamDTTransportError(SteamDTError):
    """Network/transport failure that may be retried within the configured limit."""


class SteamDTHttpStatusError(SteamDTError):
    """HTTP response status failure from SteamDT."""

    def __init__(
        self,
        message: str,
        *,
        endpoint: str | None = None,
        status_code: int,
    ) -> None:
        self.status_code = status_code
        super().__init__(message, endpoint=endpoint)

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base}: status_code={self.status_code}"


class SteamDTApiError(SteamDTError):
    """SteamDT wrapper-level API error from a successful HTTP response."""

    def __init__(
        self,
        message: str,
        *,
        endpoint: str | None = None,
        error_code: int | str | None = None,
        error_msg: str | None = None,
        error_code_str: str | None = None,
    ) -> None:
        self.error_code = error_code
        self.error_msg = redact_steamdt_error_text(error_msg)
        self.error_code_str = redact_steamdt_error_text(error_code_str)
        super().__init__(message, endpoint=endpoint)

    def __str__(self) -> str:
        base = super().__str__()
        return (
            f"{base}: error_code={self.error_code}, "
            f"error_msg={self.error_msg}, error_code_str={self.error_code_str}"
        )


class SteamDTRateLimitError(SteamDTError):
    """SteamDT HTTP/API rate-limit error that must not be automatically retried."""

    def __init__(
        self,
        message: str,
        *,
        endpoint: str | None = None,
        retry_after_seconds: float | None = None,
        error_code: int | str | None = None,
        error_msg: str | None = None,
        error_code_str: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.retry_after_seconds = retry_after_seconds
        self.error_code = error_code
        self.error_msg = redact_steamdt_error_text(error_msg)
        self.error_code_str = redact_steamdt_error_text(error_code_str)
        self.status_code = status_code
        super().__init__(message, endpoint=endpoint)

    def __str__(self) -> str:
        base = super().__str__()
        return (
            f"{base}: status_code={self.status_code}, error_code={self.error_code}, "
            f"error_msg={self.error_msg}, error_code_str={self.error_code_str}, "
            f"retry_after_seconds={self.retry_after_seconds}"
        )


class SteamDTRateLimitBackendError(SteamDTError):
    """Rate-limiter backend failure that should fail closed before SteamDT requests."""

    def __init__(
        self,
        message: str,
        *,
        endpoint: str | None = None,
        backend: str,
        operation: str,
    ) -> None:
        self.backend = redact_steamdt_error_text(backend)
        self.operation = redact_steamdt_error_text(operation)
        super().__init__(message, endpoint=endpoint)

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base}: backend={self.backend}, operation={self.operation}"


class SteamDTResponseParseError(SteamDTError, ValueError):
    """SteamDT response schema/JSON/field conversion parse failure."""
