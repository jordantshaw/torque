import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Bike, CarbSetting

FIXTURE = Path(__file__).parent.parent / "fixtures" / "bike_models" / "conftest_bike.yaml"

START = {
    "date": "2026-03-01",
    "main_jet": "175",
    "needle": "NEDK",
    "needle_position": "3rd",
    "pilot_jet": "38",
    "air_screw": "2 out",
    "note": "Starting point",
}


@pytest.fixture
def client(tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    shutil.copy(FIXTURE, models / "conftest_bike.yaml")
    text = FIXTURE.read_text().replace("key: test-bike", "key: carb-bike").replace(
        "display_name: Test Bike", "display_name: Carb Bike\ncarburetor: true"
    )
    (models / "carb_bike.yaml").write_text(text)
    app = create_app(bike_models_dir=models, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    return TestClient(app, base_url="http://localhost")


@pytest.fixture
def db_session(client):
    with client.app.state.sessionmaker() as session:
        yield session


def _bike(db_session, model_key="carb-bike"):
    bike = Bike(nickname="Carby", model_key=model_key)
    db_session.add(bike)
    db_session.commit()
    return bike


def _post(client, bike, **overrides):
    return client.post(f"/bikes/{bike.id}/carb", data={**START, **overrides})


def _rows(db_session):
    db_session.expire_all()
    return db_session.query(CarbSetting).order_by(CarbSetting.id).all()


def test_tab_link_and_page_only_for_carbureted_bikes(client, db_session):
    carb = _bike(db_session)
    plain = _bike(db_session, "test-bike")
    assert f"/bikes/{carb.id}/carb" in client.get(f"/bikes/{carb.id}").text
    assert client.get(f"/bikes/{carb.id}/carb").status_code == 200
    assert f"/bikes/{plain.id}/carb" not in client.get(f"/bikes/{plain.id}").text
    assert client.get(f"/bikes/{plain.id}/carb").status_code == 404
    assert client.post(f"/bikes/{plain.id}/carb", data=START).status_code == 404
    assert client.post(f"/bikes/{plain.id}/carb/1/delete").status_code == 404


def test_empty_state_shows_invitation_and_not_recorded_tiles(client, db_session):
    bike = _bike(db_session)
    text = client.get(f"/bikes/{bike.id}/carb").text
    assert "No setup logged yet. Log your starting setup above." in text
    assert text.count("Not recorded") == 5
    assert "Last changed" not in text


def test_first_entry_is_saved_and_becomes_current(client, db_session):
    bike = _bike(db_session)
    response = _post(client, bike)
    assert response.status_code == 200
    assert len(_rows(db_session)) == 1
    text = client.get(f"/bikes/{bike.id}/carb").text
    assert "Starting setup" in text
    for value in ("175", "NEDK", "3rd", "38", "2 out", "Starting point"):
        assert value in text
    assert "Last changed 2026-03-01" in text


def test_first_entry_needs_a_value(client, db_session):
    bike = _bike(db_session)
    response = _post(client, bike, main_jet="", needle="", needle_position="", pilot_jet="", air_screw="")
    assert response.status_code == 400
    assert "Enter at least one value." in response.text
    assert _rows(db_session) == []


def test_unchanged_entry_is_rejected(client, db_session):
    bike = _bike(db_session)
    _post(client, bike)
    response = _post(client, bike, date="2026-04-01")
    assert response.status_code == 400
    assert "Nothing changed from the previous setup." in response.text
    assert len(_rows(db_session)) == 1


def test_change_shows_only_what_changed(client, db_session):
    bike = _bike(db_session)
    _post(client, bike)
    response = _post(client, bike, date="2026-04-01", pilot_jet="40", note="")
    assert response.status_code == 200
    assert "Pilot jet 38 → 40" in response.text
    latest = response.text.split('class="carb-item"')[1]  # newest entry first
    assert "2026-04-01" in latest
    assert "Pilot jet" in latest
    assert "Main jet" not in latest


def test_backdated_entry_is_compared_with_its_predecessor_in_date_order(client, db_session):
    bike = _bike(db_session)
    _post(client, bike, date="2026-03-01", main_jet="175")
    _post(client, bike, date="2026-06-01", main_jet="172")
    assert _post(client, bike, date="2026-04-01", main_jet="172").status_code == 200
    response = _post(client, bike, date="2026-04-02", main_jet="172")
    assert response.status_code == 400
    assert "Nothing changed from the previous setup." in response.text
    assert len(_rows(db_session)) == 3


def test_same_date_entries_the_later_saved_is_current(client, db_session):
    bike = _bike(db_session)
    _post(client, bike, date="2026-03-01", main_jet="175")
    _post(client, bike, date="2026-03-01", main_jet="172")
    text = client.get(f"/bikes/{bike.id}/carb").text
    tiles = text.split("Log a change", 1)[0]
    assert "172" in tiles
    assert "175" not in tiles


def test_values_are_trimmed_and_whitespace_counts_as_blank(client, db_session):
    bike = _bike(db_session)
    response = _post(client, bike, main_jet="  172 ", pilot_jet="   ")
    assert response.status_code == 200
    row = _rows(db_session)[0]
    assert row.main_jet == "172"
    assert row.pilot_jet == ""


def test_long_value_is_rejected(client, db_session):
    bike = _bike(db_session)
    response = _post(client, bike, needle="x" * 51)
    assert response.status_code == 400
    assert "Needle must be 50 characters or fewer." in response.text
    assert _rows(db_session) == []


@pytest.mark.parametrize("overrides", [{"date": "nope"}, {"date": ""}, {"note": "n" * 1001}])
def test_bad_date_and_long_note_are_rejected(client, db_session, overrides):
    bike = _bike(db_session)
    assert _post(client, bike, **overrides).status_code == 400
    assert _rows(db_session) == []


def test_error_response_echoes_submitted_values(client, db_session):
    bike = _bike(db_session)
    response = _post(client, bike, main_jet="Z99", needle="x" * 51, note="keep me")
    assert response.status_code == 400
    assert 'value="Z99"' in response.text
    assert 'value="2026-03-01"' in response.text
    assert 'value="keep me"' in response.text


def test_markup_in_values_and_note_is_escaped(client, db_session):
    bike = _bike(db_session)
    response = _post(client, bike, main_jet="<script>x</script>", note="<script>x</script>")
    assert response.status_code == 200
    assert "&lt;script&gt;" in response.text
    assert "<script>x" not in response.text


def test_delete_removes_entry_and_rederives_current(client, db_session):
    bike = _bike(db_session)
    _post(client, bike, date="2026-03-01", main_jet="175")
    _post(client, bike, date="2026-04-01", main_jet="172")
    newest = _rows(db_session)[-1]
    response = client.post(f"/bikes/{bike.id}/carb/{newest.id}/delete")
    assert response.status_code == 200
    assert len(_rows(db_session)) == 1
    tiles = response.text.split("Log a change", 1)[0]
    assert "175" in tiles
    assert "172" not in tiles


def test_deleting_the_oldest_makes_the_next_the_starting_setup(client, db_session):
    bike = _bike(db_session)
    _post(client, bike, date="2026-03-01", main_jet="175", pilot_jet="38")
    _post(client, bike, date="2026-04-01", main_jet="172", pilot_jet="38")
    oldest = _rows(db_session)[0]
    response = client.post(f"/bikes/{bike.id}/carb/{oldest.id}/delete")
    assert response.status_code == 200
    items = response.text.split('class="carb-item"')[1:]
    assert len(items) == 1
    item = items[0]
    assert "Starting setup" in item
    assert "Main jet 172" in item
    assert "Needle NEDK" in item
    assert "Needle position 3rd" in item
    assert "Pilot jet 38" in item
    assert "Air screw 2 out" in item
    assert "→" not in item


def test_deleting_the_last_entry_returns_to_the_empty_state(client, db_session):
    bike = _bike(db_session)
    _post(client, bike)
    only = _rows(db_session)[0]
    response = client.post(f"/bikes/{bike.id}/carb/{only.id}/delete")
    assert response.status_code == 200
    assert "No setup logged yet. Log your starting setup above." in response.text
    assert response.text.count("Not recorded") == 5


def test_delete_of_another_bikes_entry_is_404(client, db_session):
    one = _bike(db_session)
    two = _bike(db_session)
    _post(client, one)
    entry = _rows(db_session)[0]
    assert client.post(f"/bikes/{two.id}/carb/{entry.id}/delete").status_code == 404
    assert len(_rows(db_session)) == 1


def test_out_of_range_ids_are_rejected(client, db_session):
    bike = _bike(db_session)
    assert client.get("/bikes/0/carb").status_code == 422
    assert client.post(f"/bikes/{bike.id}/carb/{10**12}/delete").status_code == 422


def test_delete_button_asks_for_confirmation(client, db_session):
    bike = _bike(db_session)
    _post(client, bike)
    assert 'hx-confirm="Delete this entry?"' in client.get(f"/bikes/{bike.id}/carb").text


def test_deleting_a_bike_removes_its_carb_history(client, db_session):
    bike = _bike(db_session)
    _post(client, bike)
    client.post(f"/bikes/{bike.id}/delete")
    assert _rows(db_session) == []
