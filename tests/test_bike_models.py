from pathlib import Path
import pytest
from app.bike_models import load_bike_model, load_bike_models, BikeModelError
from app.services.schedule import ActionsSchedule, EveryHoursSchedule

FIXTURES = Path(__file__).parent / "fixtures" / "bike_models"


def test_load_valid_minimal_model():
    model = load_bike_model(FIXTURES / "valid_minimal.yaml")
    assert model.key == "test-bike-1"
    by_key = {item.key: item for item in model.items}
    assert isinstance(by_key["oil"].schedule, EveryHoursSchedule)
    assert isinstance(by_key["head_screws"].schedule, ActionsSchedule)


@pytest.mark.parametrize("filename", [
    "invalid_unknown_action.yaml",
    "invalid_non_positive_hour.yaml",
    "invalid_both_actions_and_every_hours.yaml",
    "invalid_neither.yaml",
    "invalid_duplicate_item_key.yaml",
])
def test_rejects_invalid_fixtures(filename):
    with pytest.raises(BikeModelError):
        load_bike_model(FIXTURES / filename)


def test_load_bike_models_returns_dict_keyed_by_model_key(tmp_path):
    import shutil
    shutil.copy(FIXTURES / "valid_minimal.yaml", tmp_path / "a.yaml")
    shutil.copy(FIXTURES / "valid_second.yaml", tmp_path / "b.yaml")
    models = load_bike_models(tmp_path)
    assert set(models) == {"test-bike-1", "test-bike-2"}


def test_load_bike_models_rejects_duplicate_model_key_across_files(tmp_path):
    import shutil
    shutil.copy(FIXTURES / "valid_minimal.yaml", tmp_path / "a.yaml")
    shutil.copy(FIXTURES / "valid_minimal.yaml", tmp_path / "b.yaml")
    with pytest.raises(BikeModelError):
        load_bike_models(tmp_path)
