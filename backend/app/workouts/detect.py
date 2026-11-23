"""Identify the workout from recorded laps and samples before a report is written.

Average pace is not a label. A planned workout is context for the coach, not
proof the athlete ran it. Missing signals stay missing.
"""

from __future__ import annotations

from dataclasses import dataclass

METERS_PER_MILE = 1609.344


@dataclass(frozen=True)
class DetectionRules:
    min_effort_seconds: float = 6.0
    max_sprint_seconds: float = 40.0
    min_effort_meters: float = 30.0
    max_sprint_meters: float = 220.0
    min_repetitions: int = 3
    sample_speed_delta_mps: float = 1.2
    min_effort_speed_mps: float = 3.2
    lap_speed_gap_mps: float = 0.8
    recovery_speed_ratio: float = 0.7
    hill_gain_meters: float = 4.0
    hill_share: float = 0.6
    tempo_min_seconds: float = 480.0
    tempo_speed_ratio: float = 1.08
    slower_reference_seconds: float = 180.0
    long_run_meters: float = 20000.0
    pause_gap_seconds: float = 8.0
    pause_max_distance_meters: float = 5.0
    progression_chunks: int = 4
    progression_chunk_meters: float = 800.0
    progression_step_mps: float = 0.05
    progression_total_mps: float = 0.12
    lt2_window_seconds: float = 15.0
    similar_duration_cv: float = 0.45


def detect_workout(
    laps: list[dict] | None = None,
    samples: list[dict] | None = None,
    *,
    steps: list[dict] | None = None,
    timer_events: list[dict] | None = None,
    session: dict | None = None,
    plan: dict | None = None,
    lt2_pace_seconds_per_mile: float | None = None,
    rules: DetectionRules | None = None,
) -> dict:
    """Return observed measurements and a separate classification."""
    rules = rules or DetectionRules()
    laps = list(laps or [])
    samples = list(samples or [])
    steps = list(steps or [])
    timer_events = list(timer_events or [])
    points = _points(samples)
    pauses = _pauses(points, timer_events, rules)
    signals = _signals(laps, points, steps, timer_events, samples)
    missing = _missing(signals)
    limitations: list[str] = []
    if not signals["workout_steps"]:
        limitations.append("The recording has no structured workout steps.")
    if not signals["timer_events"]:
        limitations.append("Timer start and stop events were not stored, so pauses are estimated from gaps in the samples.")
    if not signals["power"]:
        limitations.append("Power was not recorded.")

    windows = _lap_windows(laps)
    repetitions = _repetitions_from_laps(laps, windows, points, rules)
    source = "recorded_laps" if repetitions else None
    if repetitions and any(item.get("lap_trigger") == "manual" for item in repetitions):
        source = "manual_laps"
    if not repetitions:
        repetitions = _repetitions_from_samples(points, rules)
        source = "samples" if repetitions else None
    step_count = _programmed_work_steps(steps)
    if not repetitions and step_count >= rules.min_repetitions:
        source = "workout_steps"
        limitations.append(
            "Structured workout steps are present, but laps and samples do not confirm the efforts. "
            "The step count is not treated as the workout that was run."
        )

    if source is None and (points or laps):
        source = "samples" if points else "recorded_laps"
    kind, confidence, evidence, ambiguous = _classify(
        repetitions,
        source,
        points,
        rules,
        lt2_pace_seconds_per_mile,
        step_count,
        has_laps=bool(laps),
    )
    if repetitions and not signals["altitude"]:
        limitations.append("Altitude was not recorded, so hill repetitions cannot be separated from flat ones.")
    if repetitions and any(not item["heart_rate_usable"] for item in repetitions):
        limitations.append("Heart rate on efforts shorter than 30 seconds has not caught up to the effort.")
    if _ascent_disagrees(repetitions):
        limitations.append("Lap ascent does not match the altitude samples. Elevation on each effort uses the samples.")
    if kind == "unknown":
        ambiguous = True
        if not points and not laps:
            limitations.append("No laps or time series were stored, so the workout structure cannot be identified.")

    observed_reps = []
    for index, item in enumerate(repetitions, start=1):
        effort = _public_effort(item)
        effort["index"] = index
        observed_reps.append(effort)
    recoveries = [_public_recovery(item) for item in repetitions if item.get("recovery_seconds") is not None]
    return {
        "observed": {
            "signals": signals,
            "moving_seconds": _moving_seconds(points, pauses, session),
            "elapsed_seconds": _elapsed_seconds(points, session),
            "pause_seconds": round(sum(item["duration_seconds"] for item in pauses), 1) if pauses else 0.0,
            "pause_count": len(pauses),
            "efforts": observed_reps,
            "recoveries": recoveries,
            "heart_rate_response": _heart_response(repetitions),
        },
        "classification": {
            "workout_type": kind,
            "confidence": round(confidence, 2),
            "repetitions": None if not observed_reps else len(observed_reps),
            "ambiguous": ambiguous,
            "source": source or "insufficient_data",
            "evidence": evidence,
        },
        "plan_context": plan,
        "plan_note": "The planned workout is context. It is not evidence that this structure was run.",
        "data_quality": {"missing_fields": missing, "limitations": limitations},
        "session_load": _load(points, repetitions, pauses, session),
    }


