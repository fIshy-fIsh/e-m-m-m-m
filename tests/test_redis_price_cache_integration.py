import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta

import pytest

from app.services.price_cache import (
    PriceCacheReadPolicy,
    PriceCacheState,
    PriceCacheWriteResult,
)
from app.services.price_cache_codec import PriceCacheCodecError
from app.services.redis_price_cache import (
    REDIS_PRICE_CACHE_GET_SCRIPT,
    RedisPriceCache,
)
from scripts import steamdt_redis_price_cache_smoke as smoke

RUN_INTEGRATION = (
    os.getenv(smoke.RUN_REDIS_PRICE_CACHE_INTEGRATION_ENV, "").strip().lower()
    == "true"
)
pytestmark = pytest.mark.skipif(
    not RUN_INTEGRATION,
    reason="Redis price-cache integration tests require explicit opt-in",
)

Scenario = Callable[[object, object, str], Awaitable[None]]


async def _run_with_clients(scenario: Scenario) -> None:
    from redis.asyncio import Redis

    redis_url = os.getenv(smoke.TEST_REDIS_URL_ENV, smoke.DEFAULT_TEST_REDIS_URL)
    namespace = smoke.build_test_namespace(
        os.getenv(smoke.TEST_REDIS_PRICE_CACHE_NAMESPACE_ENV),
        suffix=uuid.uuid4().hex,
    )
    client_a = Redis.from_url(redis_url, decode_responses=False)
    client_b = Redis.from_url(redis_url, decode_responses=False)
    primary_error: BaseException | None = None
    cleanup_error: BaseException | None = None
    try:
        await smoke.cleanup_namespace_keys(client_a, namespace)
        await scenario(client_a, client_b, namespace)
    except BaseException as exc:
        primary_error = exc
    finally:
        try:
            await smoke.cleanup_namespace_keys(client_a, namespace)
            assert await smoke.namespace_key_count(client_a, namespace) == 0
        except BaseException as exc:
            cleanup_error = exc
        finally:
            close_results = await asyncio.gather(
                client_b.aclose(),
                client_a.aclose(),
                return_exceptions=True,
            )
            close_error = next(
                (result for result in close_results if isinstance(result, BaseException)),
                None,
            )
            if cleanup_error is None:
                cleanup_error = close_error
    if primary_error is not None:
        raise primary_error
    if cleanup_error is not None:
        raise cleanup_error


def _run(scenario: Scenario) -> None:
    asyncio.run(_run_with_clients(scenario))


def test_real_redis_ping_version_time_and_basic_round_trip() -> None:
    async def scenario(client_a: object, client_b: object, namespace: str) -> None:
        assert await client_a.ping() is True
        server_info = await client_a.info(section="server")
        assert server_info["redis_version"]
        before = await smoke.redis_server_time(client_a)
        snapshot = smoke.build_snapshot(
            before - timedelta(seconds=1),
            name="integration-basic",
            stored_at=before + timedelta(days=30),
        )
        cache_a = RedisPriceCache(client_a, namespace=namespace)
        cache_b = RedisPriceCache(client_b, namespace=namespace)

        assert await cache_a.put(snapshot) == PriceCacheWriteResult.CREATED
        after = await smoke.redis_server_time(client_a)
        lookup = await cache_b.get(snapshot.key)

        assert lookup.hit is True
        assert lookup.state == PriceCacheState.FRESH
        assert lookup.snapshot is not None
        assert lookup.snapshot.key == snapshot.key
        assert lookup.snapshot.observed_at == snapshot.observed_at
        assert lookup.snapshot.policy == snapshot.policy
        assert lookup.snapshot.candidates == snapshot.candidates
        assert before <= lookup.snapshot.stored_at <= after
        assert lookup.snapshot.stored_at != snapshot.stored_at
        assert cache_a.key_for(snapshot.key) == cache_b.key_for(snapshot.key)
        assert await client_a.ping() is True
        assert await client_b.ping() is True

    _run(scenario)


