from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import MarketServiceDep
from app.api.schemas import (
    Bounds,
    CategoryOut,
    CreateMarketIn,
    DiscoveredStoreOut,
    ErrorResponse,
    LayerCounts,
    MarketOut,
    MarketPortfolioStoreOut,
    MarketStoresOut,
    MarketSummaryOut,
    RunOut,
)
from app.models import BoundaryStatus, Market
from app.services.markets import CreateMarketCommand

router = APIRouter(prefix="/markets", tags=["markets"])


def market_out(market: Market) -> MarketOut:
    run = market.runs[-1] if market.runs else None
    return MarketOut(
        id=market.id,
        name=market.name,
        status=market.status.value,
        is_finished=market.status.is_terminal,
        country=market.city.state.country.name,
        state=market.city.state.name,
        city=market.city.name,
        city_id=market.city_id,
        boundary=Bounds.of(market.bounds),
        area_sq_km=market.area_sq_km,
        categories=[CategoryOut.model_validate(c) for c in market.categories],
        portfolio_upload_id=market.portfolio_upload_id,
        created_at=market.created_at,
        run=RunOut.model_validate(run) if run else None,
    )


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MarketOut,
    responses={
        404: {"model": ErrorResponse},
        422: {
            "model": ErrorResponse,
            "description": "Invalid boundary, area over the cap, or bad input",
        },
    },
)
async def create_market(body: CreateMarketIn, service: MarketServiceDep):
    """Create a market and start geocoding and discovery in the background.

    Returns immediately with status "pending". Poll GET /markets/{id} for progress.
    """
    b = body.boundary
    market = await service.create(
        CreateMarketCommand(
            city_id=body.city_id,
            category_ids=body.category_ids,
            boundary=(b.south, b.west, b.north, b.east),
            portfolio_upload_id=body.portfolio_upload_id,
            name=body.name,
        )
    )
    return market_out(market)


@router.get("", response_model=list[MarketSummaryOut])
async def list_markets(service: MarketServiceDep):
    markets, counts = await service.list_recent()
    return [
        MarketSummaryOut(
            id=m.id,
            name=m.name,
            city_name=m.city.name,
            status=m.status.value,
            area_sq_km=m.area_sq_km,
            discovered_count=counts.get(m.id, 0),
            created_at=m.created_at,
        )
        for m in markets
    ]


@router.get("/{market_id}", response_model=MarketOut, responses={404: {"model": ErrorResponse}})
async def get_market(market_id: int, service: MarketServiceDep):
    return market_out(await service.get(market_id))


@router.get(
    "/{market_id}/stores", response_model=MarketStoresOut, responses={404: {"model": ErrorResponse}}
)
async def market_stores(market_id: int, service: MarketServiceDep):
    """Every store for the dashboard's layers. The client toggles layers without refetching."""
    result = await service.stores(market_id)
    portfolio = sorted(result.portfolio, key=lambda link: link.portfolio_store.row_number)
    by_status = {s: 0 for s in BoundaryStatus}
    for link in portfolio:
        by_status[link.boundary_status] += 1
    return MarketStoresOut(
        market_id=market_id,
        counts=LayerCounts(
            discovered=len(result.discovered),
            portfolio_inside=by_status[BoundaryStatus.INSIDE],
            portfolio_outside=by_status[BoundaryStatus.OUTSIDE],
            portfolio_unlocated=by_status[BoundaryStatus.UNLOCATED],
            matched=sum(1 for link in portfolio if link.matched_discovered_store_id is not None),
        ),
        discovered=[
            DiscoveredStoreOut(
                id=d.id,
                name=d.name,
                category=d.category.name,
                category_slug=d.category.slug,
                latitude=d.latitude,
                longitude=d.longitude,
                address=d.address,
                provider=d.provider,
                provider_place_id=d.provider_place_id,
            )
            for d in result.discovered
        ],
        portfolio=[
            MarketPortfolioStoreOut(
                id=link.portfolio_store.id,
                name=link.portfolio_store.store_name,
                category=link.portfolio_store.category,
                address=link.portfolio_store.address,
                latitude=link.portfolio_store.latitude,
                longitude=link.portfolio_store.longitude,
                boundary_status=link.boundary_status.value,
                geocode_status=link.portfolio_store.geocode_status.value,
                geocode_error=link.portfolio_store.geocode_error,
                matched_discovered_store_id=link.matched_discovered_store_id,
                match_distance_m=link.match_distance_m,
            )
            for link in portfolio
        ],
    )
