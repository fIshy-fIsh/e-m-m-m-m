from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_live_scan_once import (
    LiveScanSettings,
    LiveValuationConfigurationError,
    _build_market_universe_spec,
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
    assert args.allocation is None
    assert args.target_cohorts is None


def test_auto_universe_effective_defaults_preserve_breadth() -> None:
    from app.services.market_universe_builder import UniverseAllocationStrategy

    args = build_parser().parse_args(["--auto-universe"])
    spec = _build_market_universe_spec(args)
    assert spec.allocation_strategy is UniverseAllocationStrategy.BREADTH
    assert spec.target_cohort_count == 3


def test_parser_maps_explicit_cohort_depth_configuration() -> None:
    from app.services.market_universe_builder import UniverseAllocationStrategy

    args = build_parser().parse_args(
        [
            "--auto-universe",
            "--allocation",
            "cohort-depth",
            "--target-cohorts",
            "2",
        ]
    )
    spec = _build_market_universe_spec(args)
    assert spec.allocation_strategy is UniverseAllocationStrategy.COHORT_DEPTH
    assert spec.target_cohort_count == 2


def test_explicit_target_with_breadth_fails_closed() -> None:
    from app.services.market_universe_builder import (
        BoundedMarketUniverseBuilderError,
    )

    args = build_parser().parse_args(
        [
            "--auto-universe",
            "--allocation",
            "breadth",
            "--target-cohorts",
            "3",
        ]
    )
    with pytest.raises(BoundedMarketUniverseBuilderError) as info:
        _build_market_universe_spec(args)
    assert info.value.reason == "invalid_target_cohort_count"


def test_manual_mode_rejects_explicit_auto_allocation_before_settings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import run_live_scan_once

    def fail_settings(*args: object, **kwargs: object) -> None:
        raise AssertionError("LiveScanSettings must not be constructed")

    monkeypatch.setattr(run_live_scan_once, "LiveScanSettings", fail_settings)
    exit_code = run_live_scan_once.main(
        ["--goods-id", "34279", "--allocation", "breadth"]
    )
    assert exit_code == 2
    assert "AUTO_UNIVERSE_OPTION_REQUIRES_AUTO_UNIVERSE" in capsys.readouterr().out


def test_manual_mode_rejects_explicit_target_before_settings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import run_live_scan_once

    def fail_settings(*args: object, **kwargs: object) -> None:
        raise AssertionError("LiveScanSettings must not be constructed")

    monkeypatch.setattr(run_live_scan_once, "LiveScanSettings", fail_settings)
    exit_code = run_live_scan_once.main(
        ["--goods-id", "34279", "--target-cohorts", "3"]
    )
    assert exit_code == 2
    assert "AUTO_UNIVERSE_OPTION_REQUIRES_AUTO_UNIVERSE" in capsys.readouterr().out


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


def test_successful_depth_preview_is_structured_and_no_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json

    from scripts import run_live_scan_once

    metadata_items: list[dict[str, object]] = []
    identities: dict[str, str] = {}
    for collection_index, collection_name in enumerate(
        ("Collection A", "Collection B", "Collection C")
    ):
        for input_index in range(4):
            name = f"{collection_name} Input {input_index}"
            metadata_items.append(
                {
                    "market_hash_name": name,
                    "collection_name": collection_name,
                    "rarity": "Restricted",
                    "min_float": 0.0,
                    "max_float": 1.0,
                    "stattrak": False,
                    "souvenir": False,
                }
            )
            identities[name] = str(collection_index * 10 + input_index + 1)
        metadata_items.append(
            {
                "market_hash_name": f"{collection_name} Output",
                "collection_name": collection_name,
                "rarity": "Classified",
                "min_float": 0.0,
                "max_float": 1.0,
                "stattrak": False,
                "souvenir": False,
            }
        )
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
        "counts": {
            "source": len(identities),
            "accepted": len(identities),
            "rejected": 0,
        },
        "items": identities,
    }
    identity_path = tmp_path / "identity.json"
    metadata_path = tmp_path / "metadata.json"
    identity_path.write_text(json.dumps(identity_payload), encoding="utf-8")
    metadata_path.write_text(
        json.dumps({"items": metadata_items}), encoding="utf-8"
    )

    failures: list[str] = []

    def fail_constructor(*args: object, **kwargs: object) -> None:
        failures.append("live-constructor")

    monkeypatch.setattr(run_live_scan_once, "LiveScanSettings", fail_constructor)
    monkeypatch.setattr("httpx.AsyncClient", fail_constructor)
    monkeypatch.setattr(
        run_live_scan_once, "BuffAnonymousListingHttpClient", fail_constructor
    )
    monkeypatch.setattr(run_live_scan_once, "SteamDTHttpClient", fail_constructor)
    monkeypatch.setattr(run_live_scan_once, "ValuationService", fail_constructor)
    monkeypatch.setattr(run_live_scan_once, "LiveScannerOrchestrator", fail_constructor)

    exit_code = run_live_scan_once.main(
        [
            "--auto-universe",
            "--allocation",
            "cohort-depth",
            "--target-cohorts",
            "3",
            "--max-goods-ids",
            "10",
            "--universe-preview",
            "--identity-snapshot",
            str(identity_path),
            "--metadata-snapshot",
            str(metadata_path),
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["spec"]["allocation_strategy"] == "cohort-depth"
    assert payload["spec"]["target_cohort_count"] == 3
    diagnostics = payload["catalog_diagnostics"]
    assert diagnostics["selected_cohort_count"] == 3
    assert [
        cohort["allocated_slots"] for cohort in diagnostics["selected_cohorts"]
    ] == [4, 3, 3]
    assert payload["http_clients_constructed"] is False
    assert payload["http_requests_sent"] == 0
    assert failures == []


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
