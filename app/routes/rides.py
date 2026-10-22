"""Rides tab: log a ride (with optional suspension click/turn settings),
edit it, or delete it.

Every logged ride also advances the bike's current engine hours, which is
computed elsewhere by replaying `HoursEvent` rows (`app.services.hours`).
To keep that total accurate, each `Ride` has exactly one linked
`HoursEvent(kind="ride", ride_id=ride.id)`: creating a ride always creates
its event in the same transaction, editing a ride updates that SAME event
row in place (never a second one), and deleting a ride deletes both rows.
Letting these drift apart -- an orphaned event, a duplicate, or a ride with
none -- would make the bike's hours total silently wrong.
"""

import math
from datetime import date
from typing import NamedTuple

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Bike, HoursEvent, Ride
from app.routes.common import (
    MAX_READING,
    BikeId,
    RideId,
    get_bike_or_404,
    parse_date,
    parse_notes,
    parse_reading,
    unit_of,
)
from app.services.hours import current_hours_of

rides_router = APIRouter()

# The five click/turn suspension settings a ride can record, and the exact
# `suspension.settings[].name` string (from the bike model YAML) each one
# corresponds to. `sag_static`/`sag_rider` are deliberately not here: the
# model only has a range for those (no single factory value), so they're
# only ever prefilled from the most recent ride.
SUSPENSION_FIELD_BY_SETTING_NAME = {
    "Fork compression (clicks out)": "fork_compression",
    "Fork rebound (clicks out)": "fork_rebound",
    "Shock low-speed compression (clicks out)": "shock_lsc",
    "Shock high-speed compression (turns out)": "shock_hsc",
    "Shock rebound (clicks out)": "shock_rebound",
}
SUSPENSION_FIELDS = tuple(SUSPENSION_FIELD_BY_SETTING_NAME.values())
SAG_FIELDS = ("sag_static", "sag_rider")


def get_ride_or_404(session: Session, bike_id: BikeId, ride_id: int) -> Ride:
    """Look up a `Ride` by id, raising `HTTPException(404)` if it doesn't
    exist or belongs to a different bike."""
    ride = session.get(Ride, ride_id)
    if ride is None or ride.bike_id != bike_id:
        raise HTTPException(status_code=404)
    return ride


def _most_recent_ride(bike: Bike) -> Ride | None:
    if not bike.rides:
        return None
    return max(bike.rides, key=lambda r: (r.date, r.id))


def _default_form_values(bike: Bike, bike_model) -> dict:
    """Prefill values for the log-ride form's suspension fields: the most
    recent ride's values if any ride exists, else the bike model's factory
    setting (matched by setting name)."""
    recent = _most_recent_ride(bike)
    values: dict = {"date": date.today().isoformat(), "hours": None, "notes": ""}

    if recent is not None:
        for field in (*SUSPENSION_FIELDS, *SAG_FIELDS):
            values[field] = getattr(recent, field)
        return values

    factory_values = {
        SUSPENSION_FIELD_BY_SETTING_NAME[s.name]: s.factory
        for s in bike_model.suspension.settings
        if s.name in SUSPENSION_FIELD_BY_SETTING_NAME
    }
    for field in SUSPENSION_FIELDS:
        values[field] = factory_values.get(field)
    for field in SAG_FIELDS:
        values[field] = None
    return values


class RideInput(NamedTuple):
    """A ride's validated form fields, in the stored unit."""

    length: float
    date: str
    notes: str | None


def _parse_ride(form, unit) -> tuple[RideInput | None, str | None]:
    """A ride's length, date and notes, as (fields, error). A ride has to cover
    something, so zero is rejected."""
    length, error = parse_reading(form.get("hours"), unit, unit.ride_label, allow_zero=False)
    if error is not None:
        return None, error
    date_str, error = parse_date(str(form.get("date", "")))
    if error is not None:
        return None, error
    notes, error = parse_notes(form.get("notes"))
    if error is not None:
        return None, error
    return RideInput(length, date_str, notes), None


def _parse_optional_number(raw, *, integer: bool) -> int | float | None:
    """An optional suspension setting. Blank, non-numeric, non-finite and
    out-of-range values are treated as "not given"."""
    if raw is None or raw == "":
        return None
    try:
        value = int(raw) if integer else float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or abs(value) > MAX_READING:
        return None
    return value


def _suspension_fields_from_form(form) -> dict:
    fields = {
        f: _parse_optional_number(form.get(f), integer=True)
        for f in SUSPENSION_FIELDS
        if f != "shock_hsc"
    }
    fields["shock_hsc"] = _parse_optional_number(form.get("shock_hsc"), integer=False)
    for field in SAG_FIELDS:
        fields[field] = _parse_optional_number(form.get(field), integer=True)
    return fields


def _submitted_form_values(form) -> dict:
    """Echo back exactly what the user typed, so a validation error doesn't
    blank out the form they just filled in."""
    values = {
        "date": str(form.get("date", "") or ""),
        "hours": str(form.get("hours", "") or ""),
        "notes": str(form.get("notes", "") or ""),
    }
    for field in (*SUSPENSION_FIELDS, *SAG_FIELDS):
        values[field] = str(form.get(field, "") or "")
    return values


