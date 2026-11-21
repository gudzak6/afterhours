"""Pace on climbs, descents, and flat ground. The coach does not recompute this."""

from __future__ import annotations

METERS_PER_MILE = 1609.344
STEP_METERS = 50.0
CLIMB_GRADE = 0.015
MIN_BUCKET_METERS = 200.0
STEEP_METERS = 8.0


def _pace_label(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    rounded = int(round(seconds))
    minutes, remainder = divmod(rounded, 60)
    return f"{minutes}:{remainder:02d} per mile"


def _pace(distance: float, duration: float) -> float | None:
    if distance < MIN_BUCKET_METERS or duration <= 0:
        return None
    return METERS_PER_MILE * duration / distance


def _at(points: list[tuple[float, float, float]], distance: float, field: int) -> float:
    if distance <= points[0][0]:
        return points[0][field]
    for earlier, later in zip(points, points[1:]):
        if later[0] < distance or later[0] <= earlier[0]:
            continue
        fraction = (distance - earlier[0]) / (later[0] - earlier[0])
        return earlier[field] + (later[field] - earlier[field]) * fraction
    return points[-1][field]


def _track(samples: list[dict]) -> list[tuple[float, float, float]]:
    ordered = sorted(
        (
            sample
            for sample in samples
            if isinstance(sample.get("distance_meters"), (int, float))
            and isinstance(sample.get("elapsed_seconds"), (int, float))
            and isinstance(sample.get("altitude_meters"), (int, float))
        ),
        key=lambda sample: (float(sample["distance_meters"]), float(sample["elapsed_seconds"])),
    )
    points: list[tuple[float, float, float]] = []
    last = -1.0
    for sample in ordered:
        distance = float(sample["distance_meters"])
        if distance + 1 < last:
            continue
        distance = max(distance, last)
        points.append((distance, float(sample["elapsed_seconds"]), float(sample["altitude_meters"])))
        last = distance
    return points


def _unavailable(reason: str) -> dict:
    return {"available": False, "reason": reason, "note": None}


def elevation_effect(
    samples: list[dict],
    *,
    gain_meters: float | None = None,
    loss_meters: float | None = None,
) -> dict:
    points = _track(samples)
    if len(points) < 8 or points[-1][0] - points[0][0] < 400:
        return _unavailable("Not enough altitude samples to judge the elevation effect.")

    origin = points[0][0]
    finish = points[-1][0]
    grid: list[tuple[float, float, float]] = []
    cursor = origin
    while cursor < finish:
        grid.append((cursor, _at(points, cursor, 1), _at(points, cursor, 2)))
        cursor += STEP_METERS
    grid.append((finish, points[-1][1], points[-1][2]))
    smooth = []
    raw = [point[2] for point in grid]
    for index, altitude in enumerate(raw):
        window = raw[max(0, index - 1) : index + 2]
        smooth.append(sum(window) / len(window))

    buckets = {"climb": [0.0, 0.0], "descent": [0.0, 0.0], "flat": [0.0, 0.0]}
    profile_gain = 0.0
    profile_loss = 0.0
    for index in range(1, len(grid)):
        distance = grid[index][0] - grid[index - 1][0]
        duration = grid[index][1] - grid[index - 1][1]
        change = smooth[index] - smooth[index - 1]
        if distance <= 0 or duration <= 0:
            continue
        if change > 0:
            profile_gain += change
        elif change < 0:
            profile_loss += -change
        grade = change / distance
        kind = "climb" if grade >= CLIMB_GRADE else "descent" if grade <= -CLIMB_GRADE else "flat"
        buckets[kind][0] += distance
        buckets[kind][1] += duration

    paces = {name: _pace(distance, duration) for name, (distance, duration) in buckets.items()}
    climb_vs_flat = None if paces["climb"] is None or paces["flat"] is None else round(paces["climb"] - paces["flat"], 1)
    descent_vs_flat = None if paces["descent"] is None or paces["flat"] is None else round(paces["descent"] - paces["flat"], 1)

    miles = []
    full = int((finish - origin) // METERS_PER_MILE)
    for number in range(1, min(full, 50) + 1):
        start = origin + (number - 1) * METERS_PER_MILE
        end = origin + number * METERS_PER_MILE
        net = _at(points, end, 2) - _at(points, start, 2)
        duration = _at(points, end, 1) - _at(points, start, 1)
        pace = None if duration <= 0 else METERS_PER_MILE * duration / METERS_PER_MILE
        miles.append(
            {
                "label": f"Mile {number}",
                "net_meters": round(net, 1),
                "pace_seconds_per_mile": None if pace is None else round(pace, 1),
                "pace": _pace_label(pace),
            }
        )
    climbs = [mile for mile in miles if mile["net_meters"] >= STEEP_METERS]
    descents = [mile for mile in miles if mile["net_meters"] <= -STEEP_METERS]
    steepest_climb = max(climbs, key=lambda mile: mile["net_meters"]) if climbs else None
    steepest_descent = min(descents, key=lambda mile: mile["net_meters"]) if descents else None

    recorded_gain = None if gain_meters is None else round(float(gain_meters), 1)
    recorded_loss = None if loss_meters is None else round(float(loss_meters), 1)
    note = _note(
        recorded_gain=recorded_gain,
        recorded_loss=recorded_loss,
        climb_vs_flat=climb_vs_flat,
        descent_vs_flat=descent_vs_flat,
        steepest_climb=steepest_climb,
        steepest_descent=steepest_descent,
    )
    return {
        "available": True,
        "recorded_gain_meters": recorded_gain,
        "recorded_loss_meters": recorded_loss,
        "profile_gain_meters": round(profile_gain, 1),
        "profile_loss_meters": round(profile_loss, 1),
        "climb_distance_meters": round(buckets["climb"][0], 1),
        "descent_distance_meters": round(buckets["descent"][0], 1),
        "flat_distance_meters": round(buckets["flat"][0], 1),
        "climb_pace_seconds_per_mile": None if paces["climb"] is None else round(paces["climb"], 1),
        "descent_pace_seconds_per_mile": None if paces["descent"] is None else round(paces["descent"], 1),
        "flat_pace_seconds_per_mile": None if paces["flat"] is None else round(paces["flat"], 1),
        "climb_versus_flat_seconds_per_mile": climb_vs_flat,
        "descent_versus_flat_seconds_per_mile": descent_vs_flat,
        "steepest_climb": steepest_climb,
        "steepest_descent": steepest_descent,
        "mile_splits": miles,
        "note": note,
    }


def _sentence(seconds: float, uphill: bool) -> str:
    amount = abs(round(seconds))
    direction = "slower" if seconds > 0 else "faster"
    ground = "Uphill" if uphill else "Downhill"
    return f"{ground} running was {amount} seconds per mile {direction} than the flat running."


def _note(
    *,
    recorded_gain: float | None,
    recorded_loss: float | None,
    climb_vs_flat: float | None,
    descent_vs_flat: float | None,
    steepest_climb: dict | None,
    steepest_descent: dict | None,
) -> str:
    parts = []
    if recorded_gain is not None or recorded_loss is not None:
        gain = "unknown" if recorded_gain is None else f"{recorded_gain:.0f} m"
        loss = "unknown" if recorded_loss is None else f"{recorded_loss:.0f} m"
        parts.append(f"Recorded elevation gain was {gain} and loss was {loss}.")
    if climb_vs_flat is not None and abs(climb_vs_flat) >= 1:
        parts.append(_sentence(climb_vs_flat, True))
    if descent_vs_flat is not None and abs(descent_vs_flat) >= 1:
        parts.append(_sentence(descent_vs_flat, False))
    if steepest_climb is not None:
        parts.append(
            f"{steepest_climb['label']} climbed {steepest_climb['net_meters']:.0f} m"
            + (f" at {steepest_climb['pace']}." if steepest_climb.get("pace") else ".")
        )
    if steepest_descent is not None:
        parts.append(
            f"{steepest_descent['label']} dropped {abs(steepest_descent['net_meters']):.0f} m"
            + (f" at {steepest_descent['pace']}." if steepest_descent.get("pace") else ".")
        )
    if len(parts) <= 1 and recorded_gain is not None:
        parts.append("No sustained climb or descent was long enough to separate its pace from the flat running.")
    return " ".join(parts)
