from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.garmin.mapping import METERS_PER_MILE
from app.services.facts import build_facts_packet

SELECTED = date(2026, 11, 21)
STORED = datetime(2026, 11, 21, 18, 0, tzinfo=UTC)
SYNCED = datetime(2026, 11, 21, 21, 0, tzinfo=UTC)


def _activity(**kwargs):
    defaults = dict(
        id=1,
        garmin_activity_id=100,
        name="Run",
        start_time_local="2026-11-21 07:00:00",
        distance_meters=5 * METERS_PER_MILE,
        duration_seconds=None,
        average_speed_mps=METERS_PER_MILE / 480,
        average_heart_rate_bpm=140,
        updated_at=STORED,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _plan(**kwargs):
    defaults = dict(
        id=1,
        title="Easy",
        scheduled_date=SELECTED,
        workout_type="easy",
        distance_meters=5 * METERS_PER_MILE,
        repetitions=None,
        rep_distance_meters=None,
        recovery_seconds=None,
        target_pace_seconds_per_mile=None,
        intensity=None,
        match_source=None,
        match_activity_id=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _packet():
    friday = _activity()
    intervals = _activity(
        id=2,
        garmin_activity_id=200,
        name="Intervals",
        start_time_local="2026-11-18 07:00:00",
        distance_meters=6 * METERS_PER_MILE,
        average_speed_mps=METERS_PER_MILE / 450,
        average_heart_rate_bpm=None,
    )
    earlier = _activity(
        id=3,
        garmin_activity_id=300,
        name="Steady",
        start_time_local="2026-11-10 07:00:00",
        distance_meters=8 * METERS_PER_MILE,
        average_speed_mps=METERS_PER_MILE / 500,
        average_heart_rate_bpm=None,
    )
    long_run = _activity(
        id=4,
        garmin_activity_id=400,
        name="Long",
        start_time_local="2026-11-01 07:00:00",
        distance_meters=10 * METERS_PER_MILE,
        average_speed_mps=None,
        average_heart_rate_bpm=None,
        duration_seconds=None,
        distance_meters_override=None,
    )
    long_run.distance_meters = None
    undated = _activity(id=5, garmin_activity_id=500, start_time_local=None, distance_meters=20 * METERS_PER_MILE)
    no_distance = _activity(
        id=6,
        garmin_activity_id=600,
        name="Untitled",
        start_time_local="2026-11-16 07:00:00",
        distance_meters=None,
        average_speed_mps=None,
        average_heart_rate_bpm=None,
    )
    laps = [
        SimpleNamespace(lap_number=1, average_speed_mps=METERS_PER_MILE / 400, distance_meters=800, duration_seconds=200),
        SimpleNamespace(lap_number=2, average_speed_mps=METERS_PER_MILE / 600, distance_meters=400, duration_seconds=150),
        SimpleNamespace(lap_number=3, average_speed_mps=METERS_PER_MILE / 410, distance_meters=800, duration_seconds=205),
    ]
    plans = [
        _plan(),
        _plan(id=2, title="4 x 800", scheduled_date=date(2026, 11, 18), workout_type="intervals", repetitions=4, target_pace_seconds_per_mile=400),
        _plan(id=3, title="Easy 4", scheduled_date=date(2026, 11, 19), distance_meters=4 * METERS_PER_MILE),
        _plan(id=4, title="Next long run", scheduled_date=date(2026, 11, 28), workout_type="long_run", distance_meters=12 * METERS_PER_MILE),
        _plan(id=5, title="Too far ahead", scheduled_date=date(2026, 12, 20)),
    ]
    return build_facts_packet(
        athlete_id=4,
        athlete_name="Joey",
        selected_date=SELECTED,
        activities=[friday, intervals, earlier, long_run, undated, no_distance],
        plans=plans,
        laps_by_activity={2: laps},
        lap_evidence={2: {"work_laps": [1, 3], "recovery_laps": [2]}},
        activity_types={1: "easy", 2: "intervals"},
        last_sync_at=SYNCED,
        garmin_status="connected",
        calculated_at=datetime(2026, 11, 21, 22, 0, tzinfo=UTC),
    )


def test_window_mileage_uses_only_dated_runs_with_distance():
    packet = _packet()
    week = packet["windows"]["7"]
    assert week["start"] == "2026-11-15"
    assert week["end"] == "2026-11-21"
    assert week["activity_count"] == 3
    assert week["activities_with_distance"] == 2
    assert week["distance_miles"] == 11.0
    assert packet["windows"]["28"]["distance_miles"] == 19.0
    assert packet["data_availability"]["undated_activities"] == 1
    assert packet["data_availability"]["stored_activities"] == 6


def test_pace_and_heart_rate_trends_stay_empty_without_samples():
    packet = _packet()
    pace = packet["windows"]["7"]["pace"]
    heart = packet["windows"]["7"]["heart_rate"]
    assert pace["samples"] == 2
    assert pace["previous_samples"] == 1
    assert pace["previous_average"] == 500.0
    assert pace["change_from_previous"] is not None
    assert heart["average"] == 140.0
    assert heart["samples"] == 1
    assert heart["previous_average"] is None
    assert heart["change_from_previous"] is None


def test_adherence_distinguishes_a_matched_run_from_a_missed_day():
    packet = _packet()
    adherence = packet["windows"]["7"]["adherence"]
    assert adherence["planned_workouts"] == 3
    assert adherence["completed"] == 1
    assert adherence["partially_completed"] == 1
    assert adherence["confirmed_missed"] == 1
    assert adherence["completed_ratio"] == 0.333
    day = packet["selected_day"]
    assert day["activities"][0]["fields_present"] == ["distance", "pace", "heart_rate"]
    assert day["planned_workouts"][0]["status"] == "completed"
    assert day["planned_workouts"][0]["garmin_activity_id"] == 100


def test_interval_reps_require_labeled_work_laps():
    packet = _packet()
    interval = packet["windows"]["7"]["interval_execution"][0]
    assert interval["planned_repetitions"] == 4
    assert interval["actual_repetitions"] == 2
    assert interval["actual_repetitions_missing"] is None
    assert interval["laps_stored"] is True
    assert interval["actual_pace_seconds_per_mile"] == 405.0


def test_missing_laps_are_not_counted_as_zero_reps():
    packet = build_facts_packet(
        athlete_id=4,
        athlete_name="Joey",
        selected_date=SELECTED,
        activities=[_activity(id=2, garmin_activity_id=200, start_time_local="2026-11-18 07:00:00", average_heart_rate_bpm=None)],
        plans=[_plan(id=2, title="4 x 800", scheduled_date=date(2026, 11, 18), workout_type="intervals", repetitions=4)],
        activity_types={2: "intervals"},
        last_sync_at=SYNCED,
    )
    interval = packet["windows"]["7"]["interval_execution"][0]
    assert interval["actual_repetitions"] is None
    assert interval["actual_repetitions_missing"] == "work_laps_not_identified"


def test_load_upcoming_and_source_timestamps():
    packet = _packet()
    assert packet["training_load"]["acute_miles"] == 11.0
    assert packet["training_load"]["chronic_blocks_with_distance"] == 1
    assert packet["training_load"]["chronic_miles"] == 8.0
    assert packet["training_load"]["acute_chronic_ratio"] == 1.38
    assert [item["title"] for item in packet["upcoming"]] == ["Next long run"]
    availability = packet["data_availability"]
    assert availability["last_activity_local"] == "2026-11-21 07:00:00"
    assert availability["last_activity_stored_at"] == STORED.isoformat()
    assert availability["last_sync_at"] == SYNCED.isoformat()
    assert availability["garmin_status"] == "connected"
    assert packet["calculated_at"] == "2026-11-21T22:00:00+00:00"