def test_real_lua_reply_is_list_with_bytes_tag_and_flat_hash() -> None:
    async def scenario(client_a: object, client_b: object, namespace: str) -> None:
        now = await smoke.redis_server_time(client_a)
        snapshot = smoke.build_snapshot(
            now - timedelta(seconds=1),
            name="integration-reply",
        )
        cache = RedisPriceCache(client_a, namespace=namespace)
        await cache.put(snapshot)

        response = await client_b.eval(
            REDIS_PRICE_CACHE_GET_SCRIPT,
            1,
            cache.key_for(snapshot.key),
        )
        assert isinstance(response, list)
        assert response[0] == b"record"
        assert isinstance(response[1], int)
        assert isinstance(response[2], int)
        assert response[3] == b"fresh"
        assert all(isinstance(value, bytes) for value in response[4:])
        assert len(response[4:]) % 2 == 0

        cursor, keys = await client_b.scan(
            cursor=0,
            match=cache.scan_pattern(),
            count=1,
        )
        assert type(cursor) is int
        assert isinstance(keys, list)

    _run(scenario)


def test_cross_client_newer_older_equal_ordering_and_expiry_preservation() -> None:
    async def scenario(client_a: object, client_b: object, namespace: str) -> None:
        cache_a = RedisPriceCache(client_a, namespace=namespace)
        cache_b = RedisPriceCache(client_b, namespace=namespace)
        now = await smoke.redis_server_time(client_a)
        first = smoke.build_snapshot(now - timedelta(seconds=3), name="ordering", price="1.0")
        newer = smoke.build_snapshot(
            first.observed_at + timedelta(microseconds=2),
            name="ordering",
            price="2.000000000000000001",
        )
        older = smoke.build_snapshot(
            first.observed_at + timedelta(microseconds=1),
            name="ordering",
            price="3.0",
            fresh=timedelta(hours=2),
        )
        equal = smoke.build_snapshot(
            newer.observed_at,
            name="ordering",
            price="4.0",
            fresh=timedelta(hours=3),
            stored_at=now + timedelta(days=1),
        )

        assert await cache_a.put(first) == PriceCacheWriteResult.CREATED
        assert await cache_b.put(newer) == PriceCacheWriteResult.REPLACED
        preserved = (await cache_a.get(newer.key)).snapshot
        assert preserved is not None
        key = cache_a.key_for(newer.key)
        expiry = await smoke._pexpiretime(client_a, key)
        raw_stored = await client_a.hmget(key, "stored_seconds", "stored_microseconds")

        assert await cache_a.put(older) == PriceCacheWriteResult.IGNORED_OLDER
        assert await cache_b.put(equal) == PriceCacheWriteResult.UNCHANGED_EQUAL
        final = (await cache_a.get(newer.key)).snapshot

        assert final == preserved
        assert final is not None
        assert final.observed_at == newer.observed_at
        assert final.candidates == newer.candidates
        assert await smoke._pexpiretime(client_a, key) == expiry
        assert await client_a.hmget(key, "stored_seconds", "stored_microseconds") == raw_stored

    _run(scenario)


def test_microsecond_ordering_within_one_unix_second() -> None:
    async def scenario(client_a: object, client_b: object, namespace: str) -> None:
        cache_a = RedisPriceCache(client_a, namespace=namespace)
        cache_b = RedisPriceCache(client_b, namespace=namespace)
        past = (await smoke.redis_server_time(client_a)) - timedelta(seconds=5)
        first_time = past.replace(microsecond=456_789)
        second_time = past.replace(microsecond=456_790)
        first = smoke.build_snapshot(first_time, name="micro-order", price="1.0")
        second = smoke.build_snapshot(second_time, name="micro-order", price="2.0")

        assert await cache_a.put(first) == PriceCacheWriteResult.CREATED
        assert await cache_b.put(second) == PriceCacheWriteResult.REPLACED
        assert await cache_a.put(first) == PriceCacheWriteResult.IGNORED_OLDER
        lookup = await cache_b.get(second.key)
        assert lookup.snapshot is not None
        assert lookup.snapshot.observed_at == second_time
        assert lookup.snapshot.candidates == second.candidates

    _run(scenario)


