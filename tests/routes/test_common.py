import pytest

from app.routes.common import parse_date, parse_reading
from app.services.units import HOURS, KM_PER_MILE, MILES


def test_parse_date():
    assert parse_date("2026-02-01") == ("2026-02-01", None)
    assert parse_date("") == (None, "Date is required.")
    assert parse_date("not a date") == (None, "Date must be a valid date.")


def test_parse_reading_converts_to_the_stored_unit():
    value, error = parse_reading("100", MILES, "Odometer", allow_zero=True)
    assert error is None and value == pytest.approx(100 * KM_PER_MILE)
    assert parse_reading("1.5", HOURS, "Hours", allow_zero=True) == (1.5, None)


@pytest.mark.parametrize("raw", ["abc", "", None])
def test_parse_reading_rejects_non_numbers(raw):
    assert parse_reading(raw, HOURS, "Hours", allow_zero=True) == (None, "Hours must be a number.")


def test_parse_reading_zero_is_allowed_for_a_reading_but_not_a_ride():
    assert parse_reading("0", HOURS, "Hours", allow_zero=True) == (0.0, None)
    assert parse_reading("0", HOURS, "Hours", allow_zero=False) == (None, "Hours must be greater than zero.")
    assert parse_reading("-1", HOURS, "Engine hours", allow_zero=True) == (None, "Engine hours must be zero or greater.")
    assert parse_reading("-1", HOURS, "Hours", allow_zero=False) == (None, "Hours must be greater than zero.")
