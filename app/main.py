"""FastAPI app factory.

Wires together the pieces built in earlier tasks: loads and validates all
bike model YAML files at startup (refusing to start if any are invalid),
sets up the database engine/session machinery, and mounts the shared
static assets and Jinja2 templates every page route builds on.
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.bike_models import load_bike_models
from app.db import get_engine, get_sessionmaker, init_db
from app.routes.bikes import bikes_router
from app.routes.home import home_router
from app.routes.maintenance import maintenance_router
from app.routes.rides import rides_router
from app.routes.suspension import suspension_router

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_app(bike_models_dir: Path, database_url: str) -> FastAPI:
    app = FastAPI()

    # Load and validate bike models eagerly: a BikeModelError here propagates
    # uncaught, so the app refuses to start rather than run with bad data.
    app.state.bike_models = load_bike_models(bike_models_dir)

    engine = get_engine(database_url)
    init_db(engine)
    app.state.sessionmaker = get_sessionmaker(engine)

    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(home_router)
    app.include_router(bikes_router)
    app.include_router(maintenance_router)
    app.include_router(rides_router)
    app.include_router(suspension_router)

    @app.exception_handler(HTTPException)
    async def not_found_handler(request: Request, exc: HTTPException):
        if exc.status_code == 404:
            return app.state.templates.TemplateResponse(
                request, "404.html", {}, status_code=404
            )
        return await http_exception_handler(request, exc)

    return app


app = create_app(
    bike_models_dir=Path(os.environ.get("BIKE_MODELS_DIR", "bike_models")),
    database_url=os.environ.get("DATABASE_URL", "sqlite:////data/app.db"),
)
