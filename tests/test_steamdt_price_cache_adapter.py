from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.clients.steamdt_client import SteamDTPlatformPrice
from app.clients.steamdt_price_selection import (
    SteamDTPriceSelectionStrategy,
    select_steamdt_price_quote,
)
from app.services.price_cache import (
    NormalizedPriceCandidate,
    PriceCacheKey,
    PriceCachePolicy,
)
from app.services.steamdt_price_cache_adapter import (
    SteamDTPriceCacheAdapterError,
    SteamDTPriceCacheAdapterErrorReason,
    build_steamdt_cached_price_snapshot,
    normalized_candidate_to_steamdt_platform_price,
    normalized_candidates_to_steamdt_platform_prices,
    steamdt_platform_price_to_normalized_candidate,
    steamdt_platform_prices_to_normalized_candidates,
)

BASE_TIME = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


def _platform_price(
    *,
    platform: str = "buff",
    sell_price: Decimal = Decimal("12.34000001"),
    update_time: int | str | None = 1_721_234_567,
    raw: dict[str, object] | None = None,
) -> SteamDTPlatformPrice:
    return SteamDTPlatformPrice(
        platform=platform,
        platform_item_id=f"{platform}-item-7",
        sell_price_cny=sell_price,
        sell_count=17,
        bidding_price_cny=Decimal("11.98765432"),
        bidding_count=9,
        update_time=update_time,
        raw=raw,
    )


def _candidate(*, platform: str = "buff") -> NormalizedPriceCandidate:
    return NormalizedPriceCandidate(
        platform=platform,
        platform_item_id=f"{platform}-item-7",
        sell_price_cny=Decimal("12.34000001"),
        sell_count=17,
        bidding_price_cny=Decimal("11.98765432"),
        bidding_count=9,
        source_update_time="opaque-source-time",
    )


def test_single_candidate_round_trip_preserves_selector_fields_and_decimal() -> None:
    source = _platform_price(update_time="opaque-source-time", raw={"mutable": []})

    candidate = steamdt_platform_price_to_normalized_candidate(source)
    rebuilt = normalized_candidate_to_steamdt_platform_price(candidate)

    assert candidate == _candidate()
    assert candidate.sell_price_cny == Decimal("12.34000001")
    assert rebuilt == SteamDTPlatformPrice(
        platform=source.platform,
        platform_item_id=source.platform_item_id,
        sell_price_cny=source.sell_price_cny,
        sell_count=source.sell_count,
        bidding_price_cny=source.bidding_price_cny,
        bidding_count=source.bidding_count,
        update_time=source.update_time,
        raw=None,
    )


@pytest.mark.parametrize("source_time", [None, 1_721_234_567, "2026-07-19T12:00Z"])
def test_supported_source_timestamp_forms_round_trip(
    source_time: int | str | None,
) -> None:
    candidate = steamdt_platform_price_to_normalized_candidate(
        _platform_price(update_time=source_time)
    )

    assert candidate.source_update_time == source_time
    assert (
        normalized_candidate_to_steamdt_platform_price(candidate).update_time
        == source_time
    )


def test_collection_conversion_preserves_order_and_duplicates() -> None:
    first = _platform_price(platform="buff")
    duplicate = _platform_price(platform="buff")
    third = _platform_price(platform="steam")

    candidates = steamdt_platform_prices_to_normalized_candidates(
        [first, duplicate, third]
    )
    rebuilt = normalized_candidates_to_steamdt_platform_prices(candidates)

    assert [candidate.platform for candidate in candidates] == [
        "buff",
        "buff",
        "steam",
    ]
    assert candidates[0] == candidates[1]
    assert [price.platform for price in rebuilt] == ["buff", "buff", "steam"]
    assert rebuilt[0] == rebuilt[1]


def test_collection_adapters_reject_invalid_top_level_values() -> None:
    with pytest.raises(SteamDTPriceCacheAdapterError) as source_error:
        steamdt_platform_prices_to_normalized_candidates(object())  # type: ignore[arg-type]
    with pytest.raises(SteamDTPriceCacheAdapterError) as cached_error:
        normalized_candidates_to_steamdt_platform_prices("not-candidates")  # type: ignore[arg-type]

    assert source_error.value.field == "platform_prices"
    assert source_error.value.reason == SteamDTPriceCacheAdapterErrorReason.INVALID_TYPE
    assert cached_error.value.field == "candidates"
    assert cached_error.value.reason == SteamDTPriceCacheAdapterErrorReason.INVALID_TYPE


