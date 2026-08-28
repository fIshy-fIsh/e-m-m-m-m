import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import steamdt_redis_price_cache_smoke as smoke


class _UnexpectedRedisFactory:
    def __call__(self, redis_url: str) -> object:
        raise AssertionError(f"Redis factory was unexpectedly called for {redis_url!r}")


def test_disabled_async_main_does_not_create_redis_clients() -> None:
    output: list[str] = []

    exit_code = asyncio.run(
        smoke.async_main(
            {
                smoke.RUN_REDIS_PRICE_CACHE_INTEGRATION_ENV: "false",
                "REDIS_URL": "redis://production.example.invalid/0",
            },
            printer=output.append,
            redis_factory=_UnexpectedRedisFactory(),
        )
    )

    assert exit_code == 0
    assert output == [
        "SteamDT Redis price-cache integration smoke skipped:\n"
        f"{smoke.RUN_REDIS_PRICE_CACHE_INTEGRATION_ENV} is not true."
    ]
    assert "production.example.invalid" not in output[0]


@pytest.mark.parametrize("entrypoint", ["direct", "module"])
def test_disabled_smoke_entrypoints_exit_zero_without_redis(entrypoint: str) -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop(smoke.RUN_REDIS_PRICE_CACHE_INTEGRATION_ENV, None)
    env[smoke.TEST_REDIS_URL_ENV] = "redis://should-not-connect.invalid/15"
    command = (
        [sys.executable, "scripts/steamdt_redis_price_cache_smoke.py"]
        if entrypoint == "direct"
        else [sys.executable, "-m", "scripts.steamdt_redis_price_cache_smoke"]
    )

    result = subprocess.run(
        command,
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0
    assert "integration smoke skipped" in result.stdout
    assert "should-not-connect.invalid" not in result.stdout
    assert result.stderr == ""


def test_test_namespace_requires_prefix_and_uuid_suffix() -> None:
    suffix = "0123456789abcdef0123456789abcdef"
    namespace = smoke.build_test_namespace(suffix=suffix)

    assert namespace == f"{smoke.DEFAULT_TEST_REDIS_PRICE_CACHE_NAMESPACE}-{suffix}"
    smoke.build_namespace_scan_pattern(namespace)

    for invalid_base in (
        "",
        "steamdt-price-cache-v1",
        "steamdt-rate-limit-integration-v1",
        "other-price-cache-integration-v1",
        "steamdt-price-cache-integration-v1*",
        "steamdt-price-cache-integration-v1{bad}",
        "steamdt-price-cache-integration-v1\n",
    ):
        with pytest.raises((TypeError, ValueError)):
            smoke.build_test_namespace(invalid_base, suffix=suffix)

    for invalid_suffix in ("", "not-a-uuid", "A" * 32, "0" * 31, "0" * 33):
        with pytest.raises(ValueError):
            smoke.build_test_namespace(suffix=invalid_suffix)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, 0),
        (123, 123),
        (b"0", 0),
        (b"123", 123),
        ("0", 0),
        ("123", 123),
    ],
)
def test_exact_integer_helper_accepts_redis_shapes(value: object, expected: int) -> None:
    assert smoke._exact_nonnegative_int(value, field="test") == expected


@pytest.mark.parametrize(
    "value",
    [True, False, -1, b"-1", "-1", 1.5, b"bad", " 1", b"\xff"],
)
def test_exact_integer_helper_rejects_malformed_values(value: object) -> None:
    with pytest.raises(RuntimeError):
        smoke._exact_nonnegative_int(value, field="test")


def test_redis_time_helper_rejects_malformed_shape_without_float() -> None:
    class FakeRedis:
        def __init__(self, response: object) -> None:
            self.response = response

        async def time(self) -> object:
            return self.response

    valid = asyncio.run(smoke.redis_server_time(FakeRedis([1_700_000_000, 123_456])))
    assert valid.microsecond == 123_456

    for response in (
        None,
        b"bad",
        [1],
        [1, 2, 3],
        [True, 1],
        [-1, 1],
        [1, 1_000_000],
        [1.5, 1],
    ):
        with pytest.raises(RuntimeError):
            asyncio.run(smoke.redis_server_time(FakeRedis(response)))


def test_async_main_closes_both_owned_clients_even_when_smoke_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    owned = [FakeClient(), FakeClient()]
    clients_to_create = iter(owned)

    async def fail_smoke(
        client_a: object,
        client_b: object,
        *,
        namespace: str,
        printer=print,
    ) -> None:
        assert client_a is owned[0]
        assert client_b is owned[1]
        assert namespace.startswith(smoke.DEFAULT_TEST_REDIS_PRICE_CACHE_NAMESPACE)
        raise RuntimeError("Authorization: Bearer fake-secret-token")

    monkeypatch.setattr(smoke, "run_redis_price_cache_smoke", fail_smoke)
    output: list[str] = []

    exit_code = asyncio.run(
        smoke.async_main(
            {
                smoke.RUN_REDIS_PRICE_CACHE_INTEGRATION_ENV: "true",
                smoke.TEST_REDIS_URL_ENV: "redis://user:password@localhost:6379/15?token=query",
                smoke.TEST_REDIS_PRICE_CACHE_NAMESPACE_ENV: (
                    smoke.DEFAULT_TEST_REDIS_PRICE_CACHE_NAMESPACE
                ),
            },
            printer=output.append,
            redis_factory=lambda _url: next(clients_to_create),
        )
    )

    assert exit_code == 1
    assert all(client.closed for client in owned)
    text = "\n".join(output)
    assert "password" not in text
    assert "fake-secret-token" not in text
    assert "query" not in text
    assert "Authorization" not in text
