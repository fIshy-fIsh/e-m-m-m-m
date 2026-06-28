import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.clients.discord_client import (
    AlertDispatchResult,
    DiscordWebhookClient,
    DiscordWebhookConfig,
)
from app.services.alert_service import (
    AlertField,
    AlertMessage,
    AlertService,
    AlertServiceConfig,
    AlertSeverity,
    InMemoryAlertDedupeStore,
)
from app.services.ev_service import OpportunityMetrics
from app.services.recipe_solver import RecipeCandidate
from app.services.risk_filter import RiskDecision
from app.services.tradeup_engine import InputItem, TradeupResult


class RecordingDiscordWebhookClient(DiscordWebhookClient):
    def __init__(self) -> None:
        super().__init__(DiscordWebhookConfig(webhook_url=None, dry_run=True))
        self.payloads: list[dict[str, object]] = []

    async def send_payload(self, payload: dict[str, object]) -> AlertDispatchResult:
        self.payloads.append(payload)
        return AlertDispatchResult(
            sent=True,
            dry_run=True,
            status_code=None,
            message="Dry run: payload not sent",
        )



def _make_recipe_candidate(
    *,
    risk_passed: bool = True,
    roi: str = "0.10",
    expected_profit: str = "30.00",
) -> RecipeCandidate:
    input_items = [
        InputItem(
            market_hash_name=f"Input Skin {index}",
            collection_name="Collection Alpha",
            rarity="Restricted",
            actual_float=0.10 + index * 0.01,
            min_float=0.00,
            max_float=1.00,
            price_cny=Decimal("10.00"),
            stattrak=False,
            souvenir=False,
        )
        for index in range(10)
    ]
    tradeup_results = [
        TradeupResult(
            output_market_hash_name="Output Skin A",
            probability=1.0,
            output_float=0.12,
            output_wear="Minimal Wear",
            estimated_price_cny=Decimal("120.00"),
            expected_value_contribution=Decimal("120.00"),
        )
    ]
    metrics = OpportunityMetrics(
        input_total_cost_cny=Decimal("100.00"),
        expected_revenue_cny=Decimal("120.00"),
        expected_profit_cny=Decimal(expected_profit),
        roi=Decimal(roi),
        worst_case_profit_cny=Decimal("-5.00"),
        best_case_profit_cny=Decimal("30.00"),
        profit_probability=0.60,
        loss_probability=0.40,
        break_even_probability=0.0,
    )
    risk_decision = RiskDecision(
        passed=risk_passed,
        reasons=[] if risk_passed else ["Risk rejected"],
        reason_codes=[] if risk_passed else ["ROI_BELOW_MINIMUM"],
        risk_score=Decimal("0") if risk_passed else Decimal("20"),
    )
    return RecipeCandidate(
        input_items=input_items,
        tradeup_results=tradeup_results,
        metrics=metrics,
        risk_decision=risk_decision,
        recipe_hash="abc123def4567890",
        created_at=datetime.now(UTC),
    )



def test_alert_message_creates_successfully() -> None:
    message = AlertMessage(
        title="Test Alert",
        severity=AlertSeverity.INFO,
        content="content",
        fields=[AlertField("Field", "Value")],
        created_at=datetime.now(UTC),
    )

    assert message.title == "Test Alert"



def test_alert_message_raises_when_title_empty() -> None:
    with pytest.raises(ValueError, match="title"):
        AlertMessage(
            title="",
            severity=AlertSeverity.INFO,
            content="",
            fields=[],
            created_at=datetime.now(UTC),
        )



def test_alert_message_raises_when_created_at_not_timezone_aware() -> None:
    with pytest.raises(ValueError, match="created_at"):
        AlertMessage(
            title="Test",
            severity=AlertSeverity.INFO,
            content="",
            fields=[],
            created_at=datetime.now(),
        )



def test_build_recipe_alert_for_risk_passed_recipe_is_opportunity() -> None:
    service = AlertService(RecordingDiscordWebhookClient(), AlertServiceConfig())
    message = service.build_recipe_alert(_make_recipe_candidate(risk_passed=True))

    assert message.severity == AlertSeverity.OPPORTUNITY



def test_build_recipe_alert_for_risk_failed_recipe_is_info() -> None:
    service = AlertService(
        RecordingDiscordWebhookClient(),
        AlertServiceConfig(alert_only_passed_risk=False),
    )
    message = service.build_recipe_alert(_make_recipe_candidate(risk_passed=False))

    assert message.severity == AlertSeverity.INFO



def test_urgent_min_roi_promotes_recipe_to_urgent() -> None:
    service = AlertService(
        RecordingDiscordWebhookClient(),
        AlertServiceConfig(urgent_min_roi=Decimal("0.08")),
    )
    message = service.build_recipe_alert(_make_recipe_candidate(roi="0.10"))

    assert message.severity == AlertSeverity.URGENT



