"""Maintenance tab actions: set the current reading, complete a single item,
or complete every item due at a given service point.

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
from app.routes.bikes import build_maintenance_context
from app.routes.common import (
    MAX_READING,
    BikeId,
    ServicePoint,
    get_bike_or_404,
    parse_date,
    parse_notes,
    parse_reading,
    unit_of,
)
from app.services.due import items_for_service_point, recorded_points_by_item
from app.services.schedule import ItemSchedule, action_at, next_point

maintenance_router = APIRouter()


def _render_panel(request: Request, bike, error: str | None = None):
    context = build_maintenance_context(request, bike)
    context["error"] = error
    status_code = 400 if error else 200
    return request.app.state.templates.TemplateResponse(
        request, "_maintenance_list.html", context, status_code=status_code
    )


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

    return _render_panel(request, bike, error)


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
        return _render_panel(request, bike, error)

    date_str, reading, notes, error = _parse_completion(form, unit_of(request, bike))
    if error is not None:
        return _render_panel(request, bike, error)

    session.add(ServiceRecord(
        bike_id=bike.id,
        item_key=item_key,
        service_point=point,
        completed_date=date_str,
        engine_hours=reading,
        notes=notes,
    ))
    session.commit()

    return _render_panel(request, bike)


@maintenance_router.post("/bikes/{bike_id}/service-points/{hour}/complete")
async def complete_service_point(
    bike_id: BikeId, hour: ServicePoint, request: Request, session: Session = Depends(get_session)
):
    bike = get_bike_or_404(session, bike_id)
    bike_model = request.app.state.bike_models[bike.model_key]

    form = await request.form()
    date_str, reading, notes, error = _parse_completion(form, unit_of(request, bike))
    if error is not None:
        return _render_panel(request, bike, error)

    item_keys = items_for_service_point(
        {item.key: item.schedule for item in bike_model.items},
        hour,
        recorded_points_by_item(bike.service_records),
    )

    for item_key in item_keys:
        session.add(ServiceRecord(
            bike_id=bike.id,
            item_key=item_key,
            service_point=hour,
            completed_date=date_str,
            engine_hours=reading,
            notes=notes,
        ))
    session.commit()

    return _render_panel(request, bike)
