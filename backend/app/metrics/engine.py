"""Deterministic running metrics. Short reps do not support a heart-rate conclusion."""

from __future__ import annotations

import math

from app.metrics.elevation import elevation_effect
from app.workouts.structure import describe_workout

METERS_PER_MILE = 1609.344
SHORT_REP_SECONDS = 30


def pace_seconds_per_mile(speed_mps: float | None) -> float | None:
    if speed_mps is None or speed_mps <= 0:
        return None
    return METERS_PER_MILE / speed_mps


def coefficient_of_variation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    if mean == 0:
        return None
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance) / abs(mean)


def pace_slope_seconds_per_rep(paces: list[float]) -> float | None:
    """Least-squares change in pace per repetition. Positive means slowing down."""
    if len(paces) < 3:
        return None
    count = len(paces)
    xs = list(range(count))
    mean_x = sum(xs) / count
    mean_y = sum(paces) / count
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return None
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, paces))
    return numerator / denominator


def _zone_name(value: float, zones: list[dict], low_key: str, high_key: str) -> str | None:
    for zone in zones:
        low = zone.get(low_key)
        high = zone.get(high_key)
        if low is None or high is None:
            continue
        if low <= value < high or (value == high and value == zone.get(high_key)):
            return str(zone.get("name") or "zone")
    return None


def time_in_zones(
    samples: list[dict],
    *,
    zones: list[dict] | None,
    value_key: str,
    low_key: str,
    high_key: str,
) -> dict | None:
    if not zones:
        return None
    totals: dict[str, float] = {}
    for index, sample in enumerate(samples):
        value = sample.get(value_key)
        if not isinstance(value, (int, float)):
            continue
        name = _zone_name(float(value), zones, low_key, high_key)
        if name is None:
            continue
        nxt = samples[index + 1]["elapsed_seconds"] if index + 1 < len(samples) else None
        current = sample.get("elapsed_seconds")
        delta = 1.0
        if isinstance(current, (int, float)) and isinstance(nxt, (int, float)):
            delta = max(0.0, min(10.0, float(nxt) - float(current)))
        totals[name] = totals.get(name, 0.0) + delta
    return totals or None


def repetition_metrics(laps: list[dict], lap_numbers: list[int]) -> dict | None:
    selected = [lap for lap in laps if lap.get("lap_number") in lap_numbers]
    if len(selected) < 2:
        return None
    paces = []
    durations = []
    heart_rates = []
    heart_rate_usable = True
    for lap in selected:
        pace = pace_seconds_per_mile(lap.get("average_speed_mps"))
        if pace is not None:
            paces.append(pace)
        if isinstance(lap.get("duration_seconds"), (int, float)):
            durations.append(float(lap["duration_seconds"]))
            if lap["duration_seconds"] < SHORT_REP_SECONDS:
                heart_rate_usable = False
        if isinstance(lap.get("average_heart_rate_bpm"), (int, float)):
            heart_rates.append(float(lap["average_heart_rate_bpm"]))
    return {
        "repetitions": len(selected),
        "durations_seconds": durations,
        "mean_duration_seconds": None if not durations else sum(durations) / len(durations),
        "paces_seconds_per_mile": paces,
        "mean_pace_seconds_per_mile": None if not paces else sum(paces) / len(paces),
        "pace_coefficient_of_variation": coefficient_of_variation(paces),
        "pace_change_seconds_per_repetition": pace_slope_seconds_per_rep(paces),
        "heart_rate_mean_bpm": None if not heart_rates else sum(heart_rates) / len(heart_rates),
        "heart_rate_usable": heart_rate_usable,
        "heart_rate_note": None
        if heart_rate_usable
        else "Repetitions are shorter than 30 seconds, so heart rate has not caught up to the effort.",
    }


