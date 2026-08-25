from __future__ import annotations

import pytest

from scripts.run_live_scan_once import (
    LiveScanSettings,
    LiveValuationConfigurationError,
    build_parser,
    build_steamdt_http_client,
    validate_live_valuation_config,
)


def _settings(
    *,
    dry_run: bool,
    api_key: str,
) -> LiveScanSettings:
    return LiveScanSettings(
        _env_file=None,
        steamdt_dry_run=dry_run,
        steamdt_api_key=api_key,
    )


def test_live_gate_refuses_dry_run_true() -> None:
    with pytest.raises(
        LiveValuationConfigurationError,
        match="STEAMDT_DRY_RUN must be false",
    ):
        validate_live_valuation_config(
            _settings(dry_run=True, api_key="present"),
            max_valuation_requests=5,
        )


def test_live_gate_refuses_missing_api_key() -> None:
    with pytest.raises(
        LiveValuationConfigurationError,
        match="STEAMDT_API_KEY is required",
    ):
        validate_live_valuation_config(
            _settings(dry_run=False, api_key=""),
            max_valuation_requests=5,
        )


def test_live_gate_accepts_explicit_live_configuration() -> None:
    validate_live_valuation_config(
        _settings(dry_run=False, api_key="present"),
        max_valuation_requests=5,
    )


@pytest.mark.parametrize("cap", [0, -1, 61, True])
def test_live_gate_rejects_invalid_valuation_cap(cap: object) -> None:
    with pytest.raises(
        LiveValuationConfigurationError,
        match="max valuation requests",
    ):
        validate_live_valuation_config(
            _settings(dry_run=False, api_key="present"),
            max_valuation_requests=cap,  # type: ignore[arg-type]
        )


def test_steamdt_borrowed_http_client_has_configured_base_url() -> None:
    import asyncio

    settings = _settings(dry_run=False, api_key="present")
    client = build_steamdt_http_client(settings)
    try:
        assert str(client.base_url) == "https://open.steamdt.com"
    finally:
        asyncio.run(client.aclose())


def test_parser_defaults_to_conservative_valuation_cap() -> None:
    args = build_parser().parse_args(["--goods-id", "34279"])
    assert args.max_valuation_requests == 5


def test_parser_preserves_repeatable_goods_ids() -> None:
    args = build_parser().parse_args(
        ["--goods-id", "34279", "--goods-id", "34420"]
    )
    assert args.goods_id == ["34279", "34420"]