def test_future_observation_is_rejected_without_creation_or_replacement() -> None:
    async def scenario(client_a: object, client_b: object, namespace: str) -> None:
        cache = RedisPriceCache(client_a, namespace=namespace)
        now = await smoke.redis_server_time(client_a)
        future_time = now + timedelta(minutes=1)
        future = smoke.build_snapshot(
            future_time,
            name="future-new",
            stored_at=future_time + timedelta(days=1),
        )
        with pytest.raises(ValueError, match="Redis server time") as exc_info:
            await cache.put(future)
        assert "redis://" not in str(exc_info.value)
        assert "payload" not in str(exc_info.value).lower()
        assert await client_b.exists(cache.key_for(future.key)) == 0

        existing = smoke.build_snapshot(now - timedelta(seconds=2), name="future-existing")
        assert await cache.put(existing) == PriceCacheWriteResult.CREATED
        original = (await cache.get(existing.key)).snapshot
        future_existing = smoke.build_snapshot(
            future_time,
            name="future-existing",
            price="999.0",
            stored_at=future_time + timedelta(days=1),
        )
        with pytest.raises(ValueError):
            await cache.put(future_existing)
        assert (await cache.get(existing.key)).snapshot == original

    _run(scenario)


def test_real_redis_fresh_stale_and_stale_grace_read_policies() -> None:
    async def scenario(client_a: object, client_b: object, namespace: str) -> None:
        cache = RedisPriceCache(client_a, namespace=namespace)
        now = await smoke.redis_server_time(client_a)
        fresh = smoke.build_snapshot(now - timedelta(seconds=2), name="state-fresh")
        stale = smoke.build_snapshot(
            now - timedelta(seconds=20),
            name="state-stale",
            fresh=timedelta(seconds=10),
            stale=timedelta(seconds=30),
            grace=timedelta(seconds=30),
        )
        grace = smoke.build_snapshot(
            now - timedelta(seconds=25),
            name="state-grace",
            fresh=timedelta(seconds=5),
            stale=timedelta(seconds=5),
            grace=timedelta(seconds=40),
        )
        for snapshot in (fresh, stale, grace):
            await cache.put(snapshot)

        for policy in PriceCacheReadPolicy:
            lookup = await cache.get(fresh.key, read_policy=policy)
            assert lookup.hit is True
            assert lookup.state == PriceCacheState.FRESH
            assert lookup.needs_refresh is False

        stale_default = await cache.get(stale.key)
        stale_allowed = await cache.get(
            stale.key,
            read_policy=PriceCacheReadPolicy.ALLOW_STALE,
        )
        assert stale_default.state == PriceCacheState.STALE
        assert stale_default.snapshot is None
        assert stale_default.policy_blocked is True
        assert stale_default.needs_refresh is True
        assert stale_allowed.hit is True

        grace_stale = await cache.get(
            grace.key,
            read_policy=PriceCacheReadPolicy.ALLOW_STALE,
        )
        grace_allowed = await cache.get(
            grace.key,
            read_policy=PriceCacheReadPolicy.ALLOW_STALE_GRACE,
        )
        assert grace_stale.state == PriceCacheState.STALE_GRACE
        assert grace_stale.snapshot is None
        assert grace_stale.policy_blocked is True
        assert grace_allowed.hit is True
        assert grace_allowed.needs_refresh is True

    _run(scenario)


