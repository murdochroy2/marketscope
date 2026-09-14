from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import NotFoundError, UpstreamUnavailableError
from app.domain.geo import BoundingBox, suggest_boundary
from app.models import City, State
from app.models.entities import utcnow
from app.providers.base import Geocoder
from app.providers.http import ProviderError
from app.repositories.reference import ReferenceRepository


@dataclass(frozen=True, slots=True)
class CityBoundary:
    city: City
    extent: BoundingBox
    suggested: BoundingBox
    source: str


class LocationService:
    def __init__(self, session: AsyncSession, geocoder: Geocoder, max_area_sq_km: float) -> None:
        self._session = session
        self._repo = ReferenceRepository(session)
        self._geocoder = geocoder
        self._max_area_sq_km = max_area_sq_km

    async def states(self, country_id: int) -> Sequence[State]:
        if await self._repo.get_country(country_id) is None:
            raise NotFoundError(f"Country {country_id} does not exist")
        return await self._repo.list_states(country_id)

    async def cities(self, state_id: int) -> Sequence[City]:
        if await self._repo.get_state(state_id) is None:
            raise NotFoundError(f"State {state_id} does not exist")
        return await self._repo.list_cities(state_id)

    async def city_boundary(self, city_id: int) -> CityBoundary:
        city = await self._repo.get_city(city_id)
        if city is None:
            raise NotFoundError(f"City {city_id} does not exist")

        extent = city.cached_boundary
        if extent is None:
            try:
                extent = await self._geocoder.city_boundary(
                    city.name, city.state.name, city.state.country.name
                )
            except ProviderError as exc:
                raise UpstreamUnavailableError(
                    f"Could not fetch the boundary for {city.name} right now. Try again shortly.",
                    {"reason": str(exc)},
                ) from exc
            if extent is None:
                raise UpstreamUnavailableError(f"No boundary was found for {city.name}")
            city.boundary_south, city.boundary_west = extent.south, extent.west
            city.boundary_north, city.boundary_east = extent.north, extent.east
            city.boundary_source = self._geocoder.name
            city.boundary_fetched_at = utcnow()
            await self._session.commit()

        return CityBoundary(
            city=city,
            extent=extent,
            suggested=suggest_boundary(extent, self._max_area_sq_km * 0.8),
            source=city.boundary_source or self._geocoder.name,
        )
