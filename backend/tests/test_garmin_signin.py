"""Garmin sign-in responses are not all bad passwords."""

from app.garmin.connect import interpret_login_response


def test_invalid_password_is_distinct_from_a_blocked_sign_in() -> None:
    invalid = {
        "serviceTicketId": None,
        "responseStatus": {"type": "INVALID_USERNAME_PASSWORD", "message": "generalLoginInvalidUsernameOrPassword"},
    }
    assert interpret_login_response(401, invalid) == "invalid"
    assert interpret_login_response(401, {"responseStatus": {"type": "CAPTCHA_REQUIRED"}}) == "blocked"
    assert interpret_login_response(403, None) == "blocked"
    assert interpret_login_response(429, None) == "blocked"


def test_mfa_and_success_are_recognized() -> None:
    assert interpret_login_response(200, {"responseStatus": {"type": "MFA_REQUIRED"}, "customerMfaInfo": {}}) == "mfa"
    assert interpret_login_response(200, {"responseStatus": {"type": "SUCCESSFUL"}, "serviceTicketId": "ST-1"}) == "ok"
    assert interpret_login_response(200, {"responseStatus": {"type": "SUCCESSFUL"}}) == "unknown"
