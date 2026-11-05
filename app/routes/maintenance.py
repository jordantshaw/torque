"""Maintenance tab actions: set the current reading, complete a single item,
or complete every item due at a given service point (optionally only those in
one system, such as Engine). Completing an item at a point also records its
earlier points that were never recorded (see `_add_with_catch_up`).

Every POST here writes to the database (or rejects with an inline error and
no write) and then re-renders `_maintenance_list.html` with fresh data, via
the same `build_maintenance_context` helper `app.routes.bikes` uses for the
initial page load -- so the htmx-swapped partial always reflects what's
actually in the database.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import HoursEvent, ServiceRecord, UnplannedJob, UnplannedJobItem
from app.routes.bikes import build_maintenance_context, item_job_note
from app.routes.common import (
    MAX_READING,
    BikeId,
    JobId,
    ServicePoint,
    get_bike_or_404,
    parse_date,
    parse_notes,
    parse_reading,
    unit_of,
)
from app.services.due import compute_due_info, items_for_service_point, recorded_points_by_item
from app.services.hours import current_hours_of
from app.services.schedule import ItemSchedule, action_at, next_point, unrecorded_points_through

maintenance_router = APIRouter()


def _render_panel(request: Request, bike, error: str | None = None, view: str = "scheduled"):
    context = build_maintenance_context(request, bike, view)
    context["error"] = error
    status_code = 400 if error else 200
    return request.app.state.templates.TemplateResponse(
        request, "_maintenance_list.html", context, status_code=status_code
    )


def _view(form) -> str:
    """Which Maintenance view the form was posted from, to re-render it."""
    return "history" if form.get("view") == "history" else "scheduled"


def _resolve_point(
    schedule: ItemSchedule, recorded: set[int], raw_point
) -> tuple[int | None, str | None]:
    """The service point an item is being completed at, as (point, error).

    A row inside a service names its own point; the plain per-item form
    doesn't, and then the item's next outstanding point is the one."""
    if raw_point:
        try:
            point = int(raw_point)
        except ValueError:
            point = None
        if (
            point is None
            or not 0 < point <= MAX_READING
            or point in recorded
            or action_at(schedule, point) is None
        ):
            return None, "Nothing due for this item at that service."
        return point, None
    point = next_point(schedule, recorded)
    if point is None:
        return None, "Nothing due for this item."
    return point, None


def _parse_completion(form, unit) -> tuple[str | None, float | None, str | None, str | None]:
    """The date, reading and notes from a completion form, as
    (date, stored reading, notes, error)."""
    reading, error = parse_reading(form.get("hours"), unit, unit.reading, allow_zero=True)
    if error is not None:
        return None, None, None, error
    date_str, error = parse_date(str(form.get("date", "")))
    if error is not None:
        return None, None, None, error
    notes, error = parse_notes(form.get("notes"))
    return date_str, reading, notes, error


def _add_with_catch_up(
    session: Session, bike, item_key: str, schedule: ItemSchedule, recorded: set[int],
    point: int, date_str: str, reading: float, notes: str | None,
) -> None:
    """Record `item_key` at `point`, plus each of its earlier open points, which
    completing a later service leaves behind (marked as covered by `point`)."""
    for earlier in unrecorded_points_through(schedule, recorded, point - 1):
        session.add(ServiceRecord(
            bike_id=bike.id, item_key=item_key, service_point=earlier, completed_date=date_str,
            engine_hours=reading, notes=notes, covered_by_point=point,
        ))
    session.add(ServiceRecord(
        bike_id=bike.id, item_key=item_key, service_point=point, completed_date=date_str,
        engine_hours=reading, notes=notes,
    ))


@maintenance_router.post("/bikes/{bike_id}/hours")
async def set_hours(bike_id: BikeId, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    form = await request.form()
    unit = unit_of(request, bike)
    reading, error = parse_reading(form.get("hours"), unit, unit.reading, allow_zero=True)

    if error is None:
        session.add(HoursEvent(
            bike_id=bike.id,
            date=date.today().isoformat(),
            kind="set",
            hours=reading,
        ))
        session.commit()

    return _render_panel(request, bike, error, _view(form))


@maintenance_router.post("/bikes/{bike_id}/items/{item_key}/complete")
async def complete_item(
    bike_id: BikeId, item_key: str, request: Request, session: Session = Depends(get_session)
):
    bike = get_bike_or_404(session, bike_id)
    bike_model = request.app.state.bike_models[bike.model_key]
    item = next((i for i in bike_model.items if i.key == item_key), None)
    if item is None:
        raise HTTPException(status_code=404)

    form = await request.form()
    recorded = recorded_points_by_item(bike.service_records).get(item_key, set())
    point, error = _resolve_point(item.schedule, recorded, form.get("point"))
    if error is not None:
        return _render_panel(request, bike, error, _view(form))

    date_str, reading, notes, error = _parse_completion(form, unit_of(request, bike))
    if error is not None:
        return _render_panel(request, bike, error, _view(form))

    _add_with_catch_up(session, bike, item_key, item.schedule, recorded, point, date_str, reading, notes)
    session.commit()

    return _render_panel(request, bike, view=_view(form))


@maintenance_router.post("/bikes/{bike_id}/service-points/{hour}/complete")
async def complete_service_point(
    bike_id: BikeId, hour: ServicePoint, request: Request, session: Session = Depends(get_session)
):
    bike = get_bike_or_404(session, bike_id)
    bike_model = request.app.state.bike_models[bike.model_key]

    form = await request.form()
    date_str, reading, notes, error = _parse_completion(form, unit_of(request, bike))
    if error is not None:
        return _render_panel(request, bike, error, _view(form))

    category = form.get("category")
    schedules = {
        item.key: item.schedule
        for item in bike_model.items
        if not category or item.category == category
    }
    recorded = recorded_points_by_item(bike.service_records)
    for item_key in items_for_service_point(schedules, hour, recorded):
        _add_with_catch_up(
            session, bike, item_key, schedules[item_key], recorded.get(item_key, set()),
            hour, date_str, reading, notes,
        )
    session.commit()

    return _render_panel(request, bike, view=_view(form))


# A reading typed in a display unit (miles) converts back with float noise;
# don't reject a job logged at exactly the current reading because of it.
_READING_TOLERANCE = 0.01


@maintenance_router.post("/bikes/{bike_id}/unplanned-jobs")
async def log_unplanned_job(bike_id: BikeId, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    bike_model = request.app.state.bike_models[bike.model_key]
    form = await request.form()
    view = _view(form)
    unit = unit_of(request, bike)

    reading, error = parse_reading(form.get("hours"), unit, unit.reading, allow_zero=True)
    date_str = note = None
    if error is None:
        date_str, error = parse_date(str(form.get("date", "")))
    if error is None:
        note, error = parse_notes(form.get("note"))
    keys = list(dict.fromkeys(str(key) for key in form.getlist("items")))
    if error is None and not set(keys) <= {item.key for item in bike_model.items}:
        error = "Pick items from this bike's schedule."
    if error is None and reading > current_hours_of(bike.hours_events) + _READING_TOLERANCE:
        error = "That's above the bike's current reading. Update the reading first."
    if error is None and not keys and not note:
        error = "Add a note or pick at least one item."
    if error is not None:
        return _render_panel(request, bike, error, view)

    job = UnplannedJob(bike_id=bike.id, date=date_str, engine_hours=reading, note=note)
    job.items = [UnplannedJobItem(item_key=key) for key in keys]
    session.add(job)
    session.commit()
    return _render_panel(request, bike, view=view)


def _job_or_404(session: Session, bike, job_id: int) -> UnplannedJob:
    job = session.get(UnplannedJob, job_id)
    if job is None or job.bike_id != bike.id:
        raise HTTPException(status_code=404)
    return job


@maintenance_router.post("/bikes/{bike_id}/unplanned-jobs/{job_id}/delete")
async def delete_unplanned_job(
    bike_id: BikeId, job_id: JobId, request: Request, session: Session = Depends(get_session)
):
    """Delete a job and every service record it was counted for, so those
    points are due again -- unless a later service of the item was completed,
    which (as with any completion) leaves the earlier point caught up."""
    bike = get_bike_or_404(session, bike_id)
    job = _job_or_404(session, bike, job_id)
    form = await request.form()
    plain = [
        r for r in bike.service_records if r.unplanned_job_id is None and r.covered_by_point is None
    ]
    for record in [r for r in bike.service_records if r.unplanned_job_id == job.id]:
        later = [
            r for r in plain if r.item_key == record.item_key and r.service_point > record.service_point
        ]
        session.delete(record)
        if later:
            cover = min(later, key=lambda r: r.service_point)
            session.add(ServiceRecord(
                bike_id=bike.id, item_key=record.item_key, service_point=record.service_point,
                completed_date=cover.completed_date, engine_hours=cover.engine_hours,
                notes=cover.notes, covered_by_point=cover.service_point,
            ))
    session.delete(job)
    session.commit()
    return _render_panel(request, bike, view=_view(form))


@maintenance_router.post("/bikes/{bike_id}/unplanned-jobs/{job_id}/count/{item_key}")
async def count_unplanned_job(
    bike_id: BikeId, job_id: JobId, item_key: str, request: Request, session: Session = Depends(get_session)
):
    """Record the item's next point, and every other open point up to the
    job's reading, as done by the job."""
    bike = get_bike_or_404(session, bike_id)
    bike_model = request.app.state.bike_models[bike.model_key]
    item = next((i for i in bike_model.items if i.key == item_key), None)
    if item is None:
        raise HTTPException(status_code=404)
    job = _job_or_404(session, bike, job_id)
    form = await request.form()
    view = _view(form)

    hours = current_hours_of(bike.hours_events)
    recorded = recorded_points_by_item(bike.service_records)
    info = compute_due_info(item.schedule, hours, recorded.get(item_key, set()), bike_model.upcoming_window)
    note = item_job_note(item, bike, hours, recorded, info, bike_model.upcoming_window)
    if note is None or note.job.id != job.id:
        return _render_panel(request, bike, "This job no longer applies to that item.", view)

    for point in note.covered:
        session.add(ServiceRecord(
            bike_id=bike.id, item_key=item_key, service_point=point, completed_date=job.date,
            engine_hours=job.engine_hours, notes=job.note, unplanned_job_id=job.id,
        ))
    session.commit()
    return _render_panel(request, bike, view=view)
