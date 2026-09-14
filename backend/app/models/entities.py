"""ORM entities.

Two relationships carry most of the design weight:

* ``MarketPortfolioStore`` — whether a portfolio store is inside a boundary is a fact
  about the (market, store) pair, not about the store. The same store can be inside
  one market and outside another.
* ``DiscoveredStore`` is unique on (market, provider, provider_place_id), so a retried
  tile or a re-run can never double-insert an outlet.

Boundaries are four float columns rather than a PostGIS geometry: an axis-aligned
rectangle needs nothing more than range comparisons, and it keeps setup to plain Postgres.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.domain.geo import BoundingBox


def utcnow() -> datetime:
    return datetime.now(UTC)


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(
        cls, name=name, values_callable=lambda e: [m.value for m in e], native_enum=False, length=32
    )


class BoundsMixin:
    south: Mapped[float] = mapped_column(Float)
    west: Mapped[float] = mapped_column(Float)
    north: Mapped[float] = mapped_column(Float)
    east: Mapped[float] = mapped_column(Float)

    @property
    def bounds(self) -> BoundingBox:
        return BoundingBox(south=self.south, west=self.west, north=self.north, east=self.east)


# --------------------------------------------------------------------------- reference data


class Country(Base):
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    iso_code: Mapped[str] = mapped_column(String(2), unique=True)

    states: Mapped[list[State]] = relationship(back_populates="country", order_by="State.name")


class State(Base):
    __tablename__ = "states"
    __table_args__ = (UniqueConstraint("country_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(
        ForeignKey("countries.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))

    country: Mapped[Country] = relationship(back_populates="states")
    cities: Mapped[list[City]] = relationship(back_populates="state", order_by="City.name")


class City(Base):
    __tablename__ = "cities"
    __table_args__ = (UniqueConstraint("state_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    state_id: Mapped[int] = mapped_column(ForeignKey("states.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    # Other spellings seen in real portfolio files, e.g. "Bangalore" for Bengaluru.
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Geocoded extent, cached after the first lookup so a city is fetched once.
    boundary_south: Mapped[float | None] = mapped_column(Float)
    boundary_west: Mapped[float | None] = mapped_column(Float)
    boundary_north: Mapped[float | None] = mapped_column(Float)
    boundary_east: Mapped[float | None] = mapped_column(Float)
    boundary_source: Mapped[str | None] = mapped_column(String(50))
    boundary_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    state: Mapped[State] = relationship(back_populates="cities")

    @property
    def cached_boundary(self) -> BoundingBox | None:
        if self.boundary_south is None:
            return None
        return BoundingBox(
            south=self.boundary_south,
            west=self.boundary_west,  # type: ignore[arg-type]
            north=self.boundary_north,  # type: ignore[arg-type]
            east=self.boundary_east,  # type: ignore[arg-type]
        )

    def names(self) -> set[str]:
        return {self.name.casefold(), *(a.casefold() for a in self.aliases or [])}


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    provider_types: Mapped[list[CategoryProviderType]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )


class CategoryProviderType(Base):
    """Maps one MarketScope category to one or more provider-native place types."""

    __tablename__ = "category_provider_types"
    __table_args__ = (UniqueConstraint("category_id", "provider", "provider_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20))
    # Google: a Places type such as "supermarket". Overpass: a tag such as "shop=supermarket".
    provider_type: Mapped[str] = mapped_column(String(100))

    category: Mapped[Category] = relationship(back_populates="provider_types")


# --------------------------------------------------------------------------- portfolio


class GeocodeStatus(enum.StrEnum):
    NOT_NEEDED = "not_needed"  # coordinates came with the upload
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PortfolioUpload(Base):
    __tablename__ = "portfolio_uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    row_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    stores: Mapped[list[PortfolioStore]] = relationship(
        back_populates="upload", cascade="all, delete-orphan", order_by="PortfolioStore.row_number"
    )


class PortfolioStore(Base):
    __tablename__ = "portfolio_stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(
        ForeignKey("portfolio_uploads.id", ondelete="CASCADE"), index=True
    )
    row_number: Mapped[int] = mapped_column(Integer)
    store_name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(100))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geocode_status: Mapped[GeocodeStatus] = mapped_column(_enum(GeocodeStatus, "geocode_status"))
    geocode_error: Mapped[str | None] = mapped_column(Text)
    geocoded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    upload: Mapped[PortfolioUpload] = relationship(back_populates="stores")


# --------------------------------------------------------------------------- markets


class MarketStatus(enum.StrEnum):
    PENDING = "pending"
    GEOCODING = "geocoding"
    DISCOVERING = "discovering"
    MATCHING = "matching"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in {
            MarketStatus.COMPLETED,
            MarketStatus.COMPLETED_WITH_ERRORS,
            MarketStatus.FAILED,
        }


class BoundaryStatus(enum.StrEnum):
    INSIDE = "inside"
    OUTSIDE = "outside"
    UNLOCATED = "unlocated"  # no coordinates and could not be geocoded


class Market(BoundsMixin, Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    portfolio_upload_id: Mapped[int | None] = mapped_column(
        ForeignKey("portfolio_uploads.id", ondelete="SET NULL"), index=True
    )
    area_sq_km: Mapped[float] = mapped_column(Float)
    status: Mapped[MarketStatus] = mapped_column(_enum(MarketStatus, "market_status"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    city: Mapped[City] = relationship()
    categories: Mapped[list[Category]] = relationship(
        secondary="market_categories", order_by="Category.sort_order"
    )
    runs: Mapped[list[DiscoveryRun]] = relationship(
        back_populates="market", cascade="all, delete-orphan", order_by="DiscoveryRun.id"
    )


class MarketCategory(Base):
    __tablename__ = "market_categories"

    market_id: Mapped[int] = mapped_column(
        ForeignKey("markets.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), primary_key=True)


class MarketPortfolioStore(Base):
    __tablename__ = "market_portfolio_stores"

    market_id: Mapped[int] = mapped_column(
        ForeignKey("markets.id", ondelete="CASCADE"), primary_key=True
    )
    portfolio_store_id: Mapped[int] = mapped_column(
        ForeignKey("portfolio_stores.id", ondelete="CASCADE"), primary_key=True
    )
    boundary_status: Mapped[BoundaryStatus] = mapped_column(
        _enum(BoundaryStatus, "boundary_status")
    )
    matched_discovered_store_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovered_stores.id", ondelete="SET NULL")
    )
    match_distance_m: Mapped[float | None] = mapped_column(Float)

    portfolio_store: Mapped[PortfolioStore] = relationship()


class DiscoveredStore(Base):
    __tablename__ = "discovered_stores"
    __table_args__ = (
        UniqueConstraint(
            "market_id", "provider", "provider_place_id", name="uq_discovered_store_per_market"
        ),
        Index("ix_discovered_stores_market_category", "market_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(20))
    provider_place_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    address: Mapped[str | None] = mapped_column(Text)
    provider_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    category: Mapped[Category] = relationship()


class RunStatus(enum.StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class DiscoveryRun(Base):
    """One execution of the market-creation pipeline. Also the source of progress reporting."""

    __tablename__ = "discovery_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus, "run_status"))

    geocode_attempted: Mapped[int] = mapped_column(Integer, default=0)
    geocode_failed: Mapped[int] = mapped_column(Integer, default=0)
    tiles_planned: Mapped[int] = mapped_column(Integer, default=0)
    tiles_completed: Mapped[int] = mapped_column(Integer, default=0)
    tiles_failed: Mapped[int] = mapped_column(Integer, default=0)
    provider_requests: Mapped[int] = mapped_column(Integer, default=0)
    places_returned: Mapped[int] = mapped_column(Integer, default=0)
    stores_saved: Mapped[int] = mapped_column(Integer, default=0)
    budget_exhausted: Mapped[bool] = mapped_column(default=False)
    errors: Mapped[list[dict]] = mapped_column(JSON, default=list)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    market: Mapped[Market] = relationship(back_populates="runs")
