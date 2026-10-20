"""Suspension tab: a read-only reference table of the bike model's suspension
settings (with factory, racing, comfort, soft values), fixed values, and source.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.routes.bikes import get_bike_or_404
from app.services.hours import HoursEventInput, current_hours

suspension_router = APIRouter()


@suspension_router.get("/bikes/{bike_id}/suspension")
def suspension_tab(bike_id: int, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    bike_model = request.app.state.bike_models[bike.model_key]

    # Compute current engine hours from the bike's hours events
    events = [
        HoursEventInput(id=e.id, date=e.date, kind=e.kind, hours=e.hours)
        for e in bike.hours_events
    ]
    hours = current_hours(events)

    context = {
        "bike": bike,
        "bike_model": bike_model,
        "current_hours": hours,
    }

    return request.app.state.templates.TemplateResponse(
        request, "bike_suspension.html", context
    )