def test_mutable_raw_payload_never_enters_cache_or_rebuilt_model() -> None:
    raw: dict[str, object] = {
        "Authorization": "Bearer dummy-secret-that-must-not-survive",
        "nested": [],
    }
    source = _platform_price(raw=raw)

    candidate = steamdt_platform_price_to_normalized_candidate(source)
    raw["nested"] = ["changed"]
    rebuilt = normalized_candidate_to_steamdt_platform_price(candidate)

    assert not hasattr(candidate, "raw")
    assert "dummy-secret" not in repr(candidate)
    assert rebuilt.raw is None


def test_rebuilt_model_is_directly_accepted_by_existing_selector() -> None:
    candidates = steamdt_platform_prices_to_normalized_candidates(
        [_platform_price(platform="buff", sell_price=Decimal("7.01"))]
    )
    rebuilt = normalized_candidates_to_steamdt_platform_prices(candidates)

    result = select_steamdt_price_quote("AK-47 | Redline", rebuilt)

    assert result.quote is not None
    assert result.quote.price_cny == Decimal("7.01")
    assert (
        result.selected_strategy
        == SteamDTPriceSelectionStrategy.LIQUIDITY_AWARE_SELL_PRICE.value
    )


def test_snapshot_builder_preserves_explicit_key_candidates_time_and_policy() -> None:
    key = PriceCacheKey(market_hash_name="AK-47 | Redline")
    candidates = (_candidate(platform="buff"), _candidate(platform="steam"))
    policy = PriceCachePolicy(
        fresh_ttl=timedelta(minutes=2),
        stale_ttl=timedelta(minutes=3),
        stale_grace_ttl=timedelta(minutes=4),
    )

    snapshot = build_steamdt_cached_price_snapshot(
        key=key,
        candidates=candidates,
        observed_at=BASE_TIME,
        stored_at=BASE_TIME + timedelta(seconds=1),
        policy=policy,
    )

    assert snapshot.key == key
    assert snapshot.candidates == candidates
    assert snapshot.observed_at == BASE_TIME
    assert snapshot.stored_at == BASE_TIME + timedelta(seconds=1)
    assert snapshot.policy == policy


def test_snapshot_builder_allows_an_empty_candidate_observation() -> None:
    snapshot = build_steamdt_cached_price_snapshot(
        key=PriceCacheKey(market_hash_name="AK-47 | Redline"),
        candidates=[],
        observed_at=BASE_TIME,
        stored_at=BASE_TIME,
        policy=PriceCachePolicy(fresh_ttl=timedelta(minutes=1)),
    )

    assert snapshot.candidates == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sell_price_cny", 1.25),
        ("sell_count", True),
        ("bidding_count", "9"),
        ("update_time", True),
        ("update_time", {"ambiguous": "timestamp"}),
    ],
)
def test_ambiguous_provider_fields_raise_explicit_adapter_error(
    field: str,
    value: object,
) -> None:
    source = _platform_price(raw={"token": "dummy-secret"})
    object.__setattr__(source, field, value)

    with pytest.raises(SteamDTPriceCacheAdapterError) as exc_info:
        steamdt_platform_price_to_normalized_candidate(source)

    error = exc_info.value
    assert error.reason == SteamDTPriceCacheAdapterErrorReason.INVALID_TYPE
    assert field.replace("update_time", "source_update_time") in error.field
    assert str(error) == "SteamDT price-cache adapter rejected invalid data"
    assert "dummy-secret" not in str(error)


@pytest.mark.parametrize("field", ["platform", "platform_item_id"])
def test_noncanonical_identity_whitespace_fails_instead_of_changing_round_trip(
    field: str,
) -> None:
    source = _platform_price()
    object.__setattr__(source, field, " buff ")

    with pytest.raises(SteamDTPriceCacheAdapterError) as exc_info:
        steamdt_platform_price_to_normalized_candidate(source)

    assert exc_info.value.reason == SteamDTPriceCacheAdapterErrorReason.INVALID_VALUE
    assert field in exc_info.value.field


def test_invalid_object_type_is_not_confused_with_cache_or_codec_error() -> None:
    with pytest.raises(SteamDTPriceCacheAdapterError) as exc_info:
        steamdt_platform_price_to_normalized_candidate(object())  # type: ignore[arg-type]

    assert exc_info.value.field == "platform_price"
    assert exc_info.value.reason == SteamDTPriceCacheAdapterErrorReason.INVALID_TYPE


