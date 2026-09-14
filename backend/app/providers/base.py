"""Provider contracts. Services depend on these protocols, never on a concrete API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.domain.geo import BoundingBox, Coordinate
from app.providers.http import RequestBudget


@dataclass(frozen=True, slots=True)
class DiscoveredPlace:
    provider_place_id: str
    name: str
    location: Coordinate
    provider_types: tuple[str, ...]
    primary_type: str | None = None
    address: str | None = None


@dataclass(frozen=True, slots=True)
class TileResult:
    places: list[DiscoveredPlace]
    # True when the provider hit its per-request result cap, meaning the tile may hold
    # more places than were returned and should be subdivided.
    saturated: bool = False


@dataclass(frozen=True, slots=True)
class TilingStrategy:
    initial_max_side_km: float
    # Smallest tile the orchestrator may subdivide down to when a tile is saturated.
    min_side_km: float = field(default=0.15)


class PlacesProvider(Protocol):
    name: str
    tiling: TilingStrategy

    async def search_tile(
        self, tile: BoundingBox, provider_types: list[str], budget: RequestBudget
    ) -> TileResult: ...


@dataclass(frozen=True, slots=True)
class GeocodeQuery:
    address: str
    city: str
    state: str
    country: str


class Geocoder(Protocol):
    name: str

    async def geocode(self, query: GeocodeQuery) -> Coordinate | None: ...

    async def city_boundary(self, city: str, state: str, country: str) -> BoundingBox | None: ...
