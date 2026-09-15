"""End-to-end through HTTP: upload → boundary → create market → background job → layers."""

from app.domain.geo import BoundingBox

KORAMANGALA_BOX = {"south": 12.915, "west": 77.605, "north": 12.965, "east": 77.650}


async def ids_for(client):
    country = (await client.get("/countries")).json()[0]
    states = (await client.get(f"/countries/{country['id']}/states")).json()
    karnataka = next(s for s in states if s["name"] == "Karnataka")
    city = (await client.get(f"/states/{karnataka['id']}/cities")).json()[0]
    categories = {c["slug"]: c["id"] for c in (await client.get("/categories")).json()}
    return city["id"], categories


async def upload_sample(client, sample_csv_bytes) -> dict:
    response = await client.post(
        "/portfolio-uploads", files={"file": ("sample.csv", sample_csv_bytes, "text/csv")}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_reference_data_is_seeded(client):
    countries = (await client.get("/countries")).json()
    assert [c["name"] for c in countries] == ["India"]
    states = (await client.get(f"/countries/{countries[0]['id']}/states")).json()
    assert [s["name"] for s in states] == ["Delhi", "Karnataka", "Maharashtra"]
    slugs = [c["slug"] for c in (await client.get("/categories")).json()]
    assert slugs == ["supermarket", "grocery_store", "convenience_store", "pharmacy"]


async def test_upload_sample_portfolio(client, sample_csv_bytes):
    body = await upload_sample(client, sample_csv_bytes)
    assert body["row_count"] == 10
    assert body["rows_missing_coordinates"] == 3
    assert (await client.get(f"/portfolio-uploads/{body['id']}")).json()["row_count"] == 10


async def test_upload_with_missing_headers_returns_structured_error(client):
    response = await client.post(
        "/portfolio-uploads",
        files={"file": ("p.csv", b"store_name,city\nA,Bengaluru\n", "text/csv")},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert error["details"]["missing_headers"] == ["address", "state", "country", "category"]
    assert (await client.get("/portfolio-uploads")).json() == []


async def test_upload_with_bad_rows_lists_every_row(client):
    content = (
        b"store_name,address,city,state,country,category,latitude,longitude\n"
        b"A,1 Rd,Bengaluru,KA,India,Pharmacy,north,77.6\n"
        b"B,1 Rd,Bengaluru,KA,India,Pharmacy,12.9,\n"
    )
    response = await client.post(
        "/portfolio-uploads", files={"file": ("p.csv", content, "text/csv")}
    )
    assert response.status_code == 422
    rows = response.json()["error"]["details"]["row_errors"]
    assert [(r["row"], r["column"]) for r in rows] == [(2, "latitude"), (3, "longitude")]


async def test_city_boundary_suggests_a_rectangle_under_the_cap(client):
    city_id, _ = await ids_for(client)
    body = (await client.get(f"/cities/{city_id}/boundary")).json()
    assert body["extent_area_sq_km"] > 1000
    assert BoundingBox(**body["suggested"]).area_sq_km() <= body["max_area_sq_km"]


async def test_market_over_the_area_cap_is_refused(client):
    city_id, categories = await ids_for(client)
    response = await client.post(
        "/markets",
        json={
            "city_id": city_id,
            "category_ids": [categories["pharmacy"]],
            "boundary": {"south": 12.90, "west": 77.55, "north": 13.00, "east": 77.65},
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "boundary_too_large"


async def test_market_with_inverted_boundary_is_refused(client):
    city_id, categories = await ids_for(client)
    response = await client.post(
        "/markets",
        json={
            "city_id": city_id,
            "category_ids": [categories["pharmacy"]],
            "boundary": {"south": 12.96, "west": 77.60, "north": 12.91, "east": 77.65},
        },
    )
    assert response.status_code == 422


async def test_unknown_market_is_404(client):
    response = await client.get("/markets/999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_create_market_end_to_end(app, client, sample_csv_bytes):
    upload = await upload_sample(client, sample_csv_bytes)
    city_id, categories = await ids_for(client)
    selected = [categories["supermarket"], categories["pharmacy"]]

    created = await client.post(
        "/markets",
        json={
            "city_id": city_id,
            "category_ids": selected,
            "boundary": KORAMANGALA_BOX,
            "portfolio_upload_id": upload["id"],
            "name": "Koramangala pilot",
        },
    )
    assert created.status_code == 202, created.text
    assert created.json()["status"] == "pending"
    market_id = created.json()["id"]

    await app.state.container.runner.wait_idle()

    market = (await client.get(f"/markets/{market_id}")).json()
    assert market["status"] == "completed"
    assert market["run"]["geocode_attempted"] == 3
    assert market["run"]["tiles_failed"] == 0
    assert market["run"]["provider_requests"] == market["run"]["tiles_planned"]

    stores = (await client.get(f"/markets/{market_id}/stores")).json()
    box = BoundingBox(**KORAMANGALA_BOX)

    # Discovery: only selected categories, nothing outside the rectangle, no duplicates.
    assert stores["counts"]["discovered"] > 50
    assert {d["category_slug"] for d in stores["discovered"]} == {"supermarket", "pharmacy"}
    assert all(box.contains_point(d["latitude"], d["longitude"]) for d in stores["discovered"])
    assert len({d["provider_place_id"] for d in stores["discovered"]}) == len(stores["discovered"])

    # Portfolio: every uploaded row is classified against this market.
    status = {p["name"]: p["boundary_status"] for p in stores["portfolio"]}
    assert status["FreshMart Koramangala"] == "inside"
    assert status["Nilgiris Grocery BTM Layout"] == "inside"
    assert status["MediPlus Pharmacy Indiranagar"] == "outside"
    assert status["BigBasket Hyperstore Whitefield"] == "outside"  # geocoded, then classified
    assert stores["counts"]["portfolio_inside"] == 2
    assert stores["counts"]["portfolio_outside"] == 8

    geocoded = {p["name"]: p["geocode_status"] for p in stores["portfolio"]}
    assert geocoded["More Supermarket JP Nagar"] == "succeeded"
    assert geocoded["FreshMart Koramangala"] == "not_needed"

    # Bonus: FreshMart has a real OSM supermarket within 150 m.
    freshmart = next(p for p in stores["portfolio"] if p["name"] == "FreshMart Koramangala")
    assert freshmart["matched_discovered_store_id"] is not None
    assert freshmart["match_distance_m"] <= 150


async def test_geocoding_skips_rows_from_other_cities(app, client):
    content = (
        b"store_name,address,city,state,country,category,latitude,longitude\n"
        b'Here,"ITPL Main Road, Whitefield",Bangalore,Karnataka,India,Supermarket,,\n'
        b"Elsewhere,Linking Road,Mumbai,Maharashtra,India,Supermarket,,\n"
    )
    upload = (
        await client.post("/portfolio-uploads", files={"file": ("p.csv", content, "text/csv")})
    ).json()
    city_id, categories = await ids_for(client)
    market_id = (
        await client.post(
            "/markets",
            json={
                "city_id": city_id,
                "category_ids": [categories["supermarket"]],
                "boundary": KORAMANGALA_BOX,
                "portfolio_upload_id": upload["id"],
            },
        )
    ).json()["id"]
    await app.state.container.runner.wait_idle()

    market = (await client.get(f"/markets/{market_id}")).json()
    assert market["run"]["geocode_attempted"] == 1  # the "Bangalore" alias matched; Mumbai skipped
    stores = (await client.get(f"/markets/{market_id}/stores")).json()
    by_name = {p["name"]: p for p in stores["portfolio"]}
    assert by_name["Here"]["geocode_status"] == "succeeded"
    assert by_name["Elsewhere"]["boundary_status"] == "unlocated"
    assert by_name["Elsewhere"]["geocode_status"] == "pending"
