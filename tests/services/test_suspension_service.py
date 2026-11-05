from app.models import Ride
from app.services.carb import Change
from app.services.suspension import history


def ride(id, date, **settings):
    return Ride(id=id, bike_id=1, date=date, hours=1.0, **settings)


def test_rides_without_settings_are_left_out():
    assert history([ride(1, "2026-01-01")]) == []


def test_first_recorded_ride_is_the_starting_setup_with_its_values():
    [entry] = history([ride(1, "2026-01-01"), ride(2, "2026-01-02", fork_rebound=12, shock_hsc=1.5)])
    assert entry.ride.id == 2
    assert entry.is_start
    assert entry.changes == [
        Change("Fork rebound", "not recorded", "12"),
        Change("Shock high-speed compression", "not recorded", "1.5"),
    ]


def test_only_rides_that_changed_something_appear_newest_first():
    rides = [
        ride(3, "2026-01-15", fork_rebound=10),
        ride(1, "2026-01-01", fork_rebound=12),
        ride(2, "2026-01-08", fork_rebound=12),
    ]
    entries = history(rides)
    assert [e.ride.id for e in entries] == [3, 1]
    assert entries[0].changes == [Change("Fork rebound", "12", "10")]


def test_blank_value_is_not_a_change_and_compares_with_the_last_recorded_one():
    rides = [
        ride(1, "2026-01-01", fork_rebound=12, sag_rider=105),
        ride(2, "2026-01-08", fork_rebound=12),
        ride(3, "2026-01-15", sag_rider=100),
    ]
    entries = history(rides)
    assert [e.ride.id for e in entries] == [3, 1]
    assert entries[0].changes == [Change("Rider sag", "105 mm", "100 mm")]


def test_same_date_rides_order_by_id():
    rides = [ride(2, "2026-01-01", fork_rebound=10), ride(1, "2026-01-01", fork_rebound=12)]
    assert history(rides)[0].changes == [Change("Fork rebound", "12", "10")]


def test_current_setup_is_the_latest_recorded_value_of_each_setting():
    from app.services.suspension import current

    rides = [
        ride(1, "2026-01-01", fork_rebound=12, sag_rider=105),
        ride(2, "2026-01-08", fork_rebound=10),
    ]
    setup = current(rides)
    assert setup["Fork rebound"] == "10"
    assert setup["Rider sag"] == "105 mm"
    assert setup["Fork compression"] is None
    assert list(current([]).values()) == [None] * 7