def test_expired_get_reports_once_and_atomically_deletes() -> None:
    async def scenario(client_a: object, client_b: object, namespace: str) -> None:
        cache_a = RedisPriceCache(client_a, namespace=namespace)
        cache_b = RedisPriceCache(client_b, namespace=namespace)
        now = await smoke.redis_server_time(client_a)
        snapshot = smoke.build_snapshot(
            now,
            name="expired-get",
            fresh=timedelta(milliseconds=300),
            stale=timedelta(0),
            grace=timedelta(0),
        )
        await cache_a.put(snapshot)
        await asyncio.sleep(0.7)

        first = await cache_b.get(snapshot.key)
        second = await cache_a.get(snapshot.key)
        assert first.state == PriceCacheState.EXPIRED
        assert first.hit is False
        assert first.snapshot is None
        assert first.expired is True
        assert second.state is None
        assert second.expired is False
        assert await client_a.exists(cache_a.key_for(snapshot.key)) == 0

    _run(scenario)


def test_absolute_pexpiretime_and_noop_writes_do_not_extend_it() -> None:
    async def scenario(client_a: object, client_b: object, namespace: str) -> None:
        cache = RedisPriceCache(client_a, namespace=namespace)
        now = await smoke.redis_server_time(client_a)
        snapshot = smoke.build_snapshot(
            now - timedelta(seconds=1),
            name="absolute-expiry",
            fresh=timedelta(seconds=20, microseconds=1),
            stale=timedelta(seconds=2, microseconds=1),
            grace=timedelta(seconds=2, microseconds=1),
        )
        await cache.put(snapshot)
        key = cache.key_for(snapshot.key)
        expected = smoke.expected_physical_expiry_ms(snapshot)
        assert await smoke._pexpiretime(client_a, key) == expected

        older = smoke.build_snapshot(
            snapshot.observed_at - timedelta(microseconds=1),
            name="absolute-expiry",
            fresh=timedelta(hours=1),
        )
        equal = smoke.build_snapshot(
            snapshot.observed_at,
            name="absolute-expiry",
            fresh=timedelta(hours=2),
            price="999.0",
        )
        assert await cache.put(older) == PriceCacheWriteResult.IGNORED_OLDER
        assert await smoke._pexpiretime(client_a, key) == expected
        assert await cache.put(equal) == PriceCacheWriteResult.UNCHANGED_EQUAL
        assert await smoke._pexpiretime(client_a, key) == expected

    _run(scenario)


def test_wrong_type_fails_closed_and_clear_removes_it() -> None:
    async def scenario(client_a: object, client_b: object, namespace: str) -> None:
        cache = RedisPriceCache(client_a, namespace=namespace)
        now = await smoke.redis_server_time(client_a)
        snapshot = smoke.build_snapshot(now - timedelta(seconds=1), name="wrong-type")
        key = cache.key_for(snapshot.key)
        await client_a.set(key, "do-not-leak-this-value")

        with pytest.raises(PriceCacheCodecError) as get_error:
            await cache.get(snapshot.key)
        with pytest.raises(PriceCacheCodecError):
            await cache.put(snapshot)
        with pytest.raises(PriceCacheCodecError):
            await cache.purge_expired()
        assert "do-not-leak-this-value" not in str(get_error.value)
        assert await client_a.type(key) == b"string"
        assert await client_a.get(key) == b"do-not-leak-this-value"

        await cache.clear()
        assert await client_a.exists(key) == 0

    _run(scenario)


