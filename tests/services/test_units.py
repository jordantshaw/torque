import pytest

from app.services.units import HOURS, KM, KM_PER_MILE, MILES, unit_for


def test_hours_bikes_always_use_hours():
    assert unit_for("hours", "mi") is HOURS
    assert unit_for("hours", None) is HOURS


def test_km_bikes_default_to_km_and_honor_miles_preference():
    assert unit_for("km", None) is KM
    assert unit_for("km", "km") is KM
    assert unit_for("km", "mi") is MILES


def test_show_formats_without_trailing_zeros():
    assert HOURS.show(7.0) == "7"
    assert HOURS.show(7.25) == "7.25"
    assert HOURS.show(None) == ""


def test_miles_convert_from_stored_km_and_back():
    assert MILES.show(KM_PER_MILE * 10) == "10"
    assert MILES.to_stored(10) == pytest.approx(10 * KM_PER_MILE)
    assert KM.to_stored(42) == 42


def test_service_label():
    assert HOURS.service_label(30) == "30-hour service"
    assert KM.service_label(500) == "500 km service"
    assert MILES.service_label(KM_PER_MILE * 100) == "100 mi service"


def test_large_values_never_switch_to_exponent_notation():
    assert KM.show(1_000_000) == "1000000"
    assert KM.show(20_000) == "20000"
    assert HOURS.show(0.001) == "0"  # rounds away, and no "-0"/"0.00"
    assert HOURS.show(-0.001) == "0"


def test_edit_value_keeps_enough_precision_to_round_trip():
    assert MILES.show(100) == "62.1"  # for display
    assert MILES.edit_value(100) == "62.1371"  # for prefilling an input
    assert MILES.to_stored(float(MILES.edit_value(100))) == pytest.approx(100, abs=0.001)
    assert KM.edit_value(None) == ""
