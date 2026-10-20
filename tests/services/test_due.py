from app.services.due import Status, ItemDueInfo, compute_due_info, items_for_service_point
from app.services.schedule import ActionsSchedule, EveryHoursSchedule

def test_compute_due_info_ok_when_far_from_next_point():
    info = compute_due_info(EveryHoursSchedule(30, "S"), current_hours=10, recorded_hours=set())
    assert info == ItemDueInfo(next_point=30, status=Status.OK, hours_overdue=None)

def test_compute_due_info_upcoming_within_window():
    info = compute_due_info(EveryHoursSchedule(30, "S"), current_hours=26, recorded_hours=set())
    assert info.status == Status.UPCOMING
    assert info.next_point == 30

def test_compute_due_info_due_with_hours_overdue():
    info = compute_due_info(EveryHoursSchedule(30, "S"), current_hours=35, recorded_hours=set())
    assert info == ItemDueInfo(next_point=30, status=Status.DUE, hours_overdue=5)

def test_compute_due_info_due_at_exact_boundary():
    info = compute_due_info(EveryHoursSchedule(30, "S"), current_hours=30, recorded_hours=set())
    assert info == ItemDueInfo(next_point=30, status=Status.DUE, hours_overdue=0)

def test_compute_due_info_beyond_schedule_when_no_next_point():
    schedule = ActionsSchedule({90: "S", 180: "S"})
    info = compute_due_info(schedule, current_hours=250, recorded_hours={90, 180})
    assert info == ItemDueInfo(next_point=None, status=Status.BEYOND_SCHEDULE, hours_overdue=None)

def test_items_for_service_point_filters_by_action_and_unrecorded():
    schedules = {
        "oil": EveryHoursSchedule(30, "S"),
        "rod": ActionsSchedule({90: "S", 180: "S"}),
        "disks": ActionsSchedule({30: "C", 60: "C", 90: "S", 120: "C", 150: "C", 180: "S"}),
    }
    recorded = {"oil": set(), "rod": {90}, "disks": {30, 60}}
    # hour 90: oil has no action there (90 % 30 == 0 -> it DOES); rod has action but already recorded; disks has action, unrecorded
    result = items_for_service_point(schedules, hour=90, recorded_by_item=recorded)
    assert set(result) == {"oil", "disks"}
