"""Cross-check: the real Beta 300 RR Race model file against an
independent transcription of the manual's printed grid.

EXPECTED_GRID is transcribed directly from the spec's "Transcribed
schedule (250/300)" table (docs/superpowers/specs/2026-10-19-moto-maintenance-design.md),
not derived from the YAML file. This is intentional duplication: the
point is that two independent readings of the manual agree, not that
the test is DRY with the fixture it's checking.

"All" expands to hours {3, 30, 60, 90, 120, 150, 180} per the spec.
"""

from pathlib import Path

from app.bike_models import load_bike_model
from app.services.schedule import ActionsSchedule

MODEL_PATH = Path(__file__).parent.parent / "bike_models" / "beta-300-rr-race-2026.yaml"

ALL_HOURS = (3, 30, 60, 90, 120, 150, 180)


def _all(action: str) -> dict:
    return {hour: action for hour in ALL_HOURS}


EXPECTED_GRID: list[tuple[str, str, dict]] = [
    # Engine
    ("Engine", "Gear and clutch oil", {3: "S", 30: "S", 60: "S", 90: "S", 120: "S", 150: "S", 180: "S"}),
    ("Engine", "Spark plug", {3: "C", 60: "S", 120: "S", 180: "S"}),
    ("Engine", "Head screws", {3: "T"}),
    ("Engine", "Engine clamping screws to the frame", _all("C")),
    ("Engine", "Kick start and gearchange lever screws", _all("C")),
    ("Engine", "Spark plug cap", _all("P")),
    ("Engine", "Driving clutch disks (coated)", {30: "C", 60: "C", 90: "S", 120: "C", 150: "C", 180: "S"}),
    ("Engine", "Clutch springs length", {30: "C", 60: "C", 90: "S", 120: "C", 150: "C", 180: "S"}),
    ("Engine", "Clutch hub - clutch bell", {30: "C", 60: "C", 90: "C", 120: "C", 150: "C", 180: "C"}),
    ("Engine", "Cylinder", {60: "C", 120: "C", 180: "C"}),
    ("Engine", "Piston and segments", {60: "S", 120: "S", 180: "S"}),
    ("Engine", "Connecting rod", {90: "S", 180: "S"}),
    ("Engine", "Drive shaft bearings and seals", {90: "S", 180: "S"}),
    ("Engine", "Surface appearance of the gearbox", {90: "C", 180: "C"}),
    ("Engine", "Gearbox bearings (primary shaft)", {90: "S", 180: "S"}),
    ("Engine", "Water pump oil seal", {90: "S", 180: "S"}),
    ("Engine", "Exhaust valve", {60: "C/P", 150: "C/P"}),
    ("Engine", "Reed valve", {60: "C", 120: "C", 180: "C"}),
    ("Engine", "Noise-absorbing material of the silencer", {30: "S", 60: "S", 90: "S", 120: "S", 150: "S", 180: "S"}),

    # Carburetor -- row covers 4 named parts, each gets the row's action letters
    ("Carburetor", "Tightness", _all("C")),
    ("Carburetor", "Idling setting", _all("C")),
    ("Carburetor", "Fuel pipe", _all("C")),
    ("Carburetor", "Breather pipe", _all("C")),

    # Assembling groups -- row covers 8 named parts
    ("Assembling groups", "Coolant system tightness and level", _all("C")),
    ("Assembling groups", "Exhaust manifold tightness", _all("C")),
    ("Assembling groups", "Drives sliding and regulation", _all("C")),
    ("Assembling groups", "Liquid level clutch pump", _all("C")),
    ("Assembling groups", "Final transmission", _all("C")),
    ("Assembling groups", "OBD2 error memory read", _all("C")),
    ("Assembling groups", "Electric system (blow out and grease main connections)", _all("C")),
    ("Assembling groups", "12V battery check/recharge", _all("C")),
    ("Assembling groups", "Airbox and air filter", _all("P")),

    # Brakes -- row covers 4 named parts
    ("Brakes", "Liquid level, pads thickness", _all("C")),
    ("Brakes", "Disc thickness", _all("C")),
    ("Brakes", "Pipe tightness", _all("C")),
    ("Brakes", "Idle travel levers and drives sliding", _all("C")),

    # Cycling -- row covers 9 named parts
    ("Cycling", "Chassis", _all("C")),
    ("Cycling", "Swing arm", _all("C")),
    ("Cycling", "Mobile parts", _all("C")),
    ("Cycling", "Shock absorber and telescopic fork", _all("C")),
    ("Cycling", "Rear suspension linkage", _all("C")),
    ("Cycling", "Fork cover", _all("C")),
    ("Cycling", "Fuel lines", _all("C")),
    ("Cycling", "Bearings of steering", _all("C")),
    ("Cycling", "Bolts", _all("C")),

    # Wheels -- row covers 3 named parts
    ("Wheels", "Wheel spokes and rim coaxiality", _all("C")),
    ("Wheels", "Tyres (wear and pressure)", _all("C")),
    ("Wheels", "Bearings clearance", _all("C")),
]


def _sort_key(entry: tuple[str, str, dict]) -> tuple[str, str, tuple]:
    category, name, actions = entry
    return (category, name, tuple(sorted(actions.items())))


def test_beta_model_matches_manual_grid():
    model = load_bike_model(MODEL_PATH)
    actual = sorted(
        (
            (item.category, item.name, item.schedule.actions)
            for item in model.items
            if isinstance(item.schedule, ActionsSchedule)
        ),
        key=_sort_key,
    )
    expected = sorted(EXPECTED_GRID, key=_sort_key)
    assert actual == expected


def test_beta_model_item_count_matches_manual_row_count():
    model = load_bike_model(MODEL_PATH)
    assert len(model.items) == len(EXPECTED_GRID)


def test_beta_model_has_one_off_note():
    model = load_bike_model(MODEL_PATH)
    assert any("rear sprocket" in note for note in model.notes)


def test_beta_model_suspension_source_notes_2025_caveat():
    model = load_bike_model(MODEL_PATH)
    assert "2025" in model.suspension.source
    assert "2026" in model.suspension.source
    assert len(model.suspension.settings) == 5
    assert model.suspension.fixed_values["Fork spring"] == "REDACTED"
