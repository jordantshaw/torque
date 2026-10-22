"""Database engine and session setup.

`get_session` is a FastAPI dependency that reads the app-wide sessionmaker
off `request.app.state.sessionmaker` (set up once at app startup) and yields
a fresh `Session` per request, closing it when the request is done.
"""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base


def get_engine(database_url: str) -> Engine:
    return create_engine(database_url)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)


def _add_missing_columns(engine: Engine) -> None:
    """Upgrade databases created before a column existed (create_all only
    makes missing tables, never alters existing ones)."""
    columns = {c["name"] for c in inspect(engine).get_columns("bikes")}
    if "distance_unit" not in columns:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE bikes ADD COLUMN distance_unit VARCHAR NOT NULL DEFAULT 'km'"
            ))


def get_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.sessionmaker() as session:
        yield session
