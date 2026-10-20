from app.models import Bike, Ride, HoursEvent


def _make_bike(db_session):
    bike = Bike(nickname="Race Bike", model_key="test-bike")
    db_session.add(bike)
    db_session.commit()
    return bike


def test_log_ride_creates_ride_and_hours_event(client, db_session):
    bike = _make_bike(db_session)
    response = client.post(f"/bikes/{bike.id}/rides", data={"date": "2026-01-01", "hours": 5, "notes": ""})
    assert response.status_code == 200
    ride = db_session.query(Ride).filter_by(bike_id=bike.id).one()
    event = db_session.query(HoursEvent).filter_by(bike_id=bike.id, kind="ride").one()
    assert event.ride_id == ride.id
    assert event.hours == 5


def test_log_ride_rejects_zero_hours(client, db_session):
    bike = _make_bike(db_session)
    response = client.post(f"/bikes/{bike.id}/rides", data={"date": "2026-01-01", "hours": 0, "notes": ""})
    assert response.status_code == 400
    assert db_session.query(Ride).count() == 0
    assert db_session.query(HoursEvent).count() == 0


def test_edit_ride_updates_linked_hours_event_in_place(client, db_session):
    bike = _make_bike(db_session)
    client.post(f"/bikes/{bike.id}/rides", data={"date": "2026-01-01", "hours": 5, "notes": ""})
    ride = db_session.query(Ride).filter_by(bike_id=bike.id).one()
    response = client.post(f"/bikes/{bike.id}/rides/{ride.id}", data={"date": "2026-01-02", "hours": 8, "notes": ""})
    assert response.status_code == 200
    events = db_session.query(HoursEvent).filter_by(bike_id=bike.id, kind="ride").all()
    assert len(events) == 1
    assert events[0].hours == 8


def test_delete_ride_removes_ride_and_linked_hours_event(client, db_session):
    bike = _make_bike(db_session)
    client.post(f"/bikes/{bike.id}/rides", data={"date": "2026-01-01", "hours": 5, "notes": ""})
    ride = db_session.query(Ride).filter_by(bike_id=bike.id).one()
    response = client.post(f"/bikes/{bike.id}/rides/{ride.id}/delete")
    assert response.status_code == 200
    assert db_session.query(Ride).count() == 0
    assert db_session.query(HoursEvent).filter_by(bike_id=bike.id, kind="ride").count() == 0


def test_edit_unknown_ride_returns_404(client, db_session):
    bike = _make_bike(db_session)
    assert client.get(f"/bikes/{bike.id}/rides/999/edit").status_code == 404


def test_rides_tab_prefills_suspension_from_most_recent_ride(client, db_session):
    bike = _make_bike(db_session)
    client.post(f"/bikes/{bike.id}/rides", data={"date": "2026-01-01", "hours": 2, "notes": "", "fork_compression": 10})
    client.post(f"/bikes/{bike.id}/rides", data={"date": "2026-01-05", "hours": 2, "notes": "", "fork_compression": 12})
    response = client.get(f"/bikes/{bike.id}/rides")
    assert 'value="12"' in response.text


def test_rides_tab_prefills_factory_defaults_when_no_rides_exist(client, db_session):
    bike = _make_bike(db_session)
    response = client.get(f"/bikes/{bike.id}/rides")
    assert 'value="9"' in response.text  # factory fork_compression from conftest_bike.yaml
