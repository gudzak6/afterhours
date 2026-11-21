from app.services.program import PLAN_REQUEST_PROMPT


def test_a_mile_request_is_an_instruction_to_write_the_plan():
    assert "I want a plan for training for the mile" in PLAN_REQUEST_PROMPT
    assert "I want a plan for coach training for the mile" in PLAN_REQUEST_PROMPT
    assert "author a mile plan" in PLAN_REQUEST_PROMPT
