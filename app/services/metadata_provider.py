import json
from pathlib import Path
from typing import Protocol

from app.clients.metadata_client import MetadataClient
from app.services.metadata_models import SkinMetadata
from app.services.metadata_service import normalize_skins


class MetadataProvider(Protocol):
    """Protocol for metadata providers that return normalized skin metadata."""

    async def fetch_skins(self) -> list[SkinMetadata]:
        """Fetch and return normalized skin metadata."""


class LocalJsonMetadataProvider:
    """Metadata provider backed by a local JSON fixture or dataset file."""

    def __init__(self, json_path: Path) -> None:
        self.json_path = json_path

    async def fetch_skins(self) -> list[SkinMetadata]:
        """Load raw skins from a local JSON file and normalize them."""

        raw_payload = json.loads(self.json_path.read_text(encoding="utf-8"))
        if not isinstance(raw_payload, list):
            raise ValueError("local metadata JSON must contain a list of skin objects")
        return normalize_skins(raw_payload)


class ByMykelMetadataProvider:
    """External metadata provider skeleton backed by a mockable HTTP client.

    Assumption/TODO:
    - raw external field shapes may evolve
    - provider fetches raw payloads only and delegates all mapping to metadata_service
    """

    def __init__(self, client: MetadataClient) -> None:
        self.client = client

    async def fetch_skins(self) -> list[SkinMetadata]:
        """Fetch raw skins via the client and normalize them into internal models."""

        raw_skins = await self.client.fetch_raw_skins()
        return normalize_skins(raw_skins)