def heart_rate_drift(laps: list[dict], excluded_laps: set[int]) -> dict | None:
    steady = []
    for lap in laps:
        if lap.get("lap_number") in excluded_laps:
            continue
        duration = lap.get("duration_seconds")
        speed = lap.get("average_speed_mps")
        heart = lap.get("average_heart_rate_bpm")
        if not all(isinstance(value, (int, float)) for value in (duration, speed, heart)):
            continue
        if duration < 120 or speed <= 0:
            continue
        steady.append(lap)
    total = sum(lap["duration_seconds"] for lap in steady)
    if total < 1200 or len(steady) < 2:
        return {"available": False, "reason": "Not enough steady running with both pace and heart rate."}
    half = total / 2
    elapsed = 0.0
    first: list[dict] = []
    second: list[dict] = []
    for lap in steady:
        if elapsed < half:
            first.append(lap)
        else:
            second.append(lap)
        elapsed += lap["duration_seconds"]
    if not first or not second:
        return {"available": False, "reason": "The steady section could not be split into two comparable halves."}

    def mean(items: list[dict], key: str) -> float:
        return sum(item[key] for item in items) / len(items)

    pace_first = pace_seconds_per_mile(mean(first, "average_speed_mps"))
    pace_second = pace_seconds_per_mile(mean(second, "average_speed_mps"))
    if pace_first is None or pace_second is None or pace_first == 0:
        return {"available": False, "reason": "Pace was missing for one half of the steady section."}
    pace_difference = abs(pace_second - pace_first) / pace_first
    if pace_difference > 0.05:
        return {
            "available": False,
            "reason": "The two halves were more than 5 percent apart in pace, so heart-rate change is not drift.",
            "pace_difference_ratio": pace_difference,
        }
    hr_first = mean(first, "average_heart_rate_bpm")
    hr_second = mean(second, "average_heart_rate_bpm")
    return {
        "available": True,
        "first_half_heart_rate_bpm": hr_first,
        "second_half_heart_rate_bpm": hr_second,
        "heart_rate_change_bpm": hr_second - hr_first,
        "pace_difference_ratio": pace_difference,
        "steady_duration_seconds": total,
    }


def activity_metrics(
    laps: list[dict],
    samples: list[dict],
    *,
    classification: dict | None = None,
    pace_zones: list[dict] | None = None,
    heart_rate_zones: list[dict] | None = None,
    elevation_gain_meters: float | None = None,
    elevation_loss_meters: float | None = None,
) -> dict:
    evidence = {} if not classification else classification.get("evidence") or {}
    stride_laps = list(evidence.get("stride_laps") or evidence.get("work_laps") or [])
    recovery_laps = list(evidence.get("recovery_laps") or [])
    reps = repetition_metrics(laps, stride_laps) if stride_laps else None
    recoveries = repetition_metrics(laps, recovery_laps) if recovery_laps else None
    pace_samples = []
    for sample in samples:
        pace = pace_seconds_per_mile(sample.get("speed_mps"))
        if pace is not None and sample.get("elapsed_seconds") is not None:
            pace_samples.append({**sample, "pace_seconds_per_mile": pace})
    return {
        "repetitions": reps,
        "recoveries": recoveries,
        "heart_rate_drift": heart_rate_drift(laps, set(stride_laps) | set(recovery_laps)),
        "time_in_pace_zones_seconds": time_in_zones(
            pace_samples,
            zones=pace_zones,
            value_key="pace_seconds_per_mile",
            low_key="min_pace_seconds_per_mile",
            high_key="max_pace_seconds_per_mile",
        ),
        "time_in_heart_rate_zones_seconds": time_in_zones(
            [sample for sample in samples if sample.get("heart_rate_bpm") is not None],
            zones=heart_rate_zones,
            value_key="heart_rate_bpm",
            low_key="min_bpm",
            high_key="max_bpm",
        ),
        "zones_configured": bool(pace_zones or heart_rate_zones),
        "workout_breakdown": describe_workout(laps, samples),
        "elevation_effect": elevation_effect(
            samples,
            gain_meters=elevation_gain_meters,
            loss_meters=elevation_loss_meters,
        ),
    }
