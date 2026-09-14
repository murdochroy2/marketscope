from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_markets, routes_portfolio, routes_reference
from app.api.deps import AppState
from app.api.errors import register_error_handlers
from app.config import Settings, get_settings
from app.db import make_engine, make_session_factory
from app.jobs.market_pipeline import MarketPipeline, recover_interrupted_runs
from app.jobs.runner import JobRunner
from app.providers.factory import Providers, build_providers

logger = logging.getLogger("marketscope")


def create_app(settings: Settings | None = None, providers: Providers | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            engine = make_engine(settings.database_url)
            stack.push_async_callback(engine.dispose)
            session_factory = make_session_factory(engine)
            live_providers = providers or await build_providers(settings, stack)
            runner = JobRunner()
            stack.push_async_callback(runner.shutdown)

            recovered = await recover_interrupted_runs(session_factory)
            if recovered:
                logger.warning("marked %s interrupted run(s) as failed", recovered)

            app.state.container = AppState(
                settings=settings,
                session_factory=session_factory,
                providers=live_providers,
                runner=runner,
                pipeline=MarketPipeline(session_factory, live_providers, settings),
            )
            logger.info(
                "places provider=%s geocoder=%s",
                live_providers.places.name,
                live_providers.geocoder.name,
            )
            yield

    app = FastAPI(title="MarketScope API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    for module in (routes_reference, routes_portfolio, routes_markets):
        app.include_router(module.router, prefix="/api")

    @app.get("/api/health", tags=["meta"])
    async def health() -> dict:
        container: AppState = app.state.container
        return {
            "status": "ok",
            "places_provider": container.providers.places.name,
            "geocoder": container.providers.geocoder.name,
            "max_market_area_sq_km": settings.max_market_area_sq_km,
        }

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