def _classify(
    repetitions: list[dict],
    source: str | None,
    points: list[dict],
    rules: DetectionRules,
    lt2_pace: float | None,
    step_count: int,
    *,
    has_laps: bool,
) -> tuple[str, float, list[str], bool]:
    evidence: list[str] = []
    if step_count:
        evidence.append(f"{step_count} structured work steps are stored with the file.")
    if len(repetitions) >= rules.min_repetitions:
        climbs = [item["elevation_change_meters"] for item in repetitions if item.get("elevation_change_meters") is not None]
        hill_count = sum(1 for gain in climbs if gain >= rules.hill_gain_meters)
        durations = [item["duration_seconds"] for item in repetitions]
        distances = [item["distance_meters"] for item in repetitions]
        short = all(duration <= rules.max_sprint_seconds and distance <= rules.max_sprint_meters for duration, distance in zip(durations, distances))
        evidence.append(
            f"{len(repetitions)} fast efforts separated by slower recovery, from {source.replace('_', ' ')}."
        )
        if short and climbs and hill_count / len(repetitions) >= rules.hill_share:
            evidence.append(
                f"{hill_count} of {len(repetitions)} efforts gained at least {rules.hill_gain_meters:.0f} m of elevation."
            )
            confidence = 0.9 if source == "manual_laps" else 0.8 if source == "recorded_laps" else 0.74
            return "hill_sprints", confidence, evidence, False
        if short:
            if not climbs:
                evidence.append("The efforts are short. Elevation samples were not available, so they are not labeled as hills.")
            else:
                evidence.append("The short efforts did not climb enough to call them hill sprints.")
            confidence = 0.84 if source == "manual_laps" else 0.76 if source == "recorded_laps" else 0.68
            return "strides", confidence, evidence, False
        paces = [item["pace_seconds_per_mile"] for item in repetitions if item.get("pace_seconds_per_mile")]
        mean_pace = None if not paces else sum(paces) / len(paces)
        if lt2_pace and mean_pace is not None and abs(mean_pace - lt2_pace) <= rules.lt2_window_seconds:
            evidence.append("Mean effort pace is within 15 seconds per mile of the saved LT2 pace.")
            return "threshold", 0.8, evidence, False
        evidence.append("The repeated efforts are longer than strides.")
        if lt2_pace is None:
            evidence.append("No LT2 pace is saved, so these repeats are not labeled as threshold.")
        confidence = 0.78 if source in {"manual_laps", "recorded_laps"} else 0.7
        return "intervals", confidence, evidence, False
    if repetitions and len(repetitions) < rules.min_repetitions:
        return (
            "unknown",
            0.4,
            [f"Only {len(repetitions)} fast efforts were found, which is not enough to call a repeated workout."],
            True,
        )

    progression = _progression(points, rules)
    if progression is not None:
        evidence.append(progression)
        return "progression", 0.66, evidence, False
    block = _sustained_block(points, rules)
    if block is not None:
        pace = block["pace_seconds_per_mile"]
        evidence.append(block["evidence"])
        if lt2_pace and pace is not None and abs(pace - lt2_pace) <= rules.lt2_window_seconds:
            evidence.append("The sustained block is within 15 seconds per mile of the saved LT2 pace.")
            return "threshold", 0.8, evidence, False
        if lt2_pace is None:
            evidence.append("No LT2 pace is saved, so the sustained block is tempo rather than threshold.")
        return "tempo", 0.64, evidence, False
    distance = _distance(points, None)
    if distance is not None and distance >= rules.long_run_meters:
        evidence.append("Distance is long and no repeated effort or faster sustained block was found.")
        return "long_run", 0.7, evidence, False
    if len(points) >= 8 or has_laps:
        evidence.append("Speed stayed in one band. No repeated effort or faster sustained block was found.")
        return "easy", 0.7 if len(points) >= 8 else 0.55, evidence, False
    return "unknown", 0.0, ["Not enough laps or samples to identify a workout."], True


