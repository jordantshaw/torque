"""Service intervals: the manual's schedule read as a grid of services.

A manual is a table whose columns are service points (3h, 30h, 60h, ...)
and whose rows are items; each mark says what to do to that item at that
point. `build_intervals` turns the per-item schedules into that grid column
by column, so a service lists *every* item scheduled at that point, whether
or not the item's earlier points have been completed. (Contrast with
`due.compute_due_info`, which answers "what is this one item due for next".)
"""

from dataclasses import dataclass
from enum import Enum

from app.services.schedule import (
    ActionsSchedule,
    ItemSchedule,
    action_at,
    first_unrecorded_repeat,
    next_point,
)

# How many upcoming repeats of a repeating ("every N") item to show ahead.
LOOKAHEAD_REPEATS = 3


class RowState(str, Enum):
    """Where an item (or a whole service) stands against the current reading."""

    DONE = "done"
    DUE = "due"  # the point has been reached and isn't recorded
    UPCOMING = "upcoming"  # within the upcoming window
    LATER = "later"
    BEYOND = "beyond"  # past the end of the manual's schedule (no point)


@dataclass(frozen=True)
class IntervalRow:
    item_key: str
    action: str
    state: RowState


@dataclass(frozen=True)
class Interval:
    point: int
    rows: tuple[IntervalRow, ...]

    @property
    def pending(self) -> int:
        return sum(1 for r in self.rows if r.state != RowState.DONE)

    @property
    def status(self) -> RowState:
        """DONE once every row is recorded; otherwise the state of its
        pending rows, which all share one because it depends only on the point."""
        for row in self.rows:
            if row.state != RowState.DONE:
                return row.state
        return RowState.DONE


def build_intervals(
    schedules: dict[str, ItemSchedule],
    current: float,
    recorded_by_item: dict[str, set[int]],
    upcoming_window: float,
) -> list[Interval]:
    """Every service point that appears in any item's schedule (printed
    points, recorded points, and each item's next projected point), in
    ascending order, with the items scheduled at each."""
    points: set[int] = set()
    for key, schedule in schedules.items():
        recorded = recorded_by_item.get(key, set())
        if isinstance(schedule, ActionsSchedule):
            points.update(schedule.actions)
        else:
            points.update(schedule.once_at)
            first = first_unrecorded_repeat(schedule.every_hours, recorded)
            points.update(first + i * schedule.every_hours for i in range(LOOKAHEAD_REPEATS))
        points.update(recorded)
        upcoming = next_point(schedule, recorded)
        if upcoming is not None:
            points.add(upcoming)

    intervals = []
    for point in sorted(points):
        rows = []
        for key, schedule in schedules.items():
            action = action_at(schedule, point)
            if action is None:
                continue
            if point in recorded_by_item.get(key, set()):
                state = RowState.DONE
            elif point <= current:
                state = RowState.DUE
            elif point - current <= upcoming_window:
                state = RowState.UPCOMING
            else:
                state = RowState.LATER
            rows.append(IntervalRow(key, action, state))
        if rows:
            intervals.append(Interval(point, tuple(rows)))
    return intervals
