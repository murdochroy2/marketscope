"""Geocoding and city extents through OpenStreetMap Nominatim.

Usage policy: at most one request per second, an identifying User-Agent, and no bulk
geocoding. The client is built with a 1.1 s rate limiter, city extents are cached in
the database, and only portfolio rows that need it are ever sent.
"""

from __future__ import annotations

from typing import Any

from app.domain.geo import BoundingBox, Coordinate, InvalidBoundaryError
from app.providers.base import GeocodeQuery
from app.providers.http import ResilientHttpClient


def parse_nominatim_bbox(raw: list[str]) -> BoundingBox:
    """Nominatim returns ``boundingbox`` as ``[south, north, west, east]``, as strings."""
    south, north, west, east = (float(v) for v in raw)
    return BoundingBox(south=south, west=west, north=north, east=east)


def address_candidates(query: GeocodeQuery) -> list[str]:
    """Progressively less specific free-text queries.

    Portfolio addresses are often landmarks ("80 Feet Road, Koramangala 4th Block") that
    Nominatim cannot resolve whole but can resolve once the leading part is dropped.
    """
    parts = [p.strip() for p in query.address.split(",") if p.strip()]
    locality = ", ".join(p for p in (query.city, query.state, query.country) if p)
    candidates = [", ".join([*parts[i:], locality]) for i in range(len(parts))]
    seen: set[str] = set()
    return [c for c in candidates if not (c in seen or seen.add(c))]


class NominatimGeocoder:
    name = "nominatim"

    def __init__(self, http: ResilientHttpClient, base_url: str) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    async def _search(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        return await self._http.request_json(
            "GET", f"{self._base_url}/search", params={"format": "jsonv2", "limit": 1, **params}
        )

    async def geocode(self, query: GeocodeQuery) -> Coordinate | None:
        for text in address_candidates(query):
            results = await self._search({"q": text})
            if results:
                return Coordinate(lat=float(results[0]["lat"]), lng=float(results[0]["lon"]))
        return None

    async def city_boundary(self, city: str, state: str, country: str) -> BoundingBox | None:
        results = await self._search({"city": city, "state": state, "country": country})
        if not results:
            results = await self._search({"q": f"{city}, {state}, {country}"})
        if not results or "boundingbox" not in results[0]:
            return None
        try:
            return parse_nominatim_bbox(results[0]["boundingbox"])
        except (ValueError, InvalidBoundaryError):
            return None
