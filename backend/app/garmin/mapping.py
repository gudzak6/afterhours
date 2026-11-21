"""Map Garmin activity-search objects onto stored columns without inventing measurements.

Garmin's Personal API client returns the search payload as decoded JSON. The
activity list is a JSON array. Each object uses the Connect activity field
names (`activityId`, `distance`, `duration`, `averageSpeed`, and so on).
Numeric fields are copied only when that key is present. A present zero stays
zero. A missing key stays null.

`distance` is meters, `duration` and `movingDuration` are seconds, and
`averageSpeed` / `maxSpeed` are meters per second. Those units are the Connect
activity-list units and are labeled as such in the API. `elapsedDuration` is
stored raw because Connect has returned that field in milliseconds while
`duration` is in seconds; this importer does not convert it.
"""

from __future__ import annotations

from datetime import UTC, datetime

METERS_PER_MILE = 1609.344

NUMERIC_FIELDS = {
    "distance": "distance_meters",
    "duration": "duration_seconds",
    "movingDuration": "moving_duration_seconds",
    "elapsedDuration": "elapsed_duration_raw",
    "averageSpeed": "average_speed_mps",
    "maxSpeed": "max_speed_mps",
    "averageHR": "average_heart_rate_bpm",
    "maxHR": "max_heart_rate_bpm",
    "elevationGain": "elevation_gain_meters",
    "elevationLoss": "elevation_loss_meters",
    "averageRunningCadenceInStepsPerMinute": "average_cadence_spm",
    "calories": "calories",
    "startLatitude": "start_latitude",
    "startLongitude": "start_longitude",
}


class ActivityMappingError(ValueError):
    pass


def pace_seconds_per_mile(speed_mps: float | None) -> float | None:
    """Convert a positive speed in m/s to seconds per mile. Zero speed has no pace."""
    if speed_mps is None or speed_mps <= 0:
        return None
    return METERS_PER_MILE / speed_mps


def _optional_number(payload: dict, key: str) -> tuple[bool, float | None]:
    if key not in payload or payload[key] is None:
        return False, None
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return True, None
    return True, float(value)


def _optional_int(payload: dict, key: str) -> tuple[bool, int | None]:
    present, number = _optional_number(payload, key)
    if not present or number is None:
        return present, None
    return True, int(number)


def _optional_text(payload: dict, key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_garmin_timestamp(value: str | None) -> datetime | None:
    """Parse Connect's 'YYYY-MM-DD HH:MM:SS' GMT timestamps as UTC."""
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC)


def normalize_activity(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ActivityMappingError("activity payload must be an object")
    raw_id = payload.get("activityId")
    if isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id <= 0:
        raise ActivityMappingError("activity is missing a positive activityId")

    present: list[str] = []
    mapped: dict = {"garmin_activity_id": raw_id, "raw_summary": payload}
    for source_key, column in NUMERIC_FIELDS.items():
        key_present, number = _optional_number(payload, source_key)
        mapped[column] = number
        if key_present:
            present.append(column)

    lap_present, lap_count = _optional_int(payload, "lapCount")
    mapped["lap_count"] = lap_count
    if lap_present:
        present.append("lap_count")

    activity_type = payload.get("activityType")
    type_key = None
    if isinstance(activity_type, dict):
        type_key = _optional_text(activity_type, "typeKey")
        if "typeKey" in activity_type:
            present.append("activity_type_key")
    mapped["activity_type_key"] = type_key
    mapped["name"] = _optional_text(payload, "activityName")
    if "activityName" in payload and payload.get("activityName") is not None:
        present.append("name")

    start_gmt = _optional_text(payload, "startTimeGMT")
    start_local = _optional_text(payload, "startTimeLocal")
    mapped["start_time_gmt"] = start_gmt
    mapped["start_time_local"] = start_local
    mapped["start_time_utc"] = parse_garmin_timestamp(start_gmt)
    if "startTimeGMT" in payload and payload.get("startTimeGMT") is not None:
        present.append("start_time_gmt")
    if "startTimeLocal" in payload and payload.get("startTimeLocal") is not None:
        present.append("start_time_local")

    mapped["location_name"] = _optional_text(payload, "locationName")
    if "locationName" in payload and payload.get("locationName") is not None:
        present.append("location_name")

    manual = payload.get("manualActivity")
    mapped["manual_activity"] = manual if isinstance(manual, bool) else None
    if isinstance(manual, bool):
        present.append("manual_activity")

    mapped["present_fields"] = present
    mapped["average_pace_seconds_per_mile"] = pace_seconds_per_mile(mapped["average_speed_mps"])
    return mapped