def test_corrupt_hash_fails_closed_for_get_put_and_purge() -> None:
    async def scenario(client_a: object, client_b: object, namespace: str) -> None:
        cache = RedisPriceCache(client_a, namespace=namespace)
        now = await smoke.redis_server_time(client_a)
        snapshot = smoke.build_snapshot(now - timedelta(seconds=2), name="corrupt")
        await cache.put(snapshot)
        key = cache.key_for(snapshot.key)
        payload = await client_a.hget(key, "payload_json")
        await client_a.hdel(key, "codec_version")

        with pytest.raises(PriceCacheCodecError) as get_error:
            await cache.get(snapshot.key)
        assert payload is not None
        assert payload.decode() not in str(get_error.value)
        older = smoke.build_snapshot(
            snapshot.observed_at - timedelta(microseconds=1),
            name="corrupt",
        )
        equal = smoke.build_snapshot(snapshot.observed_at, name="corrupt", price="2.0")
        newer = smoke.build_snapshot(
            snapshot.observed_at + timedelta(microseconds=1),
            name="corrupt",
            price="3.0",
        )
        for candidate in (older, equal, newer):
            with pytest.raises(PriceCacheCodecError):
                await cache.put(candidate)
        with pytest.raises(PriceCacheCodecError):
            await cache.purge_expired()
        assert await client_a.exists(key) == 1
        assert await client_a.hexists(key, "codec_version") == 0
        await cache.clear()
        assert await client_a.exists(key) == 0

    _run(scenario)


def test_namespace_isolation_and_real_scan_pagination() -> None:
    class RecordingRedis:
        def __init__(self, client: object) -> None:
            self.client = client
            self.scan_inputs: list[int] = []

        async def eval(
            self,
            script: str,
            numkeys: int,
            *keys_and_args: object,
        ) -> object:
            return await self.client.eval(script, numkeys, *keys_and_args)

        async def scan(
            self,
            cursor: int = 0,
            *,
            match: str | None = None,
            count: int | None = None,
        ) -> tuple[int, list[bytes | str]]:
            self.scan_inputs.append(cursor)
            return await self.client.scan(cursor=cursor, match=match, count=count)

        async def delete(self, *names: str | bytes) -> object:
            return await self.client.delete(*names)

    async def scenario(client_a: object, client_b: object, namespace: str) -> None:
        recording = RecordingRedis(client_a)
        cache = RedisPriceCache(recording, namespace=namespace, scan_count=1)
        other_namespace = smoke.build_test_namespace(suffix=uuid.uuid4().hex)
        other_cache = RedisPriceCache(client_b, namespace=other_namespace)
        now = await smoke.redis_server_time(client_a)
        unrelated = f"unrelated:{uuid.uuid4().hex}"
        limiter = f"{{{smoke.LIMITER_TEST_NAMESPACE}:price_single}}:requests"
        other = smoke.build_snapshot(now - timedelta(seconds=1), name="other")
        try:
            for index in range(64):
                snapshot = smoke.build_snapshot(
                    now - timedelta(seconds=1),
                    name=f"page-{index}",
                )
                await cache.put(snapshot)
            await other_cache.put(other)
            await client_a.set(unrelated, "keep")
            await client_a.set(limiter, "keep")

            await cache.clear()
            assert await smoke.namespace_key_count(client_a, namespace) == 0
            assert any(cursor != 0 for cursor in recording.scan_inputs)
            assert all(type(cursor) is int and cursor >= 0 for cursor in recording.scan_inputs)
            assert await client_b.exists(other_cache.key_for(other.key)) == 1
            assert await client_a.exists(unrelated) == 1
            assert await client_a.exists(limiter) == 1
        finally:
            await smoke.cleanup_namespace_keys(client_b, other_namespace)
            await client_a.delete(unrelated, limiter)

    _run(scenario)


def test_purge_expired_only_removes_current_logically_expired_entry() -> None:
    async def scenario(client_a: object, client_b: object, namespace: str) -> None:
        cache = RedisPriceCache(client_a, namespace=namespace, scan_count=1)
        other_namespace = smoke.build_test_namespace(suffix=uuid.uuid4().hex)
        other_cache = RedisPriceCache(client_b, namespace=other_namespace)
        now = await smoke.redis_server_time(client_a)
        live = smoke.build_snapshot(now, name="purge-live")
        expired = smoke.build_snapshot(
            now - timedelta(seconds=1),
            name="purge-expired",
            fresh=timedelta(milliseconds=300),
            stale=timedelta(0),
            grace=timedelta(0),
        )
        outside = smoke.build_snapshot(
            now - timedelta(seconds=1),
            name="purge-outside",
            fresh=timedelta(milliseconds=300),
            stale=timedelta(0),
            grace=timedelta(0),
        )
        try:
            await cache.put(live)
            await cache.put(expired)
            await other_cache.put(outside)
            assert await cache.purge_expired() == 1
            assert await client_a.exists(cache.key_for(live.key)) == 1
            assert await client_a.exists(cache.key_for(expired.key)) == 0
            assert await client_b.exists(other_cache.key_for(outside.key)) == 1
        finally:
            await smoke.cleanup_namespace_keys(client_b, other_namespace)

    _run(scenario)


