from types import SimpleNamespace

from app.services.due import (
    ItemDueInfo,
    Status,
    compute_due_info,
    due_infos,
    health_pct,
    items_for_service_point,
    recorded_points_by_item,
)
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

def test_compute_due_info_handles_fractional_current_hours():
    info = compute_due_info(EveryHoursSchedule(30, "S"), current_hours=30.5, recorded_hours=set())
    assert info == ItemDueInfo(next_point=30, status=Status.DUE, hours_overdue=0.5)
    info = compute_due_info(EveryHoursSchedule(30, "S"), current_hours=27.5, recorded_hours=set())
    assert info.status == Status.UPCOMING
    assert info.next_point == 30

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



def test_recorded_points_by_item_groups_records():
    records = [
        SimpleNamespace(item_key="oil", service_point=3),
        SimpleNamespace(item_key="oil", service_point=30),
        SimpleNamespace(item_key="plug", service_point=3),
    ]
    assert recorded_points_by_item(records) == {"oil": {3, 30}, "plug": {3}}
    assert recorded_points_by_item([]) == {}


def test_due_infos_evaluates_every_item_with_its_recorded_points():
    schedules = {"oil": ActionsSchedule({3: "S", 30: "S"}), "plug": ActionsSchedule({3: "C"})}
    infos = due_infos(schedules, 10, {"oil": {3}}, upcoming_window=5)
    assert infos["oil"].next_point == 30 and infos["oil"].status.value == "OK"
    assert infos["plug"].next_point == 3 and infos["plug"].status.value == "DUE"


def test_health_pct():
    assert health_pct(10, 0) == 100
    assert health_pct(48, 39) == 19
    assert health_pct(0, 0) == 100  # a model with no items is healthy
