"""Carb tab: log carburetor setting changes (jetting) for bikes whose model
has a carburetor, and delete entries. The current setup and the change
history are derived from the logged entries (`app.services.carb`).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Bike, CarbSetting
from app.routes.common import BikeId, CarbId, get_bike_or_404, parse_date, parse_notes, unit_of
from app.services.carb import CARB_FIELDS, changes_between, history, parse_carb_values, previous_for
from app.services.hours import current_hours_of

carb_router = APIRouter()

_FORM_FIELDS = ("date", "note", *(attr for attr, _ in CARB_FIELDS))


def get_carb_bike_or_404(request: Request, session: Session, bike_id: int):
    """The bike and its model, raising 404 if the bike doesn't exist or its
    model has no carburetor."""
    bike = get_bike_or_404(session, bike_id)
    bike_model = request.app.state.bike_models[bike.model_key]
    if not bike_model.carburetor:
        raise HTTPException(status_code=404)
    return bike, bike_model


def get_carb_or_404(session: Session, bike: Bike, carb_id: int) -> CarbSetting:
    """A `CarbSetting` by id, raising 404 if it doesn't exist or belongs to a
    different bike."""
    entry = session.get(CarbSetting, carb_id)
    if entry is None or entry.bike_id != bike.id:
        raise HTTPException(status_code=404)
    return entry


def _default_values(current: CarbSetting | None) -> dict:
    """The log form's prefill: today's date and the current setup's values."""
    values = {attr: getattr(current, attr) if current else "" for attr, _ in CARB_FIELDS}
    return {"date": date.today().isoformat(), "note": "", **values}


def _submitted_values(form) -> dict:
    """Echo back exactly what the user typed, so an error doesn't blank the form."""
    return {name: str(form.get(name) or "") for name in _FORM_FIELDS}


def _panel_context(bike: Bike, error: str | None = None, values: dict | None = None) -> dict:
    entries = history(bike.carb_settings)  # newest first
    current = entries[0].setting if entries else None
    return {
        "bike": bike,
        "fields": CARB_FIELDS,
        "current": current,
        "history": entries,
        "rides_by_id": {ride.id: ride for ride in bike.rides},
        "error": error,
        "values": values if values is not None else _default_values(current),
    }


def _render_panel(request: Request, bike: Bike, error: str | None = None, values: dict | None = None):
    return request.app.state.templates.TemplateResponse(
        request,
        "_carb_panel.html",
        _panel_context(bike, error, values),
        status_code=400 if error else 200,
    )


@carb_router.get("/bikes/{bike_id}/carb")
def carb_tab(bike_id: BikeId, request: Request, session: Session = Depends(get_session)):
    bike, bike_model = get_carb_bike_or_404(request, session, bike_id)
    # The page shell (hour meter, tabs) needs more than the panel itself.
    context = {
        **_panel_context(bike),
        "bike_model": bike_model,
        "unit": unit_of(request, bike),
        "current_hours": current_hours_of(bike.hours_events),
    }
    return request.app.state.templates.TemplateResponse(request, "bike_carb.html", context)


@carb_router.post("/bikes/{bike_id}/carb")
async def log_carb(bike_id: BikeId, request: Request, session: Session = Depends(get_session)):
    bike, _ = get_carb_bike_or_404(request, session, bike_id)
    submitted = _submitted_values(await request.form())

    def fail(message: str):
        return _render_panel(request, bike, error=message, values=submitted)

    date_str, error = parse_date(submitted["date"])
    if error is not None:
        return fail(error)
    note, error = parse_notes(submitted["note"])
    if error is not None:
        return fail(error)
    values, error = parse_carb_values(submitted)
    if error is not None:
        return fail(error)

    # Compare against the entry before this date, before the new row exists:
    # `ordered()` needs saved rows (it breaks date ties by id).
    previous = previous_for(bike.carb_settings, date_str)
    if not changes_between(previous, values):
        return fail(
            "Enter at least one value." if previous is None else "Nothing changed from the previous setup."
        )

    session.add(CarbSetting(bike_id=bike.id, date=date_str, note=note, **values))
    session.commit()

    return _render_panel(request, bike)


@carb_router.post("/bikes/{bike_id}/carb/{carb_id}/delete")
def delete_carb(bike_id: BikeId, carb_id: CarbId, request: Request, session: Session = Depends(get_session)):
    bike, _ = get_carb_bike_or_404(request, session, bike_id)
    session.delete(get_carb_or_404(session, bike, carb_id))
    session.commit()

    return _render_panel(request, bike)
