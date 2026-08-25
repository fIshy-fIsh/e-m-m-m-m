from __future__ import annotations

from pathlib import Path

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


def test_parser_requires_one_source() -> None:
    import pytest

    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_parser_rejects_mixed_sources() -> None:
    import pytest

    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "--goods-id",
                "34279",
                "--auto-universe",
            ]
        )


def test_parser_auto_universe_defaults() -> None:
    args = build_parser().parse_args(["--auto-universe"])
    assert args.auto_universe is True
    assert args.rarity == "Restricted"
    assert args.stattrak_mode == "normal"
    assert args.souvenir == "include"
    assert args.max_goods_ids == 10


def test_parser_rejects_unsupported_rarity() -> None:
    import pytest

    with pytest.raises(SystemExit):
        build_parser().parse_args(["--auto-universe", "--rarity", "Covert"])


def test_parser_accepts_max_goods_ids_then_validates() -> None:
    """Argparse accepts the integer; the builder rejects values outside [1, 10]."""
    from app.services.market_universe_builder import (
        BoundedMarketUniverseBuilderError,
        MarketUniverseSpec,
        SouvenirInclusion,
        StatTrakMode,
    )

    args = build_parser().parse_args(["--auto-universe", "--max-goods-ids", "0"])
    with pytest.raises(BoundedMarketUniverseBuilderError):
        MarketUniverseSpec(
            rarity=args.rarity,
            stattrak_mode=StatTrakMode.NORMAL,
            souvenir_inclusion=SouvenirInclusion.INCLUDE,
            cap=args.max_goods_ids,
        )
    args = build_parser().parse_args(["--auto-universe", "--max-goods-ids", "11"])
    with pytest.raises(BoundedMarketUniverseBuilderError):
        MarketUniverseSpec(
            rarity=args.rarity,
            stattrak_mode=StatTrakMode.NORMAL,
            souvenir_inclusion=SouvenirInclusion.INCLUDE,
            cap=args.max_goods_ids,
        )


def test_parser_accepts_repeatable_collection() -> None:
    args = build_parser().parse_args(
        [
            "--auto-universe",
            "--collection",
            "The Cobblestone Collection",
            "--collection",
            "The Ancient Collection",
        ]
    )
    assert args.collection == [
        "The Cobblestone Collection",
        "The Ancient Collection",
    ]


def test_universe_preview_does_not_construct_clients(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--universe-preview` runs before settings/client construction."""
    import json

    from scripts import run_live_scan_once

    identity_payload = {
        "schema_version": 1,
        "catalog_kind": "community_catalog",
        "source": {
            "repository": "example/repo",
            "file": "x.json",
            "commit": "abc",
            "sha256": "deadbeef" * 8,
            "license": "CC-BY-4.0",
            "attribution": "test",
        },
        "counts": {"source": 0, "accepted": 0, "rejected": 0},
        "items": {},
    }
    metadata_payload = {"items": []}
    identity_path = tmp_path / "identity.json"
    metadata_path = tmp_path / "metadata.json"
    identity_path.write_bytes(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )
    metadata_path.write_bytes(
        json.dumps(metadata_payload, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )

    failures: list[str] = []

    def fail_httpx_client(*args: object, **kwargs: object) -> None:
        failures.append("httpx.AsyncClient")

    def fail_steamdt(*args: object, **kwargs: object) -> None:
        failures.append("SteamDTHttpClient")

    def fail_buff(*args: object, **kwargs: object) -> None:
        failures.append("BuffAnonymousListingHttpClient")

    def fail_provider(*args: object, **kwargs: object) -> None:
        failures.append("BuffListingProvider")

    def fail_valuation(*args: object, **kwargs: object) -> None:
        failures.append("ValuationService")

    def fail_orchestrator(*args: object, **kwargs: object) -> None:
        failures.append("LiveScannerOrchestrator")

    monkeypatch.setattr("httpx.AsyncClient", fail_httpx_client)
    monkeypatch.setattr(
        "scripts.run_live_scan_once.build_steamdt_http_client", fail_steamdt
    )
    monkeypatch.setattr(
        "scripts.run_live_scan_once.BuffAnonymousListingHttpClient", fail_buff
    )
    monkeypatch.setattr(
        "scripts.run_live_scan_once.BuffListingProvider", fail_provider
    )
    monkeypatch.setattr(
        "scripts.run_live_scan_once.ValuationService", fail_valuation
    )
    monkeypatch.setattr(
        "scripts.run_live_scan_once.LiveScannerOrchestrator", fail_orchestrator
    )

    # Empty catalogs produce empty universe -> builder fails closed.
    # The preview path surfaces that before any settings/client work.
    exit_code = run_live_scan_once.main(
        [
            "--auto-universe",
            "--rarity",
            "Restricted",
            "--max-goods-ids",
            "5",
            "--universe-preview",
            "--identity-snapshot",
            str(identity_path),
            "--metadata-snapshot",
            str(metadata_path),
        ]
    )
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "MARKET_UNIVERSE_BUILDER_BLOCKED" in captured.out
    assert failures == []
