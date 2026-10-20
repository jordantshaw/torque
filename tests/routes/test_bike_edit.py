from app.models import Bike, HoursEvent, Ride, ServiceRecord


def _make_bike(db_session):
    bike = Bike(nickname="Race Bike", model_key="test-bike")
    db_session.add(bike)
    db_session.commit()
    return bike


def test_rename_bike_updates_nickname(client, db_session):
    bike = _make_bike(db_session)
    response = client.post(f"/bikes/{bike.id}", data={"nickname": "Renamed"}, follow_redirects=False)
    assert response.status_code == 303
    db_session.refresh(bike)
    assert bike.nickname == "Renamed"


def test_rename_rejects_blank_nickname(client, db_session):
    bike = _make_bike(db_session)
    response = client.post(f"/bikes/{bike.id}", data={"nickname": ""})
    assert response.status_code == 400
    db_session.refresh(bike)
    assert bike.nickname == "Race Bike"


def test_delete_bike_removes_bike_and_all_history(client, db_session):
    bike = _make_bike(db_session)
    ride = Ride(bike_id=bike.id, date="2026-01-01", hours=3)
    db_session.add(ride)
    db_session.flush()
    db_session.add(HoursEvent(bike_id=bike.id, date="2026-01-01", kind="ride", hours=3, ride_id=ride.id))
    db_session.add(ServiceRecord(bike_id=bike.id, item_key="oil", service_point=30, completed_date="2026-01-01", engine_hours=30))
    db_session.commit()

    response = client.post(f"/bikes/{bike.id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert db_session.query(Bike).count() == 0
    assert db_session.query(Ride).count() == 0
    assert db_session.query(HoursEvent).count() == 0
    assert db_session.query(ServiceRecord).count() == 0


def test_edit_unknown_bike_404(client):
    assert client.get("/bikes/999/edit").status_code == 404
