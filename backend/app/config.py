from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://marketscope:marketscope@localhost:5432/marketscope"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Market guardrails
    max_market_area_sq_km: float = 30.0
    max_provider_requests_per_market: int = 400
    match_radius_m: float = 150.0

    # Store discovery
    places_provider: Literal["overpass", "google", "fixture"] = "overpass"
    google_places_api_key: str | None = None
    overpass_urls: list[str] = Field(
        default_factory=lambda: [
            "https://overpass-api.de/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        ]
    )
    discovery_concurrency: int = 2

    # Geocoding (city boundaries and portfolio rows without coordinates)
    geocoder: Literal["nominatim", "fixture"] = "nominatim"
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    # Nominatim's usage policy requires an identifying User-Agent with contact details.
    nominatim_user_agent: str = "MarketScope/0.1 (take-home exercise)"

    http_timeout_s: float = 40.0
    http_max_attempts: int = 4


@lru_cache
def get_settings() -> Settings:
    return Settings()
