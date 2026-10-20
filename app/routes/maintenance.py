"""Maintenance tab actions: set current hours, complete a single item, or
complete every item due at a given service point.

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
from app.models import HoursEvent, ServiceRecord
from app.routes.bikes import build_maintenance_context, get_bike_or_404
from app.services.due import items_for_service_point
from app.services.schedule import next_point

maintenance_router = APIRouter()


def _render_panel(request: Request, bike, error: str | None = None):
    context = build_maintenance_context(request, bike)
    context["error"] = error
    status_code = 400 if error else 200
    return request.app.state.templates.TemplateResponse(
        request, "_maintenance_list.html", context, status_code=status_code
    )


def _parse_hours(raw) -> tuple[float | None, str | None]:
    """Parse a form `hours` value, returning (hours, error). Fractional
    hours (e.g. 1.5) are allowed."""
    try:
        hours = float(raw)
    except (TypeError, ValueError):
        return None, "Hours must be a number."
    if hours < 0:
        return None, "Hours must be zero or greater."
    return hours, None


def _parse_date(raw: str) -> tuple[str | None, str | None]:
    """Validate a form `date` value is a parseable ISO date, returning
    (date_string, error)."""
    if not raw:
        return None, "Date is required."
    try:
        date.fromisoformat(raw)
    except ValueError:
        return None, "Date must be a valid date."
    return raw, None


@maintenance_router.post("/bikes/{bike_id}/hours")
async def set_hours(bike_id: int, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    form = await request.form()
    hours, error = _parse_hours(form.get("hours"))

    if error is None:
        session.add(HoursEvent(
            bike_id=bike.id,
            date=date.today().isoformat(),
            kind="set",
            hours=hours,
        ))
        session.commit()

    return _render_panel(request, bike, error)


@maintenance_router.post("/bikes/{bike_id}/items/{item_key}/complete")
async def complete_item(
    bike_id: int, item_key: str, request: Request, session: Session = Depends(get_session)
):
    bike = get_bike_or_404(session, bike_id)
    bike_model = request.app.state.bike_models[bike.model_key]
    item = next((i for i in bike_model.items if i.key == item_key), None)
    if item is None:
        raise HTTPException(status_code=404)

    recorded_hours = {
        r.service_point for r in bike.service_records if r.item_key == item_key
    }
    point = next_point(item.schedule, recorded_hours)
    if point is None:
        return _render_panel(request, bike, error="Nothing due for this item.")

    form = await request.form()
    hours, error = _parse_hours(form.get("hours"))
    date_str = None
    if error is None:
        date_str, error = _parse_date(str(form.get("date", "")))

    if error is not None:
        return _render_panel(request, bike, error)

    notes = str(form.get("notes", "") or "") or None
    session.add(ServiceRecord(
        bike_id=bike.id,
        item_key=item_key,
        service_point=point,
        completed_date=date_str,
        engine_hours=hours,
        notes=notes,
    ))
    session.commit()

    return _render_panel(request, bike)


@maintenance_router.post("/bikes/{bike_id}/service-points/{hour}/complete")
async def complete_service_point(
    bike_id: int, hour: int, request: Request, session: Session = Depends(get_session)
):
    bike = get_bike_or_404(session, bike_id)
    bike_model = request.app.state.bike_models[bike.model_key]

    form = await request.form()
    hours, error = _parse_hours(form.get("hours"))
    date_str = None
    if error is None:
        date_str, error = _parse_date(str(form.get("date", "")))

    if error is not None:
        return _render_panel(request, bike, error)

    recorded_by_item: dict[str, set[int]] = {}
    for record in bike.service_records:
        recorded_by_item.setdefault(record.item_key, set()).add(record.service_point)

    item_schedules = {item.key: item.schedule for item in bike_model.items}
    item_keys = items_for_service_point(item_schedules, hour, recorded_by_item)

    notes = str(form.get("notes", "") or "") or None
    for item_key in item_keys:
        session.add(ServiceRecord(
            bike_id=bike.id,
            item_key=item_key,
            service_point=hour,
            completed_date=date_str,
            engine_hours=hours,
            notes=notes,
        ))
    session.commit()

    return _render_panel(request, bike)
