import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.clients.discord_client import AlertDispatchResult, DiscordWebhookClient
from app.services.recipe_solver import RecipeCandidate


class AlertSeverity(StrEnum):
    """Supported severities for Discord alerts."""

    INFO = "INFO"
    OPPORTUNITY = "OPPORTUNITY"
    URGENT = "URGENT"
    ERROR = "ERROR"
    DAILY_SUMMARY = "DAILY_SUMMARY"


@dataclass(frozen=True)
class AlertField:
    """One display field for a Discord embed."""

    name: str
    value: str
    inline: bool = False


@dataclass(frozen=True)
class AlertMessage:
    """Internal alert message representation before Discord payload conversion."""

    title: str
    severity: AlertSeverity
    content: str
    fields: list[AlertField]
    dedupe_key: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title cannot be empty")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")


@dataclass(frozen=True)
class AlertServiceConfig:
    """Configuration for alert formatting and dispatch behavior."""

    alert_only_passed_risk: bool = True
    urgent_min_roi: Decimal | None = None
    urgent_min_expected_profit_cny: Decimal | None = None
    enable_dedupe: bool = True


class InMemoryAlertDedupeStore:
    """Simple in-memory dedupe store for already-sent alert keys."""

    def __init__(self) -> None:
        self._sent_keys: set[str] = set()

    def mark_sent(self, dedupe_key: str) -> None:
        """Mark a dedupe key as already sent."""

        self._sent_keys.add(dedupe_key)

    def was_sent(self, dedupe_key: str) -> bool:
        """Return whether the dedupe key has already been sent."""

        return dedupe_key in self._sent_keys

    def clear(self) -> None:
        """Clear all recorded dedupe keys."""

        self._sent_keys.clear()


class AlertService:
    """Formats recipe/pipeline data into Discord alerts and dispatches them."""

    def __init__(
        self,
        discord_client: DiscordWebhookClient,
        config: AlertServiceConfig,
        dedupe_store: InMemoryAlertDedupeStore | None = None,
    ) -> None:
        self.discord_client = discord_client
        self.config = config
        self.dedupe_store = dedupe_store or InMemoryAlertDedupeStore()

    def build_recipe_alert(self, recipe: RecipeCandidate) -> AlertMessage:
        """Build an alert message for one recipe candidate."""

        severity = self._determine_recipe_severity(recipe)
        title = (
            "CS2 Trade-up Opportunity"
            if recipe.risk_decision.passed
            else "CS2 Trade-up Candidate Rejected by Risk Filter"
        )
        content = f"Recipe {recipe.recipe_hash[:12]}"
        if severity == AlertSeverity.URGENT:
            mention_text = self._build_mention_text()
            if mention_text:
                content = f"{mention_text} {content}"

        fields = [
            AlertField("Input Total Cost", _format_decimal(recipe.metrics.input_total_cost_cny)),
            AlertField("Expected Profit", _format_decimal(recipe.metrics.expected_profit_cny)),
            AlertField("ROI", _format_percentage(recipe.metrics.roi)),
            AlertField("Worst Case Profit", _format_decimal(recipe.metrics.worst_case_profit_cny)),
            AlertField("Best Case Profit", _format_decimal(recipe.metrics.best_case_profit_cny)),
            AlertField(
                "Profit Probability",
                _format_probability(recipe.metrics.profit_probability),
            ),
            AlertField("Risk Passed", str(recipe.risk_decision.passed)),
            AlertField("Risk Score", _format_decimal(recipe.risk_decision.risk_score)),
            AlertField(
                "Risk Reason Codes",
                _truncate_text(", ".join(recipe.risk_decision.reason_codes) or "None"),
            ),
            AlertField("Input Items Summary", _build_input_summary(recipe), inline=False),
            AlertField("Output Results Summary", _build_output_summary(recipe), inline=False),
        ]

        return AlertMessage(
            title=title,
            severity=severity,
            content=content,
            fields=fields,
            dedupe_key=f"recipe:{recipe.recipe_hash}",
            created_at=datetime.now(UTC),
        )

    def build_pipeline_error_alert(self, errors: list[str]) -> AlertMessage:
        """Build an error alert for pipeline failures."""

        error_count = len(errors)
        joined_errors = "\n".join(errors[:5]) if errors else "No errors provided."
        dedupe_hash = (
            hashlib.sha256("|".join(errors).encode("utf-8")).hexdigest()
            if errors
            else "empty"
        )

        return AlertMessage(
            title="CS2 Trade-up Pipeline Error",
            severity=AlertSeverity.ERROR,
            content=f"Pipeline reported {error_count} error(s).",
            fields=[AlertField("Errors", _truncate_text(joined_errors), inline=False)],
            dedupe_key=f"pipeline-error:{dedupe_hash}",
            created_at=datetime.now(UTC),
        )

    async def send_alert(self, message: AlertMessage) -> AlertDispatchResult:
        """Convert an alert message to Discord payload and send it with optional dedupe."""

        if self.config.enable_dedupe and message.dedupe_key is not None:
            if self.dedupe_store.was_sent(message.dedupe_key):
                return AlertDispatchResult(
                    sent=False,
                    dry_run=self.discord_client.config.dry_run,
                    status_code=None,
                    message="Skipped duplicate alert",
                    dedupe_key=message.dedupe_key,
                )

        payload = _build_discord_payload(message)
        result = await self.discord_client.send_payload(payload)

        if result.sent and message.dedupe_key is not None and self.config.enable_dedupe:
            self.dedupe_store.mark_sent(message.dedupe_key)

        return AlertDispatchResult(
            sent=result.sent,
            dry_run=result.dry_run,
            status_code=result.status_code,
            message=result.message,
            dedupe_key=message.dedupe_key,
        )

    async def send_recipe_alert(self, recipe: RecipeCandidate) -> AlertDispatchResult | None:
        """Send a recipe alert if allowed by alert configuration."""

        if self.config.alert_only_passed_risk and not recipe.risk_decision.passed:
            return None

        message = self.build_recipe_alert(recipe)
        return await self.send_alert(message)

    async def send_pipeline_error_alert(self, errors: list[str]) -> AlertDispatchResult | None:
        """Send a pipeline error alert if there are errors to report."""

        if not errors:
            return None

        message = self.build_pipeline_error_alert(errors)
        return await self.send_alert(message)

    def _determine_recipe_severity(self, recipe: RecipeCandidate) -> AlertSeverity:
        """Determine alert severity for a recipe candidate."""

        if not recipe.risk_decision.passed:
            return AlertSeverity.INFO

        if (
            self.config.urgent_min_roi is not None
            and recipe.metrics.roi >= self.config.urgent_min_roi
        ):
            return AlertSeverity.URGENT
        if (
            self.config.urgent_min_expected_profit_cny is not None
            and recipe.metrics.expected_profit_cny >= self.config.urgent_min_expected_profit_cny
        ):
            return AlertSeverity.URGENT
        return AlertSeverity.OPPORTUNITY

    def _build_mention_text(self) -> str:
        """Build the Discord mention text for urgent alerts."""

        parts: list[str] = []
        if self.discord_client.config.mention_user_id:
            parts.append(f"<@{self.discord_client.config.mention_user_id}>")
        if self.discord_client.config.mention_role_id:
            parts.append(f"<@&{self.discord_client.config.mention_role_id}>")
        return " ".join(parts)



