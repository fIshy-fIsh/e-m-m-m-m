from pathlib import Path

import scripts.docker_smoke_test as docker_smoke_test
from app.clients.discord_client import DiscordWebhookConfig
from app.config import Settings
from app.logging_config import configure_logging


def test_settings_default_dry_run_is_true() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://cs2bot:password@postgres:5432/cs2tradeup",
        redis_url="redis://redis:6379/0",
        bymykel_base_url="https://example.test",
    )

    assert settings.dry_run is True


def test_settings_default_steamdt_rate_limiter_backend_is_inmemory() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://cs2bot:password@postgres:5432/cs2tradeup",
        redis_url="redis://redis:6379/0",
        bymykel_base_url="https://example.test",
    )

    assert settings.steamdt_rate_limit_backend == "inmemory"
    assert settings.steamdt_rate_limit_redis_namespace == "steamdt-rate-limit-v1"


def test_settings_default_steamdt_price_cache_backend_is_inmemory() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://cs2bot:password@postgres:5432/cs2tradeup",
        redis_url="redis://redis:6379/0",
        bymykel_base_url="https://example.test",
    )

    assert settings.steamdt_price_cache_backend == "inmemory"
    assert settings.steamdt_price_cache_redis_namespace == "steamdt-price-cache-v1"


def test_scheduler_env_defaults_are_reasonable() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://cs2bot:password@postgres:5432/cs2tradeup",
        redis_url="redis://redis:6379/0",
        bymykel_base_url="https://example.test",
    )

    assert settings.scheduler.heartbeat_interval_seconds == 86400
    assert settings.scheduler.cleanup_interval_seconds == 86400
    assert settings.scheduler.max_instances == 1



def test_discord_webhook_url_can_be_empty_in_dry_run() -> None:
    config = DiscordWebhookConfig(webhook_url=None, dry_run=True)

    assert config.webhook_url is None



def test_docker_smoke_test_module_is_importable() -> None:
    assert hasattr(docker_smoke_test, "main")



def test_configure_logging_executes() -> None:
    configure_logging("INFO")



def test_env_example_contains_critical_scheduler_variables() -> None:
    content = Path(".env.example").read_text(encoding="utf-8")

    assert "DRY_RUN=true" in content
    assert "SCHEDULER_HEARTBEAT_INTERVAL_SECONDS=86400" in content
    assert "SCHEDULER_CLEANUP_INTERVAL_SECONDS=86400" in content
    assert "SCHEDULER_RUN_ON_STARTUP=false" in content
    assert "SCHEDULER_MAX_INSTANCES=1" in content
    assert "STEAMDT_RATE_LIMIT_BACKEND=inmemory" in content
    assert "STEAMDT_RATE_LIMIT_REDIS_NAMESPACE=steamdt-rate-limit-v1" in content
    assert "STEAMDT_PRICE_CACHE_BACKEND=inmemory" in content
    assert (
        "STEAMDT_PRICE_CACHE_REDIS_NAMESPACE=steamdt-price-cache-v1" in content
    )


def test_dockerignore_exists_and_ignores_env() -> None:
    content = Path(".dockerignore").read_text(encoding="utf-8")

    assert ".env" in content



def test_dockerfile_uses_python_3_12_slim() -> None:
    content = Path("Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.12-slim" in content



def test_docker_compose_contains_scheduler_and_api_services() -> None:
    content = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "scheduler:" in content
    assert "api:" in content
