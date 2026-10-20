from app.models import Bike, HoursEvent, ServiceRecord


def _make_bike(db_session):
    bike = Bike(nickname="Race Bike", model_key="test-bike")
    db_session.add(bike)
    db_session.commit()
    return bike


def test_bike_page_returns_404_for_unknown_bike(client):
    assert client.get("/bikes/999").status_code == 404


def test_maintenance_tab_shows_items_with_status(client, db_session):
    bike = _make_bike(db_session)
    response = client.get(f"/bikes/{bike.id}")
    assert response.status_code == 200
    assert "Oil" in response.text
    assert "Connecting rod" in response.text


def test_maintenance_tab_links_to_edit_bike(client, db_session):
    bike = _make_bike(db_session)
    response = client.get(f"/bikes/{bike.id}")
    assert response.status_code == 200
    assert f"/bikes/{bike.id}/edit" in response.text


def test_set_hours_updates_current_hours_and_statuses(client, db_session):
    bike = _make_bike(db_session)
    response = client.post(f"/bikes/{bike.id}/hours", data={"hours": 28})
    assert response.status_code == 200
    assert "28" in response.text  # new current hours shown


def test_complete_item_creates_service_record_and_advances_next_point(client, db_session):
    bike = _make_bike(db_session)
    db_session.add(HoursEvent(bike_id=bike.id, date="2026-01-01", kind="set", hours=30))
    db_session.commit()
    response = client.post(
        f"/bikes/{bike.id}/items/oil/complete",
        data={"date": "2026-01-10", "hours": 30, "notes": ""},
    )
    assert response.status_code == 200
    records = db_session.query(ServiceRecord).filter_by(bike_id=bike.id, item_key="oil").all()
    assert len(records) == 1
    assert records[0].service_point == 30


def test_complete_item_rejects_when_beyond_schedule(client, db_session):
    bike = _make_bike(db_session)
    db_session.add_all([
        ServiceRecord(bike_id=bike.id, item_key="connecting_rod", service_point=90, completed_date="2026-01-01", engine_hours=90),
        ServiceRecord(bike_id=bike.id, item_key="connecting_rod", service_point=180, completed_date="2026-01-01", engine_hours=180),
    ])
    db_session.commit()
    response = client.post(
        f"/bikes/{bike.id}/items/connecting_rod/complete",
        data={"date": "2026-01-10", "hours": 200, "notes": ""},
    )
    assert response.status_code == 400
    assert db_session.query(ServiceRecord).filter_by(bike_id=bike.id, item_key="connecting_rod").count() == 2


def test_complete_all_for_service_point_only_affects_items_with_that_point(client, db_session):
    bike = _make_bike(db_session)
    response = client.post(
        f"/bikes/{bike.id}/service-points/30/complete",
        data={"date": "2026-01-10", "hours": 30, "notes": ""},
    )
    assert response.status_code == 200
    item_keys = {r.item_key for r in db_session.query(ServiceRecord).filter_by(bike_id=bike.id).all()}
    assert item_keys == {"oil", "clutch_disks"}  # connecting_rod has no action at hour 30
