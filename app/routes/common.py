"""Helpers shared by the route modules."""

import math
import re
from datetime import date
from typing import Annotated

from fastapi import HTTPException, Path, Request
from sqlalchemy.orm import Session

from app.models import Bike
from app.services.units import Unit, unit_for


# Limits that keep submitted values sane (and inside what SQLite can store).
MAX_ID = 2**31 - 1
MAX_READING = 1_000_000  # hours or km, in the stored unit
MAX_NICKNAME = 100
MAX_NOTES = 1000
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Path parameters: out-of-range ids are rejected (422) instead of reaching SQLite.
BikeId = Annotated[int, Path(ge=1, le=MAX_ID)]
RideId = Annotated[int, Path(ge=1, le=MAX_ID)]
ServicePoint = Annotated[int, Path(ge=1, le=MAX_READING)]


def get_bike_or_404(session: Session, bike_id: int) -> Bike:
    """Look up a `Bike` by id, raising `HTTPException(404)` if it doesn't exist."""
    bike = session.get(Bike, bike_id)
    if bike is None:
        raise HTTPException(status_code=404)
    return bike


def unit_of(request: Request, bike: Bike) -> Unit:
    """The measurement unit to show for `bike` (see `app.services.units`)."""
    bike_model = request.app.state.bike_models[bike.model_key]
    return unit_for(bike_model.unit, bike.distance_unit)


def parse_date(raw: str) -> tuple[str | None, str | None]:
    """Validate a form `date` (YYYY-MM-DD), returning (date_string, error)."""
    if not raw:
        return None, "Date is required."
    if not _ISO_DATE.fullmatch(raw):
        return None, "Date must be a valid date."
    try:
        return date.fromisoformat(raw).isoformat(), None
    except ValueError:
        return None, "Date must be a valid date."


def parse_reading(
    raw, unit: Unit, label: str, *, allow_zero: bool
) -> tuple[float | None, str | None]:
    """Parse a form value typed in the bike's display unit, returning
    (value in the stored unit, error). Fractions are allowed. `label` names
    the field in the error message; `allow_zero` is False where a zero would
    be meaningless (a ride that covered nothing). NaN, infinity and absurdly
    large values are rejected."""
    try:
        shown = float(raw)
    except (TypeError, ValueError):
        return None, f"{label} must be a number."
    if not math.isfinite(shown):
        return None, f"{label} must be a number."
    if shown < 0 or (shown == 0 and not allow_zero):
        return None, (
            f"{label} must be zero or greater." if allow_zero else f"{label} must be greater than zero."
        )
    stored = unit.to_stored(shown)
    if stored > MAX_READING:
        return None, f"{label} is too large."
    return stored, None


def parse_notes(raw) -> tuple[str | None, str | None]:
    """Optional free text, returned as (text or None, error)."""
    text = str(raw or "").strip()
    if len(text) > MAX_NOTES:
        return None, f"Notes must be {MAX_NOTES} characters or fewer."
    return text or None, None


def parse_nickname(raw) -> tuple[str | None, str | None]:
    """A bike's nickname, returned as (clean text, error)."""
    text = str(raw or "").strip()
    if not text:
        return None, "Nickname is required."
    if len(text) > MAX_NICKNAME:
        return None, f"Nickname must be {MAX_NICKNAME} characters or fewer."
    return text, None


def parse_ids(values) -> set[int]:
    """The valid ids among submitted values; anything else is ignored."""
    return {
        int(raw) for raw in values if re.fullmatch(r"[0-9]{1,10}", str(raw)) and 0 < int(raw) <= MAX_ID
    }
