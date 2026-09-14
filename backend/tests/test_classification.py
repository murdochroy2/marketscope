import pytest

from app.domain.geo import BoundingBox, Coordinate
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

SUPERMARKET, HYPERMARKET, PHARMACY = 1, 2, 5
RULES = [
    CategoryRule(SUPERMARKET, frozenset({"supermarket"})),
    CategoryRule(HYPERMARKET, frozenset({"warehouse_store", "wholesaler"})),
    CategoryRule(PHARMACY, frozenset({"pharmacy", "drugstore"})),
]


def gplace(types, primary=None):
    return DiscoveredPlace("id", "n", Coordinate(12.9, 77.6), tuple(types), primary)


def test_primary_type_decides_between_overlapping_categories():
    assert (
        resolve_category(gplace(["supermarket", "warehouse_store"], "warehouse_store"), RULES)
        == HYPERMARKET
    )


def test_falls_back_to_first_matching_category_in_order():
    assert (
        resolve_category(gplace(["store", "warehouse_store", "supermarket"], "store"), RULES)
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
