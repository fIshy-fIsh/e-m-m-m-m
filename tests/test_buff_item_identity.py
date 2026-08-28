from __future__ import annotations

import ast
import asyncio
import inspect
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import get_type_hints

import pytest

from app.services import buff_item_identity as identity_module
from app.services.buff_item_identity import (
    BuffItemIdentity,
    BuffItemIdentityResolver,
    BuffItemIdentityValidationError,
)

MARKET_NAME = "Synthetic Rifle | Contract Test (Factory New)"
GOODS_ID = "synthetic-goods-alpha"


class UnresolvedResolver:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def resolve(self, market_hash_name: str) -> BuffItemIdentity | None:
        self.calls.append(market_hash_name)
        return None


class StringSubclass(str):
    pass


def test_public_api_and_signatures_are_exact() -> None:
    assert identity_module.__all__ == (
        "BuffItemIdentityValidationError",
        "BuffItemIdentity",
        "BuffItemIdentityResolver",
    )
    assert [field.name for field in fields(BuffItemIdentity)] == [
        "market_hash_name",
        "goods_id",
    ]
    hints = get_type_hints(BuffItemIdentity)
    assert hints == {"market_hash_name": str, "goods_id": str}
    signature = inspect.signature(BuffItemIdentity)
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )
    resolve = BuffItemIdentityResolver.resolve
    assert inspect.iscoroutinefunction(resolve)
    assert list(inspect.signature(resolve).parameters) == ["self", "market_hash_name"]


def test_identity_preserves_exact_values_and_is_repr_suppressed() -> None:
    identity = BuffItemIdentity(
        market_hash_name=MARKET_NAME,
        goods_id=GOODS_ID,
    )
    assert identity.market_hash_name == MARKET_NAME
    assert identity.goods_id == GOODS_ID
    assert identity == BuffItemIdentity(
        market_hash_name=MARKET_NAME,
        goods_id=GOODS_ID,
    )
    assert MARKET_NAME not in repr(identity)
    assert GOODS_ID not in repr(identity)
    with pytest.raises(FrozenInstanceError):
        identity.goods_id = "changed"  # type: ignore[misc]


def test_case_internal_whitespace_unicode_and_nonnumeric_ids_are_preserved() -> None:
    name = "Synthetic Üpper  Name | Δ"
    goods = "alpha-BETA_goods"
    identity = BuffItemIdentity(market_hash_name=name, goods_id=goods)
    assert identity.market_hash_name == name
    assert identity.goods_id == goods


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("market_hash_name", ""),
        ("market_hash_name", "   "),
        ("market_hash_name", " padded"),
        ("market_hash_name", "padded "),
        ("market_hash_name", None),
        ("market_hash_name", 1),
        ("market_hash_name", True),
        ("market_hash_name", StringSubclass("name")),
        ("goods_id", ""),
        ("goods_id", "   "),
        ("goods_id", " padded"),
        ("goods_id", "padded "),
        ("goods_id", None),
        ("goods_id", 1),
        ("goods_id", True),
        ("goods_id", StringSubclass("goods")),
    ],
)
def test_invalid_values_fail_with_fixed_redacted_field(
    field: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "market_hash_name": MARKET_NAME,
        "goods_id": GOODS_ID,
    }
    values[field] = value
    with pytest.raises(BuffItemIdentityValidationError) as captured:
        BuffItemIdentity(**values)  # type: ignore[arg-type]

    error = captured.value
    assert str(error) == "invalid BUFF item identity contract"
    assert error.field == field
    assert repr(value) not in repr(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def test_unresolved_is_normal_and_query_is_preserved_exactly() -> None:
    resolver: BuffItemIdentityResolver = UnresolvedResolver()
    result = asyncio.run(resolver.resolve(MARKET_NAME))
    assert result is None
    assert resolver.calls == [MARKET_NAME]  # type: ignore[attr-defined]


def test_identity_module_has_no_concrete_resolver_or_external_dependencies() -> None:
    path = Path(identity_module.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    classes = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }
    assert classes == {
        "BuffItemIdentityValidationError",
        "BuffItemIdentity",
        "BuffItemIdentityResolver",
    }
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert imports == {"__future__", "dataclasses", "typing"}
    for forbidden in (
        "dict[",
        "mappingproxytype",
        "json",
        "open(",
        "os.environ",
        "httpx",
        "buff_listing_provider",
        "steamdt",
        "steamapis",
        "metadata",
        "scanner",
        "recipe_solver",
        "valuation",
        "redis",
        "cache",
        "runtime",
        "purchase",
    ):
        assert forbidden not in source.casefold()
