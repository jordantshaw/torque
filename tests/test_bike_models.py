from pathlib import Path
import pytest
from app.bike_models import BikeModelError, load_bike_model, load_bike_model_file, load_bike_models
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
    "invalid_missing_top_level_field.yaml",
    "invalid_missing_item_field.yaml",
])
def test_rejects_invalid_fixtures(filename):
    with pytest.raises(BikeModelError):
        load_bike_model(FIXTURES / filename)


def test_missing_top_level_field_raises_bike_model_error_naming_field_and_file():
    path = FIXTURES / "invalid_missing_top_level_field.yaml"
    with pytest.raises(BikeModelError) as exc_info:
        load_bike_model(path)
    message = str(exc_info.value)
    assert "display_name" in message
    assert str(path) in message


def test_missing_item_field_raises_bike_model_error_naming_field_and_file():
    path = FIXTURES / "invalid_missing_item_field.yaml"
    with pytest.raises(BikeModelError) as exc_info:
        load_bike_model(path)
    message = str(exc_info.value)
    assert "name" in message
    assert str(path) in message


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


def test_item_description_and_page_are_optional_and_loaded(tmp_path):
    path = tmp_path / "m.yaml"
    path.write_text(
        "key: m\ndisplay_name: M\nengine: e\nitems:\n"
        "  - key: a\n    category: C\n    name: A\n    description: Do the thing.\n    page: '12'\n    actions: {10: C}\n"
        "  - key: b\n    category: C\n    name: B\n    actions: {10: C}\n"
    )
    a, b = load_bike_model(path).items
    assert (a.description, a.page) == ("Do the thing.", "12")
    assert (b.description, b.page) == ("", "")


BASE = (
    "key: base\ndisplay_name: Base\nengine: e\nnotes: ['shared note']\nitems:\n"
    "  - key: a\n    category: C\n    name: A\n    description: Check A.\n    every_hours: 20\n    action: C\n    once_at: [1, 5]\n"
    "  - key: b\n    category: C\n    name: B\n    actions: {10: C, 20: S}\n"
    "  - key: c\n    category: C\n    name: C item\n    actions: {10: C}\n"
    "suspension:\n  source: base source\n"
)


def _write(tmp_path, extra=""):
    path = tmp_path / "m.yaml"
    path.write_text(BASE + extra)
    return path


def test_once_at_is_loaded(tmp_path):
    a = load_bike_model(_write(tmp_path)).items[0]
    assert a.schedule.once_at == (1, 5)


@pytest.mark.parametrize("bad", ["[5, 1]", "[0]", "[1, 1]", "['x']", "3"])
def test_once_at_must_be_an_increasing_list_of_positive_ints(tmp_path, bad):
    path = tmp_path / "m.yaml"
    path.write_text(BASE.replace("once_at: [1, 5]", f"once_at: {bad}"))
    with pytest.raises(BikeModelError, match="once_at"):
        load_bike_model(path)


def test_once_at_requires_every_hours(tmp_path):
    path = tmp_path / "m.yaml"
    path.write_text(BASE.replace("actions: {10: C}", "actions: {10: C}\n    once_at: [1]"))
    with pytest.raises(BikeModelError, match="once_at"):
        load_bike_model(path)


def test_variants_inherit_and_apply_overrides(tmp_path):
    path = _write(tmp_path, """variants:
  - key: small
    display_name: Small
    engine: s
    omit: [c]
    overrides:
      b: {every_hours: 40, action: S}
    suspension:
      source: small source
  - key: same
    display_name: Same
    engine: e2
""")
    models = {m.key: m for m in load_bike_model_file(path)}
    assert set(models) == {"base", "small", "same"}

    small = models["small"]
    assert [i.key for i in small.items] == ["a", "b"]
    assert small.items[0].description == "Check A."  # inherited
    assert small.items[1].schedule == EveryHoursSchedule(every_hours=40, action="S")
    assert small.suspension.source == "small source"
    assert small.notes == ["shared note"]
    assert small.display_name == "Small"

    same = models["same"]
    assert [i.key for i in same.items] == ["a", "b", "c"]
    assert same.suspension.source == "base source"  # inherited
    assert models["base"].items[1].schedule.actions == {10: "C", 20: "S"}  # base untouched


def test_variant_referring_to_unknown_item_fails(tmp_path):
    path = _write(tmp_path, "variants:\n  - key: v\n    display_name: V\n    engine: e\n    omit: [nope]\n")
    with pytest.raises(BikeModelError, match="unknown item 'nope'"):
        load_bike_model_file(path)


def test_variant_keys_must_be_unique_across_files(tmp_path):
    (tmp_path / "a.yaml").write_text(BASE)
    (tmp_path / "b.yaml").write_text(BASE.replace("key: base", "key: other") + "variants:\n  - key: base\n    display_name: X\n    engine: e\n")
    with pytest.raises(BikeModelError, match="duplicate"):
        load_bike_models(tmp_path)
