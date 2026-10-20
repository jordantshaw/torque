"""FastAPI app factory.

Wires together the pieces built in earlier tasks: loads and validates all
bike model YAML files at startup (refusing to start if any are invalid),
sets up the database engine/session machinery, and mounts the shared
static assets and Jinja2 templates every page route builds on.

No routes are registered here yet -- those are added by later tasks.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.bike_models import load_bike_models
from app.db import get_engine, get_sessionmaker, init_db

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

    return app
