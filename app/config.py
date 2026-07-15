from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScanSettings(BaseModel):
    high_priority_interval_seconds: int
    normal_interval_seconds: int

    model_config = ConfigDict(frozen=True)


class TradingSettings(BaseModel):
    sell_fee_rate: float
    min_roi: float
    min_expected_profit_cny: float
    max_worst_case_loss_pct: float
    min_profit_probability: float
    max_input_total_cost_cny: float

    model_config = ConfigDict(frozen=True)


class SchedulerSettings(BaseModel):
    heartbeat_interval_seconds: int
    cleanup_interval_seconds: int
    run_on_startup: bool
    max_instances: int

    model_config = ConfigDict(frozen=True)


class Settings(BaseSettings):
    app_env: str = "development"
    dry_run: bool = True
    log_level: str = "INFO"

    database_url: str
    redis_url: str

    bymykel_base_url: str

    buff_base_url: str = ""
    buff_api_key: str = ""
    buff_api_secret: str = ""
    buff_rate_limit_per_minute: int = 60

    discord_webhook_url: str = ""
    discord_mention_user_id: str = ""
    discord_mention_role_id: str = ""

    steamdt_base_url: str = "https://open.steamdt.com"
    steamdt_api_key: str = ""
    steamdt_dry_run: bool = True
    steamdt_rate_limit_per_minute: int = Field(
        default=60,
        gt=0,
        description="Deprecated; SteamDT uses endpoint-specific request budgets.",
    )
    steamdt_rate_limit_price_single_per_minute: int = Field(default=60, gt=0)
    steamdt_rate_limit_price_batch_per_minute: int = Field(default=1, gt=0)
    steamdt_rate_limit_price_avg_per_minute: int = Field(
        default=10,
        gt=0,
        description=(
            "Internal safety cap; official SteamDT limit is not documented in the "
            "permissions table."
        ),
    )
    steamdt_rate_limit_base_per_day: int = Field(default=1, gt=0)
    steamdt_rate_limit_kline_per_minute: int = Field(default=120, gt=0)
    steamdt_rate_limit_wear_per_hour: int = Field(default=36000, gt=0)
    steamdt_rate_limit_price_batch_safety_buffer_seconds: float = Field(default=5.0, ge=0)

    scan_high_priority_interval_seconds: int = 60
    scan_normal_interval_seconds: int = 300
    scheduler_heartbeat_interval_seconds: int = 86400
    scheduler_cleanup_interval_seconds: int = 86400
    scheduler_run_on_startup: bool = False
    scheduler_max_instances: int = 1

    sell_fee_rate: float = 0.025
    min_roi: float = 0.05
    min_expected_profit_cny: float = 20.0
    max_worst_case_loss_pct: float = 0.25
    min_profit_probability: float = 0.35
    max_input_total_cost_cny: float = 1000.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def scan(self) -> ScanSettings:
        return ScanSettings(
            high_priority_interval_seconds=self.scan_high_priority_interval_seconds,
            normal_interval_seconds=self.scan_normal_interval_seconds,
        )

    @property
    def trading(self) -> TradingSettings:
        return TradingSettings(
            sell_fee_rate=self.sell_fee_rate,
            min_roi=self.min_roi,
            min_expected_profit_cny=self.min_expected_profit_cny,
            max_worst_case_loss_pct=self.max_worst_case_loss_pct,
            min_profit_probability=self.min_profit_probability,
            max_input_total_cost_cny=self.max_input_total_cost_cny,
        )

    @property
    def scheduler(self) -> SchedulerSettings:
        return SchedulerSettings(
            heartbeat_interval_seconds=self.scheduler_heartbeat_interval_seconds,
            cleanup_interval_seconds=self.scheduler_cleanup_interval_seconds,
            run_on_startup=self.scheduler_run_on_startup,
            max_instances=self.scheduler_max_instances,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
