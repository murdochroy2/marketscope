"""Pure geographic primitives. No I/O lives here, so everything is unit-testable.

Coordinates are always carried as named ``lat``/``lng`` fields. Conversion to
provider-specific orderings (GeoJSON ``[lng, lat]``, Nominatim's
``[south, north, west, east]``) happens at the edges, never in this module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0088
EARTH_RADIUS_M = EARTH_RADIUS_KM * 1000


class InvalidBoundaryError(ValueError):
    """Raised when a bounding box is geometrically invalid."""


@dataclass(frozen=True, slots=True)
class Coordinate:
    lat: float
    lng: float

    def __post_init__(self) -> None:
        if not -90 <= self.lat <= 90:
            raise ValueError(f"latitude {self.lat} is outside -90..90")
        if not -180 <= self.lng <= 180:
            raise ValueError(f"longitude {self.lng} is outside -180..180")


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """An axis-aligned lat/lng rectangle. Antimeridian-crossing boxes are not supported."""

    south: float
    west: float
    north: float
    east: float

    def __post_init__(self) -> None:
        if not (-90 <= self.south <= 90 and -90 <= self.north <= 90):
            raise InvalidBoundaryError("latitudes must be within -90..90")
        if not (-180 <= self.west <= 180 and -180 <= self.east <= 180):
            raise InvalidBoundaryError("longitudes must be within -180..180")
        if self.south >= self.north:
            raise InvalidBoundaryError("south must be less than north")
        if self.west >= self.east:
            raise InvalidBoundaryError("west must be less than east")

    @classmethod
    def around(cls, center: Coordinate, width_km: float, height_km: float) -> BoundingBox:
        """A box of the given ground dimensions centred on a point."""
        half_lat = math.degrees(height_km / 2 / EARTH_RADIUS_KM)
        half_lng = math.degrees(
            width_km / 2 / (EARTH_RADIUS_KM * math.cos(math.radians(center.lat)))
        )
        return cls(
            south=center.lat - half_lat,
            west=center.lng - half_lng,
            north=center.lat + half_lat,
            east=center.lng + half_lng,
        )

    @property
    def center(self) -> Coordinate:
        return Coordinate(lat=(self.south + self.north) / 2, lng=(self.west + self.east) / 2)

    def area_sq_km(self) -> float:
        """Exact area of the lat/lng band on a spherical Earth.

        A = R² · Δλ · (sin φ₂ − sin φ₁). The frontend uses the same formula, so the
        live readout and the server-side cap check always agree.
        """
        d_lng = math.radians(self.east - self.west)
        return (
            EARTH_RADIUS_KM**2
            * d_lng
            * (math.sin(math.radians(self.north)) - math.sin(math.radians(self.south)))
        )

    def width_km(self) -> float:
        return (
            haversine_m(
                Coordinate(self.center.lat, self.west), Coordinate(self.center.lat, self.east)
            )
            / 1000
        )

    def height_km(self) -> float:
        return (
            haversine_m(
                Coordinate(self.south, self.center.lng), Coordinate(self.north, self.center.lng)
            )
            / 1000
        )

    def contains(self, point: Coordinate) -> bool:
        """Edges are inclusive: a store exactly on the boundary line belongs to the market."""
        return self.south <= point.lat <= self.north and self.west <= point.lng <= self.east

    def contains_point(self, lat: float, lng: float) -> bool:
        return self.contains(Coordinate(lat, lng))

    def circumscribed_radius_m(self) -> float:
        """Radius of the smallest circle centred on the box that covers all four corners."""
        return haversine_m(self.center, Coordinate(self.north, self.east))

    def quadrants(self) -> list[BoundingBox]:
        c = self.center
        return [
            BoundingBox(self.south, self.west, c.lat, c.lng),
            BoundingBox(self.south, c.lng, c.lat, self.east),
            BoundingBox(c.lat, self.west, self.north, c.lng),
            BoundingBox(c.lat, c.lng, self.north, self.east),
        ]

    def tiles(self, max_side_km: float) -> list[BoundingBox]:
        """Split into a regular grid whose cells are no larger than ``max_side_km`` per side."""
        if max_side_km <= 0:
            raise ValueError("max_side_km must be positive")
        rows = max(1, math.ceil(self.height_km() / max_side_km))
        cols = max(1, math.ceil(self.width_km() / max_side_km))
        d_lat = (self.north - self.south) / rows
        d_lng = (self.east - self.west) / cols
        grid: list[BoundingBox] = []
        for r in range(rows):
            for c in range(cols):
                grid.append(
                    BoundingBox(
                        south=self.south + r * d_lat,
                        west=self.west + c * d_lng,
                        # Pin the outer edges to the original values to avoid float drift.
                        north=self.north if r == rows - 1 else self.south + (r + 1) * d_lat,
                        east=self.east if c == cols - 1 else self.west + (c + 1) * d_lng,
                    )
                )
        return grid

    def clamp_within(self, outer: BoundingBox) -> BoundingBox:
        """Shift this box so it sits inside ``outer`` where possible, keeping its size."""
        lat_span = self.north - self.south
        lng_span = self.east - self.west
        south = min(max(self.south, outer.south), max(outer.north - lat_span, outer.south))
        west = min(max(self.west, outer.west), max(outer.east - lng_span, outer.west))
        return BoundingBox(south, west, south + lat_span, west + lng_span)


def haversine_m(a: Coordinate, b: Coordinate) -> float:
    """Great-circle distance in metres."""
    phi1, phi2 = math.radians(a.lat), math.radians(b.lat)
    d_phi = phi2 - phi1
    d_lambda = math.radians(b.lng - a.lng)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def suggest_boundary(city: BoundingBox, target_area_sq_km: float) -> BoundingBox:
    """A square-ish starting rectangle at the city's centre that satisfies the area cap.

    The geocoded extent of most cities is far larger than the cap, so presenting it
    unchanged would leave "Create Market" disabled on first load.
    """
    if city.area_sq_km() <= target_area_sq_km:
        return city
    side_km = math.sqrt(target_area_sq_km)
    return BoundingBox.around(city.center, side_km, side_km).clamp_within(city)
