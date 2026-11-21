"""Authenticated calls to the official Garmin Personal API client.

The API key is exchanged for a bearer token. Tokens last 24 hours and there is
no refresh token, so a 401 obtains a new token once and retries the call.
HTTP 429 is retried with backoff. Garmin's Personal API FAQ does not publish a
numeric rate limit, so the client also caps how many activities one sync reads.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import requests
from garmin_personal_api import (
    GarminPersonalApiClient,
    GarminPersonalApiError,
    HttpError,
    PersonalApiAuthenticator,
)

from app.config import Settings
from app.security import redact_secrets

logger = logging.getLogger(__name__)


def ca_bundle() -> str | bool:
    """Return a CA bundle that can verify Garmin on this machine.

    The public certifi bundle is the default. When a local OpenSSL bundle exists,
    prefer it so a trusted network filter certificate is included. Certificate
    verification stays enabled.
    """
    for name in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        value = os.environ.get(name, "").strip()
        if value and Path(value).is_file():
            return value
    brew = Path("/opt/homebrew/etc/ca-certificates/cert.pem")
    if brew.is_file():
        return str(brew)
    try:
        import certifi
    except ImportError:
        return True
    return certifi.where()


def _http_session() -> requests.Session:
    session = requests.Session()
    session.verify = ca_bundle()
    return session


class GarminConfigurationError(RuntimeError):
    """Raised when the server has no Personal API key."""


class GarminRequestError(RuntimeError):
    def __init__(self, message: str, *, code: str, http_status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class GarminSession:
    def __init__(
        self,
        settings: Settings,
        *,
        api_key: str | None = None,
        token_cache_path: Path | None = None,
    ) -> None:
        self.settings = settings
        self.token_expires_at: datetime | None = None
        self._api_key = (api_key or "").strip()
        self._token_cache_path = token_cache_path

    def search_activities(self, **kwargs):
        return self._call("search_activities", **kwargs)

    def download_activity(self, activity_id: int) -> bytes:
        return self._call("download_activity", activity_id=activity_id)

    def _call(self, method_name: str, **kwargs):
        force_refresh = False
        last_error: GarminRequestError | None = None
        for attempt in range(3):
            client, _token = self._open_client(force_refresh=force_refresh)
            try:
                return getattr(client, method_name)(**kwargs)
            except HttpError as exc:
                last_error = self._from_http(exc)
                if exc.status_code == 401 and not force_refresh:
                    logger.info("Garmin rejected the bearer token; requesting a new token")
                    force_refresh = True
                    continue
                if exc.status_code == 429 and attempt < 2:
                    delay = 2 ** (attempt + 1)
                    logger.info("Garmin returned HTTP 429; waiting %s seconds", delay)
                    time.sleep(delay)
                    force_refresh = False
                    continue
                raise last_error from None
            except GarminPersonalApiError as exc:
                raise GarminRequestError(redact_secrets(str(exc)), code="garmin_client_error") from None
            except requests.RequestException as exc:
                raise GarminRequestError(
                    redact_secrets(f"Garmin request failed: {exc.__class__.__name__}"),
                    code="garmin_network_error",
                ) from None
            finally:
                client.close()
        if last_error is not None:
            raise last_error
        raise GarminRequestError("Garmin request failed", code="garmin_request_failed")

    def _open_client(self, *, force_refresh: bool) -> tuple[GarminPersonalApiClient, object]:
        key = self._api_key or self.settings.garmin_personal_api_key.strip()
        if not key:
            if self._api_key == "" and self._token_cache_path is not None:
                raise GarminConfigurationError("No Garmin Personal API key is saved for this athlete.")
            raise GarminConfigurationError(
                "GARMIN_PERSONAL_API_KEY is not set. Create a key at "
                "https://connect.garmin.com/app/settings/personalApiToken and put it in the "
                "repository .env file, then restart the API."
            )
        authenticator = PersonalApiAuthenticator(
            timeout=self.settings.garmin_timeout_seconds,
            bearer_token_cache_file=self._token_cache_path or self.settings.garmin_token_cache_path,
            session=_http_session(),
        )
        try:
            token = authenticator.obtain_token(key, force_refresh=force_refresh)
        except HttpError as exc:
            raise self._from_http(exc) from None
        except GarminPersonalApiError as exc:
            raise GarminRequestError(redact_secrets(str(exc)), code="garmin_auth_error") from None
        except requests.RequestException as exc:
            raise GarminRequestError(
                redact_secrets(f"Garmin authentication failed: {exc.__class__.__name__}"),
                code="garmin_network_error",
            ) from None
        finally:
            authenticator.close()
        self.token_expires_at = datetime.fromtimestamp(token.expires_at, tz=UTC)
        client = GarminPersonalApiClient(
            token.access_token,
            timeout=self.settings.garmin_timeout_seconds,
            session=_http_session(),
        )
        return client, token

    @staticmethod
    def _from_http(exc: HttpError) -> GarminRequestError:
        if exc.status_code in {401, 403}:
            code = "garmin_unauthorized"
        elif exc.status_code == 429:
            code = "garmin_rate_limited"
        else:
            code = "garmin_http_error"
        message = redact_secrets(f"Garmin returned HTTP {exc.status_code}")
        return GarminRequestError(message, code=code, http_status=exc.status_code)
