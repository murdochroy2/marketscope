from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Category, CategoryProviderType, City, Country, State


class ReferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_countries(self) -> Sequence[Country]:
        return (await self._session.scalars(select(Country).order_by(Country.name))).all()

    async def list_states(self, country_id: int) -> Sequence[State]:
        stmt = select(State).where(State.country_id == country_id).order_by(State.name)
        return (await self._session.scalars(stmt)).all()

    async def list_cities(self, state_id: int) -> Sequence[City]:
        stmt = select(City).where(City.state_id == state_id).order_by(City.name)
        return (await self._session.scalars(stmt)).all()

    async def get_country(self, country_id: int) -> Country | None:
        return await self._session.get(Country, country_id)

    async def get_state(self, state_id: int) -> State | None:
        return await self._session.get(State, state_id)

    async def get_city(self, city_id: int) -> City | None:
        stmt = (
            select(City)
            .where(City.id == city_id)
            .options(selectinload(City.state).selectinload(State.country))
        )
        return await self._session.scalar(stmt)

    async def list_categories(self) -> Sequence[Category]:
        return (await self._session.scalars(select(Category).order_by(Category.sort_order))).all()

    async def get_categories(self, ids: Sequence[int]) -> Sequence[Category]:
        stmt = select(Category).where(Category.id.in_(ids)).order_by(Category.sort_order)
        return (await self._session.scalars(stmt)).all()

    async def provider_types(
        self, category_ids: Sequence[int], provider: str
    ) -> dict[int, list[str]]:
        stmt = select(CategoryProviderType).where(
            CategoryProviderType.category_id.in_(category_ids),
            CategoryProviderType.provider == provider,
        )
        mapping: dict[int, list[str]] = {cid: [] for cid in category_ids}
        for row in (await self._session.scalars(stmt)).all():
            mapping[row.category_id].append(row.provider_type)
        return mapping
