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
        ServiceRecord(bike_id=bike.id, item_key="clutch_disks", service_point=30, completed_date="2026-11-09", engine_hours=31),
    ])
    db_session.commit()
    response = client.post(f"/bikes/{bike.id}/unplanned-jobs/{job.id}/delete", data={"view": "history"})
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(UnplannedJob).count() == 0
    assert db_session.query(UnplannedJobItem).count() == 0
    assert [(r.item_key, r.service_point) for r in db_session.query(ServiceRecord)] == [("clutch_disks", 30)]


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


def _count(client, bike, job, item="oil"):
    return client.post(f"/bikes/{bike.id}/unplanned-jobs/{job.id}/count/{item}", data={"view": "scheduled"})


def test_due_row_shows_job_note(client, db_session):
    bike = _bike(db_session, hours=31)
    _job(db_session, bike, 25)
    html = client.get(f"/bikes/{bike.id}").text
    assert "You did it 6h ago, at 25h (2026-11-02)." in html
    assert "Counting this job moves the next one to 60h, 35h after the job. The manual's interval is 30h." in html
    assert "Count this job" in html
    assert "longer than the manual" not in html


def test_due_row_warns_for_long_gap(client, db_session):
    bike = _bike(db_session, hours=31)
    _job(db_session, bike, 15)
    assert "That's longer than the manual's interval." in client.get(f"/bikes/{bike.id}").text


def test_due_row_lists_every_point_a_job_covers(client, db_session):
    bike = _bike(db_session, hours=100)
    _job(db_session, bike, 90)
    assert "This covers the 30h, 60h and 90h services." in client.get(f"/bikes/{bike.id}").text


def test_no_note_when_item_not_due(client, db_session):
    bike = _bike(db_session, hours=10)
    _job(db_session, bike, 9)
    assert "Count this job" not in client.get(f"/bikes/{bike.id}").text


def test_count_job_records_point_and_links_job(client, db_session):
    bike = _bike(db_session, hours=31)
    job = _job(db_session, bike, 25)
    response = _count(client, bike, job)
    assert response.status_code == 200
    db_session.expire_all()
    [record] = db_session.query(ServiceRecord).filter_by(item_key="oil").all()
    assert (record.service_point, record.unplanned_job_id, record.engine_hours) == (30, job.id, 25)
    assert record.completed_date == "2026-11-02"
    assert "Covered by unplanned job on 2026-11-02 at 25h" in response.text
    assert "Count this job" not in response.text


def test_count_job_covers_all_missed_points(client, db_session):
    bike = _bike(db_session, hours=100)
    job = _job(db_session, bike, 90)
    assert _count(client, bike, job).status_code == 200
    db_session.expire_all()
    assert {r.service_point for r in db_session.query(ServiceRecord).filter_by(item_key="oil")} == {30, 60, 90}


def test_count_job_rejects_when_it_no_longer_applies(client, db_session):
    bike = _bike(db_session, hours=31)
    job = _job(db_session, bike, 25)
    client.post(f"/bikes/{bike.id}/items/oil/complete", data={"date": "2026-11-03", "hours": 31})
    response = _count(client, bike, job)
    assert response.status_code == 400
    assert "This job no longer applies to that item." in response.text
    assert db_session.query(ServiceRecord).filter_by(item_key="oil").count() == 1


def test_count_job_unknown_item_404(client, db_session):
    bike = _bike(db_session, hours=31)
    job = _job(db_session, bike, 25)
    assert _count(client, bike, job, item="nope").status_code == 404


def test_item_history_lists_unplanned_jobs(client, db_session):
    bike = _bike(db_session, hours=31)
    _job(db_session, bike, 25)
    assert "Unplanned, 2026-11-02 at 25h" in client.get(f"/bikes/{bike.id}").text


def test_job_just_before_an_upcoming_point_is_offered_there_and_catches_up(client, db_session):
    bike = _bike(db_session, hours=58)
    job = _job(db_session, bike, 57)
    html = client.get(f"/bikes/{bike.id}").text
    sixty = html[html.index("60-hour service"):]
    assert "You did it 1h ago, at 57h" in sixty
    assert _count(client, bike, job).status_code == 200
    db_session.expire_all()
    assert {r.service_point for r in db_session.query(ServiceRecord).filter_by(item_key="oil")} == {30, 60}


def test_deleting_a_job_behind_a_later_service_keeps_its_points_caught_up(client, db_session):
    bike = _bike(db_session, hours=85)
    job = _job(db_session, bike, 25)
    db_session.add(ServiceRecord(bike_id=bike.id, item_key="oil", service_point=30, completed_date="2026-11-02", engine_hours=25, unplanned_job_id=job.id))
    db_session.commit()
    client.post(f"/bikes/{bike.id}/items/oil/complete", data={"point": "60", "date": "2026-11-04", "hours": 61})
    client.post(f"/bikes/{bike.id}/unplanned-jobs/{job.id}/delete")
    db_session.expire_all()
    records = {r.service_point: r for r in db_session.query(ServiceRecord).filter_by(item_key="oil")}
    assert set(records) == {30, 60}
    assert (records[30].unplanned_job_id, records[30].covered_by_point) == (None, 60)
    assert records[30].completed_date == "2026-11-04"
