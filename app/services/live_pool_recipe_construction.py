from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.services.live_metadata_catalog import SkinMetadataCatalog
from app.services.live_recipe_construction import (
    LiveRecipeConstructionResult,
    construct_live_recipes,
)
from app.services.recipe_solver import RecipeSolverConfig
from app.services.steamapis_offer_pool import (
    SteamApisOfferPool,
    SteamApisOfferPoolSnapshot,
)

__all__ = (
    "LivePoolRecipeConstructionError",
    "LivePoolRecipeConstructionResult",
    "construct_live_recipes_from_pool",
)

_FIXED_ERROR_MESSAGE = "Live pool recipe construction failed"


class LivePoolRecipeConstructionError(RuntimeError):
    """Current pool construction failed without exposing listing details."""

    def __init__(self) -> None:
        super().__init__(_FIXED_ERROR_MESSAGE)


@dataclass(frozen=True, kw_only=True, repr=False)
class LivePoolRecipeConstructionResult:
    """Validated Step 2E construction from one current pool snapshot."""

    snapshot_observation_count: int
    construction: LiveRecipeConstructionResult

    def __post_init__(self) -> None:
        try:
            if (
                type(self.snapshot_observation_count) is not int
                or self.snapshot_observation_count < 0
                or type(self.construction) is not LiveRecipeConstructionResult
            ):
                raise LivePoolRecipeConstructionError
            construction = LiveRecipeConstructionResult(
                classification=self.construction.classification,
                recipes=self.construction.recipes,
            )
            classified_count = len(construction.classification.eligible) + len(
                construction.classification.rejected
            )
            if self.snapshot_observation_count != classified_count:
                raise LivePoolRecipeConstructionError
            object.__setattr__(self, "construction", construction)
        except MemoryError:
            raise
        except Exception:
            raise LivePoolRecipeConstructionError from None


def construct_live_recipes_from_pool(
    *,
    pool: SteamApisOfferPool,
    catalog: SkinMetadataCatalog,
    solver_config: RecipeSolverConfig,
) -> LivePoolRecipeConstructionResult:
    """Construct recipes from one current post-TTL pool snapshot."""

    try:
        snapshot = pool.snapshot()
        if type(snapshot) is not SteamApisOfferPoolSnapshot:
            raise LivePoolRecipeConstructionError
        construction = construct_live_recipes(
            snapshot=snapshot,
            catalog=catalog,
            solver_config=solver_config,
        )
        return LivePoolRecipeConstructionResult(
            snapshot_observation_count=len(snapshot.observations),
            construction=construction,
        )
    except (MemoryError, asyncio.CancelledError):
        raise
    except Exception:
        raise LivePoolRecipeConstructionError from None
