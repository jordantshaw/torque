"""FastAPI app factory.

Wires together the pieces built in earlier tasks: loads and validates all
bike model YAML files at startup (refusing to start if any are invalid),
sets up the database engine/session machinery, and mounts the shared
static assets and Jinja2 templates every page route builds on.
"""

import mimetypes
import os
from collections.abc import Sequence
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import UndefinedError, pass_context

from app.bike_models import load_bike_models
from app.db import get_engine, get_sessionmaker, init_db
from app.routes.bikes import bikes_router
from app.routes.home import home_router
from app.routes.maintenance import maintenance_router
from app.routes.rides import rides_router
from app.routes.suspension import suspension_router
from app.security import SECURITY_HEADERS, SecurityMiddleware

# The slim image has no mime database entry for the bundled typeface.
mimetypes.add_type("font/woff2", ".woff2")

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"


def _unit_for(context, unit):
    unit = unit or context.get("unit")
    if unit is None:
        # Falling back to hours would silently mislabel a km or mi bike.
        raise UndefinedError("this filter needs a `unit` in the template context or as an argument")
    return unit


@pass_context
def display_amount(context, value, unit=None) -> str:
    """Show a stored value in the bike's unit (hours, km or mi). The unit
    comes from the template context unless one is passed explicitly."""
    return _unit_for(context, unit).show(value)


@pass_context
def input_amount(context, value, unit=None) -> str:
    """Like `amt`, but at the precision needed to prefill an input without
    changing the stored value when it is saved untouched."""
    return _unit_for(context, unit).edit_value(value)


def create_app(
    bike_models_dir: Path,
    database_url: str,
    *,
    allowed_hosts: Sequence[str] = (),
    username: str | None = None,
    password: str | None = None,
) -> FastAPI:
    """Build the app. `allowed_hosts` adds host names to serve beyond localhost
    and IP addresses; `username` and `password` (set both or neither) put the
    whole app behind HTTP Basic authentication. See `app.security`."""
    if bool(username) != bool(password):
        raise ValueError("Set both TORQUE_USERNAME and TORQUE_PASSWORD, or neither.")

    # The generated API docs (/docs, /redoc, /openapi.json) aren't needed.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    # Load and validate bike models eagerly: a BikeModelError here propagates
    # uncaught, so the app refuses to start rather than run with bad data.
    app.state.bike_models = load_bike_models(bike_models_dir)

    engine = get_engine(database_url)
    init_db(engine)
    app.state.sessionmaker = get_sessionmaker(engine)

    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.templates.env.filters["amt"] = display_amount
    app.state.templates.env.filters["amt_input"] = input_amount

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

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        # No traceback or detail for the visitor (the server log has it).
        return PlainTextResponse(
            "Internal Server Error", status_code=500, headers=SECURITY_HEADERS
        )

    app.add_middleware(
        SecurityMiddleware, allowed_hosts=allowed_hosts, username=username, password=password
    )

    return app


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


app = create_app(
    bike_models_dir=Path(os.environ.get("BIKE_MODELS_DIR", "bike_models")),
    database_url=os.environ.get("DATABASE_URL", "sqlite:////data/app.db"),
    allowed_hosts=_csv(os.environ.get("ALLOWED_HOSTS", "")),
    username=os.environ.get("TORQUE_USERNAME") or None,
    password=os.environ.get("TORQUE_PASSWORD") or None,
)
