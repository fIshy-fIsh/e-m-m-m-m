from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.tradeup_engine import InputItem

__all__ = (
    "TradeUpInputMetadata",
    "TradeUpInputMetadataResolver",
    "InMemoryTradeUpInputMetadataResolver",
    "candidates_to_input_items",
)


@dataclass(frozen=True, kw_only=True, repr=False)
class TradeUpInputMetadata:
    """Synthetic metadata mapping one known market_hash_name to engine fields."""

    market_hash_name: str
    collection_name: str
    rarity: str
    min_float: float
    max_float: float

    def __post_init__(self) -> None:
        for value in (self.market_hash_name, self.collection_name, self.rarity):
            if type(value) is not str or not value or value != value.strip():
                raise ValueError("invalid synthetic trade-up metadata")
        if (
            type(self.min_float) is not float
            or type(self.max_float) is not float
            or not math.isfinite(self.min_float)
            or not math.isfinite(self.max_float)
            or self.min_float < 0
            or self.max_float > 1
            or self.min_float >= self.max_float
        ):
            raise ValueError("invalid synthetic trade-up metadata")


class TradeUpInputMetadataResolver(Protocol):
    """Resolve a market_hash_name to synthetic metadata or None."""

    def resolve(self, market_hash_name: str) -> TradeUpInputMetadata | None:
        """Return one synthetic record or None when unresolved."""


class InMemoryTradeUpInputMetadataResolver:
    """Test/synthetic metadata store. No I/O, no environment, no network."""

    def __init__(self, mapping: Mapping[str, TradeUpInputMetadata]) -> None:
        self._mapping = MappingProxyType(
            {key: value for key, value in mapping.items()}
        )

    def resolve(self, market_hash_name: str) -> TradeUpInputMetadata | None:
        return self._mapping.get(market_hash_name)


def candidates_to_input_items(
    candidates: Iterable[TradeUpInputCandidate],
    metadata_resolver: TradeUpInputMetadataResolver,
) -> list[InputItem]:
    """Convert TradeUpInputCandidates to engine InputItems via synthetic metadata.

    Candidates whose market_hash_name is None (unresolved) or not in the
    resolver are skipped. The returned list preserves the input order.
    """

    items: list[InputItem] = []
    for candidate in candidates:
        if candidate.market_hash_name is None:
            continue
        metadata = metadata_resolver.resolve(candidate.market_hash_name)
        if metadata is None:
            continue
        items.append(
            InputItem(
                market_hash_name=candidate.market_hash_name,
                collection_name=metadata.collection_name,
                rarity=metadata.rarity,
                actual_float=float(candidate.paintwear),
                min_float=metadata.min_float,
                max_float=metadata.max_float,
                price_cny=candidate.price_cny,
                stattrak=False,
                souvenir=False,
            )
        )
    return items
