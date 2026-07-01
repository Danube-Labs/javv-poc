"""FastAPI app factory. Conventions (api-design.md): `/api/v1` prefix for data routes, snake_case,
`extra="forbid"` request models, the single problem-details error envelope. Ingest + the versioned
index bootstrap land in the next slices; this is the runnable skeleton."""

from fastapi import FastAPI

from backend.core.errors import register_error_handlers
from backend.core.lifespan import lifespan
from backend.routers import health


def create_app() -> FastAPI:
    app = FastAPI(title="JAVV backend", version="0.1.0", lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(health.router)
    return app


app = create_app()