def _repetitions_from_laps(laps: list[dict], windows: list[tuple[float, float]], points: list[dict], rules: DetectionRules) -> list[dict]:
    candidates = []
    for index, lap in enumerate(laps):
        speed = _number(lap.get("average_speed_mps"))
        duration = _number(lap.get("duration_seconds"))
        distance = _number(lap.get("distance_meters"))
        if speed is None or duration is None or distance is None:
            continue
        if duration < rules.min_effort_seconds or distance < rules.min_effort_meters:
            continue
        candidates.append((index, speed))
    if len(candidates) < 3:
        return []
    threshold = _speed_gap([speed for _, speed in candidates], min_fast=2, min_gap=rules.lap_speed_gap_mps)
    if threshold is None:
        return []
    fast_indexes = [index for index, speed in candidates if speed >= threshold]
    if len(fast_indexes) < 2:
        return []
    if fast_indexes[-1] - fast_indexes[0] + 1 == len(fast_indexes):
        return []
    efforts = []
    for position, index in enumerate(fast_indexes):
        lap = laps[index]
        start, end = windows[index]
        measured = _window_stats(points, start, end)
        duration = _number(lap.get("duration_seconds")) or 0
        distance = _number(lap.get("distance_meters")) or 0
        speed = _number(lap.get("average_speed_mps")) or 0
        recovery_seconds = None
        recovery_meters = None
        recovery_speed = None
        if position + 1 < len(fast_indexes):
            between = laps[index + 1 : fast_indexes[position + 1]]
            recovery_seconds = sum(_number(item.get("duration_seconds")) or 0 for item in between)
            recovery_meters = sum(_number(item.get("distance_meters")) or 0 for item in between)
            weighted = 0.0
            weight = 0.0
            for item in between:
                item_speed = _number(item.get("average_speed_mps"))
                item_duration = _number(item.get("duration_seconds")) or 0
                if item_speed is not None and item_duration > 0:
                    weighted += item_speed * item_duration
                    weight += item_duration
            recovery_speed = None if weight == 0 else weighted / weight
            if recovery_speed is not None and recovery_speed > speed * rules.recovery_speed_ratio:
                return []
        elevation = measured["elevation_change_meters"]
        if elevation is None:
            ascent = _number(lap.get("ascent_meters"))
            descent = _number(lap.get("descent_meters"))
            if ascent is not None and descent is not None:
                elevation = ascent - descent
        heart = measured["average_heart_rate_bpm"]
        if heart is None:
            heart = _number(lap.get("average_heart_rate_bpm"))
        power = measured["average_power_watts"]
        if power is None:
            power = _number(lap.get("average_power_watts"))
        efforts.append(
            {
                "lap_number": lap.get("lap_number"),
                "lap_trigger": lap.get("lap_trigger"),
                "duration_seconds": duration,
                "distance_meters": distance,
                "average_speed_mps": speed,
                "pace_seconds_per_mile": _pace(distance, duration),
                "average_power_watts": power,
                "average_heart_rate_bpm": heart,
                "heart_rate_usable": duration >= 30 and heart is not None,
                "average_cadence_spm": measured["average_cadence_spm"] if measured["average_cadence_spm"] is not None else _number(lap.get("average_cadence")),
                "elevation_change_meters": elevation,
                "average_grade": None if elevation is None or distance <= 0 else elevation / distance,
                "sample_elevation_meters": measured["elevation_change_meters"],
                "lap_ascent_meters": _number(lap.get("ascent_meters")),
                "recovery_seconds": recovery_seconds,
                "recovery_meters": recovery_meters,
                "recovery_speed_mps": recovery_speed,
            }
        )
    return efforts


