"""Parse a FIT activity without filling in missing measurements.

fitdecode leaves coordinates in semicircles. Those are converted to degrees with
the FIT scale 180 / 2^31. The invalid semicircle sentinel is treated as missing,
not as a coordinate. A recorded zero stays zero.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

SEMICIRCLES_TO_DEGREES = 180 / 2**31
INVALID_SEMICIRCLE = 2147483647


def _raw(frame, name: str):
    if not frame.has_field(name):
        return None, False
    field = frame.get_field(name)
    if field is None or field.value is None:
        return None, True
    return field.value, True


def _first_number(frame, names: tuple[str, ...]) -> tuple[float | None, str | None]:
    seen = False
    for name in names:
        value, present = _raw(frame, name)
        if not present:
            continue
        seen = True
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        return float(value), name
    return None, None if not seen else names[0]


def _text(frame, name: str) -> str | None:
    value, present = _raw(frame, name)
    if not present or value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def semicircles_to_degrees(value) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if abs(number) <= 180:
        return number
    if int(number) in (INVALID_SEMICIRCLE, -2147483648):
        return None
    return number * SEMICIRCLES_TO_DEGREES


def _end_time(start: datetime | None, timestamp: datetime | None, elapsed: float | None) -> datetime | None:
    if start is not None and timestamp is not None and timestamp > start:
        return timestamp
    if start is not None and elapsed is not None:
        return start + timedelta(seconds=elapsed)
    return timestamp


def extract_lap(frame, lap_number: int) -> dict:
    distance, distance_field = _first_number(frame, ("total_distance",))
    timer, timer_field = _first_number(frame, ("total_timer_time",))
    elapsed, elapsed_field = _first_number(frame, ("total_elapsed_time",))
    speed, speed_field = _first_number(frame, ("enhanced_avg_speed", "avg_speed"))
    avg_hr, hr_field = _first_number(frame, ("avg_heart_rate",))
    max_hr, max_hr_field = _first_number(frame, ("max_heart_rate",))
    cadence, cadence_field = _first_number(frame, ("avg_running_cadence", "avg_cadence", "cadence"))
    ascent, ascent_field = _first_number(frame, ("total_ascent",))
    descent, descent_field = _first_number(frame, ("total_descent",))
    power, power_field = _first_number(frame, ("avg_power",))
    start = _as_utc(_raw(frame, "start_time")[0] if _raw(frame, "start_time")[1] else None)
    stamp_value, stamp_present = _raw(frame, "timestamp")
    stamp = _as_utc(stamp_value if isinstance(stamp_value, datetime) else None)
    present = [
        name
        for name, flag in (
            ("distance_meters", distance_field),
            ("duration_seconds", timer_field),
            ("elapsed_seconds", elapsed_field),
            ("average_speed_mps", speed_field),
            ("average_heart_rate_bpm", hr_field),
            ("max_heart_rate_bpm", max_hr_field),
            ("average_cadence", cadence_field),
            ("ascent_meters", ascent_field),
            ("descent_meters", descent_field),
            ("average_power_watts", power_field),
        )
        if flag
    ]
    intensity = _text(frame, "intensity")
    trigger = _text(frame, "lap_trigger")
    step_index, step_present = _raw(frame, "wkt_step_index")
    if intensity:
        present.append("intensity")
    if trigger:
        present.append("lap_trigger")
    if step_present:
        present.append("wkt_step_index")
    return {
        "lap_number": lap_number,
        "distance_meters": distance,
        "duration_seconds": timer,
        "elapsed_seconds": elapsed,
        "average_speed_mps": speed,
        "average_heart_rate_bpm": avg_hr,
        "max_heart_rate_bpm": max_hr,
        "average_cadence": cadence,
        "cadence_field": cadence_field,
        "ascent_meters": ascent,
        "descent_meters": descent,
        "average_power_watts": power,
        "start_time_utc": start,
        "end_time_utc": _end_time(start, stamp, elapsed),
        "intensity": intensity,
        "lap_trigger": trigger,
        "wkt_step_index": step_index if isinstance(step_index, int) else None,
        "present_fields": present,
    }


def extract_record(frame, origin: datetime | None) -> dict:
    stamp_value, _present = _raw(frame, "timestamp")
    stamp = _as_utc(stamp_value if isinstance(stamp_value, datetime) else None)
    distance, distance_field = _first_number(frame, ("distance",))
    speed, speed_field = _first_number(frame, ("enhanced_speed", "speed"))
    heart, heart_field = _first_number(frame, ("heart_rate",))
    cadence, cadence_field = _first_number(frame, ("cadence",))
    fractional, fractional_field = _first_number(frame, ("fractional_cadence",))
    altitude, altitude_field = _first_number(frame, ("enhanced_altitude", "altitude"))
    power, power_field = _first_number(frame, ("power",))
    lat_raw, lat_present = _raw(frame, "position_lat")
    lon_raw, lon_present = _raw(frame, "position_long")
    latitude = semicircles_to_degrees(lat_raw) if lat_present else None
    longitude = semicircles_to_degrees(lon_raw) if lon_present else None
    cadence_value = cadence
    if cadence is not None and fractional is not None:
        cadence_value = cadence + fractional
    elapsed = None
    if stamp is not None and origin is not None:
        elapsed = (stamp - origin).total_seconds()
    present = [
        name
        for name, flag in (
            ("distance_meters", distance_field),
            ("speed_mps", speed_field),
            ("heart_rate_bpm", heart_field),
            ("cadence", cadence_field or fractional_field),
            ("altitude_meters", altitude_field),
            ("power_watts", power_field),
            ("latitude", lat_present and latitude is not None),
            ("longitude", lon_present and longitude is not None),
        )
        if flag
    ]
    return {
        "sample_time_utc": stamp,
        "elapsed_seconds": elapsed,
        "distance_meters": distance,
        "speed_mps": speed,
        "heart_rate_bpm": heart,
        "cadence": cadence_value,
        "altitude_meters": altitude,
        "power_watts": power,
        "latitude": latitude,
        "longitude": longitude,
        "present_fields": present,
    }


def extract_event(frame) -> dict:
    stamp_value, _present = _raw(frame, "timestamp")
    stamp = _as_utc(stamp_value if isinstance(stamp_value, datetime) else None)
    return {
        "timestamp": stamp,
        "event": _text(frame, "event"),
        "event_type": _text(frame, "event_type"),
        "timer_trigger": _text(frame, "timer_trigger"),
    }


def extract_step(frame, step_index: int) -> dict:
    duration, duration_field = _first_number(frame, ("duration_time", "duration_value"))
    distance, distance_field = _first_number(frame, ("duration_distance",))
    duration_type = _text(frame, "duration_type")
    if duration_type == "distance" and distance is None and duration is not None:
        distance, duration = duration, None
    if duration_type == "time" and duration is not None and duration > 100000:
        duration = duration / 1000
    low, low_field = _first_number(frame, ("custom_target_value_low", "target_value"))
    high, high_field = _first_number(frame, ("custom_target_value_high",))
    present = [name for name, flag in (
        ("duration_seconds", duration_field and duration_type != "distance"),
        ("distance_meters", distance_field or duration_type == "distance"),
        ("target_low", low_field),
        ("target_high", high_field),
    ) if flag]
    return {
        "step_index": step_index,
        "intensity": _text(frame, "intensity"),
        "duration_seconds": duration if duration_type != "distance" else None,
        "distance_meters": distance,
        "target_type": _text(frame, "target_type"),
        "target_low": low,
        "target_high": high,
        "notes": _text(frame, "notes"),
        "present_fields": present,
        "raw_step": {
            "duration_type": duration_type,
            "intensity": _text(frame, "intensity"),
            "target_type": _text(frame, "target_type"),
        },
    }


def extract_session(frame) -> dict:
    distance, _ = _first_number(frame, ("total_distance",))
    timer, _ = _first_number(frame, ("total_timer_time",))
    elapsed, _ = _first_number(frame, ("total_elapsed_time",))
    ascent, _ = _first_number(frame, ("total_ascent",))
    descent, _ = _first_number(frame, ("total_descent",))
    speed, _ = _first_number(frame, ("enhanced_avg_speed", "avg_speed"))
    avg_hr, _ = _first_number(frame, ("avg_heart_rate",))
    max_hr, _ = _first_number(frame, ("max_heart_rate",))
    laps, _ = _first_number(frame, ("num_laps",))
    return {
        "sport": _text(frame, "sport"),
        "sub_sport": _text(frame, "sub_sport"),
        "distance_meters": distance,
        "timer_seconds": timer,
        "elapsed_seconds": elapsed,
        "ascent_meters": ascent,
        "descent_meters": descent,
        "average_speed_mps": speed,
        "average_heart_rate_bpm": avg_hr,
        "max_heart_rate_bpm": max_hr,
        "lap_count": None if laps is None else int(laps),
        "start_time_utc": _as_utc(_raw(frame, "start_time")[0] if isinstance(_raw(frame, "start_time")[0], datetime) else None),
    }


def parse_fit(payload: bytes) -> dict:
    import fitdecode

    session = None
    laps = []
    records = []
    steps = []
    events = []
    origin = None
    with fitdecode.FitReader(io.BytesIO(payload)) as reader:
        for frame in reader:
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue
            if frame.name == "session" and session is None:
                session = extract_session(frame)
                origin = session.get("start_time_utc")
            elif frame.name == "lap":
                laps.append(extract_lap(frame, len(laps) + 1))
            elif frame.name == "record":
                records.append(extract_record(frame, origin))
            elif frame.name == "workout_step":
                steps.append(extract_step(frame, len(steps) + 1))
            elif frame.name == "event":
                events.append(extract_event(frame))
    if origin is None:
        for record in records:
            if record["sample_time_utc"] is not None:
                origin = record["sample_time_utc"]
                break
        if origin is not None:
            for record in records:
                if record["sample_time_utc"] is not None and record["elapsed_seconds"] is None:
                    record["elapsed_seconds"] = (record["sample_time_utc"] - origin).total_seconds()
    return {
        "session": session or {},
        "laps": laps,
        "records": records,
        "steps": steps,
        "events": events,
        "workout_steps_found": bool(steps),
    }
