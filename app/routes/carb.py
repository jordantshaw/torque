"""Carb tab: log carburetor setting changes (jetting) for bikes whose model
has a carburetor, and delete entries. The current setup and the change
history are derived from the logged entries (`app.services.carb`).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Bike, CarbSetting
from app.routes.common import (
    MAX_CARB_VALUE,
    BikeId,
    CarbId,
    get_bike_or_404,
    parse_date,
    parse_notes,
)
from app.services.carb import CARB_FIELDS, changes_between, current, history, previous_for
from app.services.hours import current_hours_of
from app.services.units import unit_for

carb_router = APIRouter()


def get_carb_bike_or_404(request: Request, session: Session, bike_id: int):
    """The bike and its model, raising 404 if the bike doesn't exist or its
    model has no carburetor."""
    bike = get_bike_or_404(session, bike_id)
    bike_model = request.app.state.bike_models[bike.model_key]
    if not bike_model.carburetor:
        raise HTTPException(status_code=404)
    return bike, bike_model


def _default_values(bike: Bike) -> dict:
    """The log form's prefill: today's date and the current setup's values."""
    setting = current(bike.carb_settings)
    values = {attr: (getattr(setting, attr) if setting else "") for attr, _ in CARB_FIELDS}
    return {"date": date.today().isoformat(), "note": "", **values}


def _submitted_values(form) -> dict:
    """Echo back exactly what the user typed, so an error doesn't blank the form."""
    values = {"date": str(form.get("date", "") or ""), "note": str(form.get("note", "") or "")}
    for attr, _ in CARB_FIELDS:
        values[attr] = str(form.get(attr, "") or "")
    return values


def _context(bike: Bike, bike_model, error: str | None = None, values: dict | None = None) -> dict:
    return {
        "bike": bike,
        "bike_model": bike_model,
        "unit": unit_for(bike_model.unit, bike.distance_unit),
        "current_hours": current_hours_of(bike.hours_events),
        "fields": CARB_FIELDS,
        "current": current(bike.carb_settings),
        "history": history(bike.carb_settings),
        "error": error,
        "values": values if values is not None else _default_values(bike),
    }


def _render_panel(request: Request, bike: Bike, bike_model, error: str | None = None, values: dict | None = None):
    return request.app.state.templates.TemplateResponse(
        request,
        "_carb_panel.html",
        _context(bike, bike_model, error, values),
        status_code=400 if error else 200,
    )


@carb_router.get("/bikes/{bike_id}/carb")
def carb_tab(bike_id: BikeId, request: Request, session: Session = Depends(get_session)):
    bike, bike_model = get_carb_bike_or_404(request, session, bike_id)
    return request.app.state.templates.TemplateResponse(request, "bike_carb.html", _context(bike, bike_model))


@carb_router.post("/bikes/{bike_id}/carb")
async def log_carb(bike_id: BikeId, request: Request, session: Session = Depends(get_session)):
    bike, bike_model = get_carb_bike_or_404(request, session, bike_id)
    form = await request.form()
    submitted = _submitted_values(form)

    def fail(message: str):
        return _render_panel(request, bike, bike_model, error=message, values=submitted)

    date_str, error = parse_date(submitted["date"])
    if error is not None:
        return fail(error)
    note, error = parse_notes(submitted["note"])
    if error is not None:
        return fail(error)

    values = {}
    for attr, label in CARB_FIELDS:
        value = submitted[attr].strip()
        if len(value) > MAX_CARB_VALUE:
            return fail(f"{label} must be {MAX_CARB_VALUE} characters or fewer.")
        values[attr] = value

    # Compare against the entry before this date, before the new row exists:
    # `ordered()` needs saved rows (it breaks date ties by id).
    previous = previous_for(bike.carb_settings, date_str)
    if previous is None:
        if not any(values.values()):
            return fail("Enter at least one value.")
    elif not changes_between(previous, values):
        return fail("Nothing changed from the previous setup.")

    session.add(CarbSetting(bike_id=bike.id, date=date_str, note=note, **values))
    session.commit()

    return _render_panel(request, bike, bike_model)


@carb_router.post("/bikes/{bike_id}/carb/{carb_id}/delete")
def delete_carb(bike_id: BikeId, carb_id: CarbId, request: Request, session: Session = Depends(get_session)):
    bike, bike_model = get_carb_bike_or_404(request, session, bike_id)
    entry = session.get(CarbSetting, carb_id)
    if entry is None or entry.bike_id != bike.id:
        raise HTTPException(status_code=404)
    session.delete(entry)
    session.commit()

    return _render_panel(request, bike, bike_model)
