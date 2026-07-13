import re
from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

MAX_STEAMDT_SMOKE_BATCH_NAMES = 10


def parse_bool_env(
    environ: Mapping[str, str],
    name: str,
    *,
    default: bool = False,
) -> bool:
    """Return true only when an env flag is explicitly set to true."""

    raw_value = environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() == "true"


def is_explicit_false(environ: Mapping[str, str], name: str) -> bool:
    """Return true only when an env flag is explicitly set to false."""

    return environ.get(name, "").strip().lower() == "false"


def parse_decimal_env(environ: Mapping[str, str], name: str, default: str) -> Decimal:
    """Parse a Decimal env value for manual smoke configuration."""

    raw_value = environ.get(name, default).strip()
    try:
        return Decimal(raw_value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a valid decimal value") from exc


def parse_int_env(environ: Mapping[str, str], name: str, default: str) -> int:
    """Parse a non-negative integer env value for manual smoke configuration."""

    raw_value = environ.get(name, default).strip()
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid integer value") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be greater than or equal to 0")
    return parsed


def parse_market_hash_names(raw_value: str | None) -> list[str]:
    """Parse comma-separated market hash names, deduplicated in input order."""

    if raw_value is None:
        return []
    return list(dict.fromkeys(name.strip() for name in raw_value.split(",") if name.strip()))


def redact_message(message: str, *, api_key: str | None = None) -> str:
    """Redact API keys, Authorization bearer headers, and long error payloads."""

    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    message = re.sub(
        r"Authorization\s*[:=]\s*Bearer\s+[^\s,;]+",
        "[REDACTED_AUTHORIZATION]",
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


def safe_error_message(exc: Exception, *, api_key: str | None) -> str:
    """Format an exception without leaking API keys or Authorization headers."""

    message = redact_message(str(exc), api_key=api_key)
    if not message:
        return type(exc).__name__
    return f"{type(exc).__name__}: {message}"


def print_guard_exit(printer: Callable[[str], None], message: str) -> int:
    """Print a guard-exit message and return a success exit code."""

    printer(message)
    return 0


def summarize_quote_raw(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Extract safe selector summary fields from a quote raw payload."""

    raw = raw or {}
    platform_prices = raw.get("platform_prices", [])
    return {
        "selected_strategy": raw.get("selected_strategy"),
        "reason_codes": raw.get("reason_codes"),
        "selected_platform": raw.get("selected_platform"),
        "candidate_count": len(platform_prices) if isinstance(platform_prices, list) else 0,
    }
