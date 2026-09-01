"""Phase 16D — Deterministic bounded targeted BUFF scan planning.

The planner is pure. It selects exact identity-resolved, strictly quoted input
names and at most ten distinct goods IDs. It never issues a BUFF request and
never pads a family with unrelated collections.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from app.services.float_interval import FloatIntervalUnion
from app.services.market_universe_builder import StatTrakMode
from app.services.prescreen_price_book import PreScreenPriceBook
from app.services.recipe_family import RecipeFamily
from app.services.static_float_feasibility import InputIdentityFloatEvidence

__all__ = (
    "MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN",
    "TargetedBuffInputCandidate",
    "TargetedBuffScanDecision",
    "TargetedBuffScanItem",
    "TargetedBuffScanPlan",
    "TargetedBuffScanPlanError",
    "build_targeted_buff_input_candidates",
    "build_targeted_buff_scan_decision",
    "build_targeted_buff_scan_plan",
)

MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN: Final[int] = 10
_COLLECTION_ROLES: Final[tuple[str, ...]] = (
    "primary",
    "secondary",
    "tertiary",
)


class TargetedBuffScanPlanError(ValueError):
    """Targeted planning evidence violated an exact identity or cap rule."""


def _exact(value: object, *, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise TargetedBuffScanPlanError(
            f"{field} must be an exact non-empty string"
        )
    return value


def _family_hash(value: object) -> str:
    exact = _exact(value, field="family_hash")
    if len(exact) != 64 or any(ch not in "0123456789abcdef" for ch in exact):
        raise TargetedBuffScanPlanError(
            "family_hash must be full lowercase SHA-256 hex"
        )
    return exact


@dataclass(frozen=True, kw_only=True, repr=False)
class TargetedBuffInputCandidate:
    market_hash_name: str
    goods_id: str
    collection_name: str
    adjusted_intervals: FloatIntervalUnion
    sell_price_cny: Decimal
    sell_count: int | None
    stattrak: bool
    souvenir: bool

    def __post_init__(self) -> None:
        _exact(self.market_hash_name, field="market_hash_name")
        _exact(self.goods_id, field="goods_id")
        _exact(self.collection_name, field="collection_name")
        if (
            type(self.adjusted_intervals) is not FloatIntervalUnion
            or self.adjusted_intervals.is_empty
        ):
            raise TargetedBuffScanPlanError(
                "adjusted_intervals must be non-empty FloatIntervalUnion"
            )
        if (
            type(self.sell_price_cny) is not Decimal
            or not self.sell_price_cny.is_finite()
            or self.sell_price_cny <= 0
        ):
            raise TargetedBuffScanPlanError(
                "sell_price_cny must be positive finite Decimal"
            )
        if self.sell_count is not None and (
            type(self.sell_count) is not int or self.sell_count < 0
        ):
            raise TargetedBuffScanPlanError("sell_count is invalid")
        if type(self.stattrak) is not bool or type(self.souvenir) is not bool:
            raise TargetedBuffScanPlanError(
                "stattrak and souvenir must be booleans"
            )

    @property
    def adjusted_lower_bound(self) -> float:
        return self.adjusted_intervals.intervals[0].lower


def _candidate_sort_key(
    candidate: TargetedBuffInputCandidate,
) -> tuple[Decimal, float, int, int, str, str]:
    return (
        candidate.sell_price_cny,
        candidate.adjusted_lower_bound,
        candidate.sell_count is None,
        -(candidate.sell_count or 0),
        candidate.market_hash_name,
        candidate.goods_id,
    )


def build_targeted_buff_input_candidates(
    *,
    family: RecipeFamily,
    input_evidence: tuple[InputIdentityFloatEvidence, ...],
    price_book: PreScreenPriceBook,
) -> tuple[TargetedBuffInputCandidate, ...]:
    """Compose exact input identity-float evidence with strict BUFF quotes."""

    if type(family) is not RecipeFamily:
        raise TargetedBuffScanPlanError("family must be RecipeFamily")
    if type(price_book) is not PreScreenPriceBook:
        raise TargetedBuffScanPlanError("price_book must be PreScreenPriceBook")
    if type(input_evidence) is not tuple or any(
        type(item) is not InputIdentityFloatEvidence for item in input_evidence
    ):
        raise TargetedBuffScanPlanError(
            "input_evidence must contain exact InputIdentityFloatEvidence"
        )
    represented = {name for name, _count in family.collection_counts}
    expected_stattrak = family.stattrak_mode is StatTrakMode.STATTRAK
    seen_names: set[str] = set()
    candidates: list[TargetedBuffInputCandidate] = []
    for item in input_evidence:
        if item.market_hash_name in seen_names:
            raise TargetedBuffScanPlanError("duplicate exact input evidence name")
        seen_names.add(item.market_hash_name)
        if item.collection_name not in represented:
            continue
        if item.input_rarity != family.input_rarity:
            raise TargetedBuffScanPlanError(
                "input evidence rarity does not match family"
            )
        if item.stattrak is not expected_stattrak:
            raise TargetedBuffScanPlanError(
                "input evidence StatTrak mode does not match family"
            )
        quote = price_book.quote_for(item.market_hash_name)
        if quote is None:
            continue
        candidates.append(
            TargetedBuffInputCandidate(
                market_hash_name=item.market_hash_name,
                goods_id=item.goods_id,
                collection_name=item.collection_name,
                adjusted_intervals=item.adjusted_intervals,
                sell_price_cny=quote.sell_price_cny,
                sell_count=quote.sell_count,
                stattrak=item.stattrak,
                souvenir=item.souvenir,
            )
        )
    candidates.sort(key=lambda item: (item.collection_name, _candidate_sort_key(item)))
    return tuple(candidates)


@dataclass(frozen=True, kw_only=True, repr=False)
class TargetedBuffScanItem:
    market_hash_name: str
    goods_id: str
    collection_name: str
    collection_role: str
    priority_within_collection: int

    def __post_init__(self) -> None:
        _exact(self.market_hash_name, field="market_hash_name")
        _exact(self.goods_id, field="goods_id")
        _exact(self.collection_name, field="collection_name")
        if self.collection_role not in _COLLECTION_ROLES:
            raise TargetedBuffScanPlanError("unsupported collection_role")
        if (
            type(self.priority_within_collection) is not int
            or self.priority_within_collection < 1
        ):
            raise TargetedBuffScanPlanError(
                "priority_within_collection must be positive int"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class TargetedBuffScanPlan:
    family_hash: str
    items: tuple[TargetedBuffScanItem, ...]
    stattrak_mode: StatTrakMode
    priority: int
    hard_request_count: int
    unresolved_identity_count: int
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        _family_hash(self.family_hash)
        if type(self.items) is not tuple or any(
            type(item) is not TargetedBuffScanItem for item in self.items
        ):
            raise TargetedBuffScanPlanError(
                "items must contain exact TargetedBuffScanItem values"
            )
        if type(self.stattrak_mode) is not StatTrakMode:
            raise TargetedBuffScanPlanError("invalid stattrak_mode")
        if type(self.priority) is not int or self.priority < 1:
            raise TargetedBuffScanPlanError("priority must be positive int")
        if self.hard_request_count != len(self.items):
            raise TargetedBuffScanPlanError(
                "hard_request_count must equal item count"
            )
        if self.hard_request_count > MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN:
            raise TargetedBuffScanPlanError("targeted request cap exceeded")
        if (
            type(self.unresolved_identity_count) is not int
            or self.unresolved_identity_count < 0
        ):
            raise TargetedBuffScanPlanError(
                "unresolved_identity_count must be non-negative int"
            )
        if self.unresolved_identity_count != 0:
            raise TargetedBuffScanPlanError(
                "a buildable targeted plan cannot contain unresolved identity"
            )
        if type(self.diagnostics) is not tuple or any(
            type(value) is not str or not value for value in self.diagnostics
        ):
            raise TargetedBuffScanPlanError(
                "diagnostics must be tuple[non-empty str, ...]"
            )
        names = tuple(item.market_hash_name for item in self.items)
        goods_ids = tuple(item.goods_id for item in self.items)
        if len(set(names)) != len(names):
            raise TargetedBuffScanPlanError(
                "targeted plan contains duplicate exact market_hash_name"
            )
        if len(set(goods_ids)) != len(goods_ids):
            raise TargetedBuffScanPlanError(
                "targeted plan contains duplicate goods_id"
            )

    @property
    def market_hash_names(self) -> tuple[str, ...]:
        return tuple(item.market_hash_name for item in self.items)

    @property
    def goods_ids(self) -> tuple[str, ...]:
        return tuple(item.goods_id for item in self.items)


@dataclass(frozen=True, kw_only=True, repr=False)
class TargetedBuffScanDecision:
    ranked_family_keys: tuple[str, ...]
    active_family_key: str | None
    active_plan: TargetedBuffScanPlan | None
    fallback_family_key: str | None
    hard_request_cap: int
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.ranked_family_keys) is not tuple or len(
            self.ranked_family_keys
        ) > 2:
            raise TargetedBuffScanPlanError(
                "ranked_family_keys must be an exact tuple of at most two keys"
            )
        for key in self.ranked_family_keys:
            _exact(key, field="ranked_family_key")
        if len(set(self.ranked_family_keys)) != len(self.ranked_family_keys):
            raise TargetedBuffScanPlanError("ranked family keys must be unique")
        if self.active_family_key is not None:
            _exact(self.active_family_key, field="active_family_key")
        if self.fallback_family_key is not None:
            _exact(self.fallback_family_key, field="fallback_family_key")
            if self.fallback_family_key not in self.ranked_family_keys:
                raise TargetedBuffScanPlanError(
                    "fallback key must be one of ranked family keys"
                )
        if self.active_plan is not None:
            if type(self.active_plan) is not TargetedBuffScanPlan:
                raise TargetedBuffScanPlanError("invalid active_plan")
            if self.active_family_key != self.active_plan.family_hash[:24]:
                raise TargetedBuffScanPlanError(
                    "active key must match active plan family hash"
                )
            if self.active_family_key not in self.ranked_family_keys:
                raise TargetedBuffScanPlanError(
                    "active key must be one of ranked family keys"
                )
            if self.active_plan.hard_request_count > self.hard_request_cap:
                raise TargetedBuffScanPlanError(
                    "active plan exceeds decision hard request cap"
                )
        elif self.active_family_key is not None:
            raise TargetedBuffScanPlanError(
                "active_family_key requires active_plan"
            )
        if (
            self.active_family_key is not None
            and self.active_family_key == self.fallback_family_key
        ):
            raise TargetedBuffScanPlanError(
                "active and fallback family keys must differ"
            )
        if self.hard_request_cap != MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN:
            raise TargetedBuffScanPlanError(
                "hard_request_cap must equal frozen project bound"
            )
        if type(self.diagnostics) is not tuple or any(
            type(value) is not str or not value for value in self.diagnostics
        ):
            raise TargetedBuffScanPlanError(
                "diagnostics must be tuple[non-empty str, ...]"
            )


def build_targeted_buff_scan_plan(
    family: RecipeFamily,
    *,
    candidates: tuple[TargetedBuffInputCandidate, ...],
    priority: int,
) -> TargetedBuffScanPlan:
    """Allocate at most ten exact goods-page requests for one family."""

    if type(family) is not RecipeFamily:
        raise TargetedBuffScanPlanError("family must be RecipeFamily")
    if type(candidates) is not tuple or any(
        type(item) is not TargetedBuffInputCandidate for item in candidates
    ):
        raise TargetedBuffScanPlanError(
            "candidates must contain exact TargetedBuffInputCandidate values"
        )
    if type(priority) is not int or priority < 1:
        raise TargetedBuffScanPlanError("priority must be positive int")

    represented = {name for name, _count in family.collection_counts}
    expected_stattrak = family.stattrak_mode is StatTrakMode.STATTRAK
    seen_names: set[str] = set()
    goods_to_name: dict[str, str] = {}
    by_collection: dict[str, list[TargetedBuffInputCandidate]] = {
        name: [] for name in represented
    }
    for candidate in candidates:
        if candidate.collection_name not in represented:
            raise TargetedBuffScanPlanError(
                "targeted candidate belongs to unrelated collection"
            )
        if candidate.stattrak is not expected_stattrak:
            raise TargetedBuffScanPlanError(
                "targeted candidate StatTrak mode does not match family"
            )
        if candidate.market_hash_name in seen_names:
            raise TargetedBuffScanPlanError(
                "duplicate candidate market_hash_name collision"
            )
        seen_names.add(candidate.market_hash_name)
        existing_name = goods_to_name.get(candidate.goods_id)
        if existing_name is not None:
            raise TargetedBuffScanPlanError(
                "duplicate candidate goods_id collision"
            )
        goods_to_name[candidate.goods_id] = candidate.market_hash_name
        by_collection[candidate.collection_name].append(candidate)

    roles = tuple(
        sorted(family.collection_counts, key=lambda entry: (-entry[1], entry[0]))
    )
    role_by_collection = {
        name: _COLLECTION_ROLES[index]
        for index, (name, _count) in enumerate(roles)
    }
    for name in by_collection:
        by_collection[name].sort(key=_candidate_sort_key)
        if not by_collection[name]:
            raise TargetedBuffScanPlanError(
                f"represented collection has zero candidates: {name}"
            )

    selected: dict[str, list[TargetedBuffInputCandidate]] = {
        name: [] for name in represented
    }
    selected_names: set[str] = set()
    selected_goods: set[str] = set()
    target_by_collection = dict(family.collection_counts)
    for collection_name, _count in roles:
        target = target_by_collection[collection_name]
        for candidate in by_collection[collection_name][:target]:
            selected[collection_name].append(candidate)
            selected_names.add(candidate.market_hash_name)
            selected_goods.add(candidate.goods_id)

    remaining_slots = MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN - sum(
        len(values) for values in selected.values()
    )
    for collection_name, _count in roles:
        for candidate in by_collection[collection_name]:
            if remaining_slots == 0:
                break
            if (
                candidate.market_hash_name in selected_names
                or candidate.goods_id in selected_goods
            ):
                continue
            selected[collection_name].append(candidate)
            selected_names.add(candidate.market_hash_name)
            selected_goods.add(candidate.goods_id)
            remaining_slots -= 1
        if remaining_slots == 0:
            break

    items: list[TargetedBuffScanItem] = []
    for collection_name, _count in roles:
        for within, candidate in enumerate(selected[collection_name], start=1):
            items.append(
                TargetedBuffScanItem(
                    market_hash_name=candidate.market_hash_name,
                    goods_id=candidate.goods_id,
                    collection_name=collection_name,
                    collection_role=role_by_collection[collection_name],
                    priority_within_collection=within,
                )
            )
    if not items:
        raise TargetedBuffScanPlanError("targeted plan would be empty")
    return TargetedBuffScanPlan(
        family_hash=family.family_hash,
        items=tuple(items),
        stattrak_mode=family.stattrak_mode,
        priority=priority,
        hard_request_count=len(items),
        unresolved_identity_count=0,
        diagnostics=(
            "exact_identity_only",
            "offline_plan_no_http",
            "live_quantity_and_executability_unproven",
        ),
    )


def build_targeted_buff_scan_decision(
    ranked_family_keys: tuple[str, ...],
    *,
    plans_by_family_key: dict[str, TargetedBuffScanPlan | None],
) -> TargetedBuffScanDecision:
    """Choose exactly one offline-valid active plan from ranked Top-2."""

    if type(ranked_family_keys) is not tuple or len(ranked_family_keys) > 2:
        raise TargetedBuffScanPlanError(
            "ranked_family_keys must be tuple of at most two keys"
        )
    if len(set(ranked_family_keys)) != len(ranked_family_keys):
        raise TargetedBuffScanPlanError("ranked_family_keys must be unique")
    for key in ranked_family_keys:
        _exact(key, field="ranked family key")
    if type(plans_by_family_key) is not dict:
        raise TargetedBuffScanPlanError("plans_by_family_key must be dict")

    active_key: str | None = None
    active_plan: TargetedBuffScanPlan | None = None
    active_index: int | None = None
    diagnostics: list[str] = []
    for index, key in enumerate(ranked_family_keys):
        plan = plans_by_family_key.get(key)
        if plan is None:
            diagnostics.append(f"plan_unbuildable:{key}")
            continue
        if type(plan) is not TargetedBuffScanPlan:
            raise TargetedBuffScanPlanError("invalid plan mapping value")
        if plan.family_hash[:24] != key:
            raise TargetedBuffScanPlanError("plan family key mismatch")
        active_key = key
        active_plan = plan
        active_index = index
        break

    fallback_key: str | None = None
    if active_index == 0 and len(ranked_family_keys) == 2:
        fallback_key = ranked_family_keys[1]
    diagnostics.append("fallback_allowed_only_before_first_buff_request")
    return TargetedBuffScanDecision(
        ranked_family_keys=ranked_family_keys,
        active_family_key=active_key,
        active_plan=active_plan,
        fallback_family_key=fallback_key,
        hard_request_cap=MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN,
        diagnostics=tuple(diagnostics),
    )
