"""Coaching analysis guards, context, and the two-step pipeline. No live model calls."""

from datetime import UTC, datetime

from app.coach.analysis import (
    guard_report,
    run_coaching_analysis,
    score_report,
    surrounding_sessions,
    workout_rule,
)


def _context() -> dict:
    return {
        "athlete_profile": {"display_name": "Joey", "primary_race_goal": None, "training_phase": None, "intake": None},
        "current_activity": {
            "metrics": {
                "workout_intelligence": {
                    "classification": {"workout_type": "hill_sprints", "confidence": 0.9},
                    "observed": {
                        "efforts": [
                            {"duration_seconds": 14, "distance_meters": 65, "elevation_change_meters": 8.0},
                            {"duration_seconds": 11, "distance_meters": 56, "elevation_change_meters": 6.8},
                        ]
                    },
                }
            }
        },
        "same_day_activities": [
            {"name": "East Brunswick Running", "distance_meters": 19329.5, "start_time_local": "2026-11-22 15:13:13"}
        ],
        "recent_sessions": [],
    }


def _report(**overrides) -> dict:
    payload = {
        "activity_classification": "Hill Sprints",
        "summary": "Joey ran five short uphill efforts after a separate 12 mile run. The session average pace mixes the sprints with the walks.",
        "execution_analysis": "The efforts lasted about 14 and 11 seconds over 65 and 56 m, climbing about 8 m. Heart rate cannot judge these short reps.",
        "training_impact": "This is a small acceleration stimulus. It does not prove a fitness change.",
        "fitness_indicators": "Two reps cannot establish mile fitness.",
        "what_went_well": ["The climbs were repeated."],
        "where_to_focus": ["Check whether the later reps stayed as fast as the first."],
        "coach_takeaway": "Keep the next speed session as planned and judge sprint quality, not heart rate.",
        "goal_progress": "No race goal is stored.",
        "missing_information": ["No race goal is stored."],
    }
    payload.update(overrides)
    return payload


def test_hill_rule_is_not_the_easy_rule() -> None:
    hills = workout_rule("hill_sprints")
    easy = workout_rule("easy")
    assert "climb" in hills
    assert "average pace" in hills
    assert hills != easy
    assert "mile pace" in easy


def test_same_day_run_is_separate_from_the_sprint_session() -> None:
    anchor = datetime(2026, 11, 22, 21, 40, tzinfo=UTC)
    rows = [
        {
            "id": 1,
            "garmin_activity_id": 10,
            "name": "Long",
            "start_time_local": "2026-11-22 15:13:13",
            "start_time_utc": datetime(2026, 11, 22, 20, 13, tzinfo=UTC),
            "distance_meters": 19329.5,
            "duration_seconds": 5000,
            "average_speed_mps": 3.8,
            "workout_type": "easy",
        },
        {
            "id": 2,
            "garmin_activity_id": 11,
            "name": "Hills",
            "start_time_local": "2026-11-22 16:40:28",
            "start_time_utc": anchor,
            "distance_meters": 604,
            "duration_seconds": 281,
            "average_speed_mps": 2.1,
            "workout_type": "hill_sprints",
        },
    ]
    found = surrounding_sessions(rows, activity_id=2, activity_day="2026-11-22", anchor=anchor)
    assert found["same_day_activities"][0]["distance_meters"] == 19329.5
    assert found["same_day_activities"][0]["garmin_activity_id"] == 10
    assert all(item["garmin_activity_id"] != 11 for item in found["recent_sessions"])


def test_short_rep_heart_rate_claim_is_rejected() -> None:
    report = _report(execution_analysis="Heart rate confirms excellent recovery between the 14 second reps.")
    violations = guard_report(report, _context())
    assert any("Heart rate" in item for item in violations)
    scored = score_report(report, _context())
    assert scored["passed"] is False
    assert scored["scores"]["evidence"] == 1


def test_stored_gps_cannot_be_described_as_missing() -> None:
    context = _context()
    context["current_activity"]["metrics"]["workout_intelligence"]["observed"]["signals"] = {"gps": True}
    report = _report(missing_information=["GPS corroboration is absent for the effort distances."])
    assert any("GPS" in item for item in guard_report(report, context))


def test_same_day_distance_in_kilometers_counts_as_history() -> None:
    report = _report(summary="Joey ran the hills after a separate 19.3 km easy run.")
    scored = score_report(report, _context())
    assert scored["scores"]["history"] == 5


def test_invented_race_time_is_rejected_when_no_goal_is_stored() -> None:
    report = _report(summary="Joey's 2:37 marathon shows he is ready for a 4:20 mile.")
    violations = guard_report(report, _context())
    assert any("race time" in item for item in violations)


def _typed_context(kind: str, efforts: list[dict] | None = None) -> dict:
    context = _context()
    detection = context["current_activity"]["metrics"]["workout_intelligence"]
    detection["classification"] = {"workout_type": kind, "confidence": 0.85}
    detection["observed"]["efforts"] = efforts or []
    context["same_day_activities"] = []
    context["recent_sessions"] = [{"name": "Easy", "distance_meters": 10000, "workout_type": "easy"}]
    return context


