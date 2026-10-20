import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "bike_models" / "conftest_bike.yaml"


@pytest.fixture
def bike_models_dir(tmp_path):
    shutil.copy(FIXTURE, tmp_path / "conftest_bike.yaml")
    return tmp_path


@pytest.fixture
def client(bike_models_dir, tmp_path):
    app = create_app(bike_models_dir=bike_models_dir, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    return TestClient(app)


@pytest.fixture
def db_session(client):
    with client.app.state.sessionmaker() as session:
        yield session
