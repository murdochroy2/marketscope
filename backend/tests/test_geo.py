import math

import pytest

from app.domain.geo import (
    BoundingBox,
    Coordinate,
    InvalidBoundaryError,
    haversine_m,
    suggest_boundary,
)

BENGALURU = BoundingBox(south=12.8334905, west=77.4598797, north=13.1426196, east=77.7840639)


def test_area_of_one_degree_cell_at_equator():
    # R² · Δλ · (sin 1° − sin 0°) ≈ 12,364 km²
    box = BoundingBox(south=0, west=0, north=1, east=1)
    assert box.area_sq_km() == pytest.approx(12_364, rel=1e-3)


def test_area_of_bengaluru_city_extent_is_far_over_the_cap():
    assert BENGALURU.area_sq_km() == pytest.approx(1207.4, abs=0.5)


def test_area_matches_ground_dimensions_at_bengaluru_latitude():
    box = BoundingBox.around(Coordinate(12.97, 77.59), width_km=5, height_km=6)
    assert box.area_sq_km() == pytest.approx(30, rel=1e-3)
    assert box.width_km() == pytest.approx(5, rel=1e-3)
    assert box.height_km() == pytest.approx(6, rel=1e-3)


@pytest.mark.parametrize(
    ("lat", "lng", "inside"),
    [
        (12.94, 77.62, True),
        (12.90, 77.62, True),  # on the south edge: edges are inclusive
        (12.96, 77.65, True),  # north-east corner
        (12.8999, 77.62, False),
        (12.94, 77.6501, False),
    ],
)
def test_contains_treats_edges_as_inside(lat, lng, inside):
    box = BoundingBox(south=12.90, west=77.60, north=12.96, east=77.65)
    assert box.contains(Coordinate(lat, lng)) is inside


@pytest.mark.parametrize(
    "bounds",
    [
        (12.9, 77.6, 12.9, 77.7),  # zero height
        (13.0, 77.6, 12.9, 77.7),  # south above north
        (12.9, 77.7, 13.0, 77.6),  # west east of east
        (-91, 0, 0, 1),
    ],
)
def test_invalid_boxes_are_rejected(bounds):
    with pytest.raises(InvalidBoundaryError):
        BoundingBox(*bounds)


def test_tiles_cover_the_box_exactly_and_respect_max_side():
    box = BoundingBox.around(Coordinate(12.97, 77.59), width_km=5.4, height_km=5.4)
    tiles = box.tiles(max_side_km=2.5)
    assert len(tiles) == 9
    assert all(t.width_km() <= 2.5 + 1e-9 and t.height_km() <= 2.5 + 1e-9 for t in tiles)
    assert sum(t.area_sq_km() for t in tiles) == pytest.approx(box.area_sq_km(), rel=1e-9)
    assert min(t.south for t in tiles) == box.south
    assert max(t.east for t in tiles) == box.east


def test_quadrants_partition_the_box():
    box = BoundingBox(12.9, 77.6, 13.0, 77.7)
    quads = box.quadrants()
    assert sum(q.area_sq_km() for q in quads) == pytest.approx(box.area_sq_km())


def test_circumscribed_radius_reaches_the_corners():
    box = BoundingBox.around(Coordinate(12.97, 77.59), 1, 1)
    assert box.circumscribed_radius_m() == pytest.approx(math.sqrt(2) * 500, rel=0.01)


def test_haversine_known_distance():
    # 0.001° of latitude is ~110.6 m anywhere on Earth.
    assert haversine_m(Coordinate(12.97, 77.59), Coordinate(12.971, 77.59)) == pytest.approx(
        111.2, abs=0.5
    )


def test_suggested_boundary_is_under_cap_and_inside_city():
    suggested = suggest_boundary(BENGALURU, target_area_sq_km=24)
    assert suggested.area_sq_km() == pytest.approx(24, rel=1e-3)
    assert BENGALURU.contains(Coordinate(suggested.south, suggested.west))
    assert BENGALURU.contains(Coordinate(suggested.north, suggested.east))


def test_suggested_boundary_keeps_small_cities_unchanged():
    small = BoundingBox.around(Coordinate(12.97, 77.59), 3, 3)
    assert suggest_boundary(small, target_area_sq_km=24) == small
