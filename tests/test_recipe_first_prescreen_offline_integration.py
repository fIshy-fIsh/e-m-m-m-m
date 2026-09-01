"""Phase 16D — Offline recipe-first integration test."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.market_universe_builder import StatTrakMode
from app.services.metadata_models import SkinMetadata
from app.services.prescreen_price_book import PreScreenPriceBook
from app.services.recipe_family import build_recipe_family
from app.services.recipe_family_geometry import compute_recipe_family_geometry
from app.services.recipe_family_prescreen_economics import (
    RecipeFamilyPreScreenEconomicsConfig,
    compute_recipe_family_prescreen_economics,
)
from app.services.recipe_family_ranking import (
    RecipeFamilyPreScreenCandidate,
    rank_recipe_family_candidates,
)
from app.services.static_float_feasibility import (
    build_input_identity_float_evidence,
    compute_static_float_feasibility,
)
from app.services.steamdt_batch_prescreen import SteamDTBuffPreScreenQuote
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.targeted_buff_scan_plan import (
    build_targeted_buff_input_candidates,
    build_targeted_buff_scan_decision,
    build_targeted_buff_scan_plan,
)

ROOT = Path(__file__).resolve().parent.parent


def _load_pinned_skins() -> tuple[SkinMetadata, ...]:
    payload = json.loads(
        (ROOT / "data" / "metadata" / "skin_metadata_v1.json").read_bytes()
    )
    return tuple(
        SkinMetadata(
            market_hash_name=item["market_hash_name"],
            name=item.get("name"),
            weapon=item.get("weapon"),
            rarity=item["rarity"],
            category=item.get("category"),
            collection_name=item.get("collection_name"),
            min_float=item["min_float"],
            max_float=item["max_float"],
            stattrak=bool(item.get("stattrak", False)),
            souvenir=bool(item.get("souvenir", False)),
            paint_index=item.get("paint_index"),
            raw=None,
        )
        for item in payload["items"]
    )


def test_pinned_snapshot_offline_end_to_end_is_exact_and_deterministic() -> None:
    skins = _load_pinned_skins()
    identity = BuffCommunityIdentityResolver.from_snapshot_path(
        ROOT / "data" / "identity" / "buff_identity_v1.json"
    )
    finish_index = StructuralOutputFinishIndex.from_skins(skins)
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The Horizon Collection", 10),),
    )
    geometry = compute_recipe_family_geometry(family, finish_index=finish_index)
    static = compute_static_float_feasibility(
        family,
        skins=skins,
        identity_resolver=identity,
        finish_index=finish_index,
    )
    inputs = build_input_identity_float_evidence(
        skins=skins,
        identity_resolver=identity,
        input_rarity=family.input_rarity,
        stattrak_mode=family.stattrak_mode,
        represented_collections=tuple(
            name for name, _count in family.collection_counts
        ),
    )
    assert inputs
    output_names = tuple(
        sorted(
            {
                item.exact_market_hash_name
                for item in static.reachable_outputs
            }
        )
    )
    all_names = tuple(item.market_hash_name for item in inputs) + output_names
    # Entire market book is precomputed fake evidence: no client or provider exists.
    book = PreScreenPriceBook(
        quotes_by_name={
            name: SteamDTBuffPreScreenQuote(
                market_hash_name=name,
                sell_price_cny=Decimal(index + 1),
                sell_count=index % 17,
                update_time="opaque-fixture",
            )
            for index, name in enumerate(all_names)
        }
    )
    economics = compute_recipe_family_prescreen_economics(
        family,
        geometry=geometry,
        static_feasibility=static,
        input_evidence=inputs,
        price_book=book,
        config=RecipeFamilyPreScreenEconomicsConfig(
            sell_fee_rate=Decimal("0.025")
        ),
    )
    targeted_candidates = build_targeted_buff_input_candidates(
        family=family,
        input_evidence=inputs,
        price_book=book,
    )
    plan = build_targeted_buff_scan_plan(
        family,
        candidates=targeted_candidates,
        priority=1,
    )
    candidate = RecipeFamilyPreScreenCandidate(
        family=family,
        static_feasibility=static,
        economics=economics,
        targeted_plan=plan,
        batch_prescreen_succeeded=True,
    )
    ranking = rank_recipe_family_candidates(iter((candidate,)))
    decision = build_targeted_buff_scan_decision(
        ranking.ranked_family_keys,
        plans_by_family_key={family.family_key: plan},
    )

    assert len(economics) == 3
    assert ranking.ranked_family_keys == (family.family_key,)
    assert decision.active_plan is not None
    assert decision.active_plan.hard_request_count <= 10
    assert len(set(decision.active_plan.goods_ids)) == len(
        decision.active_plan.goods_ids
    )
    assert set(decision.active_plan.market_hash_names).issubset(
        {item.market_hash_name for item in inputs}
    )

    repeated_plan = build_targeted_buff_scan_plan(
        family,
        candidates=tuple(reversed(targeted_candidates)),
        priority=1,
    )
    assert repeated_plan.items == plan.items
