"""Logging a ride's location, carb and suspension setup, and seeing it on the
Carb and Suspension tabs."""

import pytest

from app.models import Bike, CarbSetting, Ride

CARB = {
    "main_jet": "175",
    "needle": "NEDK",
    "needle_position": "3rd",
    "pilot_jet": "38",
    "air_screw": "2 out",
}


@pytest.fixture
def bike_models_dir(bike_models_dir):
    """The shared test models plus a carbureted copy of the test bike."""
    text = (bike_models_dir / "conftest_bike.yaml").read_text()
    text = text.replace("key: test-bike", "key: carb-bike").replace(
        "display_name: Test Bike", "display_name: Carb Bike\ncarburetor: true"
    )
    (bike_models_dir / "carb_bike.yaml").write_text(text)
    return bike_models_dir


def _bike(db_session, model_key="carb-bike"):
    bike = Bike(nickname="Carby", model_key=model_key)
    db_session.add(bike)
    db_session.commit()
    return bike


def _ride(client, bike, **fields):
    data = {"date": "2026-04-01", "hours": "2", "notes": "", **fields}
    return client.post(f"/bikes/{bike.id}/rides", data=data)


def _carb_rows(db_session):
    db_session.expire_all()
    return db_session.query(CarbSetting).order_by(CarbSetting.id).all()


def _only_ride(db_session):
    db_session.expire_all()
    return db_session.query(Ride).one()


def test_location_is_saved_and_shown_in_the_ride_list(client, db_session):
    bike = _bike(db_session, "test-bike")
    response = _ride(client, bike, location="  Hollister Hills  ")
    assert response.status_code == 200
    assert _only_ride(db_session).location == "Hollister Hills"
    assert "Hollister Hills" in response.text


def test_blank_location_is_stored_as_none(client, db_session):
    bike = _bike(db_session, "test-bike")
    _ride(client, bike, location="  ")
    assert _only_ride(db_session).location is None


def test_carb_section_only_on_carbureted_bikes(client, db_session):
    carb = _bike(db_session)
    plain = _bike(db_session, "test-bike")
    assert 'name="main_jet"' in client.get(f"/bikes/{carb.id}/rides").text
    assert 'name="main_jet"' not in client.get(f"/bikes/{plain.id}/rides").text


def test_ride_form_prefills_the_current_carb_setup(client, db_session):
    bike = _bike(db_session)
    client.post(f"/bikes/{bike.id}/carb", data={"date": "2026-03-01", "note": "", **CARB})
    assert 'name="needle" value="NEDK"' in client.get(f"/bikes/{bike.id}/rides").text


def test_changed_carb_values_on_a_ride_save_a_linked_carb_entry(client, db_session):
    bike = _bike(db_session)
    _ride(client, bike, location="Prairie City", **CARB)
    ride = _only_ride(db_session)
    [entry] = _carb_rows(db_session)
    assert entry.ride_id == ride.id
    assert entry.date == "2026-04-01"
    assert entry.pilot_jet == "38"

    carb_tab = client.get(f"/bikes/{bike.id}/carb").text
    assert "Logged with ride" in carb_tab
    assert "Prairie City" in carb_tab


def test_unchanged_or_blank_carb_values_save_no_carb_entry(client, db_session):
    bike = _bike(db_session)
    _ride(client, bike)  # all blank, nothing logged before
    client.post(f"/bikes/{bike.id}/carb", data={"date": "2026-03-01", "note": "", **CARB})
    _ride(client, bike, **CARB)  # same as the setup in effect
    assert [e.ride_id for e in _carb_rows(db_session)] == [None]


def test_carb_values_are_ignored_on_a_bike_without_a_carburetor(client, db_session):
    bike = _bike(db_session, "test-bike")
    assert _ride(client, bike, **CARB).status_code == 200
    assert _carb_rows(db_session) == []


def test_too_long_carb_value_is_rejected_and_the_form_keeps_what_was_typed(client, db_session):
    bike = _bike(db_session)
    response = _ride(client, bike, location="Carnegie", **{**CARB, "needle": "x" * 51})
    assert response.status_code == 400
    assert "Needle must be 50 characters or fewer." in response.text
    assert 'value="Carnegie"' in response.text
    db_session.expire_all()
    assert db_session.query(Ride).count() == 0


def test_editing_a_ride_updates_then_removes_its_linked_carb_entry(client, db_session):
    bike = _bike(db_session)
    client.post(f"/bikes/{bike.id}/carb", data={"date": "2026-03-01", "note": "", **CARB})
    _ride(client, bike, **{**CARB, "pilot_jet": "40"})
    ride = _only_ride(db_session)

    form = client.get(f"/bikes/{bike.id}/rides/{ride.id}/edit").text
    assert 'name="pilot_jet" value="40"' in form

    base = {"date": "2026-04-02", "hours": "2", "notes": "", "location": "Gorman"}
    client.post(f"/bikes/{bike.id}/rides/{ride.id}", data={**base, **CARB, "pilot_jet": "42"})
    linked = [e for e in _carb_rows(db_session) if e.ride_id == ride.id]
    assert [(e.pilot_jet, e.date) for e in linked] == [("42", "2026-04-02")]

    client.post(f"/bikes/{bike.id}/rides/{ride.id}", data={**base, **CARB})  # back to the setup in effect
    assert [e.ride_id for e in _carb_rows(db_session)] == [None]


def test_editing_a_ride_without_a_carb_entry_can_add_one(client, db_session):
    bike = _bike(db_session)
    _ride(client, bike)
    ride = _only_ride(db_session)
    client.post(
        f"/bikes/{bike.id}/rides/{ride.id}",
        data={"date": "2026-04-01", "hours": "2", "notes": "", **CARB},
    )
    assert [e.ride_id for e in _carb_rows(db_session)] == [ride.id]


def test_deleting_a_ride_deletes_its_linked_carb_entry(client, db_session):
    bike = _bike(db_session)
    _ride(client, bike, **CARB)
    ride = _only_ride(db_session)
    client.post(f"/bikes/{bike.id}/rides/{ride.id}/delete")
    assert _carb_rows(db_session) == []


def test_suspension_tab_shows_setup_changes_logged_with_rides(client, db_session):
    bike = _bike(db_session, "test-bike")
    _ride(client, bike, date="2026-04-01", fork_compression="9", fork_rebound="12", location="Hollister")
    _ride(client, bike, date="2026-04-08", fork_compression="9", fork_rebound="12")
    _ride(client, bike, date="2026-04-15", fork_compression="9", fork_rebound="10", location="Gorman")

    text = client.get(f"/bikes/{bike.id}/suspension").text
    assert "Starting setup" in text
    assert "Fork rebound 12 → 10" in text
    assert "Gorman" in text
    assert "2026-04-08" not in text  # nothing changed on that ride


def test_suspension_tab_history_empty_state(client, db_session):
    bike = _bike(db_session, "test-bike")
    text = client.get(f"/bikes/{bike.id}/suspension").text
    assert "No suspension settings logged with a ride yet." in text


def test_suspension_tab_shows_current_tiles_history_and_the_reference(client, db_session):
    bike = _bike(db_session, "test-bike")
    _ride(client, bike, date="2026-04-01", fork_rebound="12")
    _ride(client, bike, date="2026-04-15", fork_rebound="10")

    text = client.get(f"/bikes/{bike.id}/suspension").text
    assert text.index("Current setup") < text.index("Setup history") < text.index("Reference settings")
    assert "Last changed 2026-04-15" in text
    assert text.count("Not recorded") == 6  # every tile but fork rebound
    assert "Test fixture source." in text  # the reference is still there
