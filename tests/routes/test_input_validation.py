"""Hostile or malformed input is rejected cleanly: never a crash, never stored."""

import pytest

from app.models import Bike, HoursEvent, Ride, ServiceRecord
from app.routes.common import MAX_NICKNAME, MAX_NOTES, parse_ids


@pytest.fixture
def bike(db_session):
    bike = Bike(nickname="Race Bike", model_key="test-bike")
    db_session.add(bike)
    db_session.commit()
    return bike


def _count(db_session, model):
    db_session.expire_all()
    return db_session.query(model).count()


@pytest.mark.parametrize("value", ["nan", "NaN", "inf", "-inf", "Infinity", "1e999", "1000001", "-1", "abc", ""])
def test_set_hours_rejects_non_finite_huge_and_negative_values(client, db_session, bike, value):
    response = client.post(f"/bikes/{bike.id}/hours", data={"hours": value})
    assert response.status_code == 400
    assert _count(db_session, HoursEvent) == 0


@pytest.mark.parametrize("value", ["nan", "inf", "1e999", "1000001", "0", "-2"])
def test_rides_reject_non_finite_huge_and_non_positive_lengths(client, db_session, bike, value):
    response = client.post(f"/bikes/{bike.id}/rides", data={"date": "2026-01-01", "hours": value})
    assert response.status_code == 400
    assert _count(db_session, Ride) == 0
    assert _count(db_session, HoursEvent) == 0


def test_the_largest_allowed_reading_is_accepted(client, db_session, bike):
    assert client.post(f"/bikes/{bike.id}/hours", data={"hours": "1000000"}).status_code == 200


@pytest.mark.parametrize("value", ["20260101", "2026-W01-1", "2026-1-1", "2026-02-30", "26-01-01", "2026-01-01T00:00", "x", ""])
def test_dates_must_be_strict_iso(client, db_session, bike, value):
    response = client.post(f"/bikes/{bike.id}/rides", data={"date": value, "hours": "1"})
    assert response.status_code == 400
    assert _count(db_session, Ride) == 0


def test_a_valid_date_is_stored_in_canonical_form(client, db_session, bike):
    client.post(f"/bikes/{bike.id}/rides", data={"date": "2026-02-01", "hours": "1"})
    assert db_session.query(Ride).one().date == "2026-02-01"


def test_notes_have_a_length_limit(client, db_session, bike):
    form = {"date": "2026-01-01", "hours": "1"}
    assert client.post(f"/bikes/{bike.id}/rides", data={**form, "notes": "n" * (MAX_NOTES + 1)}).status_code == 400
    assert client.post(f"/bikes/{bike.id}/rides", data={**form, "notes": "n" * MAX_NOTES}).status_code == 200
    # service notes too, on both completion routes
    long_notes = {"date": "2026-01-01", "hours": "31", "notes": "n" * (MAX_NOTES + 1)}
    assert client.post(f"/bikes/{bike.id}/items/oil/complete", data=long_notes).status_code == 400
    assert client.post(f"/bikes/{bike.id}/service-points/30/complete", data=long_notes).status_code == 400
    assert _count(db_session, ServiceRecord) == 0


def test_nicknames_are_trimmed_and_length_limited(client, db_session):
    too_long = "n" * (MAX_NICKNAME + 1)
    assert client.post("/bikes", data={"nickname": too_long, "model_key": "test-bike"}).status_code == 400
    assert _count(db_session, Bike) == 0
    assert client.post("/bikes", data={"nickname": "  Trail  ", "model_key": "test-bike"}, follow_redirects=False).status_code == 303
    assert db_session.query(Bike).one().nickname == "Trail"


def test_renaming_enforces_the_same_nickname_rules(client, db_session, bike):
    assert client.post(f"/bikes/{bike.id}", data={"nickname": "n" * (MAX_NICKNAME + 1)}).status_code == 400
    assert client.post(f"/bikes/{bike.id}", data={"nickname": "   "}).status_code == 400
    db_session.expire_all()
    assert db_session.get(Bike, bike.id).nickname == "Race Bike"


def test_unicode_digits_never_crash_the_bulk_route_or_the_notice(client, db_session, bike):
    for ids in ("²", "٣", "①", "1.5", "-1", "99999999999999999999"):
        response = client.post("/bulk/bikes", data={"action": "delete", "ids": ids}, follow_redirects=False)
        assert response.status_code == 303, ids
    assert _count(db_session, Bike) == 1  # nothing valid was selected
    for n in ("²", "٣", "①", "99999999", "-1"):
        assert client.get("/", params={"done": "deleted", "n": n}).status_code == 200, n


def test_parse_ids_keeps_only_plain_positive_integers():
    assert parse_ids(["1", "22", "²", "x", "-3", "0", "99999999999999999999", " 4", "5"]) == {1, 22, 5}


@pytest.mark.parametrize("path", [
    "/bikes/99999999999999999999",
    "/bikes/99999999999999999999/rides",
    "/bikes/99999999999999999999/suspension",
    "/bikes/99999999999999999999/edit",
    "/bikes/1/rides/99999999999999999999/edit",
    "/bikes/0",
])
def test_out_of_range_ids_in_urls_are_rejected_not_crashes(client, path):
    assert client.get(path).status_code in (404, 422)


def test_out_of_range_service_point_is_rejected(client, bike):
    response = client.post(f"/bikes/{bike.id}/service-points/99999999999999999999/complete", data={"date": "2026-01-01", "hours": "1"})
    assert response.status_code == 422
    response = client.post(f"/bikes/{bike.id}/items/oil/complete", data={"point": "99999999999999999999", "date": "2026-01-01", "hours": "1"})
    assert response.status_code == 400


def test_bad_suspension_numbers_are_ignored_not_stored_or_crashing(client, db_session, bike):
    response = client.post(f"/bikes/{bike.id}/rides", data={
        "date": "2026-01-01", "hours": "1",
        "sag_static": "99999999999999999999", "fork_compression": "nan",
        "shock_hsc": "inf", "shock_lsc": "1e999", "sag_rider": "95",
    })
    assert response.status_code == 200
    ride = db_session.query(Ride).one()
    assert ride.sag_static is None and ride.fork_compression is None
    assert ride.shock_hsc is None and ride.shock_lsc is None
    assert ride.sag_rider == 95
