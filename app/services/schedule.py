"""Maintenance schedule modeling and projection.

A maintenance item's schedule is transcribed from a motorcycle manual as
either:

- `EveryHoursSchedule`: a simple "every N hours, do X" rule.
- `ActionsSchedule`: a sparse mapping of printed hour -> action, as
  transcribed directly from the manual's table.

For `ActionsSchedule`, the manual only prints a finite list of hours. To
answer "what's due next" or "what happens at hour H" past the last printed
point, we need to decide whether the printed data is regular enough to
safely extrapolate (project) past it. `detect_projection` performs that
regularity check; `next_point` and `action_at` use it to answer schedule
queries, including projected ones.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionsSchedule:
    actions: dict[int, str]


@dataclass(frozen=True)
class EveryHoursSchedule:
    """Do `action` every `every_hours`, plus once at each hour in `once_at`
    (a break-in check, e.g. "after 1 hour, then every 20")."""

    every_hours: int
    action: str
    once_at: tuple[int, ...] = ()


ItemSchedule = ActionsSchedule | EveryHoursSchedule


@dataclass(frozen=True)
class Projection:
    gap: int
    block: list[str]
    last_hour: int


def detect_projection(hours: list[int], actions: list[str]) -> Projection | None:
    """Detect whether the trailing, regularly-spaced portion of a printed
    schedule can be safely projected past its last point.

    Leading points (e.g. an odd break-in interval) are ignored: only the
    longest trailing run of equal consecutive gaps is considered. Within
    that steady run, the action sequence must be exactly a whole number
    (>= 2) of repeats of some block of actions, otherwise there isn't
    enough confirmed repetition to trust a projection.
    """
    if len(hours) < 3:
        return None

    gaps = [hours[i] - hours[i - 1] for i in range(1, len(hours))]

    # Scan backward from the last gap while it equals its predecessor to
    # find the longest trailing run of equal gaps.
    i0_gap = len(gaps) - 1
    while i0_gap > 0 and gaps[i0_gap] == gaps[i0_gap - 1]:
        i0_gap -= 1

    # gaps[i] = hours[i + 1] - hours[i], so the steady sub-sequence of
    # hours/actions starts at the same index as the steady run of gaps.
    i0 = i0_gap
    steady_hours = hours[i0:]
    steady_actions = actions[i0:]
    length = len(steady_hours)
    if length < 3:
        return None

    gap = steady_hours[1] - steady_hours[0]

    for block_len in range(1, length + 1):
        if length % block_len != 0:
            continue
        repeats = length // block_len
        if repeats < 2:
            continue
        block = steady_actions[:block_len]
        if steady_actions == block * repeats:
            return Projection(gap=gap, block=block, last_hour=hours[-1])

    return None


def first_unrecorded_repeat(every_hours: int, recorded_hours: set[int]) -> int:
    """The first multiple of `every_hours` that isn't in `recorded_hours`."""
    k = 1
    while k * every_hours in recorded_hours:
        k += 1
    return k * every_hours


def next_point(schedule: ItemSchedule, recorded_hours: set[int]) -> int | None:
    """Return the next hour at which this item is due, skipping hours
    already recorded as serviced. Returns None if nothing further is due
    and the schedule can't be trusted to project further."""
    if isinstance(schedule, EveryHoursSchedule):
        pending_once = [h for h in schedule.once_at if h not in recorded_hours]
        repeat = first_unrecorded_repeat(schedule.every_hours, recorded_hours)
        return min([repeat, *pending_once])

    sorted_hours = sorted(schedule.actions.keys())
    for hour in sorted_hours:
        if hour not in recorded_hours:
            return hour

    # All printed hours are recorded; try to project past the last one.
    sorted_actions = [schedule.actions[hour] for hour in sorted_hours]
    projection = detect_projection(sorted_hours, sorted_actions)
    if projection is None:
        return None

    k = 1
    while True:
        candidate = projection.last_hour + k * projection.gap
        if candidate not in recorded_hours:
            return candidate
        k += 1


def action_at(schedule: ItemSchedule, hour: int) -> str | None:
    """Return the action due at the given hour, or None if the schedule
    doesn't define (or can't safely project) an action at that hour."""
    if isinstance(schedule, EveryHoursSchedule):
        if hour in schedule.once_at or (hour > 0 and hour % schedule.every_hours == 0):
            return schedule.action
        return None

    if hour in schedule.actions:
        return schedule.actions[hour]

    max_hour = max(schedule.actions.keys())
    if hour < max_hour:
        return None

    sorted_hours = sorted(schedule.actions.keys())
    sorted_actions = [schedule.actions[h] for h in sorted_hours]
    projection = detect_projection(sorted_hours, sorted_actions)
    if projection is None:
        return None

    if hour <= projection.last_hour or (hour - projection.last_hour) % projection.gap != 0:
        return None

    k = (hour - projection.last_hour) // projection.gap
    return projection.block[(k - 1) % len(projection.block)]
