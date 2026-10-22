"""Cross-check: the real Beta 300 RR Race model file against an
independent transcription of the manual's printed grid.

EXPECTED_GRID is transcribed directly from the manual's printed schedule
(Beta RR 2T owner's manual, pages 83-84; the 250/300 rows), not derived from
the YAML file. This is intentional duplication: the
point is that two independent readings of the manual agree, not that
the test is DRY with the fixture it's checking.

"All" expands to hours {3, 30, 60, 90, 120, 150, 180}, as printed.
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

    # Chassis & suspension -- row covers 9 named parts
    ("Chassis & suspension", "Chassis", _all("C")),
    ("Chassis & suspension", "Swing arm", _all("C")),
    ("Chassis & suspension", "Mobile parts", _all("C")),
    ("Chassis & suspension", "Shock absorber and telescopic fork", _all("C")),
    ("Chassis & suspension", "Rear suspension linkage", _all("C")),
    ("Chassis & suspension", "Fork cover", _all("C")),
    ("Chassis & suspension", "Fuel lines", _all("C")),
    ("Chassis & suspension", "Bearings of steering", _all("C")),
    ("Chassis & suspension", "Bolts", _all("C")),

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


# ---- Variants: the same manual covers the 125, 200 and 250 (page 83)
# The 125/200 rows below are read straight off the printed grid, where the
# manual splits "125/200" from "250/300".
SMALL_BORE_ROWS = {
    "Driving clutch disks (coated)": {30: "C", 60: "S", 90: "C", 120: "S", 150: "C", 180: "S"},
    "Connecting rod": {60: "S", 120: "S", 180: "S"},
    "Drive shaft bearings and seals": {60: "S", 120: "S", 180: "S"},
    "Surface appearance of the gearbox": {60: "C", 120: "C", 180: "C"},
    "Gearbox bearings (primary shaft)": {60: "S", 120: "S", 180: "S"},
}


def _models():
    from app.bike_models import load_bike_model_file

    return {m.key: m for m in load_bike_model_file(MODEL_PATH)}


def _schedule(model, name):
    return next(i for i in model.items if i.name == name).schedule


def test_250_matches_300():
    models = _models()
    assert [(i.name, i.schedule) for i in models["beta-250-rr-race-2026"].items] == [
        (i.name, i.schedule) for i in models["beta-300-rr-race-2026"].items
    ]


def test_125_and_200_use_the_small_bore_rows():
    models = _models()
    for key in ("beta-200-rr-race-2026", "beta-125-rr-race-2026"):
        for name, actions in SMALL_BORE_ROWS.items():
            assert _schedule(models[key], name).actions == actions, (key, name)
        piston = _schedule(models[key], "Piston and segments")
        assert (piston.every_hours, piston.action) == (40, "S")


def test_other_rows_are_shared_across_all_four():
    models = _models()
    changed = set(SMALL_BORE_ROWS) | {"Piston and segments"}
    base = {i.name: i.schedule for i in models["beta-300-rr-race-2026"].items if i.name not in changed}
    for key in ("beta-200-rr-race-2026", "beta-125-rr-race-2026"):
        other = {i.name: i.schedule for i in models[key].items if i.name not in changed}
        for name, schedule in other.items():
            assert base[name] == schedule, (key, name)


def test_only_the_125_omits_the_battery():
    models = _models()
    names = lambda key: {i.name for i in models[key].items}
    assert "12V battery check/recharge" in names("beta-200-rr-race-2026")
    assert "12V battery check/recharge" not in names("beta-125-rr-race-2026")


def test_125_200_use_their_own_suspension_sheet():
    models = _models()
    small = models["beta-200-rr-race-2026"].suspension
    assert small.fixed_values["Shock spring"] == "REDACTED"
    assert small.fixed_values["Fork spring"] == "REDACTED"
    assert models["beta-250-rr-race-2026"].suspension.fixed_values["Shock spring"] == "REDACTED"


def test_schedule_pages_follow_the_manuals_layout():
    """Engine and carburetor rows are printed on page 83; assembling groups,
    brakes, chassis and wheels on page 84."""
    from app.bike_models import load_bike_model

    model = load_bike_model(MODEL_PATH)
    for item in model.items:
        expected = "83" if item.category in ("Engine", "Carburetor") else "84"
        assert item.schedule_page == expected, item.name
