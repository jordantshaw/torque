"""Maintenance item due status computation.

Tracks whether a maintenance item is overdue, upcoming, or OK based on the
bike's current reading and the schedule of when it was last serviced. Readings
and service points are in the bike model's unit (engine hours or km); nothing
here depends on which.
"""

from dataclasses import dataclass
from enum import Enum

from app.services.schedule import ItemSchedule, next_point, action_at


class Status(str, Enum):
    """Status of a maintenance item relative to its schedule."""
    DUE = "DUE"
    UPCOMING = "UPCOMING"
    OK = "OK"
    BEYOND_SCHEDULE = "BEYOND_SCHEDULE"


UPCOMING_WINDOW_HOURS = 5


@dataclass(frozen=True)
class ItemDueInfo:
    """Status and due information for a maintenance item."""
    next_point: int | None
    status: Status
    hours_overdue: float | None


def compute_due_info(
    schedule: ItemSchedule,
    current_hours: float,
    recorded_hours: set[int],
    upcoming_window: float = UPCOMING_WINDOW_HOURS,
) -> ItemDueInfo:
    """Compute the due status of a maintenance item given its schedule and the
    bike's current engine hours.

    Args:
        schedule: The maintenance schedule (EveryHoursSchedule or ActionsSchedule)
        current_hours: The bike's current reading (engine hours or km)
        recorded_hours: Set of hours at which this item was last serviced
        upcoming_window: How close (in the schedule's unit) counts as upcoming

    Returns:
        ItemDueInfo with next_point, status, and hours_overdue
    """
    point = next_point(schedule, recorded_hours)

    if point is None:
        return ItemDueInfo(next_point=None, status=Status.BEYOND_SCHEDULE, hours_overdue=None)

    if current_hours >= point:
        hours_overdue = current_hours - point
        return ItemDueInfo(next_point=point, status=Status.DUE, hours_overdue=hours_overdue)

    if point - current_hours <= upcoming_window:
        return ItemDueInfo(next_point=point, status=Status.UPCOMING, hours_overdue=None)

    return ItemDueInfo(next_point=point, status=Status.OK, hours_overdue=None)


def items_for_service_point(
    item_schedules: dict[str, ItemSchedule],
    hour: int,
    recorded_by_item: dict[str, set[int]],
) -> list[str]:
    """Find all maintenance items that have an action at the given service point
    and have not yet been recorded for that point.

    Args:
        item_schedules: Mapping of item name to schedule
        hour: The service point hour to check
        recorded_by_item: Mapping of item name to set of recorded hours

    Returns:
        List of item names that have an unrecorded action at this hour
    """
    result = []
    for item_key, item_schedule in item_schedules.items():
        if action_at(item_schedule, hour) is not None:
            recorded_set = recorded_by_item.get(item_key, set())
            if hour not in recorded_set:
                result.append(item_key)
    return result


def recorded_points_by_item(records) -> dict[str, set[int]]:
    """Group stored service records (`Bike.service_records`) into the set of
    service points recorded for each item."""
    recorded: dict[str, set[int]] = {}
    for record in records:
        recorded.setdefault(record.item_key, set()).add(record.service_point)
    return recorded


def due_infos(
    schedules: dict[str, ItemSchedule],
    current: float,
    recorded_by_item: dict[str, set[int]],
    upcoming_window: float = UPCOMING_WINDOW_HOURS,
) -> dict[str, ItemDueInfo]:
    """`compute_due_info` for every item, keyed by item key."""
    return {
        key: compute_due_info(schedule, current, recorded_by_item.get(key, set()), upcoming_window)
        for key, schedule in schedules.items()
    }


def health_pct(total: int, flagged: int) -> int:
    """Percent of items that are on track (not due or upcoming). A model with
    no items counts as fully healthy."""
    return round(100 * (total - flagged) / total) if total else 100
