from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.db import Base, make_session_factory
from app.main import create_app
from app.models import Category, CategoryProviderType, City, Country, State
from app.models.seed import CATEGORIES, LOCATIONS, PROVIDERS, provider_types_for
from app.providers.factory import Providers
from app.providers.fixtures import FixtureGeocoder, FixturePlacesProvider

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_CSV = REPO_ROOT / "samples" / "sample_portfolio_bengaluru.csv"


async def seed(session_factory) -> None:
    async with session_factory() as session:
        for c in LOCATIONS:
            country = Country(name=c["country"], iso_code=c["iso_code"])
            for s in c["states"]:
                state = State(name=s["name"])
                state.cities = [City(name=x["name"], aliases=x["aliases"]) for x in s["cities"]]
                country.states.append(state)
            session.add(country)
        for order, c in enumerate(CATEGORIES):
            category = Category(slug=c["slug"], name=c["name"], sort_order=order)
            category.provider_types = [
                CategoryProviderType(provider=p, provider_type=t)
                for p in PROVIDERS
                for t in provider_types_for(c, p)
            ]
            session.add(category)
        await session.commit()


@pytest.fixture
def sample_csv_bytes() -> bytes:
    return SAMPLE_CSV.read_bytes()


@pytest.fixture
async def app(tmp_path):
    """The real application wired to a throwaway SQLite database and offline providers."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed(make_session_factory(engine))
    await engine.dispose()

    settings = Settings(
        database_url=url, places_provider="fixture", geocoder="fixture", _env_file=None
    )
    providers = Providers(places=FixturePlacesProvider(), geocoder=FixtureGeocoder())
    application = create_app(settings, providers)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api") as c:
        yield c
