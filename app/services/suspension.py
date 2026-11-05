"""Suspension setup history, derived from the clicker and sag values logged
with rides.

Rides are ordered by (date, id). A ride that recorded none of the values is
left out. A blank value means "not recorded on this ride", never a change: each
recorded value is compared with the most recent earlier recorded value for the
same setting.
"""

from collections.abc import Iterable
from typing import NamedTuple

from app.models import Ride
from app.services.carb import NOT_RECORDED, Change

# (Ride attribute, history label, unit suffix), in the ride form's order.
SUSPENSION_HISTORY_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("fork_compression", "Fork compression", ""),
    ("fork_rebound", "Fork rebound", ""),
    ("shock_lsc", "Shock low-speed compression", ""),
    ("shock_hsc", "Shock high-speed compression", ""),
    ("shock_rebound", "Shock rebound", ""),
    ("sag_static", "Static sag", " mm"),
    ("sag_rider", "Rider sag", " mm"),
)


class SuspensionEntry(NamedTuple):
    ride: Ride
    is_start: bool
    changes: list[Change]


def _display(value, suffix: str) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value}{suffix}"


def history(rides: Iterable[Ride]) -> list[SuspensionEntry]:
    """Rides that set or changed a suspension value, newest first."""
    last: dict[str, object] = {}
    entries = []
    for ride in sorted(rides, key=lambda r: (r.date, r.id)):
        is_start = not last
        changes = []
        for attr, label, suffix in SUSPENSION_HISTORY_FIELDS:
            value = getattr(ride, attr)
            if value is None or last.get(attr) == value:
                continue
            old = last.get(attr)
            changes.append(Change(label, NOT_RECORDED if old is None else _display(old, suffix), _display(value, suffix)))
            last[attr] = value
        if changes:
            entries.append(SuspensionEntry(ride, is_start, changes))
    return entries[::-1]


def current(rides: Iterable[Ride]) -> dict[str, str | None]:
    """Each setting's label and its most recently recorded value (None if no
    ride has recorded it), in the ride form's order."""
    ordered = sorted(rides, key=lambda r: (r.date, r.id))
    setup = {}
    for attr, label, suffix in SUSPENSION_HISTORY_FIELDS:
        recorded = [getattr(r, attr) for r in ordered if getattr(r, attr) is not None]
        setup[label] = _display(recorded[-1], suffix) if recorded else None
    return setup
