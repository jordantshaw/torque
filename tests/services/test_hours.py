from datetime import date
from app.services.hours import HoursEventInput, current_hours


def test_current_hours_empty_is_zero():
    assert current_hours([]) == 0


def test_current_hours_set_then_ride_accumulates():
    events = [
        HoursEventInput(1, date(2026, 1, 1), "set", 10),
        HoursEventInput(2, date(2026, 1, 5), "ride", 3),
    ]
    assert current_hours(events) == 13


def test_current_hours_set_replaces_running_total():
    events = [
        HoursEventInput(1, date(2026, 1, 1), "ride", 5),
        HoursEventInput(2, date(2026, 1, 5), "set", 20),
        HoursEventInput(3, date(2026, 1, 10), "ride", 3),
    ]
    assert current_hours(events) == 23


def test_current_hours_orders_by_date_then_id_for_same_date():
    # same date: id=1 (set to 50) must replay before id=2 (ride +2) -> 52
    events = [
        HoursEventInput(2, date(2026, 1, 1), "ride", 2),
        HoursEventInput(1, date(2026, 1, 1), "set", 50),
    ]
    assert current_hours(events) == 52
