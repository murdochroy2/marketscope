from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    City,
    DiscoveredStore,
    DiscoveryRun,
    Market,
    MarketPortfolioStore,
    RunStatus,
    State,
)


class MarketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, entity: object) -> None:
        self._session.add(entity)

    async def get(self, market_id: int) -> Market | None:
        stmt = (
            select(Market)
            .where(Market.id == market_id)
            .options(
                selectinload(Market.city).selectinload(City.state).selectinload(State.country),
                selectinload(Market.categories),
                selectinload(Market.runs),
            )
        )
        return await self._session.scalar(stmt)

    async def list_recent(self, limit: int = 20) -> Sequence[Market]:
        stmt = (
            select(Market)
            .order_by(Market.id.desc())
            .limit(limit)
            .options(selectinload(Market.city), selectinload(Market.runs))
        )
        return (await self._session.scalars(stmt)).all()

    async def discovered_stores(self, market_id: int) -> Sequence[DiscoveredStore]:
        stmt = (
            select(DiscoveredStore)
            .where(DiscoveredStore.market_id == market_id)
            .options(selectinload(DiscoveredStore.category))
            # Named stores first; OSM has plenty of unnamed pharmacies and kiranas.
            .order_by(DiscoveredStore.name == "", DiscoveredStore.name)
        )
        return (await self._session.scalars(stmt)).all()

    async def existing_place_ids(self, market_id: int, provider: str) -> set[str]:
        stmt = select(DiscoveredStore.provider_place_id).where(
            DiscoveredStore.market_id == market_id, DiscoveredStore.provider == provider
        )
        return set((await self._session.scalars(stmt)).all())

    async def portfolio_links(self, market_id: int) -> Sequence[MarketPortfolioStore]:
        stmt = (
            select(MarketPortfolioStore)
            .where(MarketPortfolioStore.market_id == market_id)
            .options(selectinload(MarketPortfolioStore.portfolio_store))
        )
        return (await self._session.scalars(stmt)).all()

    async def clear_portfolio_links(self, market_id: int) -> None:
        await self._session.execute(
            delete(MarketPortfolioStore).where(MarketPortfolioStore.market_id == market_id)
        )

    async def discovered_counts(self, market_ids: Sequence[int]) -> dict[int, int]:
        if not market_ids:
            return {}
        stmt = (
            select(DiscoveredStore.market_id, func.count())
            .where(DiscoveredStore.market_id.in_(market_ids))
            .group_by(DiscoveredStore.market_id)
        )
        return {mid: n for mid, n in (await self._session.execute(stmt)).all()}

    async def get_run(self, run_id: int) -> DiscoveryRun | None:
        return await self._session.get(DiscoveryRun, run_id)

    async def runs_in_progress(self) -> Sequence[DiscoveryRun]:
        stmt = select(DiscoveryRun).where(DiscoveryRun.status == RunStatus.RUNNING)
        return (await self._session.scalars(stmt)).all()
