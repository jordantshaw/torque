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


def test_complete_item_history_appears_in_maintenance_tab(client, db_session):
    bike = _make_bike(db_session)
    db_session.add(HoursEvent(bike_id=bike.id, date="2026-01-01", kind="set", hours=30))
    db_session.commit()
    complete_response = client.post(
        f"/bikes/{bike.id}/items/oil/complete",
        data={"date": "2026-01-10", "hours": 31, "notes": "used synthetic"},
    )
    assert complete_response.status_code == 200
    # The htmx partial response from the completion itself already reflects
    # the new history entry.
    assert "2026-01-10" in complete_response.text
    assert "31" in complete_response.text
    assert "used synthetic" in complete_response.text

    # And it's still there on a later GET of the tab.
    get_response = client.get(f"/bikes/{bike.id}")
    assert get_response.status_code == 200
    assert "2026-01-10" in get_response.text
    assert "31" in get_response.text
    assert "used synthetic" in get_response.text


def test_complete_item_history_shows_most_recent_first(client, db_session):
    bike = _make_bike(db_session)
    db_session.add_all([
        ServiceRecord(bike_id=bike.id, item_key="oil", service_point=30, completed_date="2026-01-01", engine_hours=30, notes="first"),
        ServiceRecord(bike_id=bike.id, item_key="oil", service_point=60, completed_date="2026-02-01", engine_hours=60, notes="second"),
    ])
    db_session.commit()
    response = client.get(f"/bikes/{bike.id}")
    assert response.status_code == 200
    assert response.text.index("second") < response.text.index("first")


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


def _service_group(html: str, label: str) -> str:
    """The HTML of one service's group (from its heading to the next group)."""
    start = html.index(label)
    end = html.find('<details class="service', start)
    return html[start:] if end == -1 else html[start:end]


def test_each_service_lists_every_item_scheduled_at_that_point(client, db_session):
    bike = _make_bike(db_session)
    html = client.get(f"/bikes/{bike.id}").text
    # Clutch disks print marks at 30, 60, 90...; Oil is every 30. A later
    # service lists them even though their 30h point is still outstanding.
    sixty = _service_group(html, "60-hour service")
    assert "Clutch disks" in sixty
    assert "Oil" in sixty
    assert "Connecting rod" not in sixty  # only at 90 and 180
    assert "Connecting rod" in _service_group(html, "90-hour service")


def test_complete_item_at_a_specific_service_point(client, db_session):
    bike = _make_bike(db_session)
    response = client.post(
        f"/bikes/{bike.id}/items/clutch_disks/complete",
        data={"point": "60", "date": "2026-02-01", "hours": "61", "notes": ""},
    )
    assert response.status_code == 200
    record = db_session.query(ServiceRecord).filter_by(bike_id=bike.id, item_key="clutch_disks").one()
    assert record.service_point == 60  # not the item's next point (30)
    assert "Done 2026-02-01" in _service_group(client.get(f"/bikes/{bike.id}").text, "60-hour service")


def test_complete_item_rejects_a_point_it_has_no_action_at(client, db_session):
    bike = _make_bike(db_session)
    response = client.post(
        f"/bikes/{bike.id}/items/connecting_rod/complete",
        data={"point": "30", "date": "2026-02-01", "hours": "31"},
    )
    assert response.status_code == 400
    assert db_session.query(ServiceRecord).count() == 0


def test_complete_item_rejects_an_already_recorded_point(client, db_session):
    bike = _make_bike(db_session)
    form = {"point": "30", "date": "2026-02-01", "hours": "31"}
    assert client.post(f"/bikes/{bike.id}/items/clutch_disks/complete", data=form).status_code == 200
    assert client.post(f"/bikes/{bike.id}/items/clutch_disks/complete", data=form).status_code == 400
    assert db_session.query(ServiceRecord).count() == 1


def test_row_details_show_the_items_description(client, db_session, bike_models_dir):
    (bike_models_dir / "conftest_bike.yaml").write_text(
        (bike_models_dir / "conftest_bike.yaml").read_text().replace(
            "    name: Oil\n", "    name: Oil\n    description: Drain it warm.\n    page: '52'\n    schedule_page: '83'\n", 1
        )
    )
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(bike_models_dir, f"sqlite:///{bike_models_dir / 'd.db'}")
    c = TestClient(app, base_url="http://localhost")
    with app.state.sessionmaker() as session:
        bike = Bike(nickname="B", model_key="test-bike")
        session.add(bike)
        session.commit()
        bike_id = bike.id
    html = c.get(f"/bikes/{bike_id}").text
    assert "Drain it warm." in html
    assert "Manual: schedule p. 83, how-to p. 52" in html


def test_completed_items_show_a_ticked_checkbox_and_pending_ones_an_empty_one(client, db_session):
    bike = _make_bike(db_session)
    client.post(
        f"/bikes/{bike.id}/items/clutch_disks/complete",
        data={"point": "30", "date": "2026-02-01", "hours": "31", "notes": ""},
    )
    thirty = _service_group(client.get(f"/bikes/{bike.id}").text, "30-hour service")
    disks = thirty[thirty.index("Clutch disks") - 400 : thirty.index("Clutch disks") + 200]
    assert 'aria-label="Completed"' in disks
    oil = thirty[thirty.index(">Oil<") - 400 : thirty.index(">Oil<") + 100]
    assert 'aria-label="Not done yet"' in oil
