"""Unplanned jobs against the schedule.

An unplanned job (maintenance done off-schedule) never changes the schedule by
itself. When an item it covers is due or coming up, the Maintenance tab shows
a note with what counting the job would mean, and the owner decides.
`job_note` works out that note.
"""

from dataclasses import dataclass

from app.services.due import ItemDueInfo, Status
from app.services.schedule import ItemSchedule, next_point, unrecorded_points_through


@dataclass(frozen=True)
class JobNote:
    job: object  # the UnplannedJob that applies
    point: int  # the service point the note is shown on (the highest covered)
    covered: tuple[int, ...]  # points counting it would record, ascending
    ago: float  # current reading minus the job's reading
    next_point: int | None  # the item's next point after the covered ones
    gap_after_job: float | None  # next_point minus the job's reading
    manual_interval: int | None  # next_point minus the highest covered point
    warn: bool  # the job was more than the upcoming window before the highest covered point


def job_note(
    schedule: ItemSchedule,
    recorded: set[int],
    last_record_hours: float | None,
    jobs: list,
    due: ItemDueInfo,
    current: float,
    upcoming_window: float,
) -> JobNote | None:
    """The note for an item, or None when no job applies.

    A job applies when the item is due or coming up and the job is later than
    the item's latest service record. The highest-reading job wins (ties go to
    the newest). Counting it covers every open point up to the job's reading,
    plus the first point after the job if that one is due or coming up. The
    note sits on the highest covered point."""
    if due.status not in (Status.DUE, Status.UPCOMING) or due.next_point is None:
        return None
    candidates = [
        job for job in jobs if last_record_hours is None or job.engine_hours > last_record_hours
    ]
    if not candidates:
        return None
    job = max(candidates, key=lambda j: (j.engine_hours, j.id))

    # The open points up to the job, plus the first one after it when that one
    # is due or coming up (a job just before it is what the owner may skip).
    below = unrecorded_points_through(schedule, recorded, job.engine_hours)
    first_after = next_point(schedule, recorded | set(below))
    if first_after is not None and first_after - current <= upcoming_window:
        covered = (*below, first_after)
    elif below:
        covered = tuple(below)
    else:
        return None
    after = next_point(schedule, recorded | set(covered))
    highest = covered[-1]
    return JobNote(
        job=job,
        point=highest,
        covered=covered,
        ago=current - job.engine_hours,
        next_point=after,
        gap_after_job=None if after is None else after - job.engine_hours,
        manual_interval=None if after is None else after - highest,
        warn=highest - job.engine_hours > upcoming_window,
    )
