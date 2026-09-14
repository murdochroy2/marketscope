"""Builds concrete providers from settings. The only module that knows which API is live."""

from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass

import httpx

from app.config import Settings
from app.providers.base import Geocoder, PlacesProvider
from app.providers.fixtures import FixtureGeocoder, FixturePlacesProvider
from app.providers.google_places import GooglePlacesProvider
from app.providers.http import RateLimiter, ResilientHttpClient, RetryPolicy
from app.providers.nominatim import NominatimGeocoder
from app.providers.overpass import OverpassProvider


@dataclass(slots=True)
class Providers:
    places: PlacesProvider
    geocoder: Geocoder


async def build_providers(settings: Settings, stack: AsyncExitStack) -> Providers:
    retry = RetryPolicy(max_attempts=settings.http_max_attempts)

    async def client(**kwargs) -> httpx.AsyncClient:
        return await stack.enter_async_context(
            httpx.AsyncClient(timeout=settings.http_timeout_s, **kwargs)
        )

    places: PlacesProvider
    match settings.places_provider:
        case "overpass":
            http = ResilientHttpClient(
                await client(headers={"User-Agent": settings.nominatim_user_agent}),
                rate_limiter=RateLimiter(min_interval_s=1.0),
                retry=retry,
            )
            places = OverpassProvider(http, settings.overpass_urls)
        case "google":
            http = ResilientHttpClient(
                await client(), rate_limiter=RateLimiter(min_interval_s=0.1), retry=retry
            )
            places = GooglePlacesProvider(http, settings.google_places_api_key or "")
        case "fixture":
            places = FixturePlacesProvider()

    geocoder: Geocoder
    match settings.geocoder:
        case "nominatim":
            http = ResilientHttpClient(
                await client(headers={"User-Agent": settings.nominatim_user_agent}),
                rate_limiter=RateLimiter(min_interval_s=1.1),
                retry=retry,
            )
            geocoder = NominatimGeocoder(http, settings.nominatim_url)
        case "fixture":
            geocoder = FixtureGeocoder()

    return Providers(places=places, geocoder=geocoder)
