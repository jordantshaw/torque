"""Carburetor settings: pick the current setup and derive the change history.

Entries are ordered by (date, id), so of two entries on the same date the one
saved later is the current one. Blank values mean "not recorded".
"""

from collections.abc import Iterable, Mapping
from typing import NamedTuple

from app.models import CarbSetting

CARB_FIELDS: tuple[tuple[str, str], ...] = (
    ("main_jet", "Main jet"),
    ("needle", "Needle"),
    ("needle_position", "Needle position"),
    ("pilot_jet", "Pilot jet"),
    ("air_screw", "Air screw"),
)

NOT_RECORDED = "not recorded"

# The longest value accepted for any one carb field.
MAX_CARB_VALUE = 50


class Change(NamedTuple):
    label: str
    old: str
    new: str


class HistoryEntry(NamedTuple):
    setting: CarbSetting
    is_start: bool
    changes: list[Change]


def ordered(settings: Iterable[CarbSetting]) -> list[CarbSetting]:
    return sorted(settings, key=lambda s: (s.date, s.id))


def current(settings: Iterable[CarbSetting]) -> CarbSetting | None:
    entries = ordered(settings)
    return entries[-1] if entries else None


def previous_for(settings: Iterable[CarbSetting], date: str) -> CarbSetting | None:
    earlier = [s for s in ordered(settings) if s.date <= date]
    return earlier[-1] if earlier else None


def changes_between(
    previous: CarbSetting | None, values: Mapping[str, str]
) -> list[Change]:
    changes = []
    for attr, label in CARB_FIELDS:
        old = (getattr(previous, attr) or "") if previous is not None else ""
        new = values.get(attr) or ""
        if old != new:
            changes.append(Change(label, old or NOT_RECORDED, new or NOT_RECORDED))
    return changes


def parse_carb_values(submitted: Mapping[str, object]) -> tuple[dict | None, str | None]:
    """The five carb values from a form, trimmed, as (values, error)."""
    values = {}
    for attr, label in CARB_FIELDS:
        value = str(submitted.get(attr) or "").strip()
        if len(value) > MAX_CARB_VALUE:
            return None, f"{label} must be {MAX_CARB_VALUE} characters or fewer."
        values[attr] = value
    return values, None


def _values(setting: CarbSetting) -> dict[str, str]:
    return {attr: getattr(setting, attr) for attr, _ in CARB_FIELDS}


def history(settings: Iterable[CarbSetting]) -> list[HistoryEntry]:
    entries = []
    previous = None
    for setting in ordered(settings):
        entries.append(
            HistoryEntry(setting, previous is None, changes_between(previous, _values(setting)))
        )
        previous = setting
    return entries[::-1]
