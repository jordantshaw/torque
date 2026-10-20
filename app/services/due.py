"""Maintenance item due status computation.

Tracks whether a maintenance item is overdue, upcoming, or OK based on the
bike's current engine hours and the schedule of when it was last serviced.
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
    hours_overdue: int | None


def compute_due_info(
    schedule: ItemSchedule,
    current_hours: int,
    recorded_hours: set[int],
) -> ItemDueInfo:
    """Compute the due status of a maintenance item given its schedule and the
    bike's current engine hours.

    Args:
        schedule: The maintenance schedule (EveryHoursSchedule or ActionsSchedule)
        current_hours: The bike's current engine hours
        recorded_hours: Set of hours at which this item was last serviced

    Returns:
        ItemDueInfo with next_point, status, and hours_overdue
    """
    point = next_point(schedule, recorded_hours)

    if point is None:
        return ItemDueInfo(next_point=None, status=Status.BEYOND_SCHEDULE, hours_overdue=None)

    if current_hours >= point:
        hours_overdue = current_hours - point
        return ItemDueInfo(next_point=point, status=Status.DUE, hours_overdue=hours_overdue)

    if point - current_hours <= UPCOMING_WINDOW_HOURS:
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
