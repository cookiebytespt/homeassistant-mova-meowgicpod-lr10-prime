"""MOVA cloud API client for the MeowgicPod litter box.

Speaks the same protocol as the MOVAhome mobile app (shared with Dreame's
cloud). Synchronous `requests` based; call it from an executor. Protocol
knowledge derived from EvotecIT/homeassistant-dreamelawnmower (MIT).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any

import requests

_LOGGER = logging.getLogger(__name__)

API_DOMAIN_SUFFIX = ".iot.mova-tech.com"
API_PORT = "13267"
PASSWORD_SALT = "RAylYC%fmSKp7%Tq"
USER_AGENT = "Mova_Smarthome/1.5.59 (iPhone; iOS 16.0; Scale/3.00)"
BASIC_AUTH = "Basic ZHJlYW1lX2FwcHYxOkFQXmR2QHpAU1FZVnhOODg="
DEFAULT_TENANT = "000002"
CN_RLC = "1c80b3787b2266776bcdc481f37d8fa42ba10a30af81a6df-1"

TIMEOUT = 20


class MovaCloudError(Exception):
    """Base error talking to the MOVA cloud."""


class MovaAuthError(MovaCloudError):
    """Invalid credentials or expired session that cannot be refreshed."""


class MovaCloudClient:
    """Minimal MOVA cloud client (login, device list, properties, commands)."""

    def __init__(self, username: str, password: str, country: str = "eu") -> None:
        self._username = username
        self._password = password
        self._country = country
        self._session = requests.Session()
        self._lock = threading.Lock()
        self._token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires: float = 0
        self._tenant = DEFAULT_TENANT
        self._uid: str | None = None
        self._request_id = int(time.time()) % 100000

    # ------------------------------------------------------------- auth ---
    @property
    def base_url(self) -> str:
        return f"https://{self._country}{API_DOMAIN_SUFFIX}:{API_PORT}"

    def _headers(self, json_body: bool) -> dict[str, str]:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": USER_AGENT,
            "Authorization": BASIC_AUTH,
            "Tenant-Id": self._tenant,
            "Content-Type": "application/json"
            if json_body
            else "application/x-www-form-urlencoded",
        }
        if self._country == "cn":
            headers["Dreame-Rlc"] = CN_RLC
        if self._token:
            headers["Dreame-Auth"] = self._token
        return headers

    def login(self) -> dict[str, Any]:
        """Authenticate (password grant, or refresh token when available)."""
        with self._lock:
            return self._login_locked()

    def _login_locked(self) -> dict[str, Any]:
        if self._refresh_token:
            body = (
                "platform=IOS&scope=all&grant_type=refresh_token"
                f"&refresh_token={self._refresh_token}"
            )
        else:
            hashed = hashlib.md5(
                (self._password + PASSWORD_SALT).encode()
            ).hexdigest()
            body = (
                "platform=IOS&scope=all&grant_type=password"
                f"&username={self._username}&password={hashed}&type=account"
            )
        try:
            resp = self._session.post(
                f"{self.base_url}/dreame-auth/oauth/token",
                headers={**self._headers(False), "Dreame-Auth": ""},
                data=body,
                timeout=TIMEOUT,
            )
        except requests.RequestException as err:
            raise MovaCloudError(f"Cannot reach MOVA cloud: {err}") from err

        if resp.status_code != 200:
            if self._refresh_token:
                # Stale refresh token — retry with password grant once.
                self._refresh_token = None
                return self._login_locked()
            raise MovaAuthError(
                f"Login failed (HTTP {resp.status_code}): {resp.text[:200]}"
            )

        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise MovaAuthError(f"Login returned no access token: {data}")
        self._token = token
        self._refresh_token = data.get("refresh_token")
        self._token_expires = time.time() + float(data.get("expires_in", 3600)) - 120
        self._tenant = data.get("tenant_id") or self._tenant
        self._uid = data.get("uid") or self._uid
        return data

    def _ensure_login(self) -> None:
        if not self._token or time.time() > self._token_expires:
            self.login()

    # -------------------------------------------------------------- http ---
    def _api(self, path: str, params: Any) -> dict[str, Any]:
        self._ensure_login()
        payload = (
            json.dumps(params, separators=(",", ":")) if params is not None else None
        )
        for attempt in (1, 2):
            try:
                resp = self._session.post(
                    f"{self.base_url}/{path}",
                    headers=self._headers(True),
                    data=payload,
                    timeout=TIMEOUT,
                )
            except requests.RequestException as err:
                raise MovaCloudError(f"Request to {path} failed: {err}") from err
            if resp.status_code == 401 and attempt == 1:
                self.login()
                continue
            break
        if resp.status_code != 200:
            raise MovaCloudError(
                f"{path} returned HTTP {resp.status_code}: {resp.text[:200]}"
            )
        try:
            return resp.json()
        except ValueError as err:
            raise MovaCloudError(f"{path} returned invalid JSON") from err

    # --------------------------------------------------------- endpoints ---
    def get_devices(self) -> list[dict[str, Any]]:
        """Return raw device records bound to the account."""
        response = self._api(
            "dreame-user-iot/iotuserbind/device/listV2",
            {"current": 1, "size": 50},
        )
        data = response.get("data") or {}
        page = data.get("page", data) if isinstance(data, dict) else {}
        records = page.get("records") if isinstance(page, dict) else None
        return [rec for rec in (records or []) if isinstance(rec, dict)]

    def get_device_info(self, did: str) -> dict[str, Any]:
        response = self._api(
            "dreame-user-iot/iotuserbind/device/info",
            {"did": did, "lang": "en"},
        )
        return response.get("data") or {}

    def get_cached_properties(
        self, did: str, keys: list[str]
    ) -> dict[str, Any]:
        """Read cloud-cached property values by 'siid.piid' keys."""
        result: dict[str, Any] = {}
        for start in range(0, len(keys), 60):
            chunk = keys[start : start + 60]
            response = self._api(
                "dreame-user-iot/iotstatus/props",
                {"did": str(did), "keys": chunk},
            )
            data = response.get("data")
            if isinstance(data, dict):
                result.update(data)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        key = item.get("key") or (
                            f"{item.get('siid')}.{item.get('piid')}"
                        )
                        result[key] = item.get("value")
        return result

    def get_event_history(
        self,
        did: str,
        siid: int,
        eiid: int,
        limit: int = 20,
        since: int = 1,
    ) -> list[dict[str, Any]]:
        """Fetch event-log records (e.g. cat toilet visits at 4.1).

        Each record has a JSON `history` field of [{piid,value}] arguments
        plus a `createTime` (ms). Returns the raw record list, newest first.
        """
        response = self._api(
            "dreame-user-iot/iotstatus/history",
            {
                "uid": str(self._uid) if self._uid else "",
                "did": str(did),
                "from": since,
                "limit": limit,
                "siid": str(siid),
                "eiid": str(eiid),
                "region": self._country,
                "type": 3,
            },
        )
        data = response.get("data")
        if isinstance(data, dict):
            records = data.get("list") or data.get("records") or []
        elif isinstance(data, list):
            records = data
        else:
            records = []
        return [r for r in records if isinstance(r, dict)]

    # ------------------------------------------------------ command path ---
    def _send_command(
        self,
        did: str,
        bind_domain: str | None,
        method: str,
        params: Any,
    ) -> Any:
        host = f"-{bind_domain.split('.')[0]}" if bind_domain else ""
        self._request_id += 1
        response = self._api(
            f"dreame-iot-com{host}/device/sendCommand",
            {
                "did": str(did),
                "id": self._request_id,
                "data": {
                    "did": str(did),
                    "id": self._request_id,
                    "method": method,
                    "params": params,
                },
            },
        )
        code = response.get("code")
        if code == 80001:
            raise MovaCloudError("Device appears to be offline (code 80001)")
        data = response.get("data")
        if isinstance(data, dict) and "result" in data:
            return data["result"]
        if code == 0 and response.get("success"):
            return None
        raise MovaCloudError(f"sendCommand {method} failed: {response}")

    def get_properties(
        self, did: str, bind_domain: str | None, keys: list[tuple[int, int]]
    ) -> list[dict[str, Any]]:
        """Live get_properties from the device via the app command channel."""
        params = [
            {"did": str(did), "siid": siid, "piid": piid} for siid, piid in keys
        ]
        result = self._send_command(did, bind_domain, "get_properties", params)
        return result if isinstance(result, list) else []

    def sweep_properties(
        self,
        did: str,
        bind_domain: str | None,
        keys: list[tuple[int, int]],
        chunk_size: int = 20,
    ) -> dict[str, Any]:
        """Live-read a set of properties, tolerating per-chunk failures.

        Returns {"siid.piid": value} for every key the device answered with
        code 0 (i.e. the property exists).
        """
        found: dict[str, Any] = {}
        for start in range(0, len(keys), chunk_size):
            chunk = keys[start : start + chunk_size]
            try:
                result = self.get_properties(did, bind_domain, chunk)
            except MovaCloudError as err:
                _LOGGER.debug("Property chunk %s failed: %s", chunk[:1], err)
                continue
            for item in result:
                if isinstance(item, dict) and item.get("code", 0) == 0:
                    found[f"{item.get('siid')}.{item.get('piid')}"] = item.get(
                        "value"
                    )
        return found

    def set_property(
        self,
        did: str,
        bind_domain: str | None,
        siid: int,
        piid: int,
        value: Any,
    ) -> Any:
        return self._send_command(
            did,
            bind_domain,
            "set_properties",
            [{"did": str(did), "siid": siid, "piid": piid, "value": value}],
        )

    def call_action(
        self,
        did: str,
        bind_domain: str | None,
        siid: int,
        aiid: int,
        params: list[Any] | None = None,
    ) -> Any:
        return self._send_command(
            did,
            bind_domain,
            "action",
            {
                "did": str(did),
                "siid": siid,
                "aiid": aiid,
                "in": params or [],
            },
        )

    def close(self) -> None:
        self._session.close()
