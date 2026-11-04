from app.models import CarbSetting
from app.services.carb import (
    NOT_RECORDED,
    Change,
    changes_between,
    current,
    history,
    previous_for,
)


def entry(id, date, main="", pilot="", **kwargs):
    return CarbSetting(id=id, bike_id=1, date=date, main_jet=main, pilot_jet=pilot, **kwargs)


def test_current_is_the_latest_date():
    a = entry(1, "2026-03-01", main="175")
    b = entry(2, "2026-01-01", main="170")
    assert current([a, b]) is a
    assert current([]) is None


def test_same_date_later_id_wins():
    a = entry(1, "2026-03-01", main="175")
    b = entry(2, "2026-03-01", main="172")
    assert current([b, a]) is b


def test_previous_for_uses_date_order():
    a = entry(1, "2026-03-01")
    b = entry(2, "2026-06-01")
    assert previous_for([a, b], "2026-04-01") is a
    assert previous_for([a, b], "2026-02-01") is None
    assert previous_for([a, b], "2026-06-01") is b


def test_history_shows_only_changed_values():
    start = entry(1, "2026-01-01", main="175", pilot="38")
    later = entry(2, "2026-02-01", main="172", pilot="38")
    newest = history([start, later])[0]
    assert newest.setting is later
    assert not newest.is_start
    assert newest.changes == [Change("Main jet", "175", "172")]


def test_history_marks_the_oldest_as_the_start_with_full_values():
    start = entry(1, "2026-01-01", main="175", pilot="38")
    later = entry(2, "2026-02-01", main="172", pilot="38")
    oldest = history([start, later])[-1]
    assert oldest.is_start
    assert oldest.changes == [
        Change("Main jet", NOT_RECORDED, "175"),
        Change("Pilot jet", NOT_RECORDED, "38"),
    ]


def test_blanking_a_value_is_a_change():
    start = entry(1, "2026-01-01", main="175", pilot="38")
    later = entry(2, "2026-02-01", main="175", pilot="")
    assert history([start, later])[0].changes == [Change("Pilot jet", "38", NOT_RECORDED)]


def test_identical_neighbours_give_empty_changes():
    a = entry(1, "2026-01-01", main="175")
    b = entry(2, "2026-02-01", main="175")
    assert history([a, b])[0].changes == []


def test_history_after_removing_the_oldest_promotes_the_next():
    later = entry(2, "2026-02-01", main="172", pilot="38")
    only = history([later])
    assert len(only) == 1
    assert only[0].is_start
    assert only[0].changes == [
        Change("Main jet", NOT_RECORDED, "172"),
        Change("Pilot jet", NOT_RECORDED, "38"),
    ]


def test_changes_between_without_previous_lists_non_blank_values():
    values = {"main_jet": "175", "needle": "", "pilot_jet": "38"}
    assert changes_between(None, values) == [
        Change("Main jet", NOT_RECORDED, "175"),
        Change("Pilot jet", NOT_RECORDED, "38"),
    ]
