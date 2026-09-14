"""Tile-based store discovery, independent of any particular provider or database.

The orchestrator plans a grid from the provider's tiling strategy, runs tiles with
bounded concurrency, subdivides tiles the provider reports as saturated, deduplicates
across overlapping tiles, and drops anything outside the boundary. A tile that fails
after the HTTP layer's retries goes to the back of the queue for one more pass, since
public APIs are often overloaded for tens of seconds rather than minutes. If that pass fails
too, the tile is recorded and skipped: partial results are still results, and the run
reports exactly what was missed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.domain.geo import BoundingBox
from app.providers.base import DiscoveredPlace, PlacesProvider
from app.providers.http import ProviderError, RequestBudget, RequestBudgetExceededError

logger = logging.getLogger(__name__)

MAX_RECORDED_ERRORS = 50
DEFERRED_RETRY_PASSES = 1


@dataclass(slots=True)
class DiscoveryProgress:
    tiles_planned: int = 0
    tiles_completed: int = 0
    tiles_failed: int = 0
    places_returned: int = 0
    budget_exhausted: bool = False
    errors: list[dict] = field(default_factory=list)

    def record_error(self, tile: BoundingBox, message: str) -> None:
        if len(self.errors) < MAX_RECORDED_ERRORS:
            self.errors.append(
                {
                    "stage": "discovery",
                    "tile": [round(v, 6) for v in (tile.south, tile.west, tile.north, tile.east)],
                    "message": message,
                }
            )


@dataclass(slots=True)
class DiscoveryOutcome:
    places: list[DiscoveredPlace]
    progress: DiscoveryProgress


ProgressCallback = Callable[[DiscoveryProgress], Awaitable[None]]


async def discover_places(
    provider: PlacesProvider,
    boundary: BoundingBox,
    provider_types: list[str],
    budget: RequestBudget,
    *,
    concurrency: int = 2,
    on_progress: ProgressCallback | None = None,
) -> DiscoveryOutcome:
    progress = DiscoveryProgress()
    found: dict[str, DiscoveredPlace] = {}
    # Each queue item is (tile, pass number). Pass 0 is the first attempt.
    queue: asyncio.Queue[tuple[BoundingBox, int]] = asyncio.Queue()

    for tile in boundary.tiles(provider.tiling.initial_max_side_km):
        queue.put_nowait((tile, 0))
    progress.tiles_planned = queue.qsize()

    async def process(tile: BoundingBox, attempt_pass: int) -> None:
        if budget.exhausted:
            progress.budget_exhausted = True
            progress.tiles_failed += 1
            return
        try:
            result = await provider.search_tile(tile, provider_types, budget)
        except RequestBudgetExceededError as exc:
            progress.budget_exhausted = True
            progress.tiles_failed += 1
            progress.record_error(tile, str(exc))
            return
        except ProviderError as exc:
            if attempt_pass < DEFERRED_RETRY_PASSES:
                logger.warning("tile %s failed, deferring for another pass: %s", tile, exc)
                queue.put_nowait((tile, attempt_pass + 1))
                return
            logger.warning("tile %s failed permanently: %s", tile, exc)
            progress.tiles_failed += 1
            progress.record_error(tile, str(exc))
            return

        progress.places_returned += len(result.places)
        for place in result.places:
            if boundary.contains(place.location):
                found.setdefault(place.provider_place_id, place)

        can_split = min(tile.width_km(), tile.height_km()) / 2 >= provider.tiling.min_side_km
        if result.saturated and can_split:
            for quadrant in tile.quadrants():
                queue.put_nowait((quadrant, 0))
            progress.tiles_planned += 4
        elif result.saturated:
            progress.record_error(
                tile, "result cap reached at minimum tile size; some places may be missing"
            )
        progress.tiles_completed += 1

    async def worker() -> None:
        while True:
            tile, attempt_pass = await queue.get()
            try:
                await process(tile, attempt_pass)
                if on_progress is not None:
                    await on_progress(progress)
            finally:
                queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(max(1, concurrency))]
    try:
        await queue.join()
    finally:
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    return DiscoveryOutcome(places=list(found.values()), progress=progress)