def test_adapter_error_traceback_does_not_leak_payload_or_secret() -> None:
    source = _platform_price(
        raw={
            "Authorization": "Bearer dummy-secret",
            "payload": "complete-sensitive-payload",
        }
    )
    object.__setattr__(source, "update_time", ["ambiguous"])

    with pytest.raises(SteamDTPriceCacheAdapterError) as exc_info:
        steamdt_platform_price_to_normalized_candidate(source)

    rendered = str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert "dummy-secret" not in rendered
    assert "complete-sensitive-payload" not in rendered
    assert "Bearer" not in rendered


def test_snapshot_builder_rejects_corrupt_candidate_invariants() -> None:
    candidate = _candidate()
    object.__setattr__(candidate, "source_update_time", True)

    with pytest.raises(SteamDTPriceCacheAdapterError) as exc_info:
        build_steamdt_cached_price_snapshot(
            key=PriceCacheKey(market_hash_name="AK-47 | Redline"),
            candidates=[candidate],
            observed_at=BASE_TIME,
            stored_at=BASE_TIME,
            policy=PriceCachePolicy(fresh_ttl=timedelta(minutes=1)),
        )

    assert exc_info.value.field == "candidates[0].source_update_time"
    assert exc_info.value.reason == SteamDTPriceCacheAdapterErrorReason.INVALID_TYPE


def test_snapshot_builder_rejects_invalid_candidate_container() -> None:
    with pytest.raises(SteamDTPriceCacheAdapterError) as exc_info:
        build_steamdt_cached_price_snapshot(
            key=PriceCacheKey(market_hash_name="AK-47 | Redline"),
            candidates=object(),  # type: ignore[arg-type]
            observed_at=BASE_TIME,
            stored_at=BASE_TIME,
            policy=PriceCachePolicy(fresh_ttl=timedelta(minutes=1)),
        )

    assert exc_info.value.field == "candidates"
    assert exc_info.value.reason == SteamDTPriceCacheAdapterErrorReason.INVALID_TYPE


def test_snapshot_builder_rejects_overflowing_freshness_horizon() -> None:
    with pytest.raises(SteamDTPriceCacheAdapterError) as exc_info:
        build_steamdt_cached_price_snapshot(
            key=PriceCacheKey(market_hash_name="AK-47 | Redline"),
            candidates=[_candidate()],
            observed_at=datetime.max.replace(tzinfo=UTC),
            stored_at=datetime.max.replace(tzinfo=UTC),
            policy=PriceCachePolicy(fresh_ttl=timedelta(microseconds=1)),
        )

    assert exc_info.value.field == "snapshot"
    assert (
        exc_info.value.reason
        == SteamDTPriceCacheAdapterErrorReason.SNAPSHOT_CONSTRUCTION_FAILED
    )


def test_snapshot_builder_rejects_wrong_runtime_types_as_adapter_errors() -> None:
    with pytest.raises(SteamDTPriceCacheAdapterError) as exc_info:
        build_steamdt_cached_price_snapshot(
            key=PriceCacheKey(market_hash_name="AK-47 | Redline"),
            candidates=[_candidate()],
            observed_at="dummy-secret-timestamp",  # type: ignore[arg-type]
            stored_at=BASE_TIME,
            policy=PriceCachePolicy(fresh_ttl=timedelta(minutes=1)),
        )

    assert exc_info.value.field == "observed_at"
    assert exc_info.value.reason == SteamDTPriceCacheAdapterErrorReason.INVALID_TYPE
    assert "dummy-secret" not in str(exc_info.value)


def test_naive_snapshot_timestamp_is_an_adapter_error() -> None:
    with pytest.raises(SteamDTPriceCacheAdapterError) as exc_info:
        build_steamdt_cached_price_snapshot(
            key=PriceCacheKey(market_hash_name="AK-47 | Redline"),
            candidates=[_candidate()],
            observed_at=datetime(2026, 7, 19, 12, 0),
            stored_at=BASE_TIME,
            policy=PriceCachePolicy(fresh_ttl=timedelta(minutes=1)),
        )

    assert exc_info.value.field == "snapshot"
    assert (
        exc_info.value.reason
        == SteamDTPriceCacheAdapterErrorReason.SNAPSHOT_CONSTRUCTION_FAILED
    )
    assert exc_info.value.__cause__ is None