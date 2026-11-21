from datetime import UTC, datetime, timedelta

from app.services.brief import validate_brief
from app.services.roster import attention_reasons, training_status


def test_gap_and_missed_plan_are_named():
    reasons = attention_reasons(
        last_activity_at=datetime.now(UTC) - timedelta(days=5),
        now=datetime.now(UTC),
        missed_planned_sessions=1,
        latest_effort=None,
        latest_goal_status=None,
    )
    assert any("3 days" in reason for reason in reasons)
    assert any("confirmed missed" in reason for reason in reasons)
    assert training_status(reasons, has_activities=True, goal_status=None) == "attention"


def test_no_history_is_not_a_missed_workout():
    reasons = attention_reasons(
        last_activity_at=None,
        now=datetime.now(UTC),
        missed_planned_sessions=0,
        latest_effort=None,
        latest_goal_status=None,
    )
    assert reasons == []
    assert training_status(reasons, has_activities=False, goal_status=None) == "no_data"


def test_brief_drops_unknown_athletes():
    report = validate_brief(
        {
            "daily_summary": "One athlete trained.",
            "requires_attention": [
                {"athlete_id": 9, "athlete_name": "Other", "reason": "Not on the roster", "garmin_activity_id": 0}
            ],
            "positive_developments": [],
            "suggested_actions": [
                {"athlete_id": 1, "athlete_name": "Ada", "action": "Ask about the easy run.", "garmin_activity_id": 42}
            ],
        },
        {1},
    )
    assert report["requires_attention"] == []
    assert report["suggested_actions"][0]["athlete_id"] == 1
