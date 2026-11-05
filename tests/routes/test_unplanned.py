from app.models import Bike, HoursEvent, ServiceRecord, UnplannedJob, UnplannedJobItem


def _bike(db_session, hours=31, nickname="Race Bike"):
    bike = Bike(nickname=nickname, model_key="test-bike")
    db_session.add(bike)
    db_session.flush()
    db_session.add(HoursEvent(bike_id=bike.id, date="2026-11-01", kind="set", hours=hours))
    db_session.commit()
    return bike


def _job(db_session, bike, hours, keys=("oil",), note="Bent radiators"):
    job = UnplannedJob(bike_id=bike.id, date="2026-11-02", engine_hours=hours, note=note)
    job.items.extend(UnplannedJobItem(item_key=k) for k in keys)
    db_session.add(job)
    db_session.commit()
    return job


def _log(client, bike, **fields):
    data = {"date": "2026-11-02", "hours": "25", "note": "", "view": "scheduled"} | fields
    return client.post(f"/bikes/{bike.id}/unplanned-jobs", data=data)


def test_log_job_saves_it_and_shows_in_history(client, db_session):
    bike = _bike(db_session)
    response = _log(client, bike, items="oil", note="Bent radiators", view="history")
    assert response.status_code == 200
    job = db_session.query(UnplannedJob).one()
    assert (job.engine_hours, job.note, job.item_keys) == (25, "Bent radiators", ["oil"])
    assert "Bent radiators" in response.text
    assert "Unplanned" in response.text


def test_log_job_rejects_reading_above_current(client, db_session):
    bike = _bike(db_session)
    response = _log(client, bike, items="oil", hours="40")
    assert response.status_code == 400
    assert "That&#39;s above the bike&#39;s current reading. Update the reading first." in response.text
    assert db_session.query(UnplannedJob).count() == 0


def test_log_job_rejects_unknown_item(client, db_session):
    bike = _bike(db_session)
    response = _log(client, bike, items="nope")
    assert response.status_code == 400
    assert "Pick items from this bike&#39;s schedule." in response.text


def test_log_job_needs_items_or_note(client, db_session):
    bike = _bike(db_session)
    response = _log(client, bike)
    assert response.status_code == 400
    assert "Add a note or pick at least one item." in response.text


def test_log_job_error_keeps_history_view(client, db_session):
    bike = _bike(db_session)
    response = _log(client, bike, view="history")
    assert response.status_code == 400
    assert "No maintenance logged yet." in response.text
    assert "Complete all" not in response.text


def test_log_job_accepts_no_items_with_note(client, db_session):
    bike = _bike(db_session)
    assert _log(client, bike, note="Straightened the radiators").status_code == 200
    assert db_session.query(UnplannedJob).one().item_keys == []


def test_delete_job_removes_its_counted_records(client, db_session):
    bike = _bike(db_session, hours=70)
    job = _job(db_session, bike, 25)
    db_session.add_all([
        ServiceRecord(bike_id=bike.id, item_key="oil", service_point=30, completed_date="2026-11-02", engine_hours=25, unplanned_job_id=job.id),
        ServiceRecord(bike_id=bike.id, item_key="oil", service_point=60, completed_date="2026-11-09", engine_hours=60),
    ])
    db_session.commit()
    response = client.post(f"/bikes/{bike.id}/unplanned-jobs/{job.id}/delete", data={"view": "history"})
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(UnplannedJob).count() == 0
    assert db_session.query(UnplannedJobItem).count() == 0
    assert [r.service_point for r in db_session.query(ServiceRecord)] == [60]


def test_delete_job_of_other_bike_404(client, db_session):
    bike = _bike(db_session)
    other = _bike(db_session, nickname="Other")
    job = _job(db_session, other, 25)
    assert client.post(f"/bikes/{bike.id}/unplanned-jobs/{job.id}/delete").status_code == 404
    assert db_session.query(UnplannedJob).count() == 1


def test_bike_page_history_view(client, db_session):
    bike = _bike(db_session)
    response = client.get(f"/bikes/{bike.id}?view=history")
    assert response.status_code == 200
    assert "History" in response.text
    assert "Log unplanned job" in response.text
    assert "No maintenance logged yet." in response.text
