from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

_FIXED_ERROR = "invalid BUFF item identity contract"
_ALLOWED_FIELDS = frozenset({"market_hash_name", "goods_id"})

__all__ = (
    "BuffItemIdentityValidationError",
    "BuffItemIdentity",
    "BuffItemIdentityResolver",
)


class BuffItemIdentityValidationError(ValueError):
    """A canonical BUFF item identity value violated the fixed contract."""

    def __init__(self, *, field: str) -> None:
        if field not in _ALLOWED_FIELDS:
            raise ValueError("unsupported BUFF item identity field")
        super().__init__(_FIXED_ERROR)
        self.field = field


@dataclass(frozen=True, kw_only=True, repr=False)
class BuffItemIdentity:
    """One resolved exact market-name and BUFF goods-ID pair."""

    market_hash_name: str
    goods_id: str

    def __post_init__(self) -> None:
        _validate_exact_string(self.market_hash_name, field="market_hash_name")
        _validate_exact_string(self.goods_id, field="goods_id")


class BuffItemIdentityResolver(Protocol):
    """Resolve an exact market name or return normal unresolved state."""

    async def resolve(
        self,
        market_hash_name: str,
    ) -> BuffItemIdentity | None:
        """Return one verified identity or None when unresolved."""


def _validate_exact_string(value: object, *, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise BuffItemIdentityValidationError(field=field)
    return value
