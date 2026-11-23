"""Workout detection from laps and samples. Average pace is not the label."""

from __future__ import annotations

import json
from pathlib import Path

from app.workouts.classify import classify_laps
from app.workouts.detect import DetectionRules, detect_workout
from app.workouts.structure import describe_workout

FIXTURE = Path(__file__).parent / "fixtures" / "east_brunswick_20261122.json"


def _stream(pieces: list[tuple[float, float, float, float]]) -> list[dict]:
    elapsed = 0.0
    distance = 0.0
    altitude = 40.0
    samples = []
    for meters, speed, climb, heart in pieces:
        duration = meters / speed
        steps = max(2, int(duration))
        for step in range(1, steps + 1):
            fraction = step / steps
            samples.append(
                {
                    "elapsed_seconds": elapsed + duration * fraction,
                    "distance_meters": distance + meters * fraction,
                    "speed_mps": speed,
                    "altitude_meters": altitude + climb * fraction,
                    "heart_rate_bpm": heart,
                }
            )
        elapsed += duration
        distance += meters
        altitude += climb
    return samples


def _laps(pieces: list[tuple[float, float, float, float]]) -> list[dict]:
    laps = []
    for index, (meters, speed, _climb, heart) in enumerate(pieces, start=1):
        laps.append(
            {
                "lap_number": index,
                "distance_meters": meters,
                "duration_seconds": meters / speed,
                "elapsed_seconds": meters / speed,
                "average_speed_mps": speed,
                "average_heart_rate_bpm": heart,
                "lap_trigger": "manual",
            }
        )
    return laps


def test_east_brunswick_hill_sprints_are_in_the_fit_not_the_summary() -> None:
    fixture = json.loads(FIXTURE.read_text())
    result = detect_workout(
        fixture["laps"],
        fixture["samples"],
        timer_events=fixture["timer_events"],
        session=fixture["session"],
        plan={"title": "Easy run"},
    )
    classification = result["classification"]
    assert classification["workout_type"] == "hill_sprints"
    assert classification["confidence"] >= 0.7
    assert classification["repetitions"] == 5
    assert classification["source"] == "manual_laps"
    assert classification["ambiguous"] is False
    efforts = result["observed"]["efforts"]
    assert len(efforts) == 5
    assert all(effort["elevation_change_meters"] >= 4 for effort in efforts)
    assert all(effort["duration_seconds"] < 30 for effort in efforts)
    assert all(effort["heart_rate_usable"] is False for effort in efforts)
    assert result["observed"]["pause_count"] == 0
    assert abs(result["observed"]["moving_seconds"] - result["observed"]["elapsed_seconds"]) < 2
    assert result["plan_context"]["title"] == "Easy run"
    assert "not evidence" in result["plan_note"].lower() or "not evidence" in result["plan_note"]
    assert "structured_workout_steps" in result["data_quality"]["missing_fields"]
    breakdown = describe_workout(fixture["laps"], fixture["samples"])
    assert breakdown["kind"] == "sprints"
    assert len(breakdown["repetitions"]) == 5
    assert breakdown["repetitions"][0]["measurement_source"] == "garmin_lap"
    assert breakdown["repetitions"][0]["duration_seconds"] == 14.1
    assert classify_laps(fixture["laps"], sport="running")["workout_type"] == "strides"


def test_sample_stream_finds_the_same_hill_pattern_without_laps() -> None:
    pieces = []
    for _ in range(5):
        pieces.append((60.0, 5.0, 8.0, 150.0))
        pieces.append((70.0, 1.4, -8.0, 130.0))
    result = detect_workout([], _stream(pieces))
    assert result["classification"]["workout_type"] == "hill_sprints"
    assert result["classification"]["repetitions"] == 5
    assert result["classification"]["source"] == "samples"


