from types import SimpleNamespace

from app.services.maintenance_history import history_entries

NAMES = {"oil": "Oil", "clutch_disks": "Clutch disks"}
_ids = iter(range(1, 1000))


def _rec(item, point, day, hours=None, job=None, covered_by=None, notes=None):
    return SimpleNamespace(
        id=next(_ids), item_key=item, service_point=point, completed_date=day,
        engine_hours=point if hours is None else hours, notes=notes,
        unplanned_job_id=job, covered_by_point=covered_by,
    )


def _job(id, day, hours, keys, note=None):
    return SimpleNamespace(id=id, date=day, engine_hours=hours, note=note, item_keys=keys)


def test_history_groups_a_service_into_one_entry():
    [entry] = history_entries([_rec("oil", 30, "2026-02-01"), _rec("clutch_disks", 30, "2026-02-01")], [], NAMES)
    assert (entry.kind, entry.point, entry.item_names) == ("service", 30, ("Clutch disks", "Oil"))


def test_history_splits_same_point_on_different_days():
    entries = history_entries([_rec("oil", 30, "2026-02-01"), _rec("clutch_disks", 30, "2026-02-03")], [], NAMES)
    assert [e.date for e in entries] == ["2026-02-03", "2026-02-01"]


def test_history_folds_caught_up_records_into_also_covers():
    records = [
        _rec("oil", 30, "2026-03-01", hours=91, covered_by=90),
        _rec("oil", 60, "2026-03-01", hours=91, covered_by=90),
        _rec("oil", 90, "2026-03-01", hours=91),
    ]
    [entry] = history_entries(records, [], NAMES)
    assert (entry.point, entry.also_covers, entry.reading) == (90, (30, 60), 91)


def test_history_puts_counted_records_on_the_job():
    job = _job(7, "2026-11-02", 25, ["oil"], note="Bent radiators")
    [entry] = history_entries([_rec("oil", 30, "2026-11-02", hours=25, job=7)], [job], NAMES)
    assert entry.kind == "unplanned"
    assert entry.job_id == 7
    assert entry.note == "Bent radiators"
    assert entry.item_names == ("Oil",)
    assert entry.counted_for == ((30, "Oil"),)


def test_history_orders_newest_first():
    records = [_rec("oil", 30, "2026-01-01"), _rec("oil", 60, "2026-03-01")]
    jobs = [_job(1, "2026-02-01", 45, ["oil"])]
    assert [e.date for e in history_entries(records, jobs, NAMES)] == ["2026-03-01", "2026-02-01", "2026-01-01"]


def test_history_shows_unknown_item_key_raw():
    [entry] = history_entries([], [_job(1, "2026-02-01", 45, ["gone"])], NAMES)
    assert entry.item_names == ("gone",)
