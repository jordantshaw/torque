"""Garage page: every bike as a card with its due/upcoming counts, plus adding
a bike and the clear-history / delete actions (per bike and in bulk).

For each bike, the current reading is replayed from its `HoursEvent` rows and
each maintenance item in its model is checked against the bike's
`ServiceRecord` history (`due.due_infos`) to count what is due or coming up.
"""

import re
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Bike, ServiceRecord
from app.routes.common import BikeId, get_bike_or_404, parse_ids, parse_nickname, unit_of
from app.services.due import Status, due_infos, health_pct, recorded_points_by_item
from app.services.hours import current_hours_of

home_router = APIRouter()


def _all_bikes(session: Session) -> list[Bike]:
    """Every bike by nickname, with the history `_bike_view` reads loaded in
    bulk (one query each) rather than once per bike."""
    return (
        session.query(Bike)
        .options(selectinload(Bike.hours_events), selectinload(Bike.service_records))
        .order_by(Bike.nickname)
        .all()
    )


def _bike_view(request: Request, bike: Bike) -> dict:
    """Build the template context for a single bike card."""
    bike_model = request.app.state.bike_models[bike.model_key]
    hours = current_hours_of(bike.hours_events)
    infos = due_infos(
        {item.key: item.schedule for item in bike_model.items},
        hours,
        recorded_points_by_item(bike.service_records),
        bike_model.upcoming_window,
    )
    counts = Counter(info.status for info in infos.values())
    due, upcoming = counts[Status.DUE], counts[Status.UPCOMING]

    return {
        "id": bike.id,
        "nickname": bike.nickname,
        "display_name": bike_model.display_name,
        "current_hours": hours,
        "unit": unit_of(request, bike),
        "due_count": due,
        "upcoming_count": upcoming,
        "health_pct": health_pct(len(infos), due + upcoming),
    }


def _notice(done: str | None, count: str | None) -> str | None:
    """The one-line confirmation shown after a bulk action (see `bulk_bikes`)."""
    if done not in ("deleted", "cleared") or not re.fullmatch(r"[0-9]{1,6}", count or "") or int(count) < 1:
        return None
    n = int(count)
    noun = "bike" if n == 1 else "bikes"
    if done == "deleted":
        return f"Deleted {n} {noun}."
    return f"Cleared the maintenance history of {n} {noun}."


def _clear_history(session: Session, bike_ids: list[int]) -> None:
    """Delete the service records of the given bikes. Rides and hours are kept."""
    session.query(ServiceRecord).filter(ServiceRecord.bike_id.in_(bike_ids)).delete(
        synchronize_session=False
    )


@home_router.get("/")
def home(request: Request, session: Session = Depends(get_session)):
    bikes = _all_bikes(session)
    bike_views = [_bike_view(request, bike) for bike in bikes]
    models = sorted(
        request.app.state.bike_models.values(), key=lambda m: m.display_name
    )
    return request.app.state.templates.TemplateResponse(
        request,
        "home.html",
        {
            "bikes": bike_views,
            "models": models,
            "notice": _notice(request.query_params.get("done"), request.query_params.get("n")),
        },
    )


@home_router.post("/bikes")
async def create_bike(
    request: Request,
    session: Session = Depends(get_session),
):
    form = await request.form()
    raw_nickname = str(form.get("nickname", ""))
    model_key = str(form.get("model_key", ""))

    nickname, error = parse_nickname(raw_nickname)
    if error is None and model_key not in request.app.state.bike_models:
        error = "Unknown bike model."

    if error is not None:
        bikes = _all_bikes(session)
        bike_views = [_bike_view(request, bike) for bike in bikes]
        models = sorted(
            request.app.state.bike_models.values(), key=lambda m: m.display_name
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "home.html",
            {
                "bikes": bike_views,
                "models": models,
                "error": error,
                "nickname": raw_nickname,
                "model_key": model_key,
            },
            status_code=400,
        )

    bike = Bike(nickname=nickname, model_key=model_key)
    session.add(bike)
    session.commit()
    return RedirectResponse(f"/bikes/{bike.id}", status_code=303)


@home_router.post("/bikes/{bike_id}/clear-history")
def clear_bike_history(bike_id: BikeId, session: Session = Depends(get_session)):
    """Forget every completed service on one bike (its rides and hours stay)."""
    bike = get_bike_or_404(session, bike_id)
    _clear_history(session, [bike.id])
    session.commit()
    return RedirectResponse("/?done=cleared&n=1", status_code=303)


@home_router.post("/bulk/bikes")
async def bulk_bikes(request: Request, session: Session = Depends(get_session)):
    """Apply one action (`delete` or `clear_history`) to every selected bike
    (the repeated `ids` form field). Unknown or non-numeric ids are ignored."""
    form = await request.form()
    action = form.get("action")
    if action not in ("delete", "clear_history"):
        raise HTTPException(status_code=400)

    ids = parse_ids(form.getlist("ids"))
    bikes = session.query(Bike).filter(Bike.id.in_(ids)).all() if ids else []
    if not bikes:
        return RedirectResponse("/", status_code=303)

    if action == "delete":
        for bike in bikes:
            # The relationships cascade, removing each bike's rides, hours and
            # service records with it.
            session.delete(bike)
        done = "deleted"
    else:
        _clear_history(session, [bike.id for bike in bikes])
        done = "cleared"
    session.commit()
    return RedirectResponse(f"/?done={done}&n={len(bikes)}", status_code=303)
