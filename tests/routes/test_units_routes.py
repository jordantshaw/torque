"""A distance-based (km) bike: values are stored in km and shown in the
bike's km/mi preference."""

import pytest

from app.services.units import HOURS
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app.db import init_db
from app.main import create_app
from app.models import Bike, HoursEvent, ServiceRecord
from app.services.units import KM_PER_MILE

KM_MODEL = """\
key: km-bike
display_name: "Km Bike"
engine: "electric"
unit: km
upcoming_window: 50
items:
  - key: chain
    category: Drivetrain
    name: Chain
    actions: {100: C/R, 500: C/S}
notes:
  - "Check the torque of all bolts before trail rides."
suspension: {}
"""


@pytest.fixture
def km_client(tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    (models / "km.yaml").write_text(KM_MODEL)
    app = create_app(models, f"sqlite:///{tmp_path / 'km.db'}")
    return TestClient(app, base_url="http://localhost")


@pytest.fixture
def km_bike(km_client):
    with km_client.app.state.sessionmaker() as session:
        bike = Bike(nickname="Bee", model_key="km-bike")
        session.add(bike)
        session.commit()
        return bike.id


def _bike(client, bike_id):
    with client.app.state.sessionmaker() as session:
        return session.get(Bike, bike_id)


def test_km_bike_shows_km_units_and_manual_notes(km_client, km_bike):
    text = km_client.get(f"/bikes/{km_bike}").text
    assert "100 km service" in text
    assert "Check or adjust" in text
    assert "Odometer" in text
    assert "Check the torque of all bolts before trail rides." in text


def test_set_reading_in_km_is_stored_as_km(km_client, km_bike):
    km_client.post(f"/bikes/{km_bike}/hours", data={"hours": "120"})
    with km_client.app.state.sessionmaker() as session:
        event = session.query(HoursEvent).filter_by(bike_id=km_bike).one()
    assert event.hours == 120


def test_miles_preference_converts_input_and_display(km_client, km_bike):
    response = km_client.post(
        f"/bikes/{km_bike}", data={"nickname": "Bee", "distance_unit": "mi"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert _bike(km_client, km_bike).distance_unit == "mi"

    km_client.post(f"/bikes/{km_bike}/hours", data={"hours": "100"})
    with km_client.app.state.sessionmaker() as session:
        event = session.query(HoursEvent).filter_by(bike_id=km_bike).one()
    assert event.hours == pytest.approx(100 * KM_PER_MILE)

    page = km_client.get(f"/bikes/{km_bike}").text
    assert "62.1 mi service" in page  # 100 km
    assert 'value="100"' in page  # the reading, echoed back in miles


def test_completing_item_in_miles_records_service_point_in_km(km_client, km_bike):
    km_client.post(f"/bikes/{km_bike}", data={"nickname": "Bee", "distance_unit": "mi"})
    km_client.post(
        f"/bikes/{km_bike}/items/chain/complete",
        data={"date": "2026-10-01", "hours": "70", "notes": ""},
    )
    with km_client.app.state.sessionmaker() as session:
        record = session.query(ServiceRecord).filter_by(bike_id=km_bike).one()
    assert record.service_point == 100
    assert record.engine_hours == pytest.approx(70 * KM_PER_MILE)


def test_upcoming_window_comes_from_the_model(km_client, km_bike):
    km_client.post(f"/bikes/{km_bike}/hours", data={"hours": "60"})  # 40 km before the 100 km point
    page = km_client.get(f"/bikes/{km_bike}").text
    assert "pill pill-soon" in page


def test_unit_choice_hidden_for_hours_bikes(client, db_session):
    bike = Bike(nickname="Beta", model_key="test-bike")
    db_session.add(bike)
    db_session.commit()
    assert "distance_unit" not in client.get(f"/bikes/{bike.id}/edit").text


def test_existing_database_gains_distance_unit_column(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE bikes (id INTEGER PRIMARY KEY, nickname VARCHAR NOT NULL, "
            "model_key VARCHAR NOT NULL, created_at DATETIME NOT NULL)"
        ))
        conn.execute(text(
            "INSERT INTO bikes (nickname, model_key, created_at) VALUES ('Old', 'x', '2026-01-01')"
        ))
    init_db(engine)
    assert "distance_unit" in {c["name"] for c in inspect(engine).get_columns("bikes")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT distance_unit FROM bikes")).scalar() == "km"


def test_saving_an_untouched_ride_edit_in_miles_does_not_change_the_stored_distance(km_client, km_bike):
    from app.models import Ride

    km_client.post(f"/bikes/{km_bike}", data={"nickname": "Bee", "distance_unit": "mi"})
    with km_client.app.state.sessionmaker() as session:
        session.add(Ride(bike_id=km_bike, date="2026-01-01", hours=100.0))  # 100 km = 62.137... mi
        session.add(HoursEvent(bike_id=km_bike, date="2026-01-01", kind="ride", hours=100.0, ride_id=1))
        session.commit()

    form = km_client.get(f"/bikes/{km_bike}/rides/1/edit").text
    assert 'value="62.1371"' in form  # not the rounded 62.1 shown elsewhere

    km_client.post(f"/bikes/{km_bike}/rides/1", data={"date": "2026-01-01", "hours": "62.1371", "notes": ""})
    with km_client.app.state.sessionmaker() as session:
        from app.models import Ride as R

        assert session.get(R, 1).hours == pytest.approx(100.0, abs=0.001)


def test_the_hours_input_is_prefilled_losslessly_too(km_client, km_bike):
    km_client.post(f"/bikes/{km_bike}", data={"nickname": "Bee", "distance_unit": "mi"})
    km_client.post(f"/bikes/{km_bike}/hours", data={"hours": "100"})
    page = km_client.get(f"/bikes/{km_bike}").text
    assert 'id="hours" name="hours" min="0" step="any" value="100"' in page


def test_the_amt_filter_refuses_to_guess_a_unit(client):
    from jinja2 import UndefinedError

    template = client.app.state.templates.env.from_string("{{ 5|amt }}")
    with pytest.raises(UndefinedError):
        template.render()
    assert template.environment.from_string("{{ 5|amt(unit) }}").render(unit=HOURS) == "5"
