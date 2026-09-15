import math
import random

import pytest

from app.domain.geo import BoundingBox, Coordinate, haversine_m
from app.models import BoundaryStatus
from app.providers.base import DiscoveredPlace
from app.services.classification import (
    CategoryRule,
    PointRef,
    boundary_status,
    city_matches,
    match_nearby,
    resolve_category,
)

SUPERMARKET, GROCERY_STORE, PHARMACY = 1, 2, 4
RULES = [
    CategoryRule(SUPERMARKET, frozenset({"supermarket"})),
    CategoryRule(GROCERY_STORE, frozenset({"grocery_store"})),
    CategoryRule(PHARMACY, frozenset({"pharmacy", "drugstore"})),
]


def gplace(types, primary=None):
    return DiscoveredPlace("id", "n", Coordinate(12.9, 77.6), tuple(types), primary)


def test_primary_type_decides_between_overlapping_categories():
    assert (
        resolve_category(gplace(["supermarket", "grocery_store"], "grocery_store"), RULES)
        == GROCERY_STORE
    )


def test_falls_back_to_first_matching_category_in_order():
    assert (
        resolve_category(gplace(["store", "grocery_store", "supermarket"], "store"), RULES)
        == SUPERMARKET
    )


def test_place_outside_selected_categories_is_dropped():
    only_pharmacy = [RULES[2]]
    assert resolve_category(gplace(["supermarket"], "supermarket"), only_pharmacy) is None


def test_boundary_status():
    box = BoundingBox(12.90, 77.60, 12.96, 77.65)
    assert boundary_status(box, 12.93, 77.62) is BoundaryStatus.INSIDE
    assert boundary_status(box, 12.97, 77.62) is BoundaryStatus.OUTSIDE
    assert boundary_status(box, None, None) is BoundaryStatus.UNLOCATED


def test_city_matching_uses_aliases_case_insensitively():
    names = {"bengaluru", "bangalore"}
    assert city_matches(" Bangalore ", names)
    assert not city_matches("Mumbai", names)


def offset(origin: Coordinate, north_m: float) -> Coordinate:
    return Coordinate(origin.lat + north_m / 111_195, origin.lng)


@pytest.mark.parametrize(("distance_m", "matched"), [(0, True), (149, True), (151, False)])
def test_match_radius_boundary(distance_m, matched):
    home = Coordinate(12.9352, 77.6245)
    result = match_nearby(
        [PointRef(1, home)], [PointRef(9, offset(home, distance_m))], radius_m=150
    )
    assert bool(result) is matched


@pytest.mark.parametrize(
    "origin",
    [
        Coordinate(12.9352, 77.6245),  # Bengaluru
        Coordinate(28.6139, 77.2090),  # New Delhi
        Coordinate(-33.8688, 151.2093),  # Sydney: large longitude magnifies column drift
        Coordinate(60.0, 170.0),
    ],
)
def test_grid_index_agrees_with_brute_force_near_the_radius(origin):
    """Pairs 140-150 m apart in every direction must all match, as a full scan would."""
    rng = random.Random(7)
    misses = 0
    for _ in range(2000):
        home = Coordinate(
            origin.lat + rng.uniform(-0.05, 0.05), origin.lng + rng.uniform(-0.05, 0.05)
        )
        bearing = rng.uniform(0, 2 * math.pi)
        distance = rng.uniform(140, 149.9)
        candidate = Coordinate(
            home.lat + distance * math.cos(bearing) / 111_195,
            home.lng + distance * math.sin(bearing) / (111_195 * math.cos(math.radians(home.lat))),
        )
        if haversine_m(home, candidate) > 150:
            continue
        if not match_nearby([PointRef(1, home)], [PointRef(2, candidate)], radius_m=150):
            misses += 1
    assert misses == 0


def test_nearest_candidate_wins():
    home = Coordinate(12.9352, 77.6245)
    result = match_nearby(
        [PointRef(1, home)],
        [
            PointRef(10, offset(home, 120)),
            PointRef(11, offset(home, 40)),
            PointRef(12, offset(home, 90)),
        ],
        radius_m=150,
    )
    assert [(m.discovered_id, round(m.distance_m)) for m in result] == [(11, 40)]
