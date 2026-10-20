from dataclasses import dataclass
from datetime import date
from typing import Literal


@dataclass(frozen=True)
class HoursEventInput:
    """Represents a single engine hours event (direct set or ride)."""

    id: int
    date: date
    kind: Literal["ride", "set"]
    hours: float


def current_hours(events: list[HoursEventInput]) -> float:
    """
    Compute current total engine hours by replaying events.

    Events are processed in order by (date, id). For each event:
    - "set" events replace the running total
    - "ride" events add to the running total

    Args:
        events: List of engine hours events to replay

    Returns:
        Current total engine hours after replaying all events
    """
    # Sort events by date, then by id for deterministic ordering on the same date
    sorted_events = sorted(events, key=lambda e: (e.date, e.id))

    total: float = 0
    for event in sorted_events:
        if event.kind == "set":
            total = event.hours
        elif event.kind == "ride":
            total += event.hours

    return total
