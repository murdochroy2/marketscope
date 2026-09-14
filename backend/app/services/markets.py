from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import BoundaryTooLargeError, NotFoundError, ValidationFailedError
from app.domain.geo import BoundingBox, InvalidBoundaryError
from app.models import (
    DiscoveredStore,
    DiscoveryRun,
    Market,
    MarketCategory,
    MarketPortfolioStore,
    MarketStatus,
    RunStatus,
)
from app.repositories.markets import MarketRepository
from app.repositories.portfolio import PortfolioRepository
from app.repositories.reference import ReferenceRepository

# Tolerance so a rectangle the UI shows as exactly "30.0 km²" is not refused over float noise.
AREA_EPSILON_SQ_KM = 1e-6


@dataclass(frozen=True, slots=True)
class CreateMarketCommand:
    city_id: int
    category_ids: list[int]
    boundary: tuple[float, float, float, float]  # south, west, north, east
    portfolio_upload_id: int | None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class MarketStores:
    market: Market
    discovered: Sequence[DiscoveredStore]
    portfolio: Sequence[MarketPortfolioStore]


SubmitPipeline = Callable[[int, int], None]


class MarketService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        provider_name: str,
        max_area_sq_km: float,
        submit_pipeline: SubmitPipeline,
    ) -> None:
        self._session = session
        self._markets = MarketRepository(session)
        self._reference = ReferenceRepository(session)
        self._portfolio = PortfolioRepository(session)
        self._provider_name = provider_name
        self._max_area_sq_km = max_area_sq_km
        self._submit_pipeline = submit_pipeline

    async def create(self, command: CreateMarketCommand) -> Market:
        try:
            boundary = BoundingBox(*command.boundary)
        except InvalidBoundaryError as exc:
            raise ValidationFailedError(f"Boundary is invalid: {exc}") from exc

        area = boundary.area_sq_km()
        if area > self._max_area_sq_km + AREA_EPSILON_SQ_KM:
            raise BoundaryTooLargeError(
                f"Boundary covers {area:.1f} km². "
                f"Shrink it to {self._max_area_sq_km:g} km² or less.",
                {"area_sq_km": round(area, 3), "max_area_sq_km": self._max_area_sq_km},
            )

        city = await self._reference.get_city(command.city_id)
        if city is None:
            raise NotFoundError(f"City {command.city_id} does not exist")

        category_ids = sorted(set(command.category_ids))
        if not category_ids:
            raise ValidationFailedError("Select at least one category")
        categories = await self._reference.get_categories(category_ids)
        if len(categories) != len(category_ids):
            known = {c.id for c in categories}
            raise NotFoundError(
                "Unknown category", {"category_ids": [i for i in category_ids if i not in known]}
            )
        mapping = await self._reference.provider_types(category_ids, self._provider_name)
        unmapped = [c.name for c in categories if not mapping[c.id]]
        if unmapped:
            raise ValidationFailedError(
                f"No {self._provider_name} place types are configured for: {', '.join(unmapped)}"
            )

        if command.portfolio_upload_id is not None and (
            await self._portfolio.get_upload(command.portfolio_upload_id) is None
        ):
            raise NotFoundError(f"Portfolio upload {command.portfolio_upload_id} does not exist")

        market = Market(
            name=(command.name or "").strip() or f"{city.name} · {datetime.now():%-d %b, %H:%M}",
            city_id=city.id,
            portfolio_upload_id=command.portfolio_upload_id,
            south=boundary.south,
            west=boundary.west,
            north=boundary.north,
            east=boundary.east,
            area_sq_km=round(area, 4),
            status=MarketStatus.PENDING,
        )
        self._markets.add(market)
        await self._session.flush()
        for category in categories:
            self._markets.add(MarketCategory(market_id=market.id, category_id=category.id))
        run = DiscoveryRun(
            market_id=market.id, provider=self._provider_name, status=RunStatus.RUNNING, errors=[]
        )
        self._markets.add(run)
        await self._session.commit()

        # Only hand off once the rows are committed, so the job can always see them.
        self._submit_pipeline(market.id, run.id)
        return await self.get(market.id)

    async def get(self, market_id: int) -> Market:
        market = await self._markets.get(market_id)
        if market is None:
            raise NotFoundError(f"Market {market_id} does not exist")
        return market

    async def list_recent(self) -> tuple[Sequence[Market], dict[int, int]]:
        markets = await self._markets.list_recent()
        counts = await self._markets.discovered_counts([m.id for m in markets])
        return markets, counts

    async def stores(self, market_id: int) -> MarketStores:
        market = await self.get(market_id)
        return MarketStores(
            market=market,
            discovered=await self._markets.discovered_stores(market_id),
            portfolio=await self._markets.portfolio_links(market_id),
        )
