"""Phase 16F — Live validation case freeze/serialize/verify tests.

These tests exercise the offline-only Phase 16F validation case module.
No network I/O is performed.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence

import pytest

from app.services.buff_item_identity import BuffItemIdentity
from app.services.market_universe_builder import StatTrakMode
from app.services.recipe_first_live_case import (
    LIVE_CASE_SCHEMA_VERSION,
    LiveValidationCase,
    LiveValidationCaseError,
    LiveValidationPlanItem,
    freeze_case,
    hash_case,
    serialize_case,
    verify_case_identity,
)


class _StubIdentityResolver:
    def __init__(
        self,
        mapping: dict[str, BuffItemIdentity] | None = None,
    ) -> None:
        self._mapping = mapping or {}
        self.calls: list[str] = []

    async def resolve_goods_id(self, goods_id: str) -> BuffItemIdentity | None:
        self.calls.append(goods_id)
        return self._mapping.get(goods_id)


def _valid_item(
    name: str = "AK-47 | Redline (Field-Tested)",
    goods_id: str = "33960",
) -> LiveValidationPlanItem:
    return LiveValidationPlanItem(
        market_hash_name=name,
        goods_id=goods_id,
        collection_name="The 2018 Nuke Collection",
        priority_within_collection=1,
    )


def _valid_kwargs(
    *,
    plan_items: Sequence[LiveValidationPlanItem] | None = None,
    collection_counts: Sequence[tuple[str, int]] | None = None,
    family_key: str = "a" * 24,
    repository_head_sha: str = "0" * 64,
    family_hash: str = "a" * 64,
) -> dict:
    kwargs: dict = {
        "repository_head_sha": repository_head_sha,
        "case_purpose": "test fixture",
        "family_hash": family_hash,
        "family_key": family_key,
        "input_rarity": "Restricted",
        "stattrak_mode": StatTrakMode.NORMAL,
        "plan_items": plan_items if plan_items is not None else (_valid_item(),),
    }
    if collection_counts is not None:
        kwargs["collection_counts"] = collection_counts
    else:
        kwargs["collection_counts"] = (("The 2018 Nuke Collection", 10),)
    return kwargs


def test_freeze_case_accepts_valid_fixture() -> None:
    case = freeze_case(**_valid_kwargs())
    assert isinstance(case, LiveValidationCase)
    assert case.case_schema_version == LIVE_CASE_SCHEMA_VERSION
    assert case.hard_request_count == 1


def test_freeze_case_rejects_unsupported_schema_version() -> None:
    with pytest.raises(LiveValidationCaseError, match="case_schema_version"):
        LiveValidationCase(
            case_schema_version=99,
            repository_head_sha="0" * 64,
            case_purpose="x",
            family_hash="a" * 64,
            family_key="a" * 24,
            input_rarity="Restricted",
            stattrak_mode=StatTrakMode.NORMAL,
            collection_counts=(("The 2018 Nuke Collection", 10),),
            plan_items=(_valid_item(),),
            hard_request_count=1,
        )


def test_freeze_case_rejects_collection_count_sum_not_ten() -> None:
    with pytest.raises(LiveValidationCaseError, match="sum"):
        freeze_case(
            **_valid_kwargs(
                collection_counts=(("The 2018 Nuke Collection", 9),)
            )
        )


def test_freeze_case_rejects_duplicate_collection_name() -> None:
    with pytest.raises(LiveValidationCaseError, match="duplicate"):
        freeze_case(
            **_valid_kwargs(
                collection_counts=(
                    ("The 2018 Nuke Collection", 5),
                    ("The 2018 Nuke Collection", 5),
                )
            )
        )


def test_freeze_case_rejects_plan_request_count_over_ten() -> None:
    items = tuple(
        LiveValidationPlanItem(
            market_hash_name=f"Item {i}",
            goods_id=str(1000 + i),
            collection_name="The 2018 Nuke Collection",
            priority_within_collection=i + 1,
        )
        for i in range(11)
    )
    with pytest.raises(LiveValidationCaseError, match="10"):
        freeze_case(**_valid_kwargs(plan_items=items))


def test_freeze_case_rejects_plan_collection_mismatch() -> None:
    item = LiveValidationPlanItem(
        market_hash_name="Other Skin",
        goods_id="11111",
        collection_name="Other Collection",
        priority_within_collection=1,
    )
    with pytest.raises(LiveValidationCaseError, match="collections must exactly cover"):
        freeze_case(**_valid_kwargs(plan_items=(item,)))


def test_freeze_case_rejects_duplicate_plan_goods_id() -> None:
    items = (
        _valid_item(goods_id="1"),
        _valid_item(name="Other", goods_id="1"),
    )
    with pytest.raises(LiveValidationCaseError, match="duplicate goods_id"):
        freeze_case(**_valid_kwargs(plan_items=items))


def test_freeze_case_rejects_duplicate_plan_market_name() -> None:
    items = (
        _valid_item(),
        _valid_item(goods_id="22222"),
    )
    with pytest.raises(LiveValidationCaseError, match="duplicate market_hash_name"):
        freeze_case(**_valid_kwargs(plan_items=items))


def test_freeze_case_rejects_inconsistent_family_key() -> None:
    with pytest.raises(LiveValidationCaseError, match="family_key"):
        freeze_case(**_valid_kwargs(family_key="z" * 24))


def test_serialize_case_is_deterministic_and_canonical() -> None:
    case = freeze_case(**_valid_kwargs())
    first = serialize_case(case)
    second = serialize_case(case)
    assert first == second
    parsed = json.loads(first)
    assert parsed["case_schema_version"] == LIVE_CASE_SCHEMA_VERSION
    assert parsed["hard_request_count"] == 1


def test_serialize_case_excludes_untrusted_fields() -> None:
    case = freeze_case(**_valid_kwargs())
    raw = serialize_case(case).decode("utf-8")
    for forbidden in ("listing_id", "asset_id", "paintwear", "price", "cookie"):
        assert forbidden not in raw, f"forbidden field {forbidden!r} leaked into case"


def test_hash_case_changes_when_any_field_changes() -> None:
    case = freeze_case(**_valid_kwargs())
    base = hash_case(case)
    mutated = freeze_case(
        **{**_valid_kwargs(), "repository_head_sha": "1" * 64}
    )
    assert base != hash_case(mutated)


def test_verify_case_identity_passes_when_resolver_matches() -> None:
    item = _valid_item()
    resolver = _StubIdentityResolver(
        {item.goods_id: BuffItemIdentity(
            market_hash_name=item.market_hash_name,
            goods_id=item.goods_id,
        )}
    )
    case = freeze_case(**_valid_kwargs(plan_items=(item,)))
    asyncio.run(verify_case_identity(case, identity_resolver=resolver))
    assert resolver.calls == [item.goods_id]


def test_verify_case_identity_fails_when_resolver_returns_none() -> None:
    item = _valid_item()
    resolver = _StubIdentityResolver()
    case = freeze_case(**_valid_kwargs(plan_items=(item,)))
    with pytest.raises(LiveValidationCaseError, match="not in pinned"):
        asyncio.run(verify_case_identity(case, identity_resolver=resolver))


def test_verify_case_identity_fails_on_name_mismatch() -> None:
    item = _valid_item()
    resolver = _StubIdentityResolver(
        {item.goods_id: BuffItemIdentity(
            market_hash_name="Wrong Name",
            goods_id=item.goods_id,
        )}
    )
    case = freeze_case(**_valid_kwargs(plan_items=(item,)))
    with pytest.raises(LiveValidationCaseError, match="resolved to"):
        asyncio.run(verify_case_identity(case, identity_resolver=resolver))


def test_verify_case_identity_fails_on_goods_id_mismatch() -> None:
    item = _valid_item()
    resolver = _StubIdentityResolver(
        {item.goods_id: BuffItemIdentity(
            market_hash_name=item.market_hash_name,
            goods_id="99999",
        )}
    )
    case = freeze_case(**_valid_kwargs(plan_items=(item,)))
    with pytest.raises(LiveValidationCaseError, match="goods_id"):
        asyncio.run(verify_case_identity(case, identity_resolver=resolver))


def test_verify_case_identity_sync_runner() -> None:
    """Project convention: async tests wrapped in ``asyncio.run(...)``."""

    item = _valid_item()
    resolver = _StubIdentityResolver(
        {item.goods_id: BuffItemIdentity(
            market_hash_name=item.market_hash_name,
            goods_id=item.goods_id,
        )}
    )
    case = freeze_case(**_valid_kwargs(plan_items=(item,)))
    asyncio.run(verify_case_identity(case, identity_resolver=resolver))
    assert resolver.calls == [item.goods_id]


def test_plan_item_rejects_invalid_priority() -> None:
    with pytest.raises(LiveValidationCaseError, match="priority_within_collection"):
        LiveValidationPlanItem(
            market_hash_name="AK-47 | Redline (Field-Tested)",
            goods_id="33960",
            collection_name="The 2018 Nuke Collection",
            priority_within_collection=0,
        )


def test_plan_item_rejects_whitespace_field() -> None:
    with pytest.raises(LiveValidationCaseError, match="market_hash_name"):
        LiveValidationPlanItem(
            market_hash_name="  ",
            goods_id="33960",
            collection_name="The 2018 Nuke Collection",
            priority_within_collection=1,
        )


def test_freeze_case_rejects_non_int_count() -> None:
    with pytest.raises(LiveValidationCaseError, match="count"):
        LiveValidationCase(
            case_schema_version=LIVE_CASE_SCHEMA_VERSION,
            repository_head_sha="0" * 64,
            case_purpose="x",
            family_hash="a" * 64,
            family_key="a" * 24,
            input_rarity="Restricted",
            stattrak_mode=StatTrakMode.NORMAL,
            collection_counts=(("The 2018 Nuke Collection", True),),
            plan_items=(_valid_item(),),
            hard_request_count=1,
        )