from app.clients.steamdt_errors import (
    SteamDTApiError,
    SteamDTError,
    SteamDTHttpStatusError,
    SteamDTRateLimitError,
    SteamDTResponseParseError,
    SteamDTTransportError,
    redact_steamdt_error_text,
)


def test_steamdt_error_base_str_includes_endpoint_and_message() -> None:
    error = SteamDTError("boom", endpoint="/open/cs2/v1/price/single")

    assert "SteamDTError" in str(error)
    assert "/open/cs2/v1/price/single" in str(error)
    assert "boom" in str(error)


def test_steamdt_api_error_preserves_sanitized_wrapper_fields() -> None:
    error = SteamDTApiError(
        "wrapper failed",
        endpoint="/endpoint",
        error_code=123,
        error_msg="bad request",
        error_code_str="BAD_REQUEST",
    )

    assert error.endpoint == "/endpoint"
    assert error.error_code == 123
    assert error.error_msg == "bad request"
    assert error.error_code_str == "BAD_REQUEST"
    assert "error_code=123" in str(error)


def test_steamdt_rate_limit_error_preserves_retry_after_and_endpoint() -> None:
    error = SteamDTRateLimitError(
        "rate limit",
        endpoint="/endpoint",
        retry_after_seconds=2.5,
        error_code=4005,
    )

    assert error.endpoint == "/endpoint"
    assert error.retry_after_seconds == 2.5
    assert error.error_code == 4005
    assert "retry_after_seconds=2.5" in str(error)


def test_steamdt_http_status_error_preserves_status_code() -> None:
    error = SteamDTHttpStatusError("client error", endpoint="/endpoint", status_code=403)

    assert error.status_code == 403
    assert "status_code=403" in str(error)


def test_error_redaction_removes_api_key_and_authorization_header() -> None:
    message = redact_steamdt_error_text(
        "Authorization: Bearer super-secret-steamdt-key",
        api_key="super-secret-steamdt-key",
    )

    assert "super-secret-steamdt-key" not in message
    assert "Authorization:" not in message
    assert "[REDACTED_AUTHORIZATION]" in message


def test_typed_error_str_does_not_leak_api_key() -> None:
    error = SteamDTTransportError(
        "failed with Bearer super-secret-steamdt-key",
        endpoint="/endpoint",
    )

    assert "super-secret-steamdt-key" not in str(error)
    assert "Bearer [REDACTED]" in str(error)


def test_response_parse_error_is_value_error_and_steamdt_error() -> None:
    error = SteamDTResponseParseError("bad shape", endpoint="/endpoint")

    assert isinstance(error, ValueError)
    assert isinstance(error, SteamDTError)
