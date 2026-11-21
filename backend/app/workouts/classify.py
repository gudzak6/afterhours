"""Label a workout from lap pace and pattern.

Garmin's FIT intensity field is recorded and shown as evidence. It is not the
label. Lactate threshold is used only when the athlete saved an LT2 pace.
"""

from __future__ import annotations

from statistics import median


def _number(lap: dict, key: str) -> float | None:
    value = lap.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _easy_speed(laps: list[dict]) -> float | None:
    speeds = []
    for lap in laps:
        duration = _number(lap, "duration_seconds")
        distance = _number(lap, "distance_meters")
        speed = _number(lap, "average_speed_mps")
        if duration is None or distance is None or speed is None or speed <= 0:
            continue
        if duration >= 120 and distance >= 400:
            speeds.append(speed)
    if len(speeds) < 2:
        return None
    return float(median(speeds))


def _fast_short(lap: dict, easy_speed: float | None) -> bool:
    duration = _number(lap, "duration_seconds")
    distance = _number(lap, "distance_meters")
    speed = _number(lap, "average_speed_mps")
    if duration is None or distance is None or speed is None:
        return False
    if not (8 <= duration <= 45 and 40 <= distance <= 220):
        return False
    floor = 4.5 if easy_speed is None else max(4.0, easy_speed * 1.35)
    return speed >= floor


def _recovery_between(lap: dict, stride_speed: float | None) -> bool:
    duration = _number(lap, "duration_seconds")
    speed = _number(lap, "average_speed_mps")
    if duration is None or speed is None or duration > 120:
        return False
    if stride_speed is not None and speed <= stride_speed * 0.6:
        return True
    return speed < 2.2


def _block(laps: list[dict], indexes: list[int]) -> dict | None:
    if not indexes:
        return None
    return {
        "start_lap": laps[indexes[0]]["lap_number"],
        "end_lap": laps[indexes[-1]]["lap_number"],
        "lap_numbers": [laps[index]["lap_number"] for index in indexes],
    }