def test_concurrent_newer_older_race_always_finishes_with_newer() -> None:
    async def scenario(client_a: object, client_b: object, namespace: str) -> None:
        cache_a = RedisPriceCache(client_a, namespace=namespace)
        cache_b = RedisPriceCache(client_b, namespace=namespace)
        base = (await smoke.redis_server_time(client_a)) - timedelta(seconds=2)
        older = smoke.build_snapshot(base, name="race-newer-older", price="1.0")
        newer = smoke.build_snapshot(
            base + timedelta(microseconds=1),
            name="race-newer-older",
            price="2.0",
        )
        start = asyncio.Event()

        async def put(cache: RedisPriceCache, snapshot):  # type: ignore[no-untyped-def]
            await start.wait()
            return await cache.put(snapshot)

        tasks = [
            asyncio.create_task(put(cache_a, older)),
            asyncio.create_task(put(cache_b, newer)),
        ]
        start.set()
        results = await asyncio.gather(*tasks)
        assert PriceCacheWriteResult.CREATED in results
        assert set(results) in (
            {PriceCacheWriteResult.CREATED, PriceCacheWriteResult.REPLACED},
            {PriceCacheWriteResult.CREATED, PriceCacheWriteResult.IGNORED_OLDER},
        )
        final = await cache_a.get(newer.key)
        assert final.snapshot is not None
        assert final.snapshot.observed_at == newer.observed_at
        assert final.snapshot.candidates == newer.candidates

    _run(scenario)


def test_concurrent_equal_race_keeps_first_payload_and_noop_metadata() -> None:
    async def scenario(client_a: object, client_b: object, namespace: str) -> None:
        cache_a = RedisPriceCache(client_a, namespace=namespace)
        cache_b = RedisPriceCache(client_b, namespace=namespace)
        observed = (await smoke.redis_server_time(client_a)) - timedelta(seconds=2)
        first = smoke.build_snapshot(observed, name="race-equal", price="1.0")
        second = smoke.build_snapshot(
            observed,
            name="race-equal",
            price="2.0",
            fresh=timedelta(hours=1),
        )
        start = asyncio.Event()

        async def put(cache: RedisPriceCache, snapshot):  # type: ignore[no-untyped-def]
            await start.wait()
            return await cache.put(snapshot)

        tasks = [
            asyncio.create_task(put(cache_a, first)),
            asyncio.create_task(put(cache_b, second)),
        ]
        start.set()
        results = await asyncio.gather(*tasks)
        assert sorted(results) == sorted(
            [PriceCacheWriteResult.CREATED, PriceCacheWriteResult.UNCHANGED_EQUAL]
        )
        final = (await cache_a.get(first.key)).snapshot
        assert final is not None
        assert final.candidates in (first.candidates, second.candidates)
        key = cache_a.key_for(first.key)
        stored_before = await client_a.hmget(key, "stored_seconds", "stored_microseconds")
        expiry_before = await smoke._pexpiretime(client_a, key)

        loser = second if final.candidates == first.candidates else first
        assert await cache_b.put(loser) == PriceCacheWriteResult.UNCHANGED_EQUAL
        assert await client_a.hmget(key, "stored_seconds", "stored_microseconds") == stored_before
        assert await smoke._pexpiretime(client_a, key) == expiry_before

    _run(scenario)
