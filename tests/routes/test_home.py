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
    assert "2 upcoming" in response.text.lower()


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


def test_base_page_overrides_htmx_response_handling_for_4xx_5xx(client):
    # htmx's default responseHandling treats all 4xx/5xx as non-swappable
    # errors, which would silently drop this app's "re-render partial with
    # inline validation errors" 400 responses. app.js (loaded on every page,
    # after htmx) must override it so 4xx/5xx still swap (while still firing
    # htmx:responseError).
    page = client.get("/")
    assert page.status_code == 200
    assert page.text.index("/static/htmx.min.js") < page.text.index("/static/app.js")
    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert "htmx.config.responseHandling" in script.text
    assert '{code: "[45]..", swap: true, error: true}' in script.text


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


def _bike_with_history(db_session, nickname):
    from app.models import HoursEvent, Ride, ServiceRecord

    bike = Bike(nickname=nickname, model_key="test-bike")
    db_session.add(bike)
    db_session.flush()
    ride = Ride(bike_id=bike.id, date="2026-01-01", hours=3)
    db_session.add(ride)
    db_session.flush()
    db_session.add(HoursEvent(bike_id=bike.id, date="2026-01-01", kind="ride", hours=3, ride_id=ride.id))
    db_session.add(ServiceRecord(bike_id=bike.id, item_key="oil", service_point=30, completed_date="2026-01-01", engine_hours=30))
    db_session.commit()
    return bike


def _counts(db_session):
    from app.models import HoursEvent, Ride, ServiceRecord

    db_session.expire_all()
    return (
        db_session.query(Bike).count(),
        db_session.query(ServiceRecord).count(),
        db_session.query(Ride).count(),
        db_session.query(HoursEvent).count(),
    )


def test_clear_history_removes_only_service_records(client, db_session):
    bike = _bike_with_history(db_session, "A")
    other = _bike_with_history(db_session, "B")
    response = client.post(f"/bikes/{bike.id}/clear-history", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/?done=cleared&n=1"
    bikes, records, rides, events = _counts(db_session)
    assert (bikes, rides, events) == (2, 2, 2)  # bikes, rides and hours untouched
    assert records == 1  # only the other bike's record remains
    assert db_session.query(__import__("app.models", fromlist=["ServiceRecord"]).ServiceRecord).one().bike_id == other.id


def test_clear_history_unknown_bike_404(client):
    assert client.post("/bikes/999/clear-history").status_code == 404


def test_bulk_delete_removes_selected_bikes_and_their_data(client, db_session):
    a = _bike_with_history(db_session, "A")
    b = _bike_with_history(db_session, "B")
    keep = _bike_with_history(db_session, "C")
    response = client.post("/bulk/bikes", data={"action": "delete", "ids": [a.id, b.id]}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/?done=deleted&n=2"
    assert _counts(db_session) == (1, 1, 1, 1)
    assert db_session.query(Bike).one().id == keep.id


def test_bulk_clear_history_keeps_bikes_rides_and_hours(client, db_session):
    a = _bike_with_history(db_session, "A")
    b = _bike_with_history(db_session, "B")
    response = client.post("/bulk/bikes", data={"action": "clear_history", "ids": [a.id, b.id]}, follow_redirects=False)
    assert response.headers["location"] == "/?done=cleared&n=2"
    assert _counts(db_session) == (2, 0, 2, 2)


def test_bulk_ignores_unknown_and_non_numeric_ids_and_empty_selection(client, db_session):
    _bike_with_history(db_session, "A")
    response = client.post("/bulk/bikes", data={"action": "delete", "ids": ["999", "abc"]}, follow_redirects=False)
    assert response.headers["location"] == "/"
    response = client.post("/bulk/bikes", data={"action": "delete"}, follow_redirects=False)
    assert response.headers["location"] == "/"
    assert _counts(db_session) == (1, 1, 1, 1)


def test_bulk_rejects_unknown_action(client, db_session):
    a = _bike_with_history(db_session, "A")
    assert client.post("/bulk/bikes", data={"action": "explode", "ids": [a.id]}).status_code == 400
    assert _counts(db_session) == (1, 1, 1, 1)


def test_home_shows_a_confirmation_after_a_bulk_action(client):
    assert "Deleted 2 bikes." in client.get("/?done=deleted&n=2").text
    assert "Cleared the maintenance history of 1 bike." in client.get("/?done=cleared&n=1").text
    assert "Deleted" not in client.get("/?done=deleted&n=abc").text
    assert "Deleted" not in client.get("/?done=bogus&n=3").text


def test_home_cards_have_select_checkboxes_and_per_bike_actions(client, db_session):
    bike = Bike(nickname="Race Bike", model_key="test-bike")
    db_session.add(bike)
    db_session.commit()
    html = client.get("/").text
    assert f'name="ids" value="{bike.id}" form="bulk-form"' in html
    assert f'action="/bikes/{bike.id}/clear-history"' in html
    assert f'action="/bikes/{bike.id}/delete"' in html
    assert 'action="/bulk/bikes"' in html


def test_add_bike_button_is_in_the_page_header_above_the_bike_list(client, db_session):
    db_session.add(Bike(nickname="Race Bike", model_key="test-bike"))
    db_session.commit()
    html = client.get("/").text
    assert html.index('id="add-bike-toggle"') < html.index('id="add-bike"') < html.index('class="bike-list"')


def test_add_bike_form_starts_open_when_there_are_no_bikes_or_on_error(client):
    assert 'data-open="1"' in client.get("/").text  # no bikes yet
    response = client.post("/bikes", data={"nickname": "", "model_key": "test-bike"})
    assert response.status_code == 400
    assert 'data-open="1"' in response.text


def test_add_bike_form_starts_collapsed_when_bikes_exist(client, db_session):
    db_session.add(Bike(nickname="Race Bike", model_key="test-bike"))
    db_session.commit()
    assert 'data-open="1"' not in client.get("/").text


def test_every_page_has_the_same_top_bar_with_a_garage_link_and_no_sidebar(client, db_session):
    bike = Bike(nickname="Race Bike", model_key="test-bike")
    db_session.add(bike)
    db_session.commit()
    for path in ("/", f"/bikes/{bike.id}", f"/bikes/{bike.id}/rides", f"/bikes/{bike.id}/suspension", f"/bikes/{bike.id}/edit", "/bikes/999"):
        html = client.get(path).text
        assert 'class="topbar"' in html, path
        assert 'href="/" class="topnav-link' in html, path
        assert "sidebar" not in html and "side-nav" not in html, path


def test_the_garage_is_the_only_place_bikes_are_listed(client, db_session):
    bike = Bike(nickname="Race Bike", model_key="test-bike")
    other = Bike(nickname="Other Bike", model_key="test-bike")
    db_session.add_all([bike, other])
    db_session.commit()
    assert "Other Bike" not in client.get(f"/bikes/{bike.id}").text
    assert "Other Bike" in client.get("/").text


def test_the_home_page_is_called_garage(client):
    html = client.get("/").text
    assert "<title>Garage</title>" in html
    assert "<h1>Garage</h1>" in html
    assert "Overview" not in html


def test_the_app_is_called_torque(client):
    html = client.get("/").text
    assert "Torque</a>" in html  # the brand in the top bar
    assert "Moto Maintenance" not in html
