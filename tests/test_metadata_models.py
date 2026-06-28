
import pytest

from app.services.metadata_models import SkinMetadata


def test_skin_metadata_creates_successfully() -> None:
    metadata = SkinMetadata(
        market_hash_name="AK-47 | Redline (Field-Tested)",
        name="AK-47 | Redline (Field-Tested)",
        weapon="AK-47",
        rarity="Classified",
        category="Rifle",
        collection_name="Collection Alpha",
        min_float=0.10,
        max_float=0.70,
        raw={"source": "test"},
    )

    assert metadata.market_hash_name == "AK-47 | Redline (Field-Tested)"



def test_skin_metadata_raises_when_market_hash_name_empty() -> None:
    with pytest.raises(ValueError, match="market_hash_name"):
        SkinMetadata(
            market_hash_name="",
            name="Name",
            weapon=None,
            rarity="Restricted",
            category=None,
            collection_name=None,
            min_float=0.10,
            max_float=0.60,
            raw=None,
        )



def test_skin_metadata_raises_when_rarity_empty() -> None:
    with pytest.raises(ValueError, match="rarity"):
        SkinMetadata(
            market_hash_name="Valid Name",
            name="Name",
            weapon=None,
            rarity="",
            category=None,
            collection_name=None,
            min_float=0.10,
            max_float=0.60,
            raw=None,
        )



def test_skin_metadata_raises_when_min_float_is_not_less_than_max_float() -> None:
    with pytest.raises(ValueError, match="min_float"):
        SkinMetadata(
            market_hash_name="Valid Name",
            name="Name",
            weapon=None,
            rarity="Restricted",
            category=None,
            collection_name=None,
            min_float=0.60,
            max_float=0.60,
            raw=None,
        )
