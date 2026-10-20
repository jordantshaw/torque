from app.models import Bike


def test_home_page_lists_existing_bikes(client, db_session):
    db_session.add(Bike(nickname="Race Bike", model_key="test-bike"))
    db_session.commit()
    response = client.get("/")
    assert response.status_code == 200
    assert "Race Bike" in response.text


def test_home_page_shows_due_and_upcoming_counts(client, db_session):
    # current_hours = 28: oil (every 30h) is upcoming (30-28=2<=5); clutch_disks next=30, also upcoming; connecting_rod next=90, OK
    from app.models import Bike, HoursEvent
    bike = Bike(nickname="Race Bike", model_key="test-bike")
    db_session.add(bike)
    db_session.flush()
    db_session.add(HoursEvent(bike_id=bike.id, date="2026-01-01", kind="set", hours=28))
    db_session.commit()
    response = client.get("/")
    assert "2 upcoming" in response.text.lower() or "upcoming: 2" in response.text.lower()


def test_create_bike_redirects_to_bike_page(client):
    response = client.post("/bikes", data={"nickname": "New Bike", "model_key": "test-bike"}, follow_redirects=False)
    assert response.status_code == 303
    bike_url = response.headers["location"]
    assert client.get(bike_url).status_code in (200, 404)  # 404 acceptable until Task 10 adds the bike page


def test_create_bike_rejects_blank_nickname(client, db_session):
    response = client.post("/bikes", data={"nickname": "", "model_key": "test-bike"})
    assert response.status_code == 400
    assert db_session.query(Bike).count() == 0


def test_create_bike_rejects_unknown_model_key(client, db_session):
    response = client.post("/bikes", data={"nickname": "X", "model_key": "nonexistent"})
    assert response.status_code == 400
    assert db_session.query(Bike).count() == 0


def test_create_bike_blank_nickname_preserves_chosen_model(client, db_session):
    response = client.post("/bikes", data={"nickname": "", "model_key": "test-bike"})
    assert response.status_code == 400
    # The previously chosen model stays selected in the re-rendered form.
    assert '<option value="test-bike" selected>' in response.text


def test_create_bike_unknown_model_preserves_typed_nickname(client, db_session):
    response = client.post("/bikes", data={"nickname": "My Race Bike", "model_key": "nonexistent"})
    assert response.status_code == 400
    # The typed nickname stays in the input's value attribute.
    assert 'value="My Race Bike"' in response.text