def test_urgent_min_expected_profit_promotes_recipe_to_urgent() -> None:
    service = AlertService(
        RecordingDiscordWebhookClient(),
        AlertServiceConfig(urgent_min_expected_profit_cny=Decimal("25.00")),
    )
    message = service.build_recipe_alert(_make_recipe_candidate(expected_profit="30.00"))

    assert message.severity == AlertSeverity.URGENT



def test_build_recipe_alert_contains_core_fields() -> None:
    service = AlertService(RecordingDiscordWebhookClient(), AlertServiceConfig())
    message = service.build_recipe_alert(_make_recipe_candidate())
    field_names = [field.name for field in message.fields]

    assert "Input Total Cost" in field_names
    assert "Expected Profit" in field_names
    assert "ROI" in field_names
    assert "Risk Reason Codes" in field_names



def test_build_recipe_alert_contains_input_and_output_summaries() -> None:
    service = AlertService(RecordingDiscordWebhookClient(), AlertServiceConfig())
    message = service.build_recipe_alert(_make_recipe_candidate())
    fields_by_name = {field.name: field.value for field in message.fields}

    assert "Input Items Summary" in fields_by_name
    assert "Output Results Summary" in fields_by_name
    assert "Input Skin 0" in fields_by_name["Input Items Summary"]
    assert "Output Skin A" in fields_by_name["Output Results Summary"]



def test_build_pipeline_error_alert_generates_error_message() -> None:
    service = AlertService(RecordingDiscordWebhookClient(), AlertServiceConfig())
    message = service.build_pipeline_error_alert(["error one", "error two"])

    assert message.severity == AlertSeverity.ERROR
    assert message.title == "CS2 Trade-up Pipeline Error"



def test_send_alert_skips_duplicate_by_dedupe_key() -> None:
    client = RecordingDiscordWebhookClient()
    dedupe_store = InMemoryAlertDedupeStore()
    service = AlertService(client, AlertServiceConfig(enable_dedupe=True), dedupe_store)
    message = AlertMessage(
        title="Test",
        severity=AlertSeverity.INFO,
        content="content",
        fields=[],
        dedupe_key="dup-key",
        created_at=datetime.now(UTC),
    )

    first = asyncio.run(service.send_alert(message))
    second = asyncio.run(service.send_alert(message))

    assert first.sent is True
    assert second.sent is False
    assert second.message == "Skipped duplicate alert"



def test_send_recipe_alert_returns_none_for_risk_failed_when_only_passed_alerts_enabled() -> None:
    service = AlertService(
        RecordingDiscordWebhookClient(),
        AlertServiceConfig(alert_only_passed_risk=True),
    )

    result = asyncio.run(service.send_recipe_alert(_make_recipe_candidate(risk_passed=False)))

    assert result is None



def test_send_recipe_alert_sends_info_when_risk_failed_and_allowed() -> None:
    client = RecordingDiscordWebhookClient()
    service = AlertService(client, AlertServiceConfig(alert_only_passed_risk=False))

    result = asyncio.run(service.send_recipe_alert(_make_recipe_candidate(risk_passed=False)))

    assert result is not None
    assert client.payloads
    assert (
        client.payloads[0]["embeds"][0]["title"]
        == "CS2 Trade-up Candidate Rejected by Risk Filter"
    )



def test_discord_payload_uses_embeds() -> None:
    client = RecordingDiscordWebhookClient()
    service = AlertService(client, AlertServiceConfig())

    asyncio.run(service.send_recipe_alert(_make_recipe_candidate()))

    assert "embeds" in client.payloads[0]



def test_long_fields_are_truncated() -> None:
    recipe = _make_recipe_candidate()
    recipe = RecipeCandidate(
        input_items=recipe.input_items,
        tradeup_results=recipe.tradeup_results,
        metrics=recipe.metrics,
        risk_decision=RiskDecision(
            passed=False,
            reasons=["x" * 600],
            reason_codes=["X" * 600],
            risk_score=Decimal("20"),
        ),
        recipe_hash=recipe.recipe_hash,
        created_at=recipe.created_at,
    )
    service = AlertService(
        RecordingDiscordWebhookClient(),
        AlertServiceConfig(alert_only_passed_risk=False),
    )
    message = service.build_recipe_alert(recipe)
    field = next(field for field in message.fields if field.name == "Risk Reason Codes")

    assert len(field.value) <= 512



def test_urgent_alert_adds_mentions_to_content() -> None:
    client = RecordingDiscordWebhookClient()
    client.config = DiscordWebhookConfig(
        webhook_url=None,
        dry_run=True,
        mention_user_id="123",
        mention_role_id="456",
    )
    service = AlertService(
        client,
        AlertServiceConfig(urgent_min_roi=Decimal("0.05")),
    )

    message = service.build_recipe_alert(_make_recipe_candidate())

    assert "<@123>" in message.content
    assert "<@&456>" in message.content
