from types import SimpleNamespace

from app.services.due import ItemDueInfo, Status
from app.services.schedule import ActionsSchedule, EveryHoursSchedule
from app.services.unplanned import job_note

OIL = EveryHoursSchedule(30, "S")


def _job(id, hours, date="2026-11-02"):
    return SimpleNamespace(id=id, engine_hours=hours, date=date)


def _due(point, status=Status.DUE):
    return ItemDueInfo(next_point=point, status=status, hours_overdue=None)


def _note(jobs, current, due, schedule=OIL, recorded=frozenset(), last=None):
    return job_note(schedule, set(recorded), last, jobs, due, current, 5)


def test_job_note_flush_five_hours_early():
    note = _note([_job(1, 25)], 31, _due(30))
    assert note.covered == (30,)
    assert note.ago == 6
    assert note.next_point == 60
    assert note.gap_after_job == 35
    assert note.manual_interval == 30
    assert note.warn is False


def test_job_note_flush_fifteen_hours_early_warns():
    note = _note([_job(1, 15)], 31, _due(30))
    assert note.gap_after_job == 45
    assert note.warn is True


def test_job_note_covers_all_missed_points():
    note = _note([_job(1, 90)], 100, _due(30))
    assert note.covered == (30, 60, 90)
    assert note.next_point == 120


def test_job_note_none_when_job_older_than_last_record():
    assert _note([_job(1, 25)], 31, _due(60, Status.OK), recorded={30}, last=30) is None
    assert _note([_job(1, 25)], 58, _due(60, Status.UPCOMING), recorded={30}, last=30) is None


def test_job_note_none_when_item_ok():
    assert _note([_job(1, 9)], 10, _due(30, Status.OK)) is None


def test_job_note_uses_highest_reading_job():
    note = _note([_job(2, 28), _job(1, 29)], 31, _due(30))
    assert note.job.id == 1


def test_job_note_no_next_point():
    schedule = ActionsSchedule({30: "S", 70: "S"})
    note = _note([_job(1, 68)], 70, _due(70), schedule=schedule, recorded={30}, last=30)
    assert note.covered == (70,)
    assert note.next_point is None
    assert note.gap_after_job is None
    assert note.manual_interval is None
    assert note.warn is False


def test_job_note_targets_upcoming_point_after_the_job_when_earlier_ones_are_overdue():
    note = _note([_job(1, 57)], 58, _due(30))
    assert note.point == 60
    assert note.covered == (30, 60)
    assert (note.next_point, note.gap_after_job, note.manual_interval, note.warn) == (90, 33, 30, False)


def test_job_note_point_is_the_highest_covered_point():
    assert _note([_job(1, 90)], 100, _due(30)).point == 90
    assert _note([_job(1, 25)], 31, _due(30)).point == 30