def _repetitions_from_samples(points: list[dict], rules: DetectionRules) -> list[dict]:
    if len(points) < 8:
        return []
    speeds = [point["speed_mps"] for point in points]
    baseline = _percentile(speeds, 0.4)
    cutoff = max(rules.min_effort_speed_mps, baseline + rules.sample_speed_delta_mps)
    groups: list[list[dict]] = []
    current: list[dict] = []

    def close() -> None:
        nonlocal current
        if not current:
            return
        duration = current[-1]["elapsed_seconds"] - current[0]["elapsed_seconds"]
        distance = current[-1]["distance_meters"] - current[0]["distance_meters"]
        if duration >= rules.min_effort_seconds and distance >= rules.min_effort_meters:
            groups.append(current)
        current = []

    previous: dict | None = None
    for point in points:
        if previous is not None and point["elapsed_seconds"] - previous["elapsed_seconds"] >= rules.pause_gap_seconds:
            close()
        if point["speed_mps"] >= cutoff:
            current.append(point)
        else:
            close()
        previous = point
    close()
    if len(groups) < 2:
        return []
    efforts = []
    for position, group in enumerate(groups):
        duration = group[-1]["elapsed_seconds"] - group[0]["elapsed_seconds"]
        distance = group[-1]["distance_meters"] - group[0]["distance_meters"]
        if distance <= 0 or duration <= 0:
            continue
        speed = distance / duration
        recovery_seconds = None
        recovery_meters = None
        recovery_speed = None
        if position + 1 < len(groups):
            nxt = groups[position + 1]
            recovery_seconds = nxt[0]["elapsed_seconds"] - group[-1]["elapsed_seconds"]
            recovery_meters = max(0.0, nxt[0]["distance_meters"] - group[-1]["distance_meters"])
            if recovery_seconds > 0:
                recovery_speed = recovery_meters / recovery_seconds
            if recovery_speed is not None and speed > 0 and recovery_speed > speed * rules.recovery_speed_ratio:
                return []
        elevation = _ends(group, "altitude_meters")
        heart_values = [point["heart_rate_bpm"] for point in group if point.get("heart_rate_bpm") is not None]
        power_values = [point["power_watts"] for point in group if point.get("power_watts") is not None]
        cadence_values = [point["cadence_spm"] for point in group if point.get("cadence_spm") is not None]
        efforts.append(
            {
                "lap_number": None,
                "lap_trigger": None,
                "duration_seconds": duration,
                "distance_meters": distance,
                "average_speed_mps": speed,
                "pace_seconds_per_mile": _pace(distance, duration),
                "average_power_watts": None if not power_values else sum(power_values) / len(power_values),
                "average_heart_rate_bpm": None if not heart_values else sum(heart_values) / len(heart_values),
                "heart_rate_usable": duration >= 30 and bool(heart_values),
                "average_cadence_spm": None if not cadence_values else sum(cadence_values) / len(cadence_values),
                "elevation_change_meters": elevation,
                "average_grade": None if elevation is None or distance <= 0 else elevation / distance,
                "sample_elevation_meters": elevation,
                "lap_ascent_meters": None,
                "recovery_seconds": recovery_seconds,
                "recovery_meters": recovery_meters,
                "recovery_speed_mps": recovery_speed,
            }
        )
    return efforts if len(efforts) >= 2 else []


def _progression(points: list[dict], rules: DetectionRules) -> str | None:
    if len(points) < 8:
        return None
    total = points[-1]["distance_meters"] - points[0]["distance_meters"]
    chunk = max(rules.progression_chunk_meters, total / rules.progression_chunks)
    if total < chunk * 3:
        return None
    speeds = []
    origin = points[0]["distance_meters"]
    cursor = origin
    while cursor + chunk <= points[-1]["distance_meters"] + 1:
        window = [point for point in points if cursor <= point["distance_meters"] < cursor + chunk]
        if len(window) < 2:
            break
        distance = window[-1]["distance_meters"] - window[0]["distance_meters"]
        duration = window[-1]["elapsed_seconds"] - window[0]["elapsed_seconds"]
        if distance <= 0 or duration <= 0:
            return None
        speeds.append(distance / duration)
        cursor += chunk
    if len(speeds) < 3:
        return None
    increases = sum(1 for earlier, later in zip(speeds, speeds[1:]) if later > earlier + rules.progression_step_mps)
    if increases >= len(speeds) - 1 and speeds[-1] - speeds[0] >= rules.progression_total_mps:
        return "Pace increased across the run, without a repeated effort and recovery pattern."
    return None


