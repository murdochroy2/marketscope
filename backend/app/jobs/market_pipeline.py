"""The market-creation pipeline: geocode → classify portfolio → discover → match.

Each phase commits its own results, so a failure late in the run never discards the work
done before it, and the progress endpoint can report what has happened so far.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.domain.geo import Coordinate
from app.models import (
    BoundaryStatus,
    DiscoveredStore,
    GeocodeStatus,
    Market,
    MarketPortfolioStore,
    MarketStatus,
    PortfolioStore,
    RunStatus,
)
from app.models.entities import DiscoveryRun, utcnow
from app.providers.base import GeocodeQuery
from app.providers.factory import Providers
from app.providers.http import ProviderError, RequestBudget
from app.repositories.markets import MarketRepository
from app.repositories.portfolio import PortfolioRepository
from app.repositories.reference import ReferenceRepository
from app.services.classification import (
    CategoryRule,
    PointRef,
    boundary_status,
    city_matches,
    match_nearby,
    resolve_category,
)
from app.services.discovery import DiscoveryProgress, discover_places

logger = logging.getLogger(__name__)


class MarketPipeline:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        providers: Providers,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._providers = providers
        self._settings = settings

    async def run(self, market_id: int, run_id: int) -> None:
        async with self._session_factory() as session:
            repo = MarketRepository(session)
            market = await repo.get(market_id)
            run = await repo.get_run(run_id)
            if market is None or run is None:
                logger.error(
                    "market %s / run %s vanished before the pipeline started", market_id, run_id
                )
                return
            try:
                await self._geocode_portfolio(session, market, run)
                await self._classify_portfolio(session, market)
                await self._discover(session, market, run)
                await self._match(session, market)
                self._finish(market, run)
                await session.commit()
            except Exception as exc:
                logger.exception("market %s pipeline failed", market_id)
                await session.rollback()
                await self._mark_failed(market_id, run_id, str(exc) or type(exc).__name__)

    async def _mark_failed(self, market_id: int, run_id: int, message: str) -> None:
        # A fresh session: the failed one's identity map was expired by the rollback.
        async with self._session_factory() as session:
            market = await session.get(Market, market_id)
            run = await session.get(DiscoveryRun, run_id)
            if market is not None:
                market.status = MarketStatus.FAILED
            if run is not None:
                run.status = RunStatus.FAILED
                run.errors = [*(run.errors or []), {"stage": "pipeline", "message": message}]
                run.finished_at = utcnow()
            await session.commit()

    # ------------------------------------------------------------------ geocoding

    async def _geocode_portfolio(
        self, session: AsyncSession, market: Market, run: DiscoveryRun
    ) -> None:
        """Geocode only the rows that could plausibly be in this market.

        Whether a row is inside the boundary is unknowable before it has coordinates, so
        the brief's "missing lat/long and falling within the boundary" is read as: geocode
        rows without coordinates whose city is this market's city, then classify by
        coordinates. Rows for other cities are never sent, which keeps within Nominatim's
        no-bulk-geocoding policy.
        """
        if market.portfolio_upload_id is None:
            return
        market.status = MarketStatus.GEOCODING
        await session.commit()

        stores = await PortfolioRepository(session).stores_for_upload(market.portfolio_upload_id)
        city = market.city
        city_names = city.names()
        pending = [
            s
            for s in stores
            if s.geocode_status == GeocodeStatus.PENDING and city_matches(s.city, city_names)
        ]
        for store in pending:
            run.geocode_attempted += 1
            try:
                # Query with the canonical names: the row may say "Bangalore" for Bengaluru.
                point = await self._providers.geocoder.geocode(
                    GeocodeQuery(store.address, city.name, city.state.name, city.state.country.name)
                )
            except ProviderError as exc:
                self._mark_geocode_failed(store, run, f"geocoder unavailable: {exc}")
                run.errors = [
                    *run.errors,
                    {"stage": "geocoding", "row": store.row_number, "message": str(exc)},
                ]
            else:
                if point is None:
                    self._mark_geocode_failed(store, run, "address could not be located")
                else:
                    store.latitude, store.longitude = point.lat, point.lng
                    store.geocode_status = GeocodeStatus.SUCCEEDED
                    store.geocode_error = None
                    store.geocoded_at = utcnow()
            await session.commit()

    @staticmethod
    def _mark_geocode_failed(store: PortfolioStore, run: DiscoveryRun, reason: str) -> None:
        store.geocode_status = GeocodeStatus.FAILED
        store.geocode_error = reason
        store.geocoded_at = utcnow()
        run.geocode_failed += 1

    async def _classify_portfolio(self, session: AsyncSession, market: Market) -> None:
        if market.portfolio_upload_id is None:
            return
        repo = MarketRepository(session)
        await repo.clear_portfolio_links(market.id)
        for store in await PortfolioRepository(session).stores_for_upload(
            market.portfolio_upload_id
        ):
            repo.add(
                MarketPortfolioStore(
                    market_id=market.id,
                    portfolio_store_id=store.id,
                    boundary_status=boundary_status(market.bounds, store.latitude, store.longitude),
                )
            )
        await session.commit()

    # ------------------------------------------------------------------ discovery

    async def _discover(self, session: AsyncSession, market: Market, run: DiscoveryRun) -> None:
        market.status = MarketStatus.DISCOVERING
        await session.commit()

        provider = self._providers.places
        category_ids = [c.id for c in market.categories]
        mapping = await ReferenceRepository(session).provider_types(category_ids, provider.name)
        rules = [CategoryRule(cid, frozenset(mapping[cid])) for cid in category_ids]
        all_types = sorted({t for types in mapping.values() for t in types})

        budget = RequestBudget(self._settings.max_provider_requests_per_market)
        lock = asyncio.Lock()

        async def on_progress(progress: DiscoveryProgress) -> None:
            async with lock:
                self._copy_progress(run, progress, budget)
                await session.commit()

        outcome = await discover_places(
            provider,
            market.bounds,
            all_types,
            budget,
            concurrency=self._settings.discovery_concurrency,
            on_progress=on_progress,
        )

        existing = await MarketRepository(session).existing_place_ids(market.id, provider.name)
        saved = 0
        for place in outcome.places:
            category_id = resolve_category(place, rules)
            if category_id is None or place.provider_place_id in existing:
                continue
            session.add(
                DiscoveredStore(
                    market_id=market.id,
                    provider=provider.name,
                    provider_place_id=place.provider_place_id,
                    name=place.name,
                    category_id=category_id,
                    latitude=place.location.lat,
                    longitude=place.location.lng,
                    address=place.address,
                    provider_types=list(place.provider_types),
                )
            )
            saved += 1

        self._copy_progress(run, outcome.progress, budget)
        run.stores_saved = saved
        await session.commit()

    @staticmethod
    def _copy_progress(
        run: DiscoveryRun, progress: DiscoveryProgress, budget: RequestBudget
    ) -> None:
        run.tiles_planned = progress.tiles_planned
        run.tiles_completed = progress.tiles_completed
        run.tiles_failed = progress.tiles_failed
        run.places_returned = progress.places_returned
        run.provider_requests = budget.used
        run.budget_exhausted = progress.budget_exhausted
        geocode_errors = [e for e in run.errors if e.get("stage") != "discovery"]
        run.errors = [*geocode_errors, *progress.errors]

    # ------------------------------------------------------------------ matching

    async def _match(self, session: AsyncSession, market: Market) -> None:
        """Bonus: mark portfolio stores that have a discovered store within the match radius."""
        market.status = MarketStatus.MATCHING
        await session.commit()

        repo = MarketRepository(session)
        links = [
            link
            for link in await repo.portfolio_links(market.id)
            if link.boundary_status == BoundaryStatus.INSIDE
        ]
        if not links:
            return
        discovered = await repo.discovered_stores(market.id)
        by_store = {link.portfolio_store_id: link for link in links}
        matches = match_nearby(
            [
                PointRef(
                    link.portfolio_store_id,
                    Coordinate(link.portfolio_store.latitude, link.portfolio_store.longitude),
                )
                for link in links
            ],
            [PointRef(d.id, Coordinate(d.latitude, d.longitude)) for d in discovered],
            self._settings.match_radius_m,
        )
        for match in matches:
            link = by_store[match.portfolio_id]
            link.matched_discovered_store_id = match.discovered_id
            link.match_distance_m = round(match.distance_m, 1)
        await session.commit()

    @staticmethod
    def _finish(market: Market, run: DiscoveryRun) -> None:
        discovery_errors = run.tiles_failed > 0 or run.budget_exhausted
        geocoder_outage = any(e.get("stage") == "geocoding" for e in run.errors)
        if discovery_errors or geocoder_outage:
            market.status, run.status = (
                MarketStatus.COMPLETED_WITH_ERRORS,
                RunStatus.COMPLETED_WITH_ERRORS,
            )
        else:
            market.status, run.status = MarketStatus.COMPLETED, RunStatus.COMPLETED
        run.finished_at = utcnow()


async def recover_interrupted_runs(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """Runs still marked running at startup belonged to a process that died mid-job."""
    async with session_factory() as session:
        repo = MarketRepository(session)
        runs = await repo.runs_in_progress()
        for run in runs:
            run.status = RunStatus.FAILED
            run.finished_at = utcnow()
            run.errors = [
                *run.errors,
                {"stage": "pipeline", "message": "interrupted by a server restart"},
            ]
            market = await session.get(Market, run.market_id)
            if market is not None and not market.status.is_terminal:
                market.status = MarketStatus.FAILED
        await session.commit()
        return len(runs)
