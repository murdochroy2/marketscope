"""Offline providers backed by captured real responses.

Used by the test suite, and selectable at runtime (PLACES_PROVIDER=fixture,
GEOCODER=fixture) for a demo that needs no network. They implement the same protocols
as the live providers, so the orchestration code under test is the production code.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from app.domain.geo import BoundingBox, Coordinate
from app.providers.base import GeocodeQuery, TileResult, TilingStrategy
from app.providers.http import RequestBudget
from app.providers.nominatim import address_candidates
from app.providers.overpass import parse_element

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"


@cache
def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def _element_point(element: dict) -> Coordinate:
    if "lat" in element:
        return Coordinate(element["lat"], element["lon"])
    return Coordinate(element["center"]["lat"], element["center"]["lon"])


class FixturePlacesProvider:
    name = "fixture"
    tiling = TilingStrategy(initial_max_side_km=2.5)

    def __init__(self, fixture: str = "overpass_bengaluru.json") -> None:
        self._elements = _load(fixture)["elements"]

    async def search_tile(
        self, tile: BoundingBox, provider_types: list[str], budget: RequestBudget
    ) -> TileResult:
        budget.spend()
        wanted = set(provider_types)
        places = []
        for element in self._elements:
            if not tile.contains(_element_point(element)):
                continue
            if (place := parse_element(element, wanted)) is not None:
                places.append(place)
        return TileResult(places=places)


class FixtureGeocoder:
    name = "fixture"

    def __init__(self, fixture: str = "geocoding.json") -> None:
        data = _load(fixture)
        self._addresses = data["addresses"]
        self._cities = data["cities"]

    async def geocode(self, query: GeocodeQuery) -> Coordinate | None:
        for candidate in address_candidates(query):
            if (hit := self._addresses.get(candidate.casefold())) is not None:
                return Coordinate(hit["lat"], hit["lng"])
        return None

    async def city_boundary(self, city: str, state: str, country: str) -> BoundingBox | None:
        hit = self._cities.get(f"{city}|{state}|{country}".casefold())
        return BoundingBox(**hit) if hit else None