def _sustained_block(points: list[dict], rules: DetectionRules) -> dict | None:
    if len(points) < 8:
        return None
    best: list[dict] = []
    current: list[dict] = []
    anchor: float | None = None
    for point in points:
        speed = point["speed_mps"]
        if anchor is None or abs(speed - anchor) <= 0.25:
            current.append(point)
            anchor = speed if anchor is None else (anchor * 0.8 + speed * 0.2)
        else:
            if len(current) > len(best):
                best = current
            current = [point]
            anchor = speed
    if len(current) > len(best):
        best = current
    if len(best) < 2:
        return None
    block_duration = best[-1]["elapsed_seconds"] - best[0]["elapsed_seconds"]
    distance = best[-1]["distance_meters"] - best[0]["distance_meters"]
    if block_duration < rules.tempo_min_seconds or distance <= 0:
        return None
    block_speed = distance / block_duration
    before = [point for point in points if point["elapsed_seconds"] < best[0]["elapsed_seconds"]]
    after = [point for point in points if point["elapsed_seconds"] > best[-1]["elapsed_seconds"]]
    references = []
    for segment in (before, after):
        speed, segment_duration = _segment_speed(segment)
        if speed is not None and segment_duration >= 60:
            references.append((speed, segment_duration))
    reference_time = sum(segment_duration for _, segment_duration in references)
    if reference_time < rules.slower_reference_seconds:
        return None
    outside_speed = sum(speed * segment_duration for speed, segment_duration in references) / reference_time
    if outside_speed <= 0 or block_speed < outside_speed * rules.tempo_speed_ratio:
        return None
    return {
        "pace_seconds_per_mile": _pace(distance, block_duration),
        "evidence": "One sustained block was faster than the slower running in the same activity.",
    }


def _segment_speed(points: list[dict]) -> tuple[float | None, float]:
    if len(points) < 2:
        return None, 0.0
    duration = points[-1]["elapsed_seconds"] - points[0]["elapsed_seconds"]
    distance = points[-1]["distance_meters"] - points[0]["distance_meters"]
    if duration <= 0 or distance <= 0:
        return None, 0.0
    return distance / duration, duration


def _window_stats(points: list[dict], start: float, end: float) -> dict:
    window = [point for point in points if start - 0.2 <= point["elapsed_seconds"] <= end + 0.2]
    heart = [point["heart_rate_bpm"] for point in window if point.get("heart_rate_bpm") is not None]
    power = [point["power_watts"] for point in window if point.get("power_watts") is not None]
    cadence = [point["cadence_spm"] for point in window if point.get("cadence_spm") is not None]
    return {
        "elevation_change_meters": _ends(window, "altitude_meters"),
        "average_heart_rate_bpm": None if not heart else sum(heart) / len(heart),
        "average_power_watts": None if not power else sum(power) / len(power),
        "average_cadence_spm": None if not cadence else sum(cadence) / len(cadence),
    }


def _ends(points: list[dict], key: str) -> float | None:
    values = [point[key] for point in points if point.get(key) is not None]
    if len(values) < 2:
        return None
    return values[-1] - values[0]


def _ascent_disagrees(repetitions: list[dict]) -> bool:
    for item in repetitions:
        sample = item.get("sample_elevation_meters")
        ascent = item.get("lap_ascent_meters")
        if sample is None or ascent is None:
            continue
        if abs(sample - ascent) >= 3:
            return True
    return False


def _heart_response(repetitions: list[dict]) -> dict | None:
    if not repetitions:
        return None
    effort = [item["average_heart_rate_bpm"] for item in repetitions if item.get("average_heart_rate_bpm") is not None]
    if not effort:
        return {"available": False, "reason": "Heart rate was not recorded on the efforts."}
    usable = all(item["heart_rate_usable"] for item in repetitions)
    return {
        "available": usable,
        "effort_mean_bpm": round(sum(effort) / len(effort), 1),
        "reason": None if usable else "Efforts are shorter than 30 seconds, so heart rate is not an intensity measure.",
    }


