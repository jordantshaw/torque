from app.services.intervals import RowState, build_intervals
from app.services.schedule import ActionsSchedule, EveryHoursSchedule

SCHEDULES = {
    # Checked at every service point, like most of a manual's rows.
    "bolts": ActionsSchedule({3: "C", 30: "C", 60: "C"}),
    # Only at 60.
    "piston": ActionsSchedule({60: "S"}),
    "oil": EveryHoursSchedule(every_hours=30, action="S"),
}


def _by_point(intervals):
    return {i.point: {r.item_key: r for r in i.rows} for i in intervals}


def test_every_service_lists_all_items_scheduled_at_that_point():
    grid = _by_point(build_intervals(SCHEDULES, 0, {}, 5))
    assert set(grid[3]) == {"bolts"}
    assert set(grid[30]) == {"bolts", "oil"}
    assert set(grid[60]) == {"bolts", "piston", "oil"}


def test_points_come_back_in_ascending_order():
    points = [i.point for i in build_intervals(SCHEDULES, 0, {}, 5)]
    assert points == sorted(points)


def test_row_states_reflect_current_reading_and_window():
    grid = _by_point(build_intervals(SCHEDULES, 28, {"bolts": {3}}, 5))
    assert grid[3]["bolts"].state == RowState.DONE
    assert grid[30]["bolts"].state == RowState.UPCOMING  # 2 away, window 5
    assert grid[60]["bolts"].state == RowState.LATER
    due = _by_point(build_intervals(SCHEDULES, 31, {}, 5))
    assert due[30]["bolts"].state == RowState.DUE
    assert due[3]["bolts"].state == RowState.DUE


def test_pending_counts_rows_not_done():
    intervals = build_intervals(SCHEDULES, 31, {"bolts": {30}, "oil": {30}}, 5)
    thirty = next(i for i in intervals if i.point == 30)
    assert thirty.pending == 0


def test_every_hours_items_appear_at_their_next_point():
    grid = _by_point(build_intervals({"oil": SCHEDULES["oil"]}, 0, {"oil": {30, 60}}, 5))
    assert 90 in grid  # next point after the recorded 30 and 60
    assert grid[30]["oil"].state == RowState.DONE


def test_action_comes_from_that_point():
    grid = _by_point(build_intervals(SCHEDULES, 0, {}, 5))
    assert grid[60]["piston"].action == "S"


def test_break_in_checks_and_a_short_lookahead_for_repeating_items():
    schedules = {"x": EveryHoursSchedule(every_hours=20, action="C", once_at=(1, 5))}
    points = [i.point for i in build_intervals(schedules, 0, {}, 5)]
    assert points == [1, 5, 20, 40, 60]


def test_interval_status_is_done_only_when_every_row_is_recorded():
    thirty = lambda recorded, current: next(
        i for i in build_intervals(SCHEDULES, current, recorded, 5) if i.point == 30
    )
    assert thirty({}, 0).status == RowState.LATER
    assert thirty({}, 28).status == RowState.UPCOMING
    assert thirty({}, 31).status == RowState.DUE
    assert thirty({"bolts": {30}, "oil": {30}}, 31).status == RowState.DONE
    assert thirty({"bolts": {30}}, 31).status == RowState.DUE  # oil still outstanding
    assert thirty({"bolts": {30}}, 31).pending == 1
