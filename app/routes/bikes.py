"""Bike page: the per-bike shell (tab nav) and its default Maintenance tab.

The Maintenance tab shows, per item defined by the bike's model, its due
status against the bike's recorded service history
(`due.compute_due_info`) plus the action letter due at that point
(`schedule.action_at`), grouped by the item's category. This context
building is shared with `app.routes.maintenance`, since every POST there
re-renders the same maintenance list after writing to the database.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Bike
from app.services.due import compute_due_info
from app.services.hours import HoursEventInput, current_hours
from app.services.schedule import action_at

bikes_router = APIRouter()


def get_bike_or_404(session: Session, bike_id: int) -> Bike:
    """Look up a `Bike` by id, raising `HTTPException(404)` if it doesn't exist."""
    bike = session.get(Bike, bike_id)
    if bike is None:
        raise HTTPException(status_code=404)
    return bike


def build_maintenance_context(request: Request, bike: Bike) -> dict:
    """Build the template context for the Maintenance tab: current engine
    hours, and every item in the bike's model grouped by category with its
    due status and next-due action letter."""
    bike_model = request.app.state.bike_models[bike.model_key]

    events = [
        HoursEventInput(id=e.id, date=e.date, kind=e.kind, hours=e.hours)
        for e in bike.hours_events
    ]
    hours = current_hours(events)

    recorded_by_item: dict[str, set[int]] = {}
    for record in bike.service_records:
        recorded_by_item.setdefault(record.item_key, set()).add(record.service_point)

    categories: dict[str, list[dict]] = {}
    service_points: set[int] = set()
    for item in bike_model.items:
        recorded_hours = recorded_by_item.get(item.key, set())
        info = compute_due_info(item.schedule, hours, recorded_hours)
        action = None
        if info.next_point is not None:
            action = action_at(item.schedule, info.next_point)
            service_points.add(info.next_point)
        categories.setdefault(item.category, []).append({
            "key": item.key,
            "name": item.name,
            "status": info.status,
            "next_point": info.next_point,
            "hours_overdue": info.hours_overdue,
            "action": action,
        })

    return {
        "bike": bike,
        "bike_model": bike_model,
        "current_hours": hours,
        "categories": categories,
        "service_points": sorted(service_points),
        "today": date.today().isoformat(),
    }


@bikes_router.get("/bikes/{bike_id}")
def bike_page(bike_id: int, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    context = build_maintenance_context(request, bike)
    return request.app.state.templates.TemplateResponse(
        request, "bike_maintenance.html", context
    )


@bikes_router.get("/bikes/{bike_id}/edit")
def edit_bike_form(bike_id: int, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    return request.app.state.templates.TemplateResponse(
        request, "bike_edit.html", {"bike": bike, "error": None, "nickname": bike.nickname}
    )


@bikes_router.post("/bikes/{bike_id}")
async def rename_bike(bike_id: int, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    form = await request.form()
    nickname = str(form.get("nickname", ""))

    if not nickname.strip():
        return request.app.state.templates.TemplateResponse(
            request,
            "bike_edit.html",
            {"bike": bike, "error": "Nickname is required.", "nickname": nickname},
            status_code=400,
        )

    bike.nickname = nickname
    session.commit()
    return RedirectResponse(f"/bikes/{bike_id}/edit", status_code=303)


@bikes_router.post("/bikes/{bike_id}/delete")
def delete_bike(bike_id: int, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    # Relies on the cascade="all, delete-orphan" relationships configured on
    # Bike (rides, hours_events, service_records) to remove the bike's
    # entire history along with it.
    session.delete(bike)
    session.commit()
    return RedirectResponse("/", status_code=303)