def _build_input_summary(recipe: RecipeCandidate) -> str:
    """Build a compact input-item summary for a recipe alert."""

    lines = [
        _truncate_text(
            f"{item.market_hash_name} | {item.collection_name} | "
            f"f={item.actual_float:.4f} | ¥{item.price_cny}"
        )
        for item in recipe.input_items[:10]
    ]
    return "\n".join(lines)



def _build_output_summary(recipe: RecipeCandidate) -> str:
    """Build a compact output-results summary for a recipe alert."""

    lines = [
        _truncate_text(
            f"{result.output_market_hash_name} | {_format_probability(result.probability)} | "
            f"f={result.output_float:.4f} | {result.output_wear} | ¥{result.estimated_price_cny}"
        )
        for result in recipe.tradeup_results[:10]
    ]
    return "\n".join(lines)



def _format_decimal(value: Decimal) -> str:
    """Format Decimal values with stable, human-readable precision."""

    return str(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))



def _format_percentage(value: Decimal) -> str:
    """Format a Decimal ratio as a percentage string."""

    percentage = (value * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{percentage}%"



def _format_probability(value: float) -> str:
    """Format a probability float as a percentage string."""

    percentage = Decimal(str(value * 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{percentage}%"



def _truncate_text(value: str, max_length: int = 512) -> str:
    """Truncate long field text for Discord embed safety."""

    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."



def _severity_color(severity: AlertSeverity) -> int:
    """Map alert severity to a Discord embed color integer."""

    return {
        AlertSeverity.INFO: 0x95A5A6,
        AlertSeverity.OPPORTUNITY: 0x2ECC71,
        AlertSeverity.URGENT: 0xE67E22,
        AlertSeverity.ERROR: 0xE74C3C,
        AlertSeverity.DAILY_SUMMARY: 0x3498DB,
    }[severity]



def _build_discord_payload(message: AlertMessage) -> dict[str, object]:
    """Convert an internal alert message into a Discord webhook payload."""

    return {
        "content": message.content,
        "embeds": [
            {
                "title": message.title,
                "description": message.content,
                "fields": [
                    {
                        "name": field.name,
                        "value": _truncate_text(field.value, max_length=1024),
                        "inline": field.inline,
                    }
                    for field in message.fields
                ],
                "timestamp": message.created_at.isoformat(),
                "color": _severity_color(message.severity),
            }
        ],
    }
