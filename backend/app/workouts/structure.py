"""Describe the repetitions an athlete actually ran.

Pace, not the lap button, ends a repetition. A mile auto-lap stays inside a
repetition while the recorded speed stays fast.
"""

from __future__ import annotations

METERS_PER_MILE = 1609.344

STANDARDS: list[tuple[float, str]] = [
    (100, "100 m"),
    (200, "200 m"),
    (300, "300 m"),
    (400, "400 m"),
    (600, "600 m"),
    (800, "800 m"),
    (1000, "1 km"),
    (1200, "1200 m"),
    (METERS_PER_MILE, "1 mile"),
    (2000, "2 km"),
    (3000, "3 km"),
    (5000, "5 km"),
]


def _empty() -> dict:
    return {
        "label": None,
        "kind": None,
        "warmup_meters": None,
        "cooldown_meters": None,
        "repetitions": [],
        "groups": [],
    }


def _pace_label(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    rounded = int(round(seconds))
    minutes, remainder = divmod(rounded, 60)
    return f"{minutes}:{remainder:02d} per mile"


def _duration_label(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    total = int(round(seconds))
    minutes, remainder = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{remainder:02d}"
    return f"{minutes}:{remainder:02d}"


def _snap(distance: float) -> str:
    best: tuple[float, str] | None = None
    for standard, name in STANDARDS:
        error = abs(distance - standard)
        if error <= max(25.0, standard * 0.05) and (best is None or error < best[0]):
            best = (error, name)
    if best is not None:
        return best[1]
    if distance >= METERS_PER_MILE:
        return f"{distance / METERS_PER_MILE:.2f} mi"
    return f"{round(distance)} m"


def work_threshold(laps: list[dict]) -> float | None:
    """Speed that separates the fast repetitions from the jogging laps."""
    speeds: list[float] = []
    for lap in laps:
        speed = lap.get("average_speed_mps")
        duration = lap.get("duration_seconds") or 0
        distance = lap.get("distance_meters") or 0
        if isinstance(speed, (int, float)) and speed > 0 and duration >= 15 and distance >= 80:
            speeds.append(float(speed))
    if len(speeds) < 4:
        return None
    speeds.sort()
    best_gap = 0.0
    midpoint: float | None = None
    for left, right in zip(speeds, speeds[1:]):
        gap = right - left
        above = sum(1 for speed in speeds if speed >= right - 0.01)
        if above >= 3 and gap >= 0.45 and gap > best_gap:
            best_gap = gap
            midpoint = (left + right) / 2
    return midpoint


def _finish_block(block: dict) -> dict | None:
    distance = block["end_distance"] - block["start_distance"]
    duration = block["end_elapsed"] - block["start_elapsed"]
    if distance < 40 or duration < 12:
        return None
    heart_rates = block["heart_rates"]
    return {
        "distance_meters": distance,
        "duration_seconds": duration,
        "average_heart_rate_bpm": None if not heart_rates else sum(heart_rates) / len(heart_rates),
        "recovery_meters": None,
        "recovery_seconds": None,
    }


def _blocks_from_samples(samples: list[dict], threshold: float) -> tuple[list[dict], float | None, float | None]:
    samples = sorted(samples, key=lambda sample: sample.get("elapsed_seconds") or 0)
    raw: list[dict] = []
    current: dict | None = None
    below_since: float | None = None

    def close() -> None:
        nonlocal current
        if current is None:
            return
        finished = _finish_block(current)
        if finished is not None:
            finished["start_elapsed"] = current["start_elapsed"]
            finished["end_elapsed"] = current["end_elapsed"]
            finished["start_distance"] = current["start_distance"]
            finished["end_distance"] = current["end_distance"]
            raw.append(finished)
        current = None

    for sample in samples:
        elapsed = float(sample["elapsed_seconds"])
        distance = float(sample["distance_meters"])
        speed = sample.get("speed_mps")
        fast = isinstance(speed, (int, float)) and speed >= threshold
        if fast:
            if current is None:
                current = {
                    "start_elapsed": elapsed,
                    "start_distance": distance,
                    "end_elapsed": elapsed,
                    "end_distance": distance,
                    "heart_rates": [],
                }
            current["end_elapsed"] = elapsed
            current["end_distance"] = distance
            heart = sample.get("heart_rate_bpm")
            if isinstance(heart, (int, float)):
                current["heart_rates"].append(float(heart))
            below_since = None
            continue
        if current is None:
            continue
        if below_since is None:
            below_since = elapsed
        if elapsed - below_since >= 12:
            close()
            below_since = None
    close()
    if len(raw) < 2:
        return [], None, None
    for earlier, later in zip(raw, raw[1:]):
        earlier["recovery_seconds"] = max(0.0, later["start_elapsed"] - earlier["end_elapsed"])
        earlier["recovery_meters"] = max(0.0, later["start_distance"] - earlier["end_distance"])
    warmup = raw[0]["start_distance"]
    last_distance = samples[-1].get("distance_meters")
    cooldown = None
    if isinstance(last_distance, (int, float)):
        cooldown = max(0.0, float(last_distance) - raw[-1]["end_distance"])
    for block in raw:
        for key in ("start_elapsed", "end_elapsed", "start_distance", "end_distance"):
            block.pop(key, None)
    return raw, warmup, cooldown


def _blocks_from_laps(laps: list[dict], threshold: float) -> tuple[list[dict], float | None, float | None]:
    groups: list[tuple[int, int, list[dict]]] = []
    current: list[dict] = []
    start_index: int | None = None
    for index, lap in enumerate(laps):
        speed = lap.get("average_speed_mps")
        if isinstance(speed, (int, float)) and speed >= threshold:
            if start_index is None:
                start_index = index
            current.append(lap)
        elif current:
            groups.append((start_index or 0, index - 1, current))
            current = []
            start_index = None
    if current:
        groups.append((start_index or 0, len(laps) - 1, current))
    blocks: list[dict] = []
    for group_start, group_end, group in groups:
        distance = sum(float(lap.get("distance_meters") or 0) for lap in group)
        duration = sum(float(lap.get("duration_seconds") or 0) for lap in group)
        if distance < 40 or duration < 12:
            continue
        weighted = 0.0
        weight = 0.0
        for lap in group:
            heart = lap.get("average_heart_rate_bpm")
            lap_duration = float(lap.get("duration_seconds") or 0)
            if isinstance(heart, (int, float)) and lap_duration > 0:
                weighted += float(heart) * lap_duration
                weight += lap_duration
        blocks.append(
            {
                "distance_meters": distance,
                "duration_seconds": duration,
                "average_heart_rate_bpm": None if weight == 0 else weighted / weight,
                "recovery_meters": None,
                "recovery_seconds": None,
                "start_index": group_start,
                "end_index": group_end,
            }
        )
    if len(blocks) < 2:
        return [], None, None
    for earlier, later in zip(blocks, blocks[1:]):
        between = laps[earlier["end_index"] + 1 : later["start_index"]]
        earlier["recovery_meters"] = sum(float(lap.get("distance_meters") or 0) for lap in between)
        earlier["recovery_seconds"] = sum(float(lap.get("duration_seconds") or 0) for lap in between)
    warmup = sum(float(lap.get("distance_meters") or 0) for lap in laps[: blocks[0]["start_index"]])
    cooldown = sum(float(lap.get("distance_meters") or 0) for lap in laps[blocks[-1]["end_index"] + 1 :])
    for block in blocks:
        block.pop("start_index", None)
        block.pop("end_index", None)
    return blocks, warmup, cooldown


def _phrase(count: int, pattern: list[str]) -> str:
    if count == 1:
        return pattern[0]
    if len(pattern) == 1:
        return f"{count} × {pattern[0]}"
    return f"{count} × ({', '.join(pattern)})"


def _assemble(blocks: list[dict], warmup: float | None, cooldown: float | None) -> dict:
    repetitions = []
    for index, block in enumerate(blocks, start=1):
        distance = float(block["distance_meters"])
        duration = float(block["duration_seconds"])
        pace = None if duration <= 0 or distance <= 0 else METERS_PER_MILE * duration / distance
        heart = block.get("average_heart_rate_bpm")
        repetitions.append(
            {
                "index": index,
                "label": _snap(distance),
                "distance_meters": round(distance, 1),
                "duration_seconds": round(duration, 1),
                "duration": _duration_label(duration),
                "pace_seconds_per_mile": None if pace is None else round(pace, 1),
                "pace": _pace_label(pace),
                "average_heart_rate_bpm": None if heart is None else round(float(heart)),
                "recovery_seconds": None
                if block.get("recovery_seconds") is None
                else round(float(block["recovery_seconds"]), 1),
                "recovery": _duration_label(block.get("recovery_seconds")),
                "recovery_meters": None
                if block.get("recovery_meters") is None
                else round(float(block["recovery_meters"]), 1),
            }
        )
    labels = [rep["label"] for rep in repetitions]
    groups: list[dict] = []
    phrases: list[str] = []
    cursor = 0
    count = len(labels)
    while cursor < count:
        best: tuple[int, int, int] | None = None
        for size in range(1, min(4, count - cursor) + 1):
            pattern = labels[cursor : cursor + size]
            repeats = 1
            while cursor + (repeats + 1) * size <= count and labels[cursor + repeats * size : cursor + (repeats + 1) * size] == pattern:
                repeats += 1
            covered = repeats * size
            if repeats >= 2 and (best is None or covered > best[0] or (covered == best[0] and repeats > best[2])):
                best = (covered, size, repeats)
        if best is None:
            groups.append({"heading": None, "repetitions": [repetitions[cursor]]})
            phrases.append(labels[cursor])
            cursor += 1
            continue
        _, size, repeats = best
        pattern = labels[cursor : cursor + size]
        phrases.append(_phrase(repeats, pattern))
        if size == 1:
            groups.append({"heading": None, "repetitions": repetitions[cursor : cursor + repeats]})
        else:
            for number in range(repeats):
                start = cursor + number * size
                groups.append(
                    {
                        "heading": f"Set {number + 1} of {repeats}",
                        "repetitions": repetitions[start : start + size],
                    }
                )
        cursor += repeats * size
    return {
        "label": ", ".join(phrases),
        "kind": "reps",
        "warmup_meters": None if warmup is None or warmup < 200 else round(warmup, 1),
        "cooldown_meters": None if cooldown is None or cooldown < 200 else round(cooldown, 1),
        "repetitions": repetitions,
        "groups": groups,
    }


def _clock(points: list[tuple[float, float, float | None]], distance: float) -> float:
    if distance <= points[0][1]:
        return points[0][0]
    for earlier, later in zip(points, points[1:]):
        if later[1] < distance or later[1] <= earlier[1]:
            continue
        fraction = (distance - earlier[1]) / (later[1] - earlier[1])
        return earlier[0] + (later[0] - earlier[0]) * fraction
    return points[-1][0]


def _mile_points(samples: list[dict]) -> list[tuple[float, float, float | None]]:
    ordered = sorted(samples, key=lambda sample: (float(sample["elapsed_seconds"]), float(sample["distance_meters"])))
    points: list[tuple[float, float, float | None]] = []
    last_distance = -1.0
    for sample in ordered:
        distance = float(sample["distance_meters"])
        if distance + 1 < last_distance:
            continue
        distance = max(distance, last_distance)
        heart = sample.get("heart_rate_bpm")
        points.append((float(sample["elapsed_seconds"]), distance, float(heart) if isinstance(heart, (int, float)) else None))
        last_distance = distance
    return points


def _mile_repetition(index: int, label: str, distance: float, duration: float, heart_rates: list[float]) -> dict:
    pace = None if duration <= 0 or distance <= 0 else METERS_PER_MILE * duration / distance
    return {
        "index": index,
        "label": label,
        "distance_meters": round(distance, 1),
        "duration_seconds": round(duration, 1),
        "duration": _duration_label(duration),
        "pace_seconds_per_mile": None if pace is None else round(pace, 1),
        "pace": _pace_label(pace),
        "average_heart_rate_bpm": None if not heart_rates else round(sum(heart_rates) / len(heart_rates)),
        "recovery_seconds": None,
        "recovery": None,
        "recovery_meters": None,
    }


def _miles_from_samples(samples: list[dict]) -> dict:
    points = _mile_points(samples)
    if len(points) < 2:
        return _empty()
    total = points[-1][1] - points[0][1]
    full = int(total // METERS_PER_MILE)
    if full < 2:
        return _empty()
    origin = points[0][1]
    repetitions = []
    for number in range(1, full + 1):
        start = origin + (number - 1) * METERS_PER_MILE
        end = origin + number * METERS_PER_MILE
        hearts = [heart for elapsed, distance, heart in points if heart is not None and start <= distance < end]
        repetitions.append(
            _mile_repetition(number, f"Mile {number}", METERS_PER_MILE, _clock(points, end) - _clock(points, start), hearts)
        )
    remainder = total - full * METERS_PER_MILE
    if remainder >= 100:
        start = origin + full * METERS_PER_MILE
        end = points[-1][1]
        hearts = [heart for elapsed, distance, heart in points if heart is not None and start <= distance <= end]
        repetitions.append(
            _mile_repetition(
                full + 1,
                f"{remainder / METERS_PER_MILE:.2f} mi",
                remainder,
                _clock(points, end) - _clock(points, start),
                hearts,
            )
        )
    headline = f"{full} × 1 mile" if remainder < 100 else f"{full} × 1 mile, then {remainder / METERS_PER_MILE:.2f} mi"
    return {
        "label": headline,
        "kind": "miles",
        "warmup_meters": None,
        "cooldown_meters": None,
        "repetitions": repetitions,
        "groups": [{"heading": None, "repetitions": repetitions}],
    }


def _sprint_from_laps(laps: list[dict]) -> dict:
    """Short fast laps separated by a slower lap. Pace stays the watch lap."""
    fast: list[int] = []
    for index, lap in enumerate(laps):
        duration = float(lap.get("duration_seconds") or 0)
        distance = float(lap.get("distance_meters") or 0)
        speed = lap.get("average_speed_mps")
        if not isinstance(speed, (int, float)):
            continue
        if 6 <= duration <= 40 and 30 <= distance <= 220 and float(speed) >= 3.2:
            fast.append(index)
    if len(fast) < 3 or fast[-1] - fast[0] + 1 == len(fast):
        return _empty()
    blocks: list[dict] = []
    for position, index in enumerate(fast):
        lap = laps[index]
        speed = float(lap["average_speed_mps"])
        recovery_seconds = None
        recovery_meters = None
        if position + 1 < len(fast):
            between = laps[index + 1 : fast[position + 1]]
            recovery_seconds = sum(float(item.get("duration_seconds") or 0) for item in between)
            recovery_meters = sum(float(item.get("distance_meters") or 0) for item in between)
            weighted = 0.0
            weight = 0.0
            for item in between:
                item_speed = item.get("average_speed_mps")
                item_duration = float(item.get("duration_seconds") or 0)
                if isinstance(item_speed, (int, float)) and item_duration > 0:
                    weighted += float(item_speed) * item_duration
                    weight += item_duration
            if weight > 0 and weighted / weight > speed * 0.7:
                return _empty()
        blocks.append(
            {
                "distance_meters": float(lap.get("distance_meters") or 0),
                "duration_seconds": float(lap.get("duration_seconds") or 0),
                "average_heart_rate_bpm": lap.get("average_heart_rate_bpm"),
                "recovery_seconds": recovery_seconds,
                "recovery_meters": recovery_meters,
            }
        )
    warmup = sum(float(lap.get("distance_meters") or 0) for lap in laps[: fast[0]])
    cooldown = sum(float(lap.get("distance_meters") or 0) for lap in laps[fast[-1] + 1 :])
    result = _assemble(blocks, warmup, cooldown)
    result["kind"] = "sprints"
    for repetition in result["repetitions"]:
        repetition["measurement_source"] = "garmin_lap"
    return result


def _is_mile_lap(lap: dict) -> bool:
    distance = lap.get("distance_meters")
    duration = lap.get("duration_seconds")
    return (
        isinstance(distance, (int, float))
        and abs(float(distance) - METERS_PER_MILE) <= 40
        and isinstance(duration, (int, float))
    )


def _miles_from_laps(laps: list[dict]) -> dict:
    indexed = [(index, lap) for index, lap in enumerate(laps) if _is_mile_lap(lap)]
    if len(indexed) < 2:
        return _empty()
    repetitions = []
    for number, (_index, lap) in enumerate(indexed, start=1):
        heart = lap.get("average_heart_rate_bpm")
        repetitions.append(
            _mile_repetition(
                number,
                f"Mile {number}",
                float(lap["distance_meters"]),
                float(lap["duration_seconds"]),
                [] if not isinstance(heart, (int, float)) else [float(heart)],
            )
        )
    trailing = laps[indexed[-1][0] + 1 :]
    trail_distance = sum(float(lap.get("distance_meters") or 0) for lap in trailing)
    trail_duration = sum(float(lap.get("duration_seconds") or 0) for lap in trailing)
    if trail_distance >= 100 and trail_duration > 0:
        hearts = [
            float(lap["average_heart_rate_bpm"])
            for lap in trailing
            if isinstance(lap.get("average_heart_rate_bpm"), (int, float))
        ]
        repetitions.append(
            _mile_repetition(
                len(repetitions) + 1,
                f"{trail_distance / METERS_PER_MILE:.2f} mi",
                trail_distance,
                trail_duration,
                hearts,
            )
        )
    headline = f"{len(indexed)} × 1 mile"
    if trail_distance >= 100:
        headline = f"{headline}, then {trail_distance / METERS_PER_MILE:.2f} mi"
    return {
        "label": headline,
        "kind": "miles",
        "warmup_meters": None,
        "cooldown_meters": None,
        "repetitions": repetitions,
        "groups": [{"heading": None, "repetitions": repetitions}],
    }


def _interval_breakdown(laps: list[dict], samples: list[dict]) -> dict:
    threshold = work_threshold(laps)
    if threshold is None:
        return _empty()
    if len(samples) >= 30:
        blocks, warmup, cooldown = _blocks_from_samples(samples, threshold)
    else:
        blocks, warmup, cooldown = _blocks_from_laps(laps, threshold)
    if len(blocks) < 2:
        return _empty()
    return _assemble(blocks, warmup, cooldown)


def _with_lap_source(result: dict, samples: list[dict]) -> dict:
    """Keep the watch lap pace. Record a GPS-trace pace beside it when they disagree."""
    for repetition in result.get("repetitions") or []:
        repetition["measurement_source"] = "garmin_lap"
    if len(samples) < 30:
        return result
    traced = _miles_from_samples(samples)
    traced_by_index = {repetition["index"]: repetition for repetition in traced.get("repetitions") or []}
    for repetition in result.get("repetitions") or []:
        other = traced_by_index.get(repetition["index"])
        lap_pace = repetition.get("pace_seconds_per_mile")
        trace_pace = None if other is None else other.get("pace_seconds_per_mile")
        if lap_pace is None or trace_pace is None or abs(trace_pace - lap_pace) < 15:
            continue
        repetition["sample_pace_seconds_per_mile"] = trace_pace
    return result


def describe_workout(laps: list[dict], samples: list[dict] | None = None) -> dict:
    usable = [
        sample
        for sample in (samples or [])
        if isinstance(sample.get("elapsed_seconds"), (int, float))
        and isinstance(sample.get("distance_meters"), (int, float))
        and isinstance(sample.get("speed_mps"), (int, float))
    ]
    intervals = _interval_breakdown(laps, usable)
    if intervals["label"]:
        return intervals
    sprints = _sprint_from_laps(laps)
    if sprints["label"]:
        return sprints
    lap_miles = _miles_from_laps(laps)
    if lap_miles["label"]:
        return _with_lap_source(lap_miles, usable)
    if len(usable) >= 30:
        miles = _miles_from_samples(usable)
        if miles["label"]:
            for repetition in miles["repetitions"]:
                repetition["measurement_source"] = "gps_trace"
            return miles
    return lap_miles
