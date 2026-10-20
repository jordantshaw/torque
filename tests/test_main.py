import pytest
from pathlib import Path
from app.main import create_app
from app.bike_models import BikeModelError


def test_create_app_loads_valid_bike_models(tmp_path):
    (tmp_path / "a.yaml").write_text(
        "key: m\ndisplay_name: M\nengine: t\nitems: [{key: oil, category: Engine, name: Oil, every_hours: 30, action: S}]\n"
        "notes: []\nsuspension: {settings: [], fixed_values: {}, source: s}\n"
    )
    app = create_app(bike_models_dir=tmp_path, database_url="sqlite:///:memory:")
    assert "m" in app.state.bike_models


def test_create_app_raises_on_invalid_bike_model(tmp_path):
    (tmp_path / "bad.yaml").write_text(
        "key: m\ndisplay_name: M\nengine: t\nitems: [{key: oil, category: Engine, name: Oil, actions: {3: X}}]\n"
        "notes: []\nsuspension: {settings: [], fixed_values: {}, source: s}\n"
    )
    with pytest.raises(BikeModelError):
        create_app(bike_models_dir=tmp_path, database_url="sqlite:///:memory:")
