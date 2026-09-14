from dataclasses import dataclass, field

import pytest

from app.domain.geo import BoundingBox, Coordinate
from app.providers.base import DiscoveredPlace, TileResult, TilingStrategy
from app.providers.http import ProviderError, RequestBudget
from app.services.discovery import discover_places

BOUNDARY = BoundingBox.around(Coordinate(12.94, 77.62), width_km=4, height_km=4)


def place(pid: str, lat: float, lng: float) -> DiscoveredPlace:
    return DiscoveredPlace(
        pid, pid, Coordinate(lat, lng), ("shop=supermarket",), "shop=supermarket"
    )


@dataclass
class ScriptedProvider:
    """Returns every scripted place inside the searched tile, plus configurable behaviour."""

    places: list[DiscoveredPlace]
    tiling: TilingStrategy = field(
        default_factory=lambda: TilingStrategy(initial_max_side_km=2, min_side_km=0.01)
    )
    name: str = "scripted"
    cap: int | None = None
    fail_first_n_calls: int = 0
    always_fail: bool = False
    overhang_km: float = 0.0
    calls: list[BoundingBox] = field(default_factory=list)

    async def search_tile(self, tile, provider_types, budget):
        budget.spend()
        self.calls.append(tile)
        if self.always_fail or len(self.calls) <= self.fail_first_n_calls:
            raise ProviderError("overloaded")
        # Simulate a circle query by optionally searching a slightly larger area than the tile.
        search = tile
        if self.overhang_km:
            search = BoundingBox.around(
                tile.center, tile.width_km() + self.overhang_km, tile.height_km() + self.overhang_km
            )
        hits = [p for p in self.places if search.contains(p.location)]
        if self.cap is not None and len(hits) >= self.cap:
            return TileResult(hits[: self.cap], saturated=True)
        return TileResult(hits)


async def test_places_seen_by_overlapping_tiles_are_kept_once_and_outside_ones_dropped():
    inside = place("in", BOUNDARY.center.lat, BOUNDARY.center.lng)
    outside = place("out", BOUNDARY.north + 0.002, BOUNDARY.center.lng)
    provider = ScriptedProvider([inside, outside], overhang_km=3)

    outcome = await discover_places(provider, BOUNDARY, ["shop=supermarket"], RequestBudget(100))

    assert [p.provider_place_id for p in outcome.places] == ["in"]
    assert outcome.progress.tiles_planned == 4
    assert outcome.progress.places_returned > 1  # the same store came back from several tiles


async def test_saturated_tiles_are_subdivided_until_results_fit():
    # 12 stores clustered in one corner, provider capped at 5 per call.
    c = BOUNDARY.center
    cluster = [place(f"p{i}", c.lat + 0.001 * (i % 4), c.lng + 0.001 * (i // 4)) for i in range(12)]
    provider = ScriptedProvider(cluster, cap=5)

    outcome = await discover_places(
        provider, BOUNDARY, ["shop=supermarket"], RequestBudget(500), concurrency=1
    )

    assert {p.provider_place_id for p in outcome.places} == {f"p{i}" for i in range(12)}
    assert outcome.progress.tiles_planned > 4


async def test_saturation_at_minimum_tile_size_is_reported():
    c = BOUNDARY.center
    stacked = [place(f"p{i}", c.lat + 1e-5 * i, c.lng + 1e-5 * i) for i in range(8)]
    provider = ScriptedProvider(stacked, cap=5, tiling=TilingStrategy(2, min_side_km=0.5))

    outcome = await discover_places(provider, BOUNDARY, ["shop=supermarket"], RequestBudget(500))

    assert any("minimum tile size" in e["message"] for e in outcome.progress.errors)


async def test_failed_tile_gets_a_deferred_second_pass():
    provider = ScriptedProvider(
        [place("a", BOUNDARY.center.lat, BOUNDARY.center.lng)], fail_first_n_calls=1
    )

    outcome = await discover_places(
        provider, BOUNDARY, ["shop=supermarket"], RequestBudget(100), concurrency=1
    )

    assert outcome.progress.tiles_failed == 0
    assert outcome.progress.tiles_completed == 4
    assert len(provider.calls) == 5


async def test_persistent_failures_are_recorded_without_aborting():
    provider = ScriptedProvider([], always_fail=True)

    outcome = await discover_places(provider, BOUNDARY, ["shop=supermarket"], RequestBudget(100))

    assert outcome.places == []
    assert outcome.progress.tiles_failed == 4
    assert len(outcome.progress.errors) == 4
    assert outcome.progress.errors[0]["message"] == "overloaded"


async def test_budget_exhaustion_stops_requests_and_is_reported():
    provider = ScriptedProvider([place("a", BOUNDARY.center.lat, BOUNDARY.center.lng)])
    budget = RequestBudget(limit=2)

    outcome = await discover_places(provider, BOUNDARY, ["shop=supermarket"], budget, concurrency=1)

    assert len(provider.calls) == 2
    assert outcome.progress.budget_exhausted
    assert outcome.progress.tiles_completed == 2
    assert outcome.progress.tiles_failed == 2


async def test_progress_callback_is_invoked_per_tile():
    seen: list[int] = []

    async def on_progress(progress):
        seen.append(progress.tiles_completed + progress.tiles_failed)

    await discover_places(
        ScriptedProvider([]),
        BOUNDARY,
        ["shop=supermarket"],
        RequestBudget(10),
        concurrency=1,
        on_progress=on_progress,
    )
    assert seen == [1, 2, 3, 4]


@pytest.mark.parametrize("concurrency", [1, 3])
async def test_concurrency_does_not_change_results(concurrency):
    c = BOUNDARY.center
    stores = [place(f"s{i}", c.lat + 0.003 * (i - 5), c.lng + 0.003 * (5 - i)) for i in range(10)]
    outcome = await discover_places(
        ScriptedProvider(stores),
        BOUNDARY,
        ["shop=supermarket"],
        RequestBudget(50),
        concurrency=concurrency,
    )
    assert len(outcome.places) == 10
