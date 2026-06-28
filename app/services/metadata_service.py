from decimal import Decimal
from typing import Any

from app.services.metadata_models import RarityOrder, SkinMetadata
from app.services.tradeup_engine import OutputCandidate


def normalize_skin(raw: dict[str, Any]) -> SkinMetadata:
    """Normalize one raw metadata payload into the internal skin metadata model.

    Fallback rule:
    - prefer raw['market_hash_name']
    - if missing/empty, use a non-empty raw['name'] as internal market_hash_name
    - if both are missing/empty, raise ValueError
    """

    raw_market_hash_name = _as_optional_str(raw.get("market_hash_name"))
    raw_name = _as_optional_str(raw.get("name"))
    market_hash_name = raw_market_hash_name or raw_name
    if not market_hash_name:
        raise ValueError("market_hash_name is required")

    rarity = _as_optional_str(raw.get("rarity"))
    if not rarity:
        raise ValueError("rarity is required")

    min_float = _require_float(raw, "min_float")
    max_float = _require_float(raw, "max_float")

    return SkinMetadata(
        market_hash_name=market_hash_name,
        name=raw_name,
        weapon=_as_optional_str(raw.get("weapon")),
        rarity=rarity,
        category=_as_optional_str(raw.get("category")),
        collection_name=_extract_collection_name(raw),
        min_float=min_float,
        max_float=max_float,
        stattrak=bool(raw.get("stattrak", False)),
        souvenir=bool(raw.get("souvenir", False)),
        paint_index=_as_optional_int(raw.get("paint_index")),
        raw=dict(raw),
    )



def normalize_skins(raw_skins: list[dict[str, Any]]) -> list[SkinMetadata]:
    """Normalize a list of raw metadata payloads in strict mode."""

    return [normalize_skin(raw_skin) for raw_skin in raw_skins]



def get_next_rarity(rarity: str) -> str | None:
    """Return the next normal weapon trade-up rarity, or None for Covert."""

    current_index = RarityOrder.INDEX_BY_NAME.get(rarity)
    if current_index is None:
        raise ValueError(f"unsupported rarity: {rarity}")

    next_index = current_index + 1
    if next_index >= len(RarityOrder.ORDER):
        return None

    return RarityOrder.ORDER[next_index]



def build_output_candidates_by_collection(
    skins: list[SkinMetadata],
    input_rarity: str,
) -> dict[str, list[OutputCandidate]]:
    """Build trade-up output candidates grouped by collection for one input rarity."""

    next_rarity = get_next_rarity(input_rarity)
    if next_rarity is None:
        return {}

    skins_by_collection: dict[str, list[SkinMetadata]] = {}
    for skin in skins:
        if skin.collection_name is None:
            continue
        skins_by_collection.setdefault(skin.collection_name, []).append(skin)

    output_candidates_by_collection: dict[str, list[OutputCandidate]] = {}
    for collection_name, collection_skins in skins_by_collection.items():
        input_skins = [skin for skin in collection_skins if skin.rarity == input_rarity]
        if not input_skins:
            continue

        output_skins = [skin for skin in collection_skins if skin.rarity == next_rarity]
        if not output_skins:
            continue

        output_candidates_by_collection[collection_name] = [
            OutputCandidate(
                market_hash_name=skin.market_hash_name,
                collection_name=collection_name,
                rarity=skin.rarity,
                min_float=skin.min_float,
                max_float=skin.max_float,
                estimated_price_cny=Decimal("0"),
            )
            for skin in output_skins
        ]

    return output_candidates_by_collection



def _require_float(raw: dict[str, Any], field_name: str) -> float:
    """Read a required float field from a raw metadata payload."""

    if field_name not in raw:
        raise ValueError(f"{field_name} is required")
    value = raw[field_name]
    if value is None:
        raise ValueError(f"{field_name} is required")
    return float(value)



def _extract_collection_name(raw: dict[str, Any]) -> str | None:
    """Extract collection_name from supported raw metadata field patterns."""

    direct_collection_name = _as_optional_str(raw.get("collection_name"))
    if direct_collection_name:
        return direct_collection_name

    collection = raw.get("collection")
    if isinstance(collection, dict):
        return _as_optional_str(collection.get("name"))

    return _as_optional_str(collection)



def _as_optional_str(value: Any) -> str | None:
    """Convert a raw value into a stripped optional string."""

    if value is None:
        return None
    string_value = str(value).strip()
    return string_value or None



def _as_optional_int(value: Any) -> int | None:
    """Convert a raw value into an optional integer."""

    if value is None:
        return None
    return int(value)