def _load(points: list[dict], repetitions: list[dict], pauses: list[dict], session: dict | None) -> dict:
    pause = sum(item["duration_seconds"] for item in pauses)
    distance = _distance(points, session)
    gain = None if not session else _number(session.get("ascent_meters"))
    if gain is None and points:
        deltas = []
        previous = None
        for point in points:
            altitude = point.get("altitude_meters")
            if altitude is None or previous is None:
                previous = altitude if altitude is not None else previous
                continue
            deltas.append(altitude - previous)
            previous = altitude
        if deltas:
            gain = sum(delta for delta in deltas if delta > 0)
    powers = [item["average_power_watts"] for item in repetitions if item.get("average_power_watts") is not None]
    return {
        "distance_meters": None if distance is None else round(distance, 1),
        "moving_seconds": _moving_seconds(points, pauses, session),
        "elapsed_seconds": _elapsed_seconds(points, session),
        "effort_seconds": None if not repetitions else round(sum(item["duration_seconds"] for item in repetitions), 1),
        "pause_seconds": round(pause, 1),
        "elevation_gain_meters": None if gain is None else round(gain, 1),
        "mean_effort_power_watts": None if not powers else round(sum(powers) / len(powers), 1),
        "method": "Recorded distance, moving time, effort time, climb, and effort power. Not a proprietary training-load score.",
    }


def _public_effort(item: dict) -> dict:
    return {
        "index": None,
        "lap_number": item.get("lap_number"),
        "duration_seconds": round(item["duration_seconds"], 1),
        "distance_meters": round(item["distance_meters"], 1),
        "average_speed_mps": round(item["average_speed_mps"], 3),
        "pace_seconds_per_mile": None if item.get("pace_seconds_per_mile") is None else round(item["pace_seconds_per_mile"], 1),
        "average_power_watts": None if item.get("average_power_watts") is None else round(item["average_power_watts"], 1),
        "average_heart_rate_bpm": None if item.get("average_heart_rate_bpm") is None else round(item["average_heart_rate_bpm"], 1),
        "heart_rate_usable": item["heart_rate_usable"],
        "average_cadence_spm": None if item.get("average_cadence_spm") is None else round(item["average_cadence_spm"], 1),
        "elevation_change_meters": None if item.get("elevation_change_meters") is None else round(item["elevation_change_meters"], 1),
        "average_grade": None if item.get("average_grade") is None else round(item["average_grade"], 3),
        "recovery_seconds": None if item.get("recovery_seconds") is None else round(item["recovery_seconds"], 1),
        "recovery_meters": None if item.get("recovery_meters") is None else round(item["recovery_meters"], 1),
    }


def _public_recovery(item: dict) -> dict:
    return {
        "duration_seconds": round(item["recovery_seconds"], 1),
        "distance_meters": None if item.get("recovery_meters") is None else round(item["recovery_meters"], 1),
        "average_speed_mps": None if item.get("recovery_speed_mps") is None else round(item["recovery_speed_mps"], 3),
    }


def _points(samples: list[dict]) -> list[dict]:
    points = []
    for sample in samples:
        elapsed = _number(sample.get("elapsed_seconds"))
        distance = _number(sample.get("distance_meters"))
        speed = _number(sample.get("speed_mps"))
        if elapsed is None or distance is None or speed is None:
            continue
        points.append(
            {
                "elapsed_seconds": elapsed,
                "distance_meters": distance,
                "speed_mps": speed,
                "heart_rate_bpm": _number(sample.get("heart_rate_bpm")),
                "cadence_spm": _number(sample.get("cadence_spm") if sample.get("cadence_spm") is not None else sample.get("cadence")),
                "altitude_meters": _number(sample.get("altitude_meters")),
                "power_watts": _number(sample.get("power_watts")),
            }
        )
    points.sort(key=lambda point: (point["elapsed_seconds"], point["distance_meters"]))
    return points


def _lap_windows(laps: list[dict]) -> list[tuple[float, float]]:
    cursor = 0.0
    windows = []
    for lap in laps:
        duration = _number(lap.get("elapsed_seconds"))
        if duration is None:
            duration = _number(lap.get("duration_seconds")) or 0
        windows.append((cursor, cursor + duration))
        cursor += duration
    return windows


