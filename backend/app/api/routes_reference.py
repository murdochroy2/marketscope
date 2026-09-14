from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import LocationServiceDep, SessionDep, StateDep
from app.api.schemas import Bounds, CategoryOut, CityBoundaryOut, CityOut, CountryOut, StateOut
from app.repositories.reference import ReferenceRepository

router = APIRouter(tags=["reference data"])


@router.get("/countries", response_model=list[CountryOut])
async def list_countries(session: SessionDep):
    return await ReferenceRepository(session).list_countries()


@router.get("/countries/{country_id}/states", response_model=list[StateOut])
async def list_states(country_id: int, service: LocationServiceDep):
    return await service.states(country_id)


@router.get("/states/{state_id}/cities", response_model=list[CityOut])
async def list_cities(state_id: int, service: LocationServiceDep):
    return await service.cities(state_id)


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(session: SessionDep):
    return await ReferenceRepository(session).list_categories()


@router.get("/cities/{city_id}/boundary", response_model=CityBoundaryOut)
async def city_boundary(city_id: int, service: LocationServiceDep, state: StateDep):
    result = await service.city_boundary(city_id)
    return CityBoundaryOut(
        city_id=result.city.id,
        city_name=result.city.name,
        extent=Bounds.of(result.extent),
        extent_area_sq_km=round(result.extent.area_sq_km(), 2),
        suggested=Bounds.of(result.suggested),
        max_area_sq_km=state.settings.max_market_area_sq_km,
        source=result.source,
    )
