"""Sign an athlete in to Garmin Connect with the email and password they already use.

The password is sent to Garmin once and is not stored. A successful sign-in is
kept as a bearer token. The coach Personal API key is a separate credential.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from datetime import UTC, datetime
from urllib.parse import urlencode

from curl_cffi import requests as cffi_requests

from app.garmin.client import GarminRequestError, ca_bundle

logger = logging.getLogger(__name__)

_MFA_TTL_SECONDS = 10 * 60
_pending_mfa: dict[int, tuple[float, dict]] = {}

_SSO = "https://sso.garmin.com"
_IOS_CLIENT_ID = "GCM_IOS_DARK"
_IOS_SERVICE = "https://mobile.integration.garmin.com/gcm/ios"
_IOS_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
)
_PORTAL_CLIENT_ID = "GarminConnect"
_PORTAL_SERVICE = "https://connect.garmin.com/app"
_DI_TOKEN_URL = "https://diauth.garmin.com/di-oauth2-service/oauth/token"
_DI_GRANT = "https://connectapi.garmin.com/di-oauth2-service/oauth/grant/service_ticket"
_DI_CLIENTS = (
    "GARMIN_CONNECT_MOBILE_ANDROID_DI_2025Q2",
    "GARMIN_CONNECT_MOBILE_ANDROID_DI_2024Q4",
    "GARMIN_CONNECT_MOBILE_ANDROID_DI",
    "GARMIN_CONNECT_MOBILE_IOS_DI",
)
_ACTIVITY_URL = "https://connectapi.garmin.com/activitylist-service/activities/search/activities"

_INVALID = "Garmin did not accept that email and password. If you usually sign in to Garmin with Google or Apple, set a Garmin password first and use that."
_BLOCKED = "Garmin blocked this sign-in check. Wait a minute and try the same email and password again."
_UNAVAILABLE = "Garmin could not be reached. Try again."


class GarminSignInError(RuntimeError):
    """Raised when Garmin rejects the email, password, or verification code."""


class GarminMfaRequired(RuntimeError):
    """Raised when Garmin needs a verification code before the sign-in can finish."""


def sign_in_garmin(athlete_id: int, email: str, password: str, mfa_code: str | None = None) -> str:
    """Return a stored Garmin session. The password is not part of that session."""
    address = email.strip()
    if "@" not in address or len(address) > 320:
        raise GarminSignInError("Enter the email you use for Garmin Connect.")
    if not password or not password.strip():
        raise GarminSignInError("Enter your Garmin Connect password.")
    code = (mfa_code or "").strip()
    if code:
        return _finish_mfa(athlete_id, code)

    blocked = False
    for flow in ("ios", "portal"):
        for impersonate in ("safari_ios", "safari"):
            try:
                return _attempt(athlete_id, address, password, flow, impersonate)
            except GarminMfaRequired:
                raise
            except _InvalidCredentials:
                raise GarminSignInError(_INVALID) from None
            except _Blocked:
                blocked = True
                continue
            except _Unavailable:
                raise GarminSignInError(_UNAVAILABLE) from None
    if blocked:
        raise GarminSignInError(_BLOCKED)
    raise GarminSignInError(_UNAVAILABLE)


def interpret_login_response(status_code: int, body: object) -> str:
    """Classify a Garmin login response without treating every failure as a bad password."""
    if status_code in {429, 403}:
        return "blocked"
    if not isinstance(body, dict):
        return "blocked" if status_code >= 400 else "unknown"
    kind = str((body.get("responseStatus") or {}).get("type") or "")
    if kind == "SUCCESSFUL" and body.get("serviceTicketId"):
        return "ok"
    if kind == "MFA_REQUIRED":
        return "mfa"
    if kind == "INVALID_USERNAME_PASSWORD":
        return "invalid"
    if kind == "CAPTCHA_REQUIRED":
        return "blocked"
    if status_code in {429, 403}:
        return "blocked"
    return "unknown"


class GarminConnectSession:
    """Activity search for one athlete who signed in with email and password."""

    def __init__(self, token: str) -> None:
        try:
            saved = json.loads(token)
        except (ValueError, TypeError):
            raise GarminRequestError("Sign in to Garmin again.", code="garmin_auth_error") from None
        if not isinstance(saved, dict) or not saved.get("access_token"):
            raise GarminRequestError("Sign in to Garmin again.", code="garmin_auth_error")
        self._saved = saved
        expires_at = saved.get("expires_at")
        self.token_expires_at = None if not isinstance(expires_at, int) else datetime.fromtimestamp(expires_at, tz=UTC)

    def dumps(self) -> str:
        return json.dumps(self._saved)

    def search_activities(self, **kwargs):
        self._refresh_if_needed()
        params = {
            "start": kwargs["start"],
            "limit": kwargs["limit"],
            "startDate": kwargs["start_date"],
            "endDate": kwargs["end_date"],
        }
        activity_type = kwargs.get("activity_type")
        if activity_type:
            params["activityType"] = activity_type
        response = _api_get(self._saved["access_token"], params)
        if response.status_code == 401:
            self._refresh()
            response = _api_get(self._saved["access_token"], params)
        if response.status_code == 429:
            raise GarminRequestError("Garmin returned HTTP 429", code="garmin_rate_limited", http_status=429)
        if response.status_code in {401, 403}:
            raise GarminRequestError("Sign in to Garmin again.", code="garmin_unauthorized", http_status=response.status_code)
        if response.status_code >= 400:
            raise GarminRequestError(f"Garmin returned HTTP {response.status_code}", code="garmin_http_error", http_status=response.status_code)
        try:
            return response.json()
        except ValueError:
            raise GarminRequestError("Garmin did not return activities.", code="garmin_client_error") from None

    def _refresh_if_needed(self) -> None:
        expires_at = self._saved.get("expires_at")
        if isinstance(expires_at, int) and expires_at - 60 <= int(time.time()):
            self._refresh()

    def _refresh(self) -> None:
        refresh = self._saved.get("refresh_token")
        client_id = self._saved.get("client_id")
        if not isinstance(refresh, str) or not isinstance(client_id, str):
            raise GarminRequestError("Sign in to Garmin again.", code="garmin_unauthorized", http_status=401)
        response = _token_post(client_id, {"grant_type": "refresh_token", "client_id": client_id, "refresh_token": refresh})
        if response.status_code >= 400:
            raise GarminRequestError("Sign in to Garmin again.", code="garmin_unauthorized", http_status=response.status_code)
        self._saved = _session_from_token(response.json(), client_id)
        self.token_expires_at = datetime.fromtimestamp(self._saved["expires_at"], tz=UTC)


class _InvalidCredentials(Exception):
    pass


class _Blocked(Exception):
    pass


class _Unavailable(Exception):
    pass


def _attempt(athlete_id: int, email: str, password: str, flow: str, impersonate: str) -> str:
    session = cffi_requests.Session(impersonate=impersonate, verify=ca_bundle())
    if flow == "ios":
        page = f"{_SSO}/mobile/sso/en_US/sign-in"
        params = {"clientId": _IOS_CLIENT_ID, "locale": "en-US", "service": _IOS_SERVICE}
        user_agent = _IOS_UA
        login_url = f"{_SSO}/mobile/api/login"
        service_url = _IOS_SERVICE
    else:
        page = f"{_SSO}/portal/sso/en-US/sign-in"
        params = {"clientId": _PORTAL_CLIENT_ID, "locale": "en-US", "service": _PORTAL_SERVICE}
        user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"
        )
        login_url = f"{_SSO}/portal/api/login"
        service_url = _PORTAL_SERVICE
    page_params = {"clientId": params["clientId"], "service": service_url}
    try:
        opened = session.get(
            page,
            params=page_params,
            headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"},
            timeout=30,
        )
    except Exception:
        raise _Unavailable from None
    if opened.status_code in {403, 429}:
        raise _Blocked
    time.sleep(1.5)
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": _SSO,
        "Referer": f"{page}?{urlencode(page_params)}",
    }
    try:
        response = session.post(
            login_url,
            params=params,
            headers=headers,
            json={"username": email, "password": password, "rememberMe": True, "captchaToken": ""},
            timeout=30,
        )
    except Exception:
        raise _Unavailable from None
    body = _json_or_none(response)
    kind = interpret_login_response(response.status_code, body)
    logger.info("Garmin sign-in %s via %s returned %s", flow, impersonate, kind)
    if kind == "invalid":
        raise _InvalidCredentials
    if kind == "blocked":
        raise _Blocked
    if kind == "mfa" and isinstance(body, dict):
        method = str((body.get("customerMfaInfo") or {}).get("mfaLastMethodUsed") or "email")
        _pending_mfa[athlete_id] = (
            time.time(),
            {"session": session, "params": params, "headers": headers, "service_url": service_url, "flow": flow, "method": method},
        )
        raise GarminMfaRequired("Garmin sent a verification code. Enter it to finish signing in.")
    if kind == "ok" and isinstance(body, dict):
        return _exchange(str(body["serviceTicketId"]), service_url)
    raise _Blocked


def _finish_mfa(athlete_id: int, code: str) -> str:
    pending = _pending_mfa.get(athlete_id)
    if pending is None or time.time() - pending[0] > _MFA_TTL_SECONDS:
        _pending_mfa.pop(athlete_id, None)
        raise GarminSignInError("That verification step expired. Sign in again.")
    state = pending[1]
    path = "mobile" if state["flow"] == "ios" else "portal"
    try:
        response = state["session"].post(
            f"{_SSO}/{path}/api/mfa/verifyCode",
            params=state["params"],
            headers=state["headers"],
            json={
                "mfaMethod": state["method"],
                "mfaVerificationCode": code,
                "rememberMyBrowser": True,
                "reconsentList": [],
                "mfaSetup": False,
            },
            timeout=30,
        )
    except Exception:
        raise GarminSignInError(_UNAVAILABLE) from None
    body = _json_or_none(response)
    if not isinstance(body, dict) or not body.get("serviceTicketId"):
        raise GarminSignInError("Garmin did not accept that verification code.")
    _pending_mfa.pop(athlete_id, None)
    return _exchange(str(body["serviceTicketId"]), state["service_url"])


def _exchange(ticket: str, service_url: str) -> str:
    for client_id in _DI_CLIENTS:
        response = _token_post(
            client_id,
            {
                "client_id": client_id,
                "service_ticket": ticket,
                "grant_type": _DI_GRANT,
                "service_url": service_url,
            },
        )
        if response.status_code >= 400:
            continue
        try:
            return json.dumps(_session_from_token(response.json(), client_id))
        except (ValueError, KeyError, TypeError):
            continue
    raise GarminSignInError("Garmin accepted the sign-in, but the activity connection did not finish. Try again.")


def _session_from_token(payload: dict, client_id: str) -> dict:
    access = payload["access_token"]
    refresh = payload.get("refresh_token")
    if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh:
        raise ValueError("token response is incomplete")
    expires_in = payload.get("expires_in")
    expires_at = int(time.time()) + int(expires_in if isinstance(expires_in, int) else 3600)
    return {"access_token": access, "refresh_token": refresh, "client_id": client_id, "expires_at": expires_at}


def _token_post(client_id: str, data: dict):
    encoded = base64.b64encode(f"{client_id}:".encode()).decode()
    return cffi_requests.post(
        _DI_TOKEN_URL,
        impersonate="safari",
        verify=ca_bundle(),
        headers={
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "GCM-Android-5.23",
        },
        data=data,
        timeout=30,
    )


def _api_get(access_token: str, params: dict):
    return cffi_requests.get(
        _ACTIVITY_URL,
        impersonate="safari",
        verify=ca_bundle(),
        params=params,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": "GCM-Android-5.23",
        },
        timeout=30,
    )


def _json_or_none(response) -> object:
    try:
        return response.json()
    except ValueError:
        return None
