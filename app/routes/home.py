"""Home page: list existing bikes with due/upcoming maintenance counts, and
add a new bike.

For each bike, current engine hours are replayed from its `HoursEvent` rows
(`hours.current_hours`), and each maintenance item defined by the bike's
model is checked against the bike's `ServiceRecord` history
(`due.compute_due_info`) to tally how many items are due now vs. upcoming.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Bike
from app.services.due import Status, compute_due_info
from app.services.hours import HoursEventInput, current_hours

home_router = APIRouter()


def _bike_view(request: Request, bike: Bike) -> dict:
    """Build the template context for a single bike row on the home page."""
    bike_model = request.app.state.bike_models[bike.model_key]

    events = [
        HoursEventInput(id=e.id, date=e.date, kind=e.kind, hours=e.hours)
        for e in bike.hours_events
    ]
    hours = current_hours(events)

    recorded_by_item: dict[str, set[int]] = {}
    for record in bike.service_records:
        recorded_by_item.setdefault(record.item_key, set()).add(record.service_point)

    due_count = 0
    upcoming_count = 0
    for item in bike_model.items:
        recorded_hours = recorded_by_item.get(item.key, set())
        info = compute_due_info(item.schedule, hours, recorded_hours)
        if info.status == Status.DUE:
            due_count += 1
        elif info.status == Status.UPCOMING:
            upcoming_count += 1

    return {
        "id": bike.id,
        "nickname": bike.nickname,
        "display_name": bike_model.display_name,
        "current_hours": hours,
        "due_count": due_count,
        "upcoming_count": upcoming_count,
    }


@home_router.get("/")
def home(request: Request, session: Session = Depends(get_session)):
    bikes = session.query(Bike).all()
    bike_views = [_bike_view(request, bike) for bike in bikes]
    models = sorted(
        request.app.state.bike_models.values(), key=lambda m: m.display_name
    )
    return request.app.state.templates.TemplateResponse(
        request, "home.html", {"bikes": bike_views, "models": models}
    )


@home_router.post("/bikes")
async def create_bike(
    request: Request,
    session: Session = Depends(get_session),
):
    form = await request.form()
    nickname = str(form.get("nickname", ""))
    model_key = str(form.get("model_key", ""))

    error = None
    if not nickname.strip():
        error = "Nickname is required."
    elif model_key not in request.app.state.bike_models:
        error = "Unknown bike model."

    if error is not None:
        bikes = session.query(Bike).all()
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
                "nickname": nickname,
                "model_key": model_key,
            },
            status_code=400,
        )

    bike = Bike(nickname=nickname, model_key=model_key)
    session.add(bike)
    session.commit()
    return RedirectResponse(f"/bikes/{bike.id}", status_code=303)
