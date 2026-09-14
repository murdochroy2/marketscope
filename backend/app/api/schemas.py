"""HTTP contracts. Kept separate from ORM entities so the database can change freely."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.geo import BoundingBox


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Bounds(ApiModel):
    south: float = Field(ge=-90, le=90)
    west: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)

    @classmethod
    def of(cls, box: BoundingBox) -> Bounds:
        return cls(south=box.south, west=box.west, north=box.north, east=box.east)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


# ---------------------------------------------------------------- reference data


class CountryOut(ApiModel):
    id: int
    name: str
    iso_code: str


class StateOut(ApiModel):
    id: int
    name: str


class CityOut(ApiModel):
    id: int
    name: str


class CategoryOut(ApiModel):
    id: int
    slug: str
    name: str


class CityBoundaryOut(BaseModel):
    city_id: int
    city_name: str
    extent: Bounds
    extent_area_sq_km: float
    suggested: Bounds
    max_area_sq_km: float
    source: str


# ---------------------------------------------------------------- portfolio


class PortfolioStoreOut(ApiModel):
    id: int
    row_number: int
    store_name: str
    address: str
    city: str
    state: str
    country: str
    category: str
    latitude: float | None
    longitude: float | None
    geocode_status: str


class PortfolioUploadOut(ApiModel):
    id: int
    filename: str
    row_count: int
    rows_missing_coordinates: int
    created_at: datetime


class PortfolioUploadDetailOut(PortfolioUploadOut):
    ignored_columns: list[str] = Field(default_factory=list)
    stores: list[PortfolioStoreOut]


# ---------------------------------------------------------------- markets


class CreateMarketIn(BaseModel):
    city_id: int
    category_ids: list[int] = Field(min_length=1)
    boundary: Bounds
    portfolio_upload_id: int | None = None
    name: str | None = Field(default=None, max_length=150)

    @model_validator(mode="after")
    def _boundary_is_ordered(self) -> CreateMarketIn:
        b = self.boundary
        if b.south >= b.north or b.west >= b.east:
            raise ValueError("boundary must have south < north and west < east")
        return self


class RunOut(ApiModel):
    id: int
    provider: str
    status: str
    geocode_attempted: int
    geocode_failed: int
    tiles_planned: int
    tiles_completed: int
    tiles_failed: int
    provider_requests: int
    places_returned: int
    stores_saved: int
    budget_exhausted: bool
    errors: list[dict]
    started_at: datetime
    finished_at: datetime | None


class MarketSummaryOut(BaseModel):
    id: int
    name: str
    city_name: str
    status: str
    area_sq_km: float
    discovered_count: int
    created_at: datetime


class MarketOut(BaseModel):
    id: int
    name: str
    status: str
    is_finished: bool
    country: str
    state: str
    city: str
    city_id: int
    boundary: Bounds
    area_sq_km: float
    categories: list[CategoryOut]
    portfolio_upload_id: int | None
    created_at: datetime
    run: RunOut | None


class DiscoveredStoreOut(BaseModel):
    id: int
    name: str
    category: str
    category_slug: str
    latitude: float
    longitude: float
    address: str | None
    provider: str
    provider_place_id: str


class MarketPortfolioStoreOut(BaseModel):
    id: int
    name: str
    category: str
    address: str
    latitude: float | None
    longitude: float | None
    boundary_status: str
    geocode_status: str
    geocode_error: str | None
    matched_discovered_store_id: int | None
    match_distance_m: float | None


class LayerCounts(BaseModel):
    discovered: int
    portfolio_inside: int
    portfolio_outside: int
    portfolio_unlocated: int
    matched: int


class MarketStoresOut(BaseModel):
    market_id: int
    counts: LayerCounts
    discovered: list[DiscoveredStoreOut]
    portfolio: list[MarketPortfolioStoreOut]
