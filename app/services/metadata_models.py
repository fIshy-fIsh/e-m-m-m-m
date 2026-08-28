from dataclasses import dataclass, field
from typing import Any, ClassVar

from app.services.tradeup_engine import OutputCandidate


@dataclass(frozen=True)
class SkinMetadata:
    """Normalized internal metadata representation for a CS2 skin."""

    market_hash_name: str
    name: str | None
    weapon: str | None
    rarity: str
    category: str | None
    collection_name: str | None
    min_float: float
    max_float: float
    stattrak: bool = False
    souvenir: bool = False
    paint_index: int | None = None
    raw: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.market_hash_name.strip():
            raise ValueError("market_hash_name cannot be empty")
        if not self.rarity.strip():
            raise ValueError("rarity cannot be empty")
        if self.min_float >= self.max_float:
            raise ValueError("min_float must be less than max_float")


@dataclass(frozen=True)
class CollectionMetadata:
    """Collection-level view of normalized skins."""

    collection_name: str
    skins: list[SkinMetadata]


@dataclass(frozen=True)
class OutputCandidateBuildResult:
    """Output candidates derived from one input rarity within one collection."""

    input_collection_name: str
    input_rarity: str
    output_candidates: list[OutputCandidate]


@dataclass(frozen=True)
class RarityOrder:
    """Rarity progression used for normal weapon trade-ups in V1."""

    ORDER: ClassVar[tuple[str, ...]] = (
        "Consumer Grade",
        "Industrial Grade",
        "Mil-Spec Grade",
        "Restricted",
        "Classified",
        "Covert",
    )
    INDEX_BY_NAME: ClassVar[dict[str, int]] = {
        rarity: index for index, rarity in enumerate(ORDER)
    }
    VALUES: tuple[str, ...] = field(default=ORDER, init=False)