def _list_context(
    request: Request, bike: Bike, bike_model, error: str | None = None, form_values: dict | None = None
) -> dict:
    rides = sorted(bike.rides, key=lambda r: (r.date, r.id), reverse=True)
    if form_values is None:
        form_values = _default_form_values(bike, bike_model)
    return {
        "bike": bike,
        "bike_model": bike_model,
        "unit": unit_of(request, bike),
        "rides": rides,
        "current_hours": current_hours_of(bike.hours_events),
        "error": error,
        "values": form_values,
        "action": f"/bikes/{bike.id}/rides",
        "submit_label": "Log ride",
        "cancel_url": None,
    }


def _render_list(
    request: Request, bike: Bike, bike_model, error: str | None = None, form_values: dict | None = None
):
    context = _list_context(request, bike, bike_model, error=error, form_values=form_values)
    status_code = 400 if error else 200
    return request.app.state.templates.TemplateResponse(
        request, "_rides_list.html", context, status_code=status_code
    )


@rides_router.get("/bikes/{bike_id}/rides")
def rides_tab(bike_id: BikeId, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    bike_model = request.app.state.bike_models[bike.model_key]
    context = _list_context(request, bike, bike_model)
    return request.app.state.templates.TemplateResponse(request, "bike_rides.html", context)


@rides_router.post("/bikes/{bike_id}/rides")
async def create_ride(bike_id: BikeId, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    bike_model = request.app.state.bike_models[bike.model_key]
    form = await request.form()

    fields, error = _parse_ride(form, unit_of(request, bike))
    if error is not None:
        return _render_list(request, bike, bike_model, error=error, form_values=_submitted_form_values(form))

    ride = Ride(
        bike_id=bike.id,
        date=fields.date,
        hours=fields.length,
        notes=fields.notes,
        **_suspension_fields_from_form(form),
    )
    session.add(ride)
    session.flush()  # assign ride.id before the linked HoursEvent references it
    session.add(HoursEvent(bike_id=bike.id, date=fields.date, kind="ride", hours=fields.length, ride_id=ride.id))
    session.commit()

    return _render_list(request, bike, bike_model)


@rides_router.get("/bikes/{bike_id}/rides/{ride_id}/edit")
def edit_ride_form(bike_id: BikeId, ride_id: RideId, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    ride = get_ride_or_404(session, bike_id, ride_id)
    unit = unit_of(request, bike)

    values = {
        "date": ride.date,
        "hours": unit.edit_value(ride.hours),
        "notes": ride.notes or "",
        **{field: getattr(ride, field) for field in (*SUSPENSION_FIELDS, *SAG_FIELDS)},
    }
    context = {
        "unit": unit,
        "error": None,
        "values": values,
        "action": f"/bikes/{bike_id}/rides/{ride.id}",
        "submit_label": "Save",
        "cancel_url": f"/bikes/{bike_id}/rides",
        # Keeps the `ride-{id}` id on the swapped-in element (replacing the
        # display `<li id="ride-{id}">`), so a later failed update POST can
        # retarget its error back onto this same element by id.
        "wrapper_id": f"ride-{ride.id}",
    }
    return request.app.state.templates.TemplateResponse(request, "_ride_form.html", context)


@rides_router.post("/bikes/{bike_id}/rides/{ride_id}")
async def update_ride(bike_id: BikeId, ride_id: RideId, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    bike_model = request.app.state.bike_models[bike.model_key]
    ride = get_ride_or_404(session, bike_id, ride_id)
    form = await request.form()

    fields, error = _parse_ride(form, unit_of(request, bike))
    if error is not None:
        # Re-render just this ride's edit form in place (not the whole
        # list, and not the "log a ride" create form) with the user's
        # submitted values preserved, so a bad edit doesn't revert to the
        # ride's old DB values or silently discard what they typed. The
        # submitting form's own `hx-target` is "#rides-panel" (needed for
        # the success path, which swaps the whole list); `HX-Retarget`
        # overrides that for this response only, so htmx swaps this ride's
        # row instead.
        context = {
            "unit": unit_of(request, bike),
            "error": error,
            "values": _submitted_form_values(form),
            "action": f"/bikes/{bike_id}/rides/{ride.id}",
            "submit_label": "Save",
            "cancel_url": f"/bikes/{bike_id}/rides",
            "wrapper_id": f"ride-{ride.id}",
        }
        response = request.app.state.templates.TemplateResponse(
            request, "_ride_form.html", context, status_code=400
        )
        response.headers["HX-Retarget"] = f"#ride-{ride.id}"
        return response

    ride.date = fields.date
    ride.hours = fields.length
    ride.notes = fields.notes
    for field, value in _suspension_fields_from_form(form).items():
        setattr(ride, field, value)

    # Update the SAME linked HoursEvent row in place -- never create a
    # second one -- so the bike's current-hours total stays in sync with
    # this ride's new date/hours rather than drifting.
    event = session.query(HoursEvent).filter_by(bike_id=bike.id, kind="ride", ride_id=ride.id).one()
    event.date = fields.date
    event.hours = fields.length

    session.commit()

    return _render_list(request, bike, bike_model)


@rides_router.post("/bikes/{bike_id}/rides/{ride_id}/delete")
def delete_ride(bike_id: BikeId, ride_id: RideId, request: Request, session: Session = Depends(get_session)):
    bike = get_bike_or_404(session, bike_id)
    bike_model = request.app.state.bike_models[bike.model_key]
    ride = get_ride_or_404(session, bike_id, ride_id)

    event = session.query(HoursEvent).filter_by(bike_id=bike.id, kind="ride", ride_id=ride.id).one_or_none()
    if event is not None:
        session.delete(event)
    session.delete(ride)
    session.commit()

    return _render_list(request, bike, bike_model)