def test_flat_track_intervals_are_not_called_hills() -> None:
    pieces = [(800.0, 3.0, 0.0, 130.0)]
    for _ in range(4):
        pieces.append((400.0, 5.2, 0.0, 160.0))
        pieces.append((200.0, 2.5, 0.0, 140.0))
    result = detect_workout(_laps(pieces), _stream(pieces))
    assert result["classification"]["workout_type"] == "intervals"
    assert result["classification"]["repetitions"] == 4
    assert all(abs(effort["elevation_change_meters"] or 0) < 1 for effort in result["observed"]["efforts"])


def test_easy_run_is_not_labeled_from_its_average_pace() -> None:
    pieces = [(1609.0, 3.2, 1.0, 140.0) for _ in range(4)]
    result = detect_workout(_laps(pieces), _stream(pieces), plan={"title": "5 hill sprints"})
    assert result["classification"]["workout_type"] == "easy"
    assert result["classification"]["repetitions"] is None
    assert result["observed"]["efforts"] == []
    assert result["plan_context"]["title"] == "5 hill sprints"


def test_threshold_uses_saved_lt2_and_a_slower_section() -> None:
    pieces = [(2000.0, 3.0, 0.0, 140.0), (5000.0, 4.2, 0.0, 168.0), (1000.0, 3.0, 0.0, 145.0)]
    pace = 1609.344 / 4.2
    result = detect_workout(_laps(pieces), _stream(pieces), lt2_pace_seconds_per_mile=pace)
    assert result["classification"]["workout_type"] == "threshold"
    without = detect_workout(_laps(pieces), _stream(pieces))
    assert without["classification"]["workout_type"] == "tempo"


def test_progression_speeds_up_without_repeats() -> None:
    pieces = [(1609.0, speed, 0.0, 140.0) for speed in (3.0, 3.2, 3.4, 3.6)]
    result = detect_workout(_laps(pieces), _stream(pieces))
    assert result["classification"]["workout_type"] == "progression"


def test_pause_is_separated_from_moving_time() -> None:
    pieces: list[tuple[float, float, float, float]] = [(400.0, 5.0, 0.0, 160.0), (200.0, 2.4, 0.0, 130.0)] * 4
    samples = _stream(pieces)
    for sample in samples:
        if sample["elapsed_seconds"] > 80:
            sample["elapsed_seconds"] += 45
    result = detect_workout([], samples)
    assert result["classification"]["workout_type"] == "intervals"
    assert result["observed"]["pause_count"] >= 1
    assert result["observed"]["moving_seconds"] < result["observed"]["elapsed_seconds"]


def test_missing_records_stay_unknown() -> None:
    result = detect_workout([], [], session={"distance_meters": 604.11, "timer_seconds": 281, "elapsed_seconds": 281})
    assert result["classification"]["workout_type"] == "unknown"
    assert result["classification"]["confidence"] == 0
    assert result["classification"]["repetitions"] is None
    assert result["observed"]["efforts"] == []
    assert "laps" in result["data_quality"]["missing_fields"]
    assert "speed" in result["data_quality"]["missing_fields"]
    assert any("cannot be identified" in item for item in result["data_quality"]["limitations"])


def test_repetition_minimum_is_configurable() -> None:
    fixture = json.loads(FIXTURE.read_text())
    result = detect_workout(
        fixture["laps"],
        fixture["samples"],
        rules=DetectionRules(min_repetitions=6),
    )
    assert result["classification"]["workout_type"] == "unknown"
    assert result["classification"]["ambiguous"] is True


def test_coordinates_mark_gps_present() -> None:
    samples = _stream([(60, 4.5, 8, 150), (50, 1.3, 0, 120)] * 5)
    for sample in samples:
        sample["latitude"] = 40.4
        sample["longitude"] = -74.4
    result = detect_workout(_laps([(60, 4.5, 8, 150), (50, 1.3, 0, 120)] * 5), samples)
    assert result["observed"]["signals"]["gps"] is True
