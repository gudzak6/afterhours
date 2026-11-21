"""Classification, metrics, and FIT field handling."""

from datetime import UTC, datetime

from app.fit.parse import INVALID_SEMICIRCLE, extract_lap, extract_record, semicircles_to_degrees
from app.metrics.engine import (
    coefficient_of_variation,
    heart_rate_drift,
    pace_slope_seconds_per_rep,
)
import pytest
from pydantic import ValidationError

from app.coach.engine import validate_report
from app.workouts.classify import classify_laps, compare_reference


class _Field:
    def __init__(self, value) -> None:
        self.value = value


class _Frame:
    def __init__(self, values: dict) -> None:
        self.values = values

    def has_field(self, name: str) -> bool:
        return name in self.values

    def get_field(self, name: str):
        if name not in self.values:
            return None
        return _Field(self.values[name])


def _lap(number: int, distance: float, duration: float, speed: float) -> dict:
    return {
        "lap_number": number,
        "distance_meters": distance,
        "duration_seconds": duration,
        "average_speed_mps": speed,
        "average_heart_rate_bpm": 140,
    }


def test_semicircle_conversion_keeps_zero_and_drops_invalid() -> None:
    assert semicircles_to_degrees(0) == 0
    assert semicircles_to_degrees(INVALID_SEMICIRCLE) is None
    degrees = semicircles_to_degrees(int(40 * 2**31 / 180))
    assert degrees is not None
    assert abs(degrees - 40) < 0.001


def test_lap_keeps_zero_and_marks_missing_heart_rate() -> None:
    lap = extract_lap(
        _Frame(
            {
                "total_distance": 0,
                "total_timer_time": 12.5,
                "enhanced_avg_speed": 0,
                "start_time": datetime(2026, 11, 9, 21, 31, tzinfo=UTC),
                "total_elapsed_time": 12.5,
            }
        ),
        1,
    )
    assert lap["distance_meters"] == 0
    assert lap["average_speed_mps"] == 0
    assert "average_heart_rate_bpm" not in lap["present_fields"]
    assert lap["average_heart_rate_bpm"] is None


def test_record_converts_coordinates() -> None:
    record = extract_record(
        _Frame(
            {
                "timestamp": datetime(2026, 11, 9, 21, 31, 1, tzinfo=UTC),
                "position_lat": int(41 * 2**31 / 180),
                "position_long": INVALID_SEMICIRCLE,
                "enhanced_speed": 3.2,
                "distance": 10,
            }
        ),
        datetime(2026, 11, 9, 21, 31, tzinfo=UTC),
    )
    assert record["latitude"] is not None
    assert abs(record["latitude"] - 41) < 0.001
    assert record["longitude"] is None
    assert "longitude" not in record["present_fields"]
    assert record["elapsed_seconds"] == 1


def test_stride_pattern_uses_pace_not_fit_intensity() -> None:
    laps = [
        _lap(1, 1609, 500, 3.22),
        _lap(2, 1609, 480, 3.35),
    ]
    for number in range(3, 11):
        if number % 2 == 1:
            laps.append(_lap(number, 100, 18, 5.7))
        else:
            laps.append(_lap(number, 50, 40, 1.2))
    laps.append(_lap(11, 1609, 510, 3.15))
    result = classify_laps(laps, sport="running")
    assert result["workout_type"] == "strides"
    assert result["evidence"]["stride_laps"] == [3, 5, 7, 9]
    comparison = compare_reference(laps, result, {"distance_meters": 5000, "elapsed_seconds": 1000})
    stride_check = next(item for item in comparison["checks"] if item["name"] == "stride_laps")
    assert stride_check["matches"] is False
    assert result["evidence"]["stride_laps"] == [3, 5, 7, 9]


def test_metrics_variation_slope_and_insufficient_drift() -> None:
    assert coefficient_of_variation([100, 100, 100]) == 0
    slope = pace_slope_seconds_per_rep([300, 305, 310, 320])
    assert slope is not None
    assert slope > 0
    drift = heart_rate_drift(
        [
            {"lap_number": 1, "duration_seconds": 30, "average_speed_mps": 5.5, "average_heart_rate_bpm": 120},
            {"lap_number": 2, "duration_seconds": 40, "average_speed_mps": 1.2, "average_heart_rate_bpm": 130},
        ],
        {1, 2},
    )
    assert drift is not None
    assert drift["available"] is False


def _report() -> dict:
    return {
        "activity_classification": "Strides",
        "effort_level": "Moderate",
        "summary": "The athlete ran 7.34 miles with eight short strides after the aerobic portion. Average pace on the strides was 4:39 per mile.",
        "training_impact": "The short reps support speed development. They do not establish a lactate threshold.",
        "fitness_indicators": "No race goal or saved lactate threshold is available, so this session cannot be read as a fitness change.",
        "what_went_well": [
            "The eight stride splits stayed near 4:39 per mile.",
            "Pace did not slow across the repetitions.",
        ],
        "where_to_focus": [
            "Heart rate on reps under 30 seconds is not an effort signal.",
            "The next stride session can be compared once another one is stored.",
        ],
        "goal_progress_status": "insufficient_evidence",
        "goal_progress": "No race goal is saved, so progress toward a goal cannot be judged from this run.",
        "missing_information": ["LT2 pace is not saved."],
    }


def test_report_schema_accepts_a_complete_briefing() -> None:
    report = validate_report(_report())
    assert report["activity_classification"] == "Strides"
    assert report["goal_progress_status"] == "insufficient_evidence"


def test_report_schema_accepts_one_focus_point_for_an_easy_run() -> None:
    payload = _report()
    payload["where_to_focus"] = ["Nothing to review on this easy run."]
    payload["what_went_well"] = ["Pace stayed near 8:00 per mile."]
    report = validate_report(payload)
    assert report["where_to_focus"] == ["Nothing to review on this easy run."]


def test_report_schema_rejects_an_empty_focus_list() -> None:
    payload = _report()
    payload["where_to_focus"] = []
    with pytest.raises(ValidationError):
        validate_report(payload)


def test_easy_run_summary_keeps_the_written_analysis() -> None:
    from app.coach.engine import present_report

    summary = "You completed 8.12 miles at an average pace of 8:00 per mile, longer than the planned 5.0 miles."
    shown = present_report(
        {
            "summary": summary,
            "activity_classification": "Easy Run",
            "effort_level": "Easy",
        },
        workout_type="easy",
        distance_meters=8.12 * 1609.344,
        average_speed_mps=1609.344 / 480,
    )
    assert shown is not None
    assert shown["analysis_kind"] == "easy"
    assert shown["summary"] == summary


def test_workout_summary_keeps_the_split_review() -> None:
    from app.coach.engine import present_report

    summary = "Completed 6 of 8 repetitions, averaging 5 seconds per mile slower than prescribed. Mile 4 climbed 18 m."
    shown = present_report(
        {"summary": summary, "activity_classification": "Interval Training"},
        workout_type="intervals",
        distance_meters=10000,
        average_speed_mps=3.5,
    )
    assert shown is not None
    assert shown["analysis_kind"] == "workout"
    assert shown["summary"] == summary
