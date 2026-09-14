"""Store discovery through Google Places API (New), Nearby Search.

Nearby Search restricts by circle rather than rectangle, returns at most 20 places, and
does not paginate. The provider therefore searches the circle that circumscribes each tile
and reports the tile as saturated when it gets a full page back. The orchestrator then
subdivides that tile. Results that fall outside the rectangle are filtered upstream.
"""

from __future__ import annotations

from typing import Any

from app.domain.geo import BoundingBox, Coordinate
from app.providers.base import DiscoveredPlace, TileResult, TilingStrategy
from app.providers.http import RequestBudget, ResilientHttpClient

NEARBY_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"
MAX_RESULTS = 20
FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.location",
        "places.types",
        "places.primaryType",
        "places.formattedAddress",
    ]
)


def build_request(tile: BoundingBox, provider_types: list[str]) -> dict[str, Any]:
    center = tile.center
    return {
        "includedTypes": sorted(set(provider_types)),
        "maxResultCount": MAX_RESULTS,
        "rankPreference": "DISTANCE",
        "locationRestriction": {
            "circle": {
                "center": {"latitude": center.lat, "longitude": center.lng},
                "radius": min(50_000.0, tile.circumscribed_radius_m()),
            }
        },
    }


def parse_place(raw: dict[str, Any]) -> DiscoveredPlace | None:
    location = raw.get("location") or {}
    if "latitude" not in location or "longitude" not in location:
        return None
    return DiscoveredPlace(
        provider_place_id=raw["id"],
        name=(raw.get("displayName") or {}).get("text", ""),
        location=Coordinate(lat=location["latitude"], lng=location["longitude"]),
        provider_types=tuple(raw.get("types") or ()),
        primary_type=raw.get("primaryType"),
        address=raw.get("formattedAddress"),
    )


class GooglePlacesProvider:
    name = "google"
    tiling = TilingStrategy(initial_max_side_km=1.0, min_side_km=0.15)

    def __init__(self, http: ResilientHttpClient, api_key: str) -> None:
        if not api_key:
            raise ValueError("GOOGLE_PLACES_API_KEY is required for the google provider")
        self._http = http
        self._api_key = api_key

    async def search_tile(
        self, tile: BoundingBox, provider_types: list[str], budget: RequestBudget
    ) -> TileResult:
        body = await self._http.request_json(
            "POST",
            NEARBY_SEARCH_URL,
            json=build_request(tile, provider_types),
            headers={"X-Goog-Api-Key": self._api_key, "X-Goog-FieldMask": FIELD_MASK},
            budget=budget,
        )
        raw_places = body.get("places") or []
        places = [p for r in raw_places if (p := parse_place(r)) is not None]
        return TileResult(places=places, saturated=len(raw_places) >= MAX_RESULTS)