def _stride_pattern(laps: list[dict], easy_speed: float | None) -> dict | None:
    fast_indexes = [index for index, lap in enumerate(laps) if _fast_short(lap, easy_speed)]
    if len(fast_indexes) < 3:
        return None
    speeds = [_number(laps[index], "average_speed_mps") for index in fast_indexes]
    known = [speed for speed in speeds if speed is not None]
    stride_speed = float(median(known)) if known else None
    recoveries = []
    alternating = 0
    for position, index in enumerate(fast_indexes[:-1]):
        gap = fast_indexes[position + 1] - index
        if gap == 2 and _recovery_between(laps[index + 1], stride_speed):
            alternating += 1
            recoveries.append(index + 1)
    last_stride = fast_indexes[-1]
    if last_stride + 1 < len(laps) and _recovery_between(laps[last_stride + 1], stride_speed):
        recoveries.append(last_stride + 1)
    if alternating < max(2, len(fast_indexes) // 2):
        return None
    covered = set(fast_indexes) | set(recoveries)
    first = min(covered)
    last = max(covered)
    warmup = list(range(0, first))
    cooldown = list(range(last + 1, len(laps)))
    return {
        "stride_indexes": fast_indexes,
        "recovery_indexes": recoveries,
        "warmup_indexes": warmup,
        "cooldown_indexes": cooldown,
        "easy_speed_mps": easy_speed,
        "stride_speed_mps": stride_speed,
    }


def _interval_pattern(laps: list[dict], easy_speed: float | None) -> dict | None:
    if easy_speed is None:
        return None
    work = []
    for index, lap in enumerate(laps):
        duration = _number(lap, "duration_seconds")
        speed = _number(lap, "average_speed_mps")
        if duration is None or speed is None:
            continue
        if 45 < duration <= 600 and speed >= easy_speed * 1.12:
            work.append(index)
    if len(work) < 3:
        return None
    return {"work_indexes": work}


def _steady_block(laps: list[dict], easy_speed: float | None) -> dict | None:
    if easy_speed is None:
        return None
    current: list[int] = []
    best: list[int] = []
    for index, lap in enumerate(laps):
        duration = _number(lap, "duration_seconds")
        speed = _number(lap, "average_speed_mps")
        if (
            duration is not None
            and speed is not None
            and duration >= 180
            and easy_speed * 1.08 <= speed <= easy_speed * 1.3
        ):
            current.append(index)
        else:
            if len(current) > len(best):
                best = current
            current = []
    if len(current) > len(best):
        best = current
    if not best:
        return None
    duration = sum(_number(laps[index], "duration_seconds") or 0 for index in best)
    if duration < 600:
        return None
    return {"indexes": best, "duration_seconds": duration}


def _progression(laps: list[dict]) -> bool:
    long_laps = [
        lap
        for lap in laps
        if (_number(lap, "distance_meters") or 0) >= 800 and _number(lap, "average_speed_mps") is not None
    ]
    if len(long_laps) < 3:
        return False
    speeds = [_number(lap, "average_speed_mps") or 0 for lap in long_laps]
    increases = sum(1 for earlier, later in zip(speeds, speeds[1:]) if later > earlier + 0.02)
    return increases >= len(speeds) - 1 and speeds[-1] - speeds[0] >= 0.12


def _distance(laps: list[dict], indexes: list[int]) -> float | None:
    values = [_number(laps[index], "distance_meters") for index in indexes]
    known = [value for value in values if value is not None]
    if not known:
        return None
    return float(sum(known))


def classify_laps(laps: list[dict], *, sport: str | None = None, lt2_speed_mps: float | None = None) -> dict:
    if sport and sport not in {"running", "trail_running", "walking", None}:
        return {
            "workout_type": "other",
            "confidence": 0.5,
            "segments": [],
            "evidence": {"sport": sport},
            "uncertainty": "Classification rules in this version cover running laps.",
        }
    if not laps:
        return {
            "workout_type": "unknown",
            "confidence": 0.0,
            "segments": [],
            "evidence": {},
            "uncertainty": "The FIT file did not contain lap messages.",
        }
    easy = _easy_speed(laps)
    intensities = sorted({str(lap.get("intensity")) for lap in laps if lap.get("intensity")})
    evidence: dict = {"fit_intensity_values": intensities, "easy_speed_mps": easy, "rules": []}
    segments = []
    strides = _stride_pattern(laps, easy)
    if strides is not None:
        evidence["rules"].append("short_fast_reps_alternating_with_slower_laps")

        def segment(kind: str, indexes: list[int]) -> dict | None:
            block = _block(laps, indexes)
            if block is None:
                return None
            return {"kind": kind, **block}

        segments = [
            item
            for item in (
                segment("warmup", strides["warmup_indexes"]),
                segment("stride", strides["stride_indexes"]),
                segment("recovery_interval", strides["recovery_indexes"]),
                segment("cooldown", strides["cooldown_indexes"]),
            )
            if item is not None
        ]
        evidence["stride_laps"] = [laps[index]["lap_number"] for index in strides["stride_indexes"]]
        evidence["recovery_laps"] = [laps[index]["lap_number"] for index in strides["recovery_indexes"]]
        evidence["cooldown_distance_meters"] = _distance(laps, strides["cooldown_indexes"])
        evidence["warmup_distance_meters"] = _distance(laps, strides["warmup_indexes"])
        confidence = 0.9 if len(strides["stride_indexes"]) >= 6 else 0.75
        uncertainty = None
        if len(intensities) == 1:
            uncertainty = (
                "Every FIT lap shares the same intensity value, so the label comes from "
                "duration, distance, and pace rather than the device intensity field."
            )
        return {
            "workout_type": "strides",
            "confidence": confidence,
            "segments": segments,
            "evidence": evidence,
            "uncertainty": uncertainty,
        }
    intervals = _interval_pattern(laps, easy)
    if intervals is not None:
        evidence["rules"].append("repeated_efforts_faster_than_the_steady_laps")
        evidence["work_laps"] = [laps[index]["lap_number"] for index in intervals["work_indexes"]]
        return {
            "workout_type": "intervals",
            "confidence": 0.7,
            "segments": [{"kind": "interval", **_block(laps, intervals["work_indexes"])}],
            "evidence": evidence,
            "uncertainty": "LT2 pace is not configured." if lt2_speed_mps is None else None,
        }
    steady = _steady_block(laps, easy)
    if steady is not None:
        speeds = [_number(laps[index], "average_speed_mps") for index in steady["indexes"]]
        known = [speed for speed in speeds if speed]
        block_speed = float(median(known)) if known else None
        kind = "tempo"
        uncertainty = "LT2 pace is not configured, so this is a pace pattern rather than a lactate-threshold label."
        if lt2_speed_mps and block_speed and abs((1609.344 / block_speed) - (1609.344 / lt2_speed_mps)) <= 15:
            kind = "threshold"
            uncertainty = "The sustained block is within 15 seconds per mile of the saved LT2 pace."
        evidence["rules"].append("sustained_block_faster_than_easy_laps")
        return {
            "workout_type": kind,
            "confidence": 0.62 if kind == "tempo" else 0.8,
            "segments": [{"kind": kind, **_block(laps, steady["indexes"])}],
            "evidence": evidence,
            "uncertainty": uncertainty,
        }
    total_distance = sum(_number(lap, "distance_meters") or 0 for lap in laps)
    total_duration = sum(_number(lap, "duration_seconds") or 0 for lap in laps)
    if _progression(laps):
        evidence["rules"].append("longer_laps_become_faster")
        return {
            "workout_type": "progression",
            "confidence": 0.66,
            "segments": [{"kind": "progression", "start_lap": laps[0]["lap_number"], "end_lap": laps[-1]["lap_number"]}],
            "evidence": evidence,
            "uncertainty": None,
        }
    if total_distance >= 20000 or total_duration >= 5400:
        evidence["rules"].append("long_steady_distance")
        return {
            "workout_type": "long_run",
            "confidence": 0.7,
            "segments": [{"kind": "long_run", "start_lap": laps[0]["lap_number"], "end_lap": laps[-1]["lap_number"]}],
            "evidence": evidence,
            "uncertainty": None if easy is not None else "No separate steady-lap reference was available.",
        }
    if total_distance and total_distance <= 6000 and easy is not None and easy < 3.0:
        return {
            "workout_type": "recovery",
            "confidence": 0.55,
            "segments": [{"kind": "recovery", "start_lap": laps[0]["lap_number"], "end_lap": laps[-1]["lap_number"]}],
            "evidence": evidence,
            "uncertainty": "Recovery is based on short distance and slow steady laps, not a saved recovery zone.",
        }
    return {
        "workout_type": "easy",
        "confidence": 0.6 if easy is not None else 0.4,
        "segments": [{"kind": "easy", "start_lap": laps[0]["lap_number"], "end_lap": laps[-1]["lap_number"]}],
        "evidence": evidence,
        "uncertainty": None if easy is not None else "Pace varied too little to call a workout, and no training zones are saved.",
    }


REFERENCE_NOV_9 = {
    "distance_miles": 7.34,
    "duration_seconds": 61 * 60 + 29,
    "lap_count": 24,
    "stride_laps": [7, 9, 11, 13, 15, 17, 19, 21],
    "cooldown_miles": 1.11,
}


def compare_reference(laps: list[dict], classification: dict, session: dict | None = None) -> dict:
    """Compare independent output with the supplied reference. Nothing here changes labels."""
    distance = None if not session else session.get("distance_meters")
    if distance is None:
        values = [_number(lap, "distance_meters") for lap in laps]
        known = [value for value in values if value is not None]
        distance = sum(known) if known else None
    miles = None if distance is None else distance / 1609.344
    timer = None if not session else session.get("timer_seconds")
    elapsed = None if not session else session.get("elapsed_seconds")
    stride_laps = classification.get("evidence", {}).get("stride_laps", [])
    cooldown = classification.get("evidence", {}).get("cooldown_distance_meters")
    cooldown_miles = None if cooldown is None else cooldown / 1609.344
    checks = []

    def add(name: str, actual, reference, close: bool):
        checks.append({"name": name, "actual": actual, "reference": reference, "matches": close})

    add("lap_count", len(laps), REFERENCE_NOV_9["lap_count"], len(laps) == REFERENCE_NOV_9["lap_count"])
    add(
        "distance_miles",
        None if miles is None else round(miles, 2),
        REFERENCE_NOV_9["distance_miles"],
        miles is not None and abs(miles - REFERENCE_NOV_9["distance_miles"]) <= 0.05,
    )
    add(
        "timer_seconds",
        timer,
        REFERENCE_NOV_9["duration_seconds"],
        timer is not None and abs(timer - REFERENCE_NOV_9["duration_seconds"]) <= 20,
    )
    add(
        "elapsed_seconds",
        elapsed,
        REFERENCE_NOV_9["duration_seconds"],
        elapsed is not None and abs(elapsed - REFERENCE_NOV_9["duration_seconds"]) <= 20,
    )
    add("stride_laps", stride_laps, REFERENCE_NOV_9["stride_laps"], stride_laps == REFERENCE_NOV_9["stride_laps"])
    add(
        "cooldown_miles",
        None if cooldown_miles is None else round(cooldown_miles, 2),
        REFERENCE_NOV_9["cooldown_miles"],
        cooldown_miles is not None and abs(cooldown_miles - REFERENCE_NOV_9["cooldown_miles"]) <= 0.05,
    )
    return {"source": "reference_notes_not_used_to_fit_the_calculation", "checks": checks}
