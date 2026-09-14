"""Pure rules that relate places, categories, boundaries and portfolio stores."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.domain.geo import BoundingBox, Coordinate, haversine_m
from app.models.entities import BoundaryStatus
from app.providers.base import DiscoveredPlace


@dataclass(frozen=True, slots=True)
class CategoryRule:
    category_id: int
    provider_types: frozenset[str]


def resolve_category(place: DiscoveredPlace, rules: Sequence[CategoryRule]) -> int | None:
    """Pick the selected category a place belongs to.

    The provider's primary type wins when it maps to a selected category. Otherwise the
    first matching rule in category order wins. A place matching no selected category is
    dropped, which is how "only discover the selected categories" is enforced even when a
    provider returns loosely related types.
    """
    if place.primary_type is not None:
        for rule in rules:
            if place.primary_type in rule.provider_types:
                return rule.category_id
    types = set(place.provider_types)
    for rule in rules:
        if types & rule.provider_types:
            return rule.category_id
    return None


def boundary_status(boundary: BoundingBox, lat: float | None, lng: float | None) -> BoundaryStatus:
    if lat is None or lng is None:
        return BoundaryStatus.UNLOCATED
    return (
        BoundaryStatus.INSIDE if boundary.contains(Coordinate(lat, lng)) else BoundaryStatus.OUTSIDE
    )


def city_matches(row_city: str, city_names: set[str]) -> bool:
    return row_city.strip().casefold() in city_names


@dataclass(frozen=True, slots=True)
class PointRef:
    id: int
    location: Coordinate


@dataclass(frozen=True, slots=True)
class Match:
    portfolio_id: int
    discovered_id: int
    distance_m: float


def match_nearby(
    portfolio: Iterable[PointRef], discovered: Iterable[PointRef], radius_m: float
) -> list[Match]:
    """For each portfolio point, the nearest discovered point within ``radius_m``.

    Discovered points are bucketed into a grid whose cells are at least ``radius_m`` on
    each side, so every candidate within range sits in one of the nine cells around a
    portfolio store and each lookup avoids scanning the whole market.
    """
    # One degree of latitude is never shorter than ~110.57 km, so dividing by 110 km
    # keeps cells slightly larger than the radius, which is the safe direction.
    cell_deg = radius_m / 110_000
    grid: dict[tuple[int, int], list[PointRef]] = defaultdict(list)

    def cell(c: Coordinate) -> tuple[int, int]:
        lng_scale = max(math.cos(math.radians(c.lat)), 1e-6)
        return (math.floor(c.lat / cell_deg), math.floor(c.lng * lng_scale / cell_deg))

    for point in discovered:
        grid[cell(point.location)].append(point)

    matches: list[Match] = []
    for store in portfolio:
        row, col = cell(store.location)
        best: Match | None = None
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                for candidate in grid.get((row + dr, col + dc), ()):
                    distance = haversine_m(store.location, candidate.location)
                    if distance <= radius_m and (best is None or distance < best.distance_m):
                        best = Match(store.id, candidate.id, distance)
        if best is not None:
            matches.append(best)
    return matches
