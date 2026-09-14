import httpx
import pytest

from app.domain.geo import BoundingBox, Coordinate
from app.providers.base import GeocodeQuery
from app.providers.google_places import MAX_RESULTS, GooglePlacesProvider, build_request
from app.providers.http import RequestBudget, ResilientHttpClient, RetryableResponseError
from app.providers.nominatim import address_candidates, parse_nominatim_bbox
from app.providers.overpass import build_query, parse_element, validate_response

TILE = BoundingBox(12.93, 77.61, 12.95, 77.63)


def test_nominatim_bbox_order_is_south_north_west_east():
    box = parse_nominatim_bbox(["12.8334905", "13.1426196", "77.4598797", "77.7840639"])
    assert (box.south, box.north, box.west, box.east) == (
        12.8334905,
        13.1426196,
        77.4598797,
        77.7840639,
    )


def test_address_candidates_drop_leading_parts():
    q = GeocodeQuery("80 Feet Road, Koramangala 4th Block", "Bengaluru", "Karnataka", "India")
    assert address_candidates(q) == [
        "80 Feet Road, Koramangala 4th Block, Bengaluru, Karnataka, India",
        "Koramangala 4th Block, Bengaluru, Karnataka, India",
    ]


def test_overpass_query_uses_south_west_north_east_and_every_tag():
    query = build_query(TILE, ["shop=supermarket", "amenity=pharmacy"])
    assert "(12.930000,77.610000,12.950000,77.630000)" in query
    assert 'nwr["shop"="supermarket"]' in query
    assert 'nwr["amenity"="pharmacy"]' in query
    assert "out center tags" in query


def test_overpass_parses_nodes_and_way_centres_and_ignores_unrelated_tags():
    wanted = {"shop=supermarket"}
    node = {
        "type": "node",
        "id": 1,
        "lat": 12.94,
        "lon": 77.62,
        "tags": {"shop": "supermarket", "name": "A"},
    }
    way = {
        "type": "way",
        "id": 2,
        "center": {"lat": 12.94, "lon": 77.62},
        "tags": {"shop": "supermarket"},
    }
    other = {"type": "node", "id": 3, "lat": 12.94, "lon": 77.62, "tags": {"shop": "bakery"}}
    assert parse_element(node, wanted).provider_place_id == "node/1"
    assert parse_element(way, wanted).location == Coordinate(12.94, 77.62)
    assert parse_element(other, wanted) is None


def test_overpass_runtime_error_remark_is_retryable():
    with pytest.raises(RetryableResponseError):
        validate_response({"elements": [], "remark": "runtime error: Query timed out"})
    validate_response({"elements": []})


def test_google_request_restricts_to_circle_covering_the_tile():
    body = build_request(TILE, ["pharmacy", "supermarket", "pharmacy"])
    circle = body["locationRestriction"]["circle"]
    assert body["includedTypes"] == ["pharmacy", "supermarket"]
    assert circle["center"] == {"latitude": TILE.center.lat, "longitude": TILE.center.lng}
    assert circle["radius"] == pytest.approx(TILE.circumscribed_radius_m())


async def test_google_full_page_marks_tile_saturated_and_sends_field_mask():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = request.headers
        places = [
            {
                "id": f"p{i}",
                "displayName": {"text": f"S{i}"},
                "location": {"latitude": 12.94, "longitude": 77.62},
                "types": ["pharmacy"],
                "primaryType": "pharmacy",
            }
            for i in range(MAX_RESULTS)
        ]
        return httpx.Response(200, json={"places": places})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GooglePlacesProvider(ResilientHttpClient(client), api_key="k")
        result = await provider.search_tile(TILE, ["pharmacy"], RequestBudget(10))
    assert result.saturated
    assert len(result.places) == MAX_RESULTS
    assert seen["headers"]["X-Goog-Api-Key"] == "k"
    assert "places.location" in seen["headers"]["X-Goog-FieldMask"]
