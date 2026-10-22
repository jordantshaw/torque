from app.services.schedule import (
    ActionsSchedule, EveryHoursSchedule, Projection,
    detect_projection, next_point, action_at,
)

def test_detect_projection_requires_at_least_three_points():
    assert detect_projection([90, 180], ["S", "S"]) is None

def test_detect_projection_rejects_irregular_gaps():
    assert detect_projection([60, 150, 400], ["C", "C", "C"]) is None

def test_detect_projection_confirms_constant_action():
    hours = [30, 60, 90, 120, 150, 180]
    assert detect_projection(hours, ["S"] * 6) == Projection(gap=30, block=["S"], last_hour=180)

def test_detect_projection_confirms_alternating_block_after_two_repeats():
    hours = [30, 60, 90, 120, 150, 180]
    actions = ["C", "C", "S", "C", "C", "S"]
    assert detect_projection(hours, actions) == Projection(gap=30, block=["C", "C", "S"], last_hour=180)

def test_detect_projection_ignores_odd_leading_gap():
    hours = [3, 30, 60, 90, 120, 150, 180]
    assert detect_projection(hours, ["S"] * 7) == Projection(gap=30, block=["S"], last_hour=180)

def test_detect_projection_rejects_single_cycle_alternating_block():
    # only one C,C,S cycle printed -> not confirmed
    assert detect_projection([30, 60, 90], ["C", "C", "S"]) is None

def test_next_point_every_hours_skips_recorded():
    assert next_point(EveryHoursSchedule(7, "S"), {7, 14}) == 21

def test_next_point_actions_walks_unrecorded_printed_hour():
    assert next_point(ActionsSchedule({3: "T"}), set()) == 3

def test_next_point_actions_none_when_unconfirmed_and_exhausted():
    assert next_point(ActionsSchedule({90: "S", 180: "S"}), {90, 180}) is None

def test_next_point_actions_projects_past_last_printed_hour():
    schedule = ActionsSchedule({30: "C", 60: "C", 90: "S", 120: "C", 150: "C", 180: "S"})
    assert next_point(schedule, {30, 60, 90, 120, 150, 180}) == 210

def test_next_point_actions_continues_projecting_multiple_cycles():
    schedule = ActionsSchedule({30: "C", 60: "C", 90: "S", 120: "C", 150: "C", 180: "S"})
    recorded = {30, 60, 90, 120, 150, 180, 210, 240}
    assert next_point(schedule, recorded) == 270

def test_action_at_every_hours():
    schedule = EveryHoursSchedule(15, "S")
    assert action_at(schedule, 45) == "S"
    assert action_at(schedule, 50) is None

def test_action_at_actions_printed_hour():
    assert action_at(ActionsSchedule({3: "T"}), 3) == "T"

def test_action_at_actions_projected_hour():
    schedule = ActionsSchedule({30: "C", 60: "C", 90: "S", 120: "C", 150: "C", 180: "S"})
    assert action_at(schedule, 270) == "S"
    assert action_at(schedule, 300) == "C"

def test_action_at_actions_unprojectable_beyond_last_hour():
    assert action_at(ActionsSchedule({90: "S", 180: "S"}), 270) is None



def test_once_at_points_come_before_the_repeats():
    schedule = EveryHoursSchedule(every_hours=20, action="C", once_at=(1, 5))
    assert next_point(schedule, set()) == 1
    assert next_point(schedule, {1}) == 5
    assert next_point(schedule, {1, 5}) == 20
    assert next_point(schedule, {1, 5, 20}) == 40


def test_once_at_action_and_repeats():
    schedule = EveryHoursSchedule(every_hours=40, action="S", once_at=(5,))
    assert action_at(schedule, 5) == "S"
    assert action_at(schedule, 40) == "S"
    assert action_at(schedule, 20) is None
    assert action_at(schedule, 6) is None


def test_first_unrecorded_repeat():
    from app.services.schedule import first_unrecorded_repeat

    assert first_unrecorded_repeat(20, set()) == 20
    assert first_unrecorded_repeat(20, {20, 40}) == 60
    assert first_unrecorded_repeat(20, {40}) == 20  # a gap is still the first
