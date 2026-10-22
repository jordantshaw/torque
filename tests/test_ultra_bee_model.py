"""Cross-check: the Ultra Bee model file against an independent, column-by-
column reading of the manual's maintenance schedule table (page 10.2).

The manual prints one column per interval with a mark in each row that
applies. EXPECTED_COLUMNS mirrors that layout (interval -> {item: action}),
deliberately not the item-by-item layout of the YAML, so the two are
independent readings of the same page. "every rider" and the 12/24-month
columns' time component are not tracked as items (see the model's notes).
"""

from pathlib import Path

from app.bike_models import load_bike_model
from app.services.schedule import ActionsSchedule

MODEL_PATH = Path(__file__).parent.parent / "bike_models" / "surron-ultra-bee-2026.yaml"

EXPECTED_COLUMNS: dict[int, dict[str, str]] = {
    100: {
        "Brake pads (wear)": "C", "Chain": "C/R", "Brake fluid (DOT4)": "C", "Wheel spokes": "R",
    },
    500: {
        "Brake pads (wear)": "C", "Brake disc (wear)": "C", "Chain": "C/R",
    },
    2000: {
        "Brake pads (wear)": "C", "Chain": "C/R", "Sprockets (front and rear)": "C",
        "Primary belt and primary drive pulley": "C/R", "Brake fluid (DOT4)": "C",
        "Bearings": "C", "Swingarm protection block": "C", "Tilt switch": "C", "Screw torque": "C",
    },
    5000: {
        "Brake pads (wear)": "C/S", "Brake disc (wear)": "C/S", "Chain": "C/S",
        "Sprockets (front and rear)": "C/S", "Front fork and rear shock": "C/R",
        "Bearings": "C/R", "Wheel spokes": "R",
    },
    10000: {
        "Brake pads (wear)": "C/S", "Brake disc (wear)": "C/S", "Chain": "C/S",
        "Sprockets (front and rear)": "C/S", "Primary belt and primary drive pulley": "C/S",
        "Front fork and rear shock": "C/R", "Brake fluid (DOT4)": "C/S", "Bearings": "C/S",
        "Wheel spokes": "R", "Swingarm protection block": "C/S",
    },
    20000: {
        "Tires (wear)": "S", "Brake pads (wear)": "S", "Brake disc (wear)": "S", "Chain": "S",
        "Sprockets (front and rear)": "C/S", "Primary belt and primary drive pulley": "S",
        "Swingarm protection block": "C/S",
    },
}


def test_model_is_distance_based():
    model = load_bike_model(MODEL_PATH)
    assert model.unit == "km"
    assert model.upcoming_window == 50


def test_schedule_matches_manual_table_column_by_column():
    model = load_bike_model(MODEL_PATH)
    actual: dict[int, dict[str, str]] = {}
    for item in model.items:
        assert isinstance(item.schedule, ActionsSchedule), item.name
        for km, action in item.schedule.actions.items():
            actual.setdefault(km, {})[item.name] = action
    assert actual == EXPECTED_COLUMNS


def test_every_item_has_a_note_free_unique_key():
    model = load_bike_model(MODEL_PATH)
    keys = [i.key for i in model.items]
    assert len(keys) == len(set(keys)) == 13
