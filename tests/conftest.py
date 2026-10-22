import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# app.main builds a module-level `app` at import time from DATABASE_URL /
# BIKE_MODELS_DIR env vars (for `uvicorn app.main:app` in Docker). Its default
# DATABASE_URL points at /data/app.db, the container's volume mount, which
# doesn't exist on a bare test host. Point it at an in-memory db before
# importing so collecting this module doesn't fail outside Docker; no test
# fixture uses this module-level instance, they all call create_app() directly.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.main import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "bike_models" / "conftest_bike.yaml"


@pytest.fixture
def bike_models_dir(tmp_path):
    shutil.copy(FIXTURE, tmp_path / "conftest_bike.yaml")
    return tmp_path


@pytest.fixture
def client(bike_models_dir, tmp_path):
    app = create_app(bike_models_dir=bike_models_dir, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    return TestClient(app, base_url="http://localhost")


@pytest.fixture
def db_session(client):
    with client.app.state.sessionmaker() as session:
        yield session
