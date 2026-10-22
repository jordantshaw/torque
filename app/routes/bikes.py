"""Bike page: the per-bike shell (tab nav) and its default Maintenance tab.

The Maintenance tab shows summary tiles, then the manual's schedule as a list
of services (one per service point, each split by system), with every item's
state at that service. The grid itself comes from `app.services.intervals`;
this module attaches display details and builds the template context, which
`app.routes.maintenance` reuses because every POST there re-renders the same
panel after writing to the database.
"""

from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Bike
from app.routes.common import BikeId, get_bike_or_404, parse_nickname, unit_of
from app.services.due import Status, due_infos, health_pct, recorded_points_by_item
from app.services.hours import current_hours_of
from app.services.intervals import RowState, build_intervals
from app.services.units import DISPLAY_PREFERENCES

bikes_router = APIRouter()

# The manual prints single-letter action codes; spell them out for the UI.
ACTION_LABELS = {
    "C": "Check",
    "S": "Replace",
    "P": "Clean",
    "T": "Tighten",
    "R": "Adjust",
    "C/P": "Check or clean",
    "C/S": "Check or replace",
    "C/R": "Check or adjust",
}


def _history_by_item(records) -> dict[str, list]:
    """Each item's service records, most recent first."""
    history: dict[str, list] = {}
    for record in records:
        history.setdefault(record.item_key, []).append(record)
    for item_records in history.values():
        item_records.sort(key=lambda r: (r.completed_date, r.id), reverse=True)
    return history


def _row(item, state: RowState, point: int | None, action: str | None, history, records) -> dict:
    """One item as the template shows it within a service."""
    return {
        "key": item.key,
        "name": item.name,
        "category": item.category,
        "description": item.description,
        "page": item.page,
        "schedule_page": item.schedule_page,
        "action_label": ACTION_LABELS.get(action, action),
        "state": state.value,
        "point": point,
        "record": records.get((item.key, point)),
        "history": history.get(item.key, []),
    }


def _systems(rows: list[dict]) -> list[dict]:
    """Split a service's rows by system (category), in the model's order."""
    by_system: dict[str, list[dict]] = {}
    for row in rows:
        by_system.setdefault(row["category"], []).append(row)
    return [
        {"name": name, "items": sorted(items, key=lambda r: r["name"])}
        for name, items in by_system.items()
    ]


def _service_groups(bike_model, bike: Bike, hours: float, recorded, infos) -> list[dict]:
    """The services list: one group per service point, then a final group for
    items past the end of the manual's schedule."""
    items = {item.key: item for item in bike_model.items}
    history = _history_by_item(bike.service_records)
    records = {(r.item_key, r.service_point): r for r in bike.service_records}
    intervals = build_intervals(
        {key: item.schedule for key, item in items.items()},
        hours,
        recorded,
        bike_model.upcoming_window,
    )

    groups = [
        {
            "point": interval.point,
            "status": interval.status.value,
            "hours_overdue": hours - interval.point,
            "hours_until": interval.point - hours,
            "pending": interval.pending,
            "count": len(interval.rows),
            "systems": _systems([
                _row(items[r.item_key], r.state, interval.point, r.action, history, records)
                for r in interval.rows
            ]),
        }
        for interval in intervals
    ]

    beyond = [
        _row(item, RowState.BEYOND, None, None, history, records)
        for item in bike_model.items
        if infos[item.key].status == Status.BEYOND_SCHEDULE
    ]
    if beyond:
        groups.append({
            "point": None, "status": RowState.BEYOND.value, "hours_overdue": None,
            "hours_until": None, "pending": 0, "count": len(beyond), "systems": _systems(beyond),
        })
    return groups


def build_maintenance_context(request: Request, bike: Bike) -> dict:
    """Build the template context for the Maintenance tab."""
    bike_model = request.app.state.bike_models[bike.model_key]
    hours = current_hours_of(bike.hours_events)
    recorded = recorded_points_by_item(bike.service_records)
    infos = due_infos(
        {item.key: item.schedule for item in bike_model.items},
        hours,
        recorded,
        bike_model.upcoming_window,
    )

    counts = Counter(info.status for info in infos.values())
    due, upcoming = counts[Status.DUE], counts[Status.UPCOMING]
    groups = _service_groups(bike_model, bike, hours, recorded, infos)

    return {
        "bike": bike,
        "bike_model": bike_model,
        "unit": unit_of(request, bike),
        "upcoming_window": bike_model.upcoming_window,
        "current_hours": hours,
        "total_items": len(infos),
        "due_count": due,
        "upcoming_count": upcoming,
        "health_pct": health_pct(len(infos), due + upcoming),
        # The next service that isn't already due or coming up.
        "next_service": next((g for g in groups if g["status"] == RowState.LATER.value), None),
        "service_groups": groups,
        "today": date.today().isoformat(),
    }


@bikes_router.get("/bikes/{bike_id}")
def bike_page(bike_id: BikeId, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    context = build_maintenance_context(request, bike)
    return request.app.state.templates.TemplateResponse(
        request, "bike_maintenance.html", context
    )


def _edit_context(request: Request, bike: Bike, error: str | None, nickname: str) -> dict:
    bike_model = request.app.state.bike_models[bike.model_key]
    return {
        "bike": bike,
        "bike_model": bike_model,
        "unit": unit_of(request, bike),
        "error": error,
        "nickname": nickname,
    }


@bikes_router.get("/bikes/{bike_id}/edit")
def edit_bike_form(bike_id: BikeId, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    return request.app.state.templates.TemplateResponse(
        request, "bike_edit.html", _edit_context(request, bike, None, bike.nickname)
    )


@bikes_router.post("/bikes/{bike_id}")
async def rename_bike(bike_id: BikeId, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    form = await request.form()
    raw_nickname = str(form.get("nickname", ""))

    nickname, error = parse_nickname(raw_nickname)
    if error is not None:
        return request.app.state.templates.TemplateResponse(
            request,
            "bike_edit.html",
            _edit_context(request, bike, error, raw_nickname),
            status_code=400,
        )

    bike.nickname = nickname
    distance_unit = str(form.get("distance_unit", ""))
    if distance_unit in DISPLAY_PREFERENCES:
        bike.distance_unit = distance_unit
    session.commit()
    return RedirectResponse(f"/bikes/{bike_id}/edit", status_code=303)


@bikes_router.post("/bikes/{bike_id}/delete")
def delete_bike(bike_id: BikeId, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    # Relies on the cascade="all, delete-orphan" relationships configured on
    # Bike (rides, hours_events, service_records) to remove the bike's
    # entire history along with it.
    session.delete(bike)
    session.commit()
    return RedirectResponse("/", status_code=303)
