"""Download a Garmin activity ZIP, store it, and replace parsed laps and samples."""

from __future__ import annotations

import hashlib
import io
import threading
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import DATA_DIR, Settings
from app.fit.parse import parse_fit
from app.garmin.client import GarminRequestError, GarminSession
from app.models import (
    Activity,
    ActivityFile,
    ActivityLap,
    ActivitySample,
    ActivityWorkoutStep,
    AthleteThreshold,
    WorkoutClassification,
    WorkoutSegment,
)
from app.workouts.classify import classify_laps, compare_reference
from app.workouts.detect import detect_workout

_FILE_LOCK = threading.Lock()


def raw_dir(garmin_activity_id: int) -> Path:
    return DATA_DIR / "raw" / str(garmin_activity_id)


def _write_private(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(0o600)


def _lt2_speed(session: Session, athlete_id: int) -> float | None:
    row = session.scalar(
        select(AthleteThreshold).where(
            AthleteThreshold.athlete_id == athlete_id,
            AthleteThreshold.name == "lt2",
        )
    )
    if row is None or not row.pace_seconds_per_mile or row.pace_seconds_per_mile <= 0:
        return None
    return 1609.344 / row.pace_seconds_per_mile


def store_parsed_activity(session: Session, activity: Activity, parsed: dict, zip_bytes: bytes, fit_bytes: bytes) -> None:
    directory = raw_dir(activity.garmin_activity_id)
    zip_path = directory / "activity.zip"
    fit_path = directory / "activity.fit"
    _write_private(zip_path, zip_bytes)
    _write_private(fit_path, fit_bytes)
    now = datetime.now(UTC)
    for kind, path, payload in (("zip", zip_path, zip_bytes), ("fit", fit_path, fit_bytes)):
        existing = session.scalar(
            select(ActivityFile).where(ActivityFile.activity_id == activity.id, ActivityFile.kind == kind)
        )
        digest = hashlib.sha256(payload).hexdigest()
        if existing is None:
            session.add(
                ActivityFile(
                    activity_id=activity.id,
                    kind=kind,
                    storage_path=str(path),
                    byte_size=len(payload),
                    sha256=digest,
                    downloaded_at=now,
                )
            )
        else:
            existing.storage_path = str(path)
            existing.byte_size = len(payload)
            existing.sha256 = digest
            existing.downloaded_at = now

    existing_classification = session.scalar(
        select(WorkoutClassification).where(WorkoutClassification.activity_id == activity.id)
    )
    user_locked = existing_classification is not None and existing_classification.source == "user"
    session.execute(delete(ActivityLap).where(ActivityLap.activity_id == activity.id))
    session.execute(delete(ActivitySample).where(ActivitySample.activity_id == activity.id))
    session.execute(delete(ActivityWorkoutStep).where(ActivityWorkoutStep.activity_id == activity.id))
    if not user_locked:
        session.execute(delete(WorkoutSegment).where(WorkoutSegment.activity_id == activity.id))

    for lap in parsed["laps"]:
        session.add(
            ActivityLap(
                activity_id=activity.id,
                lap_number=lap["lap_number"],
                distance_meters=lap["distance_meters"],
                duration_seconds=lap["duration_seconds"],
                average_speed_mps=lap["average_speed_mps"],
                average_heart_rate_bpm=lap["average_heart_rate_bpm"],
                max_heart_rate_bpm=lap["max_heart_rate_bpm"],
                average_cadence_spm=lap["average_cadence"],
                start_time_utc=lap["start_time_utc"],
                end_time_utc=lap["end_time_utc"],
                present_fields=lap["present_fields"],
                raw_lap={
                    "elapsed_seconds": lap["elapsed_seconds"],
                    "intensity": lap["intensity"],
                    "lap_trigger": lap["lap_trigger"],
                    "wkt_step_index": lap["wkt_step_index"],
                    "cadence_field": lap["cadence_field"],
                    "ascent_meters": lap["ascent_meters"],
                    "descent_meters": lap["descent_meters"],
                    "average_power_watts": lap.get("average_power_watts"),
                },
            )
        )
    session.bulk_insert_mappings(
        ActivitySample,
        [
            {
                "activity_id": activity.id,
                "sample_time_utc": record["sample_time_utc"],
                "elapsed_seconds": record["elapsed_seconds"],
                "distance_meters": record["distance_meters"],
                "speed_mps": record["speed_mps"],
                "heart_rate_bpm": record["heart_rate_bpm"],
                "cadence_spm": record["cadence"],
                "altitude_meters": record["altitude_meters"],
                "power_watts": record.get("power_watts"),
                "latitude": record["latitude"],
                "longitude": record["longitude"],
                "present_fields": record["present_fields"],
            }
            for record in parsed["records"]
        ],
    )
    for step in parsed["steps"]:
        session.add(
            ActivityWorkoutStep(
                activity_id=activity.id,
                step_index=step["step_index"],
                intensity=step["intensity"],
                duration_seconds=step["duration_seconds"],
                distance_meters=step["distance_meters"],
                target_type=step["target_type"],
                target_low=step["target_low"],
                target_high=step["target_high"],
                notes=step["notes"],
                present_fields=step["present_fields"],
                raw_step=step["raw_step"],
            )
        )

    fit_session = parsed["session"]
    sport = fit_session.get("sport")
    lt2_mps = _lt2_speed(session, activity.athlete_id)
    classified = classify_laps(
        parsed["laps"],
        sport=sport,
        lt2_speed_mps=lt2_mps,
    )
    if (
        activity.start_time_local
        and activity.start_time_local.startswith("2026-11-09")
        and activity.distance_meters
        and abs(activity.distance_meters / 1609.344 - 7.34) < 0.1
    ):
        classified["evidence"]["reference_comparison"] = compare_reference(
            parsed["laps"], classified, fit_session
        )
    if not parsed["workout_steps_found"]:
        classified["evidence"]["workout_steps"] = "The FIT file has no workout_step messages."
    lt2_pace = None if lt2_mps is None else 1609.344 / lt2_mps
    detected = detect_workout(
        parsed["laps"],
        parsed["records"],
        steps=parsed["steps"],
        timer_events=parsed.get("events") or [],
        session=fit_session,
        lt2_pace_seconds_per_mile=lt2_pace,
    )
    detected_class = detected["classification"]
    classified["evidence"]["workout_intelligence"] = {
        "workout_type": detected_class["workout_type"],
        "confidence": detected_class["confidence"],
        "repetitions": detected_class["repetitions"],
        "source": detected_class["source"],
        "evidence": detected_class["evidence"],
        "ambiguous": detected_class["ambiguous"],
    }
    if (
        not user_locked
        and detected_class["workout_type"] != "unknown"
        and detected_class["confidence"] >= 0.7
    ):
        classified["workout_type"] = detected_class["workout_type"]
        classified["confidence"] = detected_class["confidence"]
        classified["uncertainty"] = None if not detected["data_quality"]["limitations"] else detected["data_quality"]["limitations"][0]

    existing = existing_classification
    if user_locked:
        if "reference_comparison" in classified["evidence"]:
            evidence = dict(existing.evidence or {})
            evidence["reference_comparison"] = classified["evidence"]["reference_comparison"]
            existing.evidence = evidence
    else:
        if existing is None:
            existing = WorkoutClassification(
                activity_id=activity.id,
                workout_type=classified["workout_type"],
                confidence=classified["confidence"],
                evidence=classified["evidence"],
                uncertainty=classified["uncertainty"],
                source="rules",
                created_at=now,
            )
            session.add(existing)
        else:
            existing.workout_type = classified["workout_type"]
            existing.confidence = classified["confidence"]
            existing.evidence = classified["evidence"]
            existing.uncertainty = classified["uncertainty"]
            existing.source = "rules"
            existing.created_at = now
        for index, segment in enumerate(classified["segments"]):
            session.add(
                WorkoutSegment(
                    activity_id=activity.id,
                    segment_index=index,
                    kind=segment["kind"],
                    start_lap=segment.get("start_lap"),
                    end_lap=segment.get("end_lap"),
                    confidence=classified["confidence"],
                    evidence={"lap_numbers": segment.get("lap_numbers", [])},
                    source="rules",
                )
            )
    activity.fit_summary = {
        **fit_session,
        "record_count": len(parsed["records"]),
        "parsed_lap_count": len(parsed["laps"]),
        "workout_step_count": len(parsed["steps"]),
        "timer_events": [
            {
                "event": event.get("event"),
                "event_type": event.get("event_type"),
                "timer_trigger": event.get("timer_trigger"),
                "timestamp": event["timestamp"].isoformat() if event.get("timestamp") else None,
            }
            for event in parsed.get("events") or []
        ],
        "power_sample_count": sum(1 for record in parsed["records"] if record.get("power_watts") is not None),
        "start_time_utc": fit_session.get("start_time_utc").isoformat()
        if fit_session.get("start_time_utc")
        else None,
    }
    activity.import_status = "parsed"
    activity.updated_at = now
    if fit_session.get("lap_count") is not None:
        activity.lap_count = int(fit_session["lap_count"])
    session.commit()


def import_one(session: Session, settings: Settings, activity: Activity) -> str:
    if not _FILE_LOCK.acquire(blocking=False):
        return "already_running"
    try:
        return import_activity_file(session, settings, activity)
    finally:
        _FILE_LOCK.release()


def import_activity_file(session: Session, settings: Settings, activity: Activity) -> str:
    gateway = GarminSession(settings)
    try:
        zip_bytes = gateway.download_activity(activity.garmin_activity_id)
    except GarminRequestError as exc:
        if exc.http_status == 404:
            activity.import_status = "file_unavailable"
            activity.updated_at = datetime.now(UTC)
            session.commit()
            return "file_unavailable"
        raise
    if zip_bytes[:2] != b"PK":
        activity.import_status = "parse_failed"
        activity.updated_at = datetime.now(UTC)
        session.commit()
        return "parse_failed"
    archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    fit_name = next((name for name in archive.namelist() if name.lower().endswith(".fit")), None)
    if fit_name is None:
        activity.import_status = "parse_failed"
        activity.updated_at = datetime.now(UTC)
        session.commit()
        return "parse_failed"
    fit_bytes = archive.read(fit_name)
    parsed = parse_fit(fit_bytes)
    store_parsed_activity(session, activity, parsed, zip_bytes, fit_bytes)
    return "parsed"


def start_file_import(*, limit: int | None = None) -> dict:
    if _FILE_LOCK.locked():
        return {"status": "already_running"}
    thread = threading.Thread(
        target=_import_in_background,
        kwargs={"limit": limit},
        name="fit-import",
        daemon=True,
    )
    thread.start()
    return {"status": "started"}


def _import_in_background(*, limit: int | None) -> None:
    from app.config import get_settings
    from app.database import SessionLocal

    session = SessionLocal()
    try:
        import_missing_files(session, get_settings(), limit=limit)
    finally:
        session.close()


def file_import_status(session: Session) -> dict:
    rows = session.execute(
        select(Activity.import_status, Activity.id).order_by(Activity.import_status)
    ).all()
    counts: dict[str, int] = {}
    for status, _activity_id in rows:
        counts[status] = counts.get(status, 0) + 1
    return {"running": _FILE_LOCK.locked(), "counts": counts}


def import_missing_files(session: Session, settings: Settings, *, limit: int | None = None) -> dict:
    if not _FILE_LOCK.acquire(blocking=False):
        return {"status": "already_running"}
    try:
        rows = session.scalars(
            select(Activity)
            .where(Activity.import_status.in_(["summary_only", "parse_failed"]))
            .order_by(Activity.start_time_utc.desc())
        ).all()
        if limit is not None:
            rows = rows[:limit]
        counts = {"parsed": 0, "file_unavailable": 0, "failed": 0}
        for activity in rows:
            try:
                result = import_activity_file(session, settings, activity)
                counts[result] = counts.get(result, 0) + 1
            except GarminRequestError:
                session.rollback()
                counts["failed"] += 1
            except Exception:
                session.rollback()
                activity = session.get(Activity, activity.id)
                if activity is not None:
                    activity.import_status = "parse_failed"
                    activity.updated_at = datetime.now(UTC)
                    session.commit()
                counts["failed"] += 1
        remaining = session.scalar(
            select(Activity.id).where(Activity.import_status == "summary_only").limit(1)
        )
        return {"status": "finished", **counts, "remaining": remaining is not None}
    finally:
        _FILE_LOCK.release()
