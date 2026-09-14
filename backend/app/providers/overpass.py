"""OpenStreetMap store discovery through the Overpass API.

Overpass has no result cap, so tiles never saturate. What it does have is a shared public
quota and a habit of answering overload with HTTP 200 and an HTML page, or with JSON
carrying a "runtime error" remark. Both are treated as retryable, and each retry moves
to the next mirror.
"""

from __future__ import annotations

from typing import Any

from app.domain.geo import BoundingBox, Coordinate
from app.providers.base import DiscoveredPlace, TileResult, TilingStrategy
from app.providers.http import RequestBudget, ResilientHttpClient, RetryableResponseError

QUERY_TIMEOUT_S = 25


def build_query(tile: BoundingBox, provider_types: list[str]) -> str:
    bbox = f"{tile.south:.6f},{tile.west:.6f},{tile.north:.6f},{tile.east:.6f}"
    selectors = []
    for tag in sorted(set(provider_types)):
        key, _, value = tag.partition("=")
        selectors.append(f'  nwr["{key}"="{value}"]({bbox});')
    body = "\n".join(selectors)
    # "out center" gives ways and relations (mall buildings, etc.) a single point.
    return f"[out:json][timeout:{QUERY_TIMEOUT_S}];\n(\n{body}\n);\nout center tags;"


def validate_response(body: Any) -> None:
    if not isinstance(body, dict) or "elements" not in body:
        raise RetryableResponseError("Overpass response had no elements")
    remark = body.get("remark") or ""
    if "runtime error" in remark.lower() or "timeout" in remark.lower():
        raise RetryableResponseError(f"Overpass reported: {remark[:160]}")


def _address(tags: dict[str, str]) -> str | None:
    parts = [
        " ".join(p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p),
        tags.get("addr:suburb") or tags.get("addr:neighbourhood"),
        tags.get("addr:city"),
        tags.get("addr:postcode"),
    ]
    text = ", ".join(p for p in parts if p)
    return text or tags.get("addr:full")


def parse_element(element: dict[str, Any], provider_types: set[str]) -> DiscoveredPlace | None:
    tags: dict[str, str] = element.get("tags") or {}
    if "lat" in element and "lon" in element:
        lat, lng = element["lat"], element["lon"]
    elif "center" in element:
        lat, lng = element["center"]["lat"], element["center"]["lon"]
    else:
        return None

    matched = tuple(f"{k}={v}" for k, v in tags.items() if f"{k}={v}" in provider_types)
    if not matched:
        return None

    return DiscoveredPlace(
        provider_place_id=f"{element['type']}/{element['id']}",
        name=tags.get("name:en") or tags.get("name") or tags.get("brand") or "",
        location=Coordinate(lat=lat, lng=lng),
        provider_types=matched,
        primary_type=matched[0],
        address=_address(tags),
    )


class OverpassProvider:
    name = "overpass"
    # Small enough that a dense tile finishes well inside the server-side timeout.
    tiling = TilingStrategy(initial_max_side_km=2.5)

    def __init__(self, http: ResilientHttpClient, endpoints: list[str]) -> None:
        if not endpoints:
            raise ValueError("at least one Overpass endpoint is required")
        self._http = http
        self._endpoints = endpoints

    def _endpoint_for_attempt(self, attempt: int) -> str:
        return self._endpoints[(attempt - 1) % len(self._endpoints)]

    async def search_tile(
        self, tile: BoundingBox, provider_types: list[str], budget: RequestBudget
    ) -> TileResult:
        body = await self._http.request_json(
            "POST",
            self._endpoint_for_attempt,
            data={"data": build_query(tile, provider_types)},
            budget=budget,
            validate=validate_response,
        )
        wanted = set(provider_types)
        places = [p for e in body["elements"] if (p := parse_element(e, wanted)) is not None]
        return TileResult(places=places, saturated=False)
