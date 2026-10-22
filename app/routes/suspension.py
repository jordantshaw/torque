"""Suspension tab: a read-only reference table of the bike model's suspension
settings (with factory, racing, comfort, soft values), fixed values, and source.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.routes.common import BikeId, get_bike_or_404, unit_of
from app.services.hours import current_hours_of

suspension_router = APIRouter()


@suspension_router.get("/bikes/{bike_id}/suspension")
def suspension_tab(bike_id: BikeId, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    bike_model = request.app.state.bike_models[bike.model_key]

    context = {
        "bike": bike,
        "bike_model": bike_model,
        "unit": unit_of(request, bike),
        "current_hours": current_hours_of(bike.hours_events),
    }

    return request.app.state.templates.TemplateResponse(
        request, "bike_suspension.html", context
    )
