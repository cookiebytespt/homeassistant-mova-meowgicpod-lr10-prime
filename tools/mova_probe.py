#!/usr/bin/env python3
"""MOVA cloud probe for the MeowgicPod LR10 Prime (and other MOVA devices).

Read-only: it logs into the MOVA cloud (same API the MOVAhome app uses),
lists your devices, and dumps everything needed to build a Home Assistant
integration:

  * the device list (model ids, firmware, bind domain)
  * per-device cloud info
  * the public "key definition" JSON (property descriptions, if published)
  * a sweep of cached property values (siid/piid grid) via iotstatus/props
  * a live get_properties call over the app command channel (optional)

It never sets a property and never calls an action.

Usage:
    export MOVA_USERNAME="you@example.com"
    export MOVA_PASSWORD="your-password"
    export MOVA_COUNTRY="eu"          # eu / us / cn / sg ... (default eu)
    python3 mova_probe.py

Output: prints a summary and writes mova_probe_output.json next to the
script. Review the JSON before sharing it — it contains your device ids
and cloud region, but no password or tokens.

Requires: python3 + requests  (pip install requests)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time

import requests

# --- MOVA cloud constants (same values the MOVAhome iOS app uses) ---------
API_DOMAIN_SUFFIX = ".iot.mova-tech.com"
API_PORT = "13267"
PASSWORD_SALT = "RAylYC%fmSKp7%Tq"
USER_AGENT = "Mova_Smarthome/1.5.59 (iPhone; iOS 16.0; Scale/3.00)"
BASIC_AUTH = "Basic ZHJlYW1lX2FwcHYxOkFQXmR2QHpAU1FZVnhOODg="
DEFAULT_TENANT = "000002"
CN_RLC = "1c80b3787b2266776bcdc481f37d8fa42ba10a30af81a6df-1"

# Sweep ranges for the property grid probe.
SWEEP_SIIDS = range(1, 16)      # service ids 1..15
SWEEP_PIIDS = range(1, 31)      # property ids 1..30
CHUNK = 60


class MovaCloud:
    def __init__(self, username: str, password: str, country: str) -> None:
        self.username = username
        self.password = password
        self.country = country
        self.session = requests.Session()
        self.token: str | None = None
        self.tenant = DEFAULT_TENANT
        self.request_id = int(time.time()) % 100000

    @property
    def base(self) -> str:
        return f"https://{self.country}{API_DOMAIN_SUFFIX}:{API_PORT}"

    def _headers(self, json_body: bool = False) -> dict[str, str]:
        h = {
            "Accept": "*/*",
            "Accept-Language": "en-US;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": USER_AGENT,
            "Authorization": BASIC_AUTH,
            "Tenant-Id": self.tenant,
            "Content-Type": "application/json" if json_body
            else "application/x-www-form-urlencoded",
        }
        if self.country == "cn":
            h["Dreame-Rlc"] = CN_RLC
        if self.token:
            h["Dreame-Auth"] = self.token
        return h

    def login(self) -> dict:
        hashed = hashlib.md5((self.password + PASSWORD_SALT).encode()).hexdigest()
        body = (
            "platform=IOS&scope=all&grant_type=password"
            f"&username={self.username}&password={hashed}&type=account"
        )
        resp = self.session.post(
            f"{self.base}/dreame-auth/oauth/token",
            headers=self._headers(),
            data=body,
            timeout=15,
        )
        if resp.status_code != 200:
            raise SystemExit(
                f"Login failed (HTTP {resp.status_code}): {resp.text[:400]}\n"
                "Check MOVA_USERNAME / MOVA_PASSWORD / MOVA_COUNTRY "
                "(try eu, us, sg or cn)."
            )
        data = resp.json()
        self.token = data.get("access_token")
        self.tenant = data.get("tenant_id") or self.tenant
        if not self.token:
            raise SystemExit(f"Login returned no access_token: {data}")
        return data

    def api(self, path: str, params: dict | None) -> dict | None:
        resp = self.session.post(
            f"{self.base}/{path}",
            headers=self._headers(json_body=True),
            data=json.dumps(params, separators=(",", ":")) if params is not None else None,
            timeout=20,
        )
        if resp.status_code != 200:
            print(f"  ! {path} -> HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        try:
            return resp.json()
        except ValueError:
            print(f"  ! {path} -> non-JSON response")
            return None

    # ---- endpoints -------------------------------------------------------
    def device_list(self) -> dict | None:
        return self.api(
            "dreame-user-iot/iotuserbind/device/listV2",
            {"current": 1, "size": 50},
        )

    def device_info(self, did: str) -> dict | None:
        return self.api(
            "dreame-user-iot/iotuserbind/device/info",
            {"did": did, "lang": "en"},
        )

    def props_snapshot(self, did: str, keys: list[str]) -> dict | None:
        return self.api(
            "dreame-user-iot/iotstatus/props",
            {"did": str(did), "keys": keys},
        )

    def send_command(self, did: str, bind_domain: str | None, method: str,
                     params) -> dict | None:
        host = ""
        if bind_domain:
            host = f"-{bind_domain.split('.')[0]}"
        self.request_id += 1
        return self.api(
            f"dreame-iot-com{host}/device/sendCommand",
            {
                "did": str(did),
                "id": self.request_id,
                "data": {
                    "did": str(did),
                    "id": self.request_id,
                    "method": method,
                    "params": params,
                },
            },
        )


def watch(cloud: "MovaCloud", did: str, bind_domain: str | None,
          keys: list[str], interval: float = 5.0) -> None:
    """Poll live properties and print every change until Ctrl-C.

    Use this while pressing buttons in the MOVAhome app (start clean,
    empty, deodorize...), while a cat visits, or while adding litter —
    the properties that change tell us what each siid.piid means.
    """
    params = [
        {"did": did, "siid": int(k.split(".")[0]), "piid": int(k.split(".")[1])}
        for k in keys
    ]
    # Known-noisy keys that change every poll without carrying state
    # (2.5 is the device clock).
    noisy = {"2.5"}
    last: dict[str, object] = {}
    print(f"Watching {len(keys)} properties every {interval:.0f}s "
          f"(ignoring noisy: {', '.join(sorted(noisy))}). "
          "Do things in the MOVAhome app now. Ctrl-C to stop.")
    changes_log = []
    try:
        while True:
            now: dict[str, object] = {}
            for i in range(0, len(params), 20):
                try:
                    resp = cloud.send_command(
                        did, bind_domain, "get_properties", params[i:i + 20])
                except Exception as exc:  # noqa: BLE001
                    print(f"  ! chunk failed: {exc}")
                    continue
                result = (resp or {}).get("data", {}).get("result")
                for item in result or []:
                    if isinstance(item, dict) and item.get("code", 0) == 0:
                        now[f"{item.get('siid')}.{item.get('piid')}"] = item.get("value")
            stamp = time.strftime("%H:%M:%S")
            for k in sorted(now, key=lambda x: tuple(int(p) for p in x.split("."))):
                if k in noisy:
                    continue
                if k in last and last[k] != now[k]:
                    line = f"[{stamp}] {k}: {last[k]!r} -> {now[k]!r}"
                    print(line)
                    changes_log.append(line)
            if not last:
                print(f"[{stamp}] baseline captured "
                      f"({len(now)} properties). Waiting for changes ...")
            last.update(now)
            time.sleep(interval)
    except KeyboardInterrupt:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "mova_watch_log.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(changes_log) + "\n")
        print(f"\nStopped. {len(changes_log)} change(s) saved to {path}")
        print("Annotate what you did at each time and share the file back.")


def main() -> None:
    username = os.environ.get("MOVA_USERNAME")
    password = os.environ.get("MOVA_PASSWORD")
    country = os.environ.get("MOVA_COUNTRY", "eu")
    if not username or not password:
        raise SystemExit("Set MOVA_USERNAME and MOVA_PASSWORD env vars first.")

    if "--watch" in sys.argv:
        cloud = MovaCloud(username, password, country)
        print(f"Logging in to {cloud.base} ...")
        cloud.login()
        listing = cloud.device_list()
        records = []
        if listing and isinstance(listing.get("data"), dict):
            page = listing["data"].get("page", listing["data"])
            records = page.get("records", []) or []
        if not records:
            raise SystemExit("No devices found.")
        rec = records[0]
        did = str(rec.get("did"))
        print(f"Watching {rec.get('model')} ({rec.get('customName')})")
        keys = [f"{s}.{p}" for s in SWEEP_SIIDS for p in SWEEP_PIIDS]
        # Narrow to the keys that actually exist (quick pre-sweep).
        existing: list[str] = []
        for i in range(0, len(keys), 20):
            params = [
                {"did": did, "siid": int(k.split(".")[0]),
                 "piid": int(k.split(".")[1])}
                for k in keys[i:i + 20]
            ]
            try:
                resp = cloud.send_command(
                    did, rec.get("bindDomain"), "get_properties", params)
            except Exception:  # noqa: BLE001
                continue
            for item in (resp or {}).get("data", {}).get("result") or []:
                if isinstance(item, dict) and item.get("code", 0) == 0:
                    existing.append(f"{item.get('siid')}.{item.get('piid')}")
        watch(cloud, did, rec.get("bindDomain"), existing)
        return

    out: dict = {"country": country, "probe_version": 2}
    cloud = MovaCloud(username, password, country)

    print(f"Logging in to {cloud.base} ...")
    login = cloud.login()
    out["login"] = {
        "region": login.get("region"),
        "tenant_id": login.get("tenant_id"),
        "uid": login.get("uid"),
        "expires_in": login.get("expires_in"),
    }
    print(f"  OK (region={login.get('region')})")

    print("Fetching device list ...")
    listing = cloud.device_list()
    out["device_list_v2"] = listing
    records = []
    if listing and isinstance(listing.get("data"), dict):
        page = listing["data"].get("page", listing["data"])
        records = page.get("records", []) or []
    print(f"  {len(records)} device(s) found")
    for rec in records:
        print(f"   - model={rec.get('model')} did={rec.get('did')} "
              f"name={rec.get('customName') or rec.get('deviceInfo', {}).get('displayName') if isinstance(rec.get('deviceInfo'), dict) else rec.get('customName')} "
              f"online={rec.get('online')} bindDomain={rec.get('bindDomain')}")

    out["devices"] = {}
    for rec in records:
        did = str(rec.get("did"))
        model = rec.get("model", "?")
        bind_domain = rec.get("bindDomain")
        dev_out: dict = {"model": model, "record": rec}
        print(f"\nProbing device {did} ({model}) ...")

        # 1. device info
        print("  device/info ...")
        info = cloud.device_info(did)
        dev_out["device_info"] = info
        info_data = (info or {}).get("data") or {}
        bind_domain = info_data.get("bindDomain") or bind_domain

        # 2. key definition (public property-description JSON)
        key_define = (info_data.get("keyDefine")
                      or rec.get("keyDefine") or {})
        dev_out["key_define_meta"] = key_define
        url = key_define.get("url") if isinstance(key_define, dict) else None
        if url:
            print(f"  keyDefine JSON: {url}")
            try:
                kd = requests.get(url, timeout=15)
                dev_out["key_definition"] = (
                    kd.json() if kd.status_code == 200 else
                    {"error": f"HTTP {kd.status_code}"}
                )
            except Exception as exc:  # noqa: BLE001
                dev_out["key_definition"] = {"error": str(exc)}
        else:
            print("  (no keyDefine url advertised)")

        # 3. cached property sweep (keep one raw response for debugging)
        print(f"  sweeping cached props siid {SWEEP_SIIDS.start}-{SWEEP_SIIDS.stop - 1}, "
              f"piid {SWEEP_PIIDS.start}-{SWEEP_PIIDS.stop - 1} ...")
        keys = [f"{s}.{p}" for s in SWEEP_SIIDS for p in SWEEP_PIIDS]
        found: dict[str, object] = {}
        for i in range(0, len(keys), CHUNK):
            chunk = keys[i:i + CHUNK]
            resp = cloud.props_snapshot(did, chunk)
            if i == 0:
                dev_out["cached_props_raw_first_chunk"] = resp
            data = (resp or {}).get("data")
            if isinstance(data, dict):
                for k, v in data.items():
                    if v not in (None, ""):
                        found[k] = v
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("value") not in (None, ""):
                        found[item.get("key", f"{item.get('siid')}.{item.get('piid')}")] = item.get("value")
        dev_out["cached_properties"] = dict(sorted(
            found.items(),
            key=lambda kv: tuple(int(x) if x.isdigit() else 0 for x in kv[0].split(".")),
        ))
        print(f"  -> {len(found)} non-empty cached properties")

        # 4. live get_properties sweep over the app command channel
        # (read-only; the device answers per key with a code — code 0 means
        # the property exists). Small chunks, tolerant of per-chunk errors.
        print("  live get_properties sweep over sendCommand "
              "(takes a minute or two) ...")
        live_found: dict[str, object] = {}
        live_errors: list[dict] = []
        live_chunk = 15
        for i in range(0, len(keys), live_chunk):
            chunk = keys[i:i + live_chunk]
            params = [
                {"did": did, "siid": int(k.split(".")[0]),
                 "piid": int(k.split(".")[1])}
                for k in chunk
            ]
            try:
                resp = cloud.send_command(did, bind_domain,
                                          "get_properties", params)
            except Exception as exc:  # noqa: BLE001
                live_errors.append({"chunk_start": chunk[0], "error": str(exc)})
                time.sleep(0.5)
                continue
            if i == 0:
                dev_out["live_props_raw_first_chunk"] = resp
            result = resp.get("data", {}).get("result") if isinstance(resp, dict) else None
            if result is None and isinstance(resp, dict):
                result = resp.get("result") or resp.get("data")
            if isinstance(result, list):
                for item in result:
                    if not isinstance(item, dict):
                        continue
                    code = item.get("code", 0)
                    key = f"{item.get('siid')}.{item.get('piid')}"
                    if code == 0:
                        live_found[key] = item.get("value")
            time.sleep(0.3)
        dev_out["live_properties"] = dict(sorted(
            live_found.items(),
            key=lambda kv: tuple(int(x) if str(x).isdigit() else 0
                                 for x in kv[0].split(".")),
        ))
        dev_out["live_errors"] = live_errors
        print(f"  -> {len(live_found)} live properties exist on the device:")
        for k, v in dev_out["live_properties"].items():
            preview = str(v)
            if len(preview) > 60:
                preview = preview[:57] + "..."
            print(f"     {k} = {preview}")
        out["devices"][did] = dev_out

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "mova_probe_output.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False, sort_keys=False)
    print(f"\nDone. Full output written to: {path}")
    print("Review it, then share the file back in the chat.")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError as exc:
        raise SystemExit(
            f"Could not reach the MOVA cloud: {exc}\n"
            "Check your internet connection, or try another MOVA_COUNTRY "
            "(eu, us, sg, cn)."
        )
