"""Cross-check: the KTM model file against an independent, column-by-column
reading of the manual's service schedule (pages 39-40).

The manual prints one column per interval with a mark in each row that
applies; the sets below mirror those columns rather than the item-by-item
layout of the YAML, so the two are independent readings of the same pages.
A row marked in both "every 20 hours" and "every 40 hours" is every 20.
"""

from pathlib import Path

from app.bike_models import load_bike_model_file

PATH = Path(__file__).parent.parent / "bike_models" / "ktm-300-xcw-2017.yaml"

# Required work (10.2)
ONCE_AFTER_1H = {
    "Electrical system function", "Tire condition", "Tire air pressure", "Rim run-out",
    "Spoke tension", "Chain tension", "Steering head bearing play", "Hoses and sleeves",
    "Antifreeze and coolant level", "Throttle cables", "Screws and nuts", "Headlight setting",
    "Final check and test ride",
}
ONCE_AFTER_5H = {"Gear oil", "Final check and test ride"}
EVERY_20H = {
    "Electrical system function", "Battery (check and charge)", "Front brake linings",
    "Rear brake linings", "Brake discs", "Brake lines", "Rear brake fluid level",
    "Foot brake lever free travel", "Frame and swingarm", "Swingarm bearing play",
    "Shock absorber heim joints", "Tire condition", "Tire air pressure", "Wheel bearing play",
    "Wheel hubs", "Rim run-out", "Spoke tension", "Chain, sprockets and chain guide",
    "Chain tension", "Moving parts (grease)", "Hydraulic clutch fluid level",
    "Front brake fluid level", "Hand brake lever free travel", "Steering head bearing play",
    "Inlet membrane", "Hoses and sleeves", "Antifreeze and coolant level", "Cables",
    "Throttle cables", "Air filter and air filter box", "Main silencer glass fiber packing",
    "Screws and nuts", "Headlight setting", "Idle", "Final check and test ride",
}
EVERY_40H_ONLY = {"Spark plug and spark plug connector", "Gear oil"}

# Recommended work (10.3), normal use
RECOMMENDED_ONCE_AFTER_10H = {"Fork service"}
RECOMMENDED_EVERY_40H = {"Fork service", "Shock absorber service", "Starter drive", "Minor engine service"}
RECOMMENDED_EVERY_80H = {"Carburetor components", "Piston and cylinder", "Major engine service"}


def _expected():
    expected = {}
    for name in EVERY_20H:
        expected[name] = 20
    for name in EVERY_40H_ONLY | RECOMMENDED_EVERY_40H:
        expected[name] = 40
    for name in RECOMMENDED_EVERY_80H:
        expected[name] = 80
    once = {}
    for hour, names in ((1, ONCE_AFTER_1H), (5, ONCE_AFTER_5H), (10, RECOMMENDED_ONCE_AFTER_10H)):
        for name in names:
            once.setdefault(name, []).append(hour)
    return {n: (every, tuple(once.get(n, ()))) for n, every in expected.items()}


def _actual(model):
    return {i.name: (i.schedule.every_hours, i.schedule.once_at) for i in model.items}


def test_300_xcw_schedule_matches_the_manuals_columns():
    model = load_bike_model_file(PATH)[0]
    assert _actual(model) == _expected()


def test_250_and_300_variants_share_the_300_schedule():
    models = {m.key: m for m in load_bike_model_file(PATH)}
    for key in ("ktm-300-exc-2017", "ktm-250-xcw-2017", "ktm-250-exc-2017"):
        assert _actual(models[key]) == _actual(models["ktm-300-xcw-2017"])


def test_125_xcw_drops_electric_start_rows_and_services_the_piston_sooner():
    models = {m.key: m for m in load_bike_model_file(PATH)}
    small = _actual(models["ktm-125-xcw-2017"])
    big = _actual(models["ktm-300-xcw-2017"])
    assert set(big) - set(small) == {"Battery (check and charge)", "Starter drive"}
    assert small["Piston and cylinder"] == (40, ())
    assert big["Piston and cylinder"] == (80, ())
    assert {k: v for k, v in small.items() if k != "Piston and cylinder"} == {
        k: v for k, v in big.items() if k in small and k != "Piston and cylinder"
    }