def _pauses(points: list[dict], events: list[dict], rules: DetectionRules) -> list[dict]:
    found = []
    previous = None
    for point in points:
        if previous is not None:
            gap = point["elapsed_seconds"] - previous["elapsed_seconds"]
            moved = point["distance_meters"] - previous["distance_meters"]
            if gap >= rules.pause_gap_seconds and moved <= rules.pause_max_distance_meters:
                found.append({"duration_seconds": gap})
        previous = point
    stopped_at = None
    ordered = sorted(events, key=lambda item: str(item.get("timestamp") or item.get("elapsed_seconds") or ""))
    for event in ordered:
        kind = str(event.get("event_type") or "")
        if kind in {"stop", "stop_all"}:
            stopped_at = event.get("elapsed_seconds")
            continue
        if kind == "start" and isinstance(stopped_at, (int, float)) and isinstance(event.get("elapsed_seconds"), (int, float)):
            gap = float(event["elapsed_seconds"]) - float(stopped_at)
            if gap >= rules.pause_gap_seconds:
                found.append({"duration_seconds": gap})
            stopped_at = None
    return found


def _signals(laps: list[dict], points: list[dict], steps: list[dict], events: list[dict], samples: list[dict]) -> dict:
    def any_point(key: str) -> bool:
        return any(point.get(key) is not None for point in points)

    return {
        "speed": bool(points) or any(_number(lap.get("average_speed_mps")) is not None for lap in laps),
        "cadence": any_point("cadence_spm") or any(_number(lap.get("average_cadence")) is not None for lap in laps),
        "power": any_point("power_watts") or any(_number(lap.get("average_power_watts")) is not None for lap in laps),
        "altitude": any_point("altitude_meters") or any(_number(lap.get("ascent_meters")) is not None for lap in laps),
        "heart_rate": any_point("heart_rate_bpm") or any(_number(lap.get("average_heart_rate_bpm")) is not None for lap in laps),
        "laps": bool(laps),
        "workout_steps": bool(steps),
        "timer_events": bool(events),
        "gps": any(sample.get("latitude") is not None and sample.get("longitude") is not None for sample in samples),
    }


def _missing(signals: dict) -> list[str]:
    names = {
        "speed": "speed",
        "cadence": "cadence",
        "power": "power",
        "altitude": "altitude",
        "heart_rate": "heart_rate",
        "laps": "laps",
        "workout_steps": "structured_workout_steps",
        "timer_events": "timer_events",
    }
    return [label for key, label in names.items() if not signals.get(key)]


def _programmed_work_steps(steps: list[dict]) -> int:
    count = 0
    for step in steps:
        intensity = str(step.get("intensity") or "").lower()
        if intensity in {"active", "interval"}:
            count += 1
    return count


def _moving_seconds(points: list[dict], pauses: list[dict], session: dict | None) -> float | None:
    if session and _number(session.get("timer_seconds")) is not None:
        return round(float(session["timer_seconds"]), 1)
    elapsed = _elapsed_seconds(points, session)
    if elapsed is None:
        return None
    return round(max(0.0, elapsed - sum(item["duration_seconds"] for item in pauses)), 1)


def _elapsed_seconds(points: list[dict], session: dict | None) -> float | None:
    if session and _number(session.get("elapsed_seconds")) is not None:
        return round(float(session["elapsed_seconds"]), 1)
    if not points:
        return None
    return round(points[-1]["elapsed_seconds"] - points[0]["elapsed_seconds"], 1)


def _distance(points: list[dict], session: dict | None) -> float | None:
    if session and _number(session.get("distance_meters")) is not None:
        return float(session["distance_meters"])
    if not points:
        return None
    return points[-1]["distance_meters"] - points[0]["distance_meters"]


def _speed_gap(speeds: list[float], *, min_fast: int, min_gap: float) -> float | None:
    ordered = sorted(speeds)
    best_gap = 0.0
    midpoint = None
    for left, right in zip(ordered, ordered[1:]):
        gap = right - left
        above = sum(1 for speed in ordered if speed >= right - 0.01)
        if above >= min_fast and gap >= min_gap and gap > best_gap:
            best_gap = gap
            midpoint = (left + right) / 2
    return midpoint


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def _pace(distance: float, duration: float) -> float | None:
    if distance <= 0 or duration <= 0:
        return None
    return METERS_PER_MILE * duration / distance


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