def test_other_workout_types_pass_when_the_claims_stay_grounded() -> None:
    cases = {
        "intervals": (
            [{"duration_seconds": 40, "distance_meters": 200}],
            _report(
                activity_classification="Intervals",
                summary="Joey ran 200 m repetitions. The 40 second rep is the session.",
                execution_analysis="The recorded rep covered 200 m in 40 seconds.",
                training_impact="This is interval practice. It does not prove a fitness change.",
                fitness_indicators="One rep cannot establish a change.",
            ),
        ),
        "threshold": (
            [{"duration_seconds": 600, "distance_meters": 2500}],
            _report(
                activity_classification="Threshold",
                summary="Joey held a faster block. No threshold pace is stored.",
                execution_analysis="The faster work lasted about 600 seconds over 2500 m.",
                training_impact="This targets sustained faster running. It does not prove the threshold moved.",
                fitness_indicators="Without a saved threshold, the pace cannot be labeled as threshold.",
            ),
        ),
        "easy": (
            [],
            _report(
                activity_classification="Easy run",
                summary="Joey ran easy. The pace stayed in one band.",
                execution_analysis="Pace and heart rate stayed steady.",
                training_impact="This is ordinary aerobic running.",
                fitness_indicators="An easy run cannot establish a fitness change.",
            ),
        ),
        "progression": (
            [],
            _report(
                activity_classification="Progression",
                summary="Joey ran a progression. Pace rose through the run.",
                execution_analysis="The later miles were faster and the pace stayed controlled.",
                training_impact="The faster finish is the stimulus. It does not prove a fitness change.",
                fitness_indicators="One progression does not establish a fitness change.",
            ),
        ),
        "marathon_pace": (
            [{"duration_seconds": 1200, "distance_meters": 5000}],
            _report(
                activity_classification="Marathon pace",
                summary="Joey practiced a faster segment. No marathon pace is stored.",
                execution_analysis="The faster segment lasted about 1200 seconds over 5000 m.",
                training_impact="This is race-pace practice. It does not prove marathon fitness.",
                fitness_indicators="The segment cannot predict a marathon result.",
            ),
        ),
        "unknown": (
            [],
            _report(
                activity_classification="Unknown",
                summary="Joey's recording does not identify the workout. Pace is available only as a session average.",
                execution_analysis="There are no confirmed repetitions to judge.",
                training_impact="No stimulus can be named from this recording.",
                fitness_indicators="This cannot establish a fitness change.",
                what_went_well=[],
                where_to_focus=["The structure is missing, so the session should not be scored as a quality workout."],
            ),
        ),
    }
    for kind, (efforts, report) in cases.items():
        scored = score_report(report, _typed_context(kind, efforts))
        assert scored["passed"], (kind, scored)


def test_grounded_hill_report_passes_the_rubric() -> None:
    scored = score_report(_report(), _context())
    assert scored["passed"] is True
    assert scored["scores"]["history"] == 5
    assert scored["scores"]["workout_understanding"] == 5


def _assessment() -> dict:
    return {
        "ranked_findings": ["The later reps held their speed."],
        "execution_judgment": "You held the pace after a slower opening rep.",
        "primary_stimulus": "Short uphill acceleration.",
        "future_consideration": "Keep the next session as planned.",
        "adjustment": "continue",
        "material_limitations": ["Heart rate cannot score these short reps."],
        "historical_context": "A separate 12 mile run came earlier the same day.",
    }


def _brief(**overrides) -> dict:
    payload = {
        "workout_analysis": (
            "You ran five hill sprints, and the opening 14 second effort over 65 m was the slow one. "
            "The next efforts settled together, so the session was consistent after that first rep."
        ),
        "training_impact": (
            "These short climbs are acceleration practice after your separate 12 mile run. "
            "They do not prove a fitness change."
        ),
        "coach_takeaway": "Keep the next speed session as planned. Judge the reps by speed, not heart rate.",
        "coaching_assessment": _assessment(),
    }
    payload.update(overrides)
    return payload


def test_brief_report_stays_within_the_three_sections() -> None:
    from app.coach.engine import validate_report

    report = validate_report(_brief())
    assert set(report) == {"workout_analysis", "training_impact", "coach_takeaway", "coaching_assessment"}
    words = len(" ".join(report[key] for key in ("workout_analysis", "training_impact", "coach_takeaway")).split())
    assert 60 <= words <= 180
    scored = score_report(report, _context())
    assert scored["passed"] is True


def test_a_long_brief_is_sent_back_for_a_shorter_draft() -> None:
    report = _brief(workout_analysis="You ran. " * 120)
    assert any("too long" in item or "words" in item for item in guard_report(report, _context()))


def test_pipeline_runs_analyst_then_coach_and_revises_a_bad_draft() -> None:
    calls = []

    def complete(**kwargs):
        calls.append(kwargs["schema_name"])
        if kwargs["schema_name"] == "workout_analyst_notes":
            return {
                "detected_workout": "hill_sprints",
                "confidence_note": "Five efforts were recorded.",
                "primary_stimulus": "Short uphill acceleration.",
                "secondary_stimulus": "None beyond the climbs.",
                "execution": "Reps were 11 to 14 seconds.",
                "rep_notes": ["Reps stayed short."],
                "strengths": ["Climbs repeated."],
                "limitations": ["Heart rate is not usable."],
                "evidence": ["Efforts were under 15 seconds."],
                "uncertainty": ["No saved race goal."],
            }
        if len(calls) == 2:
            return _brief(workout_analysis="Heart rate confirms excellent recovery between your short reps.")
        return _brief()

    class Settings:
        openai_model = "test-model"

    report, trace = run_coaching_analysis(Settings(), _context(), complete)
    assert calls == ["workout_analyst_notes", "workout_coaching_report", "workout_coaching_report"]
    assert "excellent recovery" not in report["workout_analysis"].lower()
    assert trace["analyst"]["detected_workout"] == "hill_sprints"
    assert trace["prompt_version"]
    assert trace["guard_violations"] == []
