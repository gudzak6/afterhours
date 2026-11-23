"""Repetition structure from lap pace and the record stream."""

from app.workouts.structure import describe_workout


def _lap(distance: float, duration: float, speed: float, heart: float = 140) -> dict:
    return {
        "distance_meters": distance,
        "duration_seconds": duration,
        "average_speed_mps": speed,
        "average_heart_rate_bpm": heart,
    }


def _stream(segments: list[tuple[float, float, float]]) -> list[dict]:
    elapsed = 0.0
    distance = 0.0
    samples = []
    for meters, speed, heart in segments:
        duration = meters / speed
        steps = max(2, int(duration))
        for step in range(1, steps + 1):
            fraction = step / steps
            samples.append(
                {
                    "elapsed_seconds": elapsed + duration * fraction,
                    "distance_meters": distance + meters * fraction,
                    "speed_mps": speed,
                    "heart_rate_bpm": heart,
                }
            )
        elapsed += duration
        distance += meters
    return samples


def test_fast_tail_after_a_mile_lap_stays_one_two_kilometer_rep() -> None:
    segments: list[tuple[float, float, float]] = [
        (1609, 2.84, 117),
        (2039, 4.40, 122),
        (620, 3.04, 111),
    ]
    for _ in range(3):
        segments.extend(
            [
                (800, 5.00, 155),
                (200, 1.80, 140),
                (600, 5.10, 158),
                (200, 1.70, 135),
                (400, 5.20, 145),
                (280, 2.00, 132),
            ]
        )
    segments.extend(
        [
            (1609, 4.60, 165),
            (400, 4.50, 170),
            (1209, 3.50, 145),
        ]
    )
    laps = [_lap(meters, meters / speed, speed, heart) for meters, speed, heart in segments]
    result = describe_workout(laps, _stream(segments))
    assert result["label"] == "2 km, 3 × (800 m, 600 m, 400 m), 2 km"
    assert len(result["repetitions"]) == 11
    assert result["repetitions"][0]["label"] == "2 km"
    assert result["repetitions"][1]["pace"] == "5:22 per mile"
    assert result["repetitions"][-1]["label"] == "2 km"
    assert result["repetitions"][-1]["distance_meters"] > 1900
    assert result["groups"][1]["heading"] == "Set 1 of 3"
    assert [rep["label"] for rep in result["groups"][1]["repetitions"]] == ["800 m", "600 m", "400 m"]


def test_mile_that_slows_down_is_not_called_a_two_kilometer() -> None:
    segments: list[tuple[float, float, float]] = [(1609, 2.9, 120)]
    for _ in range(3):
        segments.extend([(800, 5.0, 155), (200, 1.8, 130)])
    segments.extend([(1609, 4.6, 160), (1609, 3.4, 140)])
    laps = [_lap(meters, meters / speed, speed) for meters, speed, _heart in segments]
    result = describe_workout(laps, _stream(segments))
    assert result["repetitions"][-1]["label"] == "1 mile"


def test_even_laps_describe_repeated_800s_without_samples() -> None:
    laps = []
    for _ in range(6):
        laps.append(_lap(800, 160, 5.0, 160))
        laps.append(_lap(200, 110, 1.82, 130))
    result = describe_workout(laps, [])
    assert result["label"] == "6 × 800 m"
    assert len(result["repetitions"]) == 6
    assert result["repetitions"][0]["pace"] == "5:22 per mile"
    assert result["repetitions"][0]["recovery"] == "1:50"


def test_steady_marathon_lists_each_mile() -> None:
    segments = [(1609.344, 4.2, 160), (1609.344, 4.0, 165), (1609.344, 3.8, 162), (700, 3.7, 160)]
    result = describe_workout(
        [_lap(meters, meters / speed, speed, heart) for meters, speed, heart in segments],
        _stream(segments),
    )
    assert result["kind"] == "miles"
    assert result["label"] == "3 × 1 mile, then 0.43 mi"
    assert [rep["label"] for rep in result["repetitions"]] == ["Mile 1", "Mile 2", "Mile 3", "0.43 mi"]
    assert result["repetitions"][0]["pace"] == "6:23 per mile"
    assert result["repetitions"][1]["pace"] == "6:42 per mile"


def test_watch_mile_pace_ignores_a_stop_in_the_gps_trace() -> None:
    laps = [_lap(1609.344, 405, 3.97, 150) for _ in range(3)]
    samples = _stream([(1609.344, 3.97, 150), (1609.344, 3.97, 150), (20, 3.97, 150)])
    stalled = samples[-1]
    samples.append(
        {
            "elapsed_seconds": stalled["elapsed_seconds"] + 91,
            "distance_meters": stalled["distance_meters"] + 1.6,
            "speed_mps": 1.0,
            "heart_rate_bpm": 140,
        }
    )
    remaining = 1609.344 - 21.6
    samples.extend(
        {
            "elapsed_seconds": stalled["elapsed_seconds"] + 91 + step,
            "distance_meters": stalled["distance_meters"] + 1.6 + remaining * step / 384,
            "speed_mps": 3.97,
            "heart_rate_bpm": 150,
        }
        for step in range(1, 385)
    )
    result = describe_workout(laps, samples)
    assert result["kind"] == "miles"
    assert result["repetitions"][2]["pace"] == "6:45 per mile"
    assert result["repetitions"][2]["measurement_source"] == "garmin_lap"
    assert result["repetitions"][2]["sample_pace_seconds_per_mile"] > result["repetitions"][2]["pace_seconds_per_mile"] + 15


def test_short_hill_efforts_use_the_watch_lap() -> None:
    laps = []
    for _ in range(5):
        laps.append(_lap(60, 12, 5.0, 150))
        laps.append(_lap(70, 50, 1.4, 120))
    result = describe_workout(laps, [])
    assert result["kind"] == "sprints"
    assert result["label"].startswith("5 ×")
    assert len(result["repetitions"]) == 5
    assert result["repetitions"][0]["pace"] == "5:22 per mile"
    assert result["repetitions"][0]["measurement_source"] == "garmin_lap"
    assert result["repetitions"][0]["recovery"] == "0:50"


def test_short_steady_run_has_no_mile_list() -> None:
    laps = [_lap(1200, 400, 3.2), _lap(800, 260, 3.1)]
    result = describe_workout(laps, _stream([(1200, 3.2, 140), (800, 3.1, 142)]))
    assert result["label"] is None
    assert result["repetitions"] == []
