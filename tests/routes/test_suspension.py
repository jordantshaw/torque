from app.models import Bike


def test_suspension_tab_shows_reference_values_and_source(client, db_session):
    bike = Bike(nickname="Race Bike", model_key="test-bike")
    db_session.add(bike)
    db_session.commit()
    response = client.get(f"/bikes/{bike.id}/suspension")
    assert response.status_code == 200
    assert "Fork compression" in response.text
    assert "Test fixture source." in response.text


def test_suspension_tab_404_for_unknown_bike(client):
    assert client.get("/bikes/999/suspension").status_code == 404
