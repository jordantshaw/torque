"""The Maintenance tab's History view: scheduled services and unplanned jobs
in one list, newest first.

A scheduled service is one entry per service point and completion date, so
completing a whole service makes one entry. Points caught up by completing a
later one fold into that entry's `also_covers`. Points recorded by counting an
unplanned job show on the job's entry as `counted_for`, not as a service.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class HistoryEntry:
    kind: str  # "service" or "unplanned"
    date: str
    reading: float
    point: int | None
    item_names: tuple[str, ...]
    also_covers: tuple[int, ...]
    note: str | None
    job_id: int | None
    counted_for: tuple[tuple[int, str], ...]
    sort_id: int  # newest-saved tiebreak


def history_entries(records, jobs, item_names: dict[str, str]) -> list[HistoryEntry]:
    """Every service and unplanned job, newest first. Item keys missing from
    `item_names` (an item since removed from the model) are shown raw."""
    name = lambda key: item_names.get(key, key)  # noqa: E731
    counted: dict[int, list] = {}
    services: dict[tuple[int, str], list] = {}
    caught_up: dict[tuple[int, str], set[int]] = {}
    for record in records:
        if record.unplanned_job_id is not None:
            counted.setdefault(record.unplanned_job_id, []).append(record)
        elif record.covered_by_point is not None:
            caught_up.setdefault((record.covered_by_point, record.completed_date), set()).add(record.service_point)
        else:
            services.setdefault((record.service_point, record.completed_date), []).append(record)

    entries = [
        HistoryEntry(
            kind="service",
            date=day,
            reading=max(r.engine_hours for r in group),
            point=point,
            item_names=tuple(sorted({name(r.item_key) for r in group})),
            also_covers=tuple(sorted(caught_up.get((point, day), ()))),
            note=next((r.notes for r in group if r.notes), None),
            job_id=None,
            counted_for=(),
            sort_id=max(r.id for r in group),
        )
        for (point, day), group in services.items()
    ]
    entries += [
        HistoryEntry(
            kind="unplanned",
            date=job.date,
            reading=job.engine_hours,
            point=None,
            item_names=tuple(sorted(name(key) for key in job.item_keys)),
            also_covers=(),
            note=job.note,
            job_id=job.id,
            counted_for=tuple(sorted(
                (r.service_point, name(r.item_key)) for r in counted.get(job.id, [])
            )),
            sort_id=job.id,
        )
        for job in jobs
    ]
    return sorted(entries, key=lambda e: (e.date, e.reading, e.sort_id), reverse=True)
