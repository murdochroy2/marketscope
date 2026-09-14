"""Request-scoped wiring. Routes ask for a service; they never construct infrastructure."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.jobs.market_pipeline import MarketPipeline
from app.jobs.runner import JobRunner
from app.providers.factory import Providers
from app.services.locations import LocationService
from app.services.markets import MarketService
from app.services.portfolio import PortfolioService


@dataclass(slots=True)
class AppState:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    providers: Providers
    runner: JobRunner
    pipeline: MarketPipeline


def get_state(request: Request) -> AppState:
    return request.app.state.container


async def get_session(
    state: Annotated[AppState, Depends(get_state)],
) -> AsyncIterator[AsyncSession]:
    async with state.session_factory() as session:
        yield session


StateDep = Annotated[AppState, Depends(get_state)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_portfolio_service(session: SessionDep) -> PortfolioService:
    return PortfolioService(session)


def get_location_service(session: SessionDep, state: StateDep) -> LocationService:
    return LocationService(session, state.providers.geocoder, state.settings.max_market_area_sq_km)


def get_market_service(session: SessionDep, state: StateDep) -> MarketService:
    def submit(market_id: int, run_id: int) -> None:
        state.runner.submit(state.pipeline.run(market_id, run_id), name=f"market-{market_id}")

    return MarketService(
        session,
        provider_name=state.providers.places.name,
        max_area_sq_km=state.settings.max_market_area_sq_km,
        submit_pipeline=submit,
    )


PortfolioServiceDep = Annotated[PortfolioService, Depends(get_portfolio_service)]
LocationServiceDep = Annotated[LocationService, Depends(get_location_service)]
MarketServiceDep = Annotated[MarketService, Depends(get_market_service)]
