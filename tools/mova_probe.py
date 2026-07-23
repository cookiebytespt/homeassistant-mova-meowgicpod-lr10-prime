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

The default run and --watch are read-only. The --action mode is the ONE
exception: it sends a single MIOT action after an explicit typed YES
confirmation (used to discover clean/empty/level action IDs on real hardware).

Usage:
    export MOVA_USERNAME="you@example.com"
    export MOVA_PASSWORD="your-password"
    export MOVA_COUNTRY="eu"          # eu / us / cn / sg ... (default eu)
    python3 mova_probe.py                       # read-only full dump
    python3 mova_probe.py --watch               # read-only live diff
    python3 mova_probe.py --action 2 1          # send action siid=2 aiid=1
    python3 mova_probe.py --action 2 1 '[{"piid":1,"value":0}]'  # with params

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
SWEEP_PIIDS = range(1, 41)      # property ids 1..40 (widened for cat/visit props)
CHUNK = 60


class MovaCloud:
    def __init__(self, username: str, password: str, country: str) -> None:
        self.username = username
        self.password = password
        self.country = country
        self.session = requests.Session()
        self.token: str | None = None
        self.tenant = DEFAULT_TENANT
        self.uid: str | None = None
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
        self.uid = data.get("uid") or self.uid
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

    def history(self, did: str, siid: int, sub_iid: int, kind: str = "eiid",
                limit: int = 20, since: int = 0) -> dict | None:
        """Query the device data-history log (events/props/actions).

        `kind` is 'eiid' (events — cat visits etc.), 'piid' or 'aiid'.
        This is how the app retrieves per-visit weight/duration records.
        """
        params = {
            "uid": str(self.uid) if self.uid else "",
            "did": str(did),
            "from": since if since else 1,
            "limit": limit,
            "siid": str(siid),
            kind: str(sub_iid),
            "region": self.country,
            "type": 3,
        }
        return self.api("dreame-user-iot/iotstatus/history", params)

    def user_data(self, did: str, props: str = "") -> dict | None:
        """App-side per-device user data (e.g. cat profiles)."""
        return self.api(
            "dreame-user-iot/iotuserdata/getDeviceData",
            {"did": str(did), "model": props},
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
                result = ((resp or {}).get("data") or {}).get("result")
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


def _first_device(cloud: "MovaCloud") -> dict:
    """Log in and return the first bound device record."""
    print(f"Logging in to {cloud.base} ...")
    cloud.login()
    listing = cloud.device_list()
    records = []
    if listing and isinstance(listing.get("data"), dict):
        page = listing["data"].get("page", listing["data"])
        records = page.get("records", []) or []
    if not records:
        raise SystemExit("No devices found.")
    return records[0]


def _result_code(resp: object) -> object:
    """Return the effective (inner if present) status code of a response."""
    if not isinstance(resp, dict):
        return None
    data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    result = data.get("result")
    if isinstance(result, dict) and "code" in result:
        return result.get("code")
    if isinstance(result, list) and result and isinstance(result[0], dict):
        return result[0].get("code")
    return resp.get("code")


def _interpret(resp: object) -> str:
    """Human-readable interpretation of a sendCommand response."""
    if not isinstance(resp, dict):
        return "no/blank response (HTTP error or device offline)"
    code = resp.get("code")
    data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    inner = None
    result = data.get("result")
    if isinstance(result, dict):
        inner = result.get("code")
    elif isinstance(result, list) and result and isinstance(result[0], dict):
        inner = result[0].get("code")
    eff = inner if inner is not None else code
    meaning = {
        0: "OK — accepted (action exists)",
        -4001: "property not readable",
        -4002: "property not writable",
        -4003: "does not exist (invalid siid/aiid)",
        -4004: "method does not exist",
        -4005: "value/arg error (action likely EXISTS)",
        -4006: "invalid params (action likely EXISTS)",
        80001: "device offline / timed out",
    }.get(eff, "unknown code (action may exist)")
    return f"code={code} result_code={inner} -> {meaning}"


def action_mode(cloud: "MovaCloud", siid: int, aiid: int,
                params: list) -> None:
    """Send ONE MIOT action and poll status 2.1 for ~20s.

    WRITE OPERATION. Prints a safety warning and requires the user to type
    YES before anything is sent. Use only with the device in standby, no cat
    nearby, and one action at a time.
    """
    rec = _first_device(cloud)
    did = str(rec.get("did"))
    bind_domain = rec.get("bindDomain")
    model = rec.get("model")
    name = rec.get("customName")

    # Read the current status (2.1) so we can show the transition.
    def read_status() -> object:
        try:
            resp = cloud.send_command(
                did, bind_domain, "get_properties",
                [{"did": did, "siid": 2, "piid": 1}])
        except Exception as exc:  # noqa: BLE001
            return f"<error: {exc}>"
        for item in ((resp or {}).get("data") or {}).get("result") or []:
            if isinstance(item, dict) and item.get("code", 0) == 0:
                return item.get("value")
        return None

    before = read_status()
    print("\n" + "=" * 68)
    print("  !!  SAFETY WARNING — this SENDS A COMMAND to the device  !!")
    print("=" * 68)
    print(f"  Device : {model} ({name})  did={did}")
    print(f"  Action : siid={siid} aiid={aiid} in={params!r}")
    print(f"  Current status 2.1 = {before!r}")
    print("-" * 68)
    print("  Before continuing, make sure:")
    print("    * the litter box is in STANDBY (2.1 == 0),")
    print("    * NO cat is inside or near the device,")
    print("    * you are testing ONE action at a time.")
    print("  An unknown action can start a clean/empty/level cycle or move")
    print("  the drum. Stop the cycle from the MOVAhome app if needed.")
    print("=" * 68)
    answer = input("Type YES (uppercase) to send this action, anything else to abort: ")
    if answer.strip() != "YES":
        print("Aborted. Nothing was sent.")
        return

    print(f"\nSending action siid={siid} aiid={aiid} ...")
    try:
        resp = cloud.send_command(
            did, bind_domain, "action",
            {"did": did, "siid": siid, "aiid": aiid, "in": params})
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Action send failed: {exc}")
    print(f"  raw response: {json.dumps(resp, ensure_ascii=False)}")
    print(f"  interpreted : {_interpret(resp)}")

    print("\nPolling status 2.1 for ~20s (Ctrl-C to stop early) ...")
    last = before
    print(f"  t=0s   2.1 = {before!r}")
    try:
        for elapsed in range(2, 22, 2):
            time.sleep(2)
            now = read_status()
            marker = "  <-- changed" if now != last else ""
            print(f"  t={elapsed:<2}s  2.1 = {now!r}{marker}")
            last = now
    except KeyboardInterrupt:
        print("\nStopped polling.")
    print(f"\nDone. 2.1 went {before!r} -> {last!r}. "
          "Note the transition to confirm what this action does.")


def scan_actions_mode(cloud: "MovaCloud", siid_lo: int, siid_hi: int,
                      aiid_lo: int, aiid_hi: int) -> None:
    """Sweep a range of (siid, aiid) actions and report which ones exist.

    WRITE OPERATION. For each candidate it sends an empty-arg action and
    records the response code, so actions that DON'T exist (error code) are
    told apart from ones that DO (code 0). If status 2.1 changes, a real
    cycle likely started, so the sweep STOPS immediately and reports it.
    Run only in standby, no cat nearby.
    """
    rec = _first_device(cloud)
    did = str(rec.get("did"))
    bind_domain = rec.get("bindDomain")

    def status() -> object:
        resp = cloud.send_command(did, bind_domain, "get_properties",
                                  [{"did": did, "siid": 2, "piid": 1}])
        for item in ((resp or {}).get("data") or {}).get("result") or []:
            if isinstance(item, dict) and item.get("code", 0) == 0:
                return item.get("value")
        return None

    baseline = status()
    combos = [(s, a) for s in range(siid_lo, siid_hi + 1)
              for a in range(aiid_lo, aiid_hi + 1)]
    print("\n" + "=" * 68)
    print("  !!  SAFETY WARNING — this SENDS COMMANDS to the device  !!")
    print("=" * 68)
    print(f"  Device : {rec.get('model')} ({rec.get('customName')}) did={did}")
    print(f"  Sweep  : siid {siid_lo}-{siid_hi} x aiid {aiid_lo}-{aiid_hi} "
          f"= {len(combos)} actions (empty args)")
    print(f"  Status : 2.1 = {baseline!r} (must be 0 / standby)")
    print("  Ensure NO cat is near the box. The sweep stops the moment 2.1")
    print("  changes so at most ONE cycle can start.")
    print("=" * 68)
    if input("Type YES to sweep: ").strip() != "YES":
        print("Aborted. Nothing was sent.")
        return

    exists: list[str] = []
    for siid, aiid in combos:
        resp = cloud.send_command(
            did, bind_domain, "action",
            {"did": did, "siid": siid, "aiid": aiid, "in": []})
        info = _interpret(resp)
        # An action "exists" if the device didn't report it missing.
        # -4003 (no such siid/aiid) and -4004 (no such method) mean absent;
        # anything else (0 accepted, -4005/-4006 arg errors) means present.
        rc = _result_code(resp)
        ok = rc not in (-4003, -4004, None)
        flag = "  <== EXISTS" if ok else ""
        if ok:
            exists.append(f"{siid}.{aiid}")
        print(f"  action {siid}.{aiid:<2} : {info}{flag}")
        time.sleep(0.4)
        now = status()
        if now != baseline:
            print(f"\n  ** 2.1 changed {baseline!r} -> {now!r} after "
                  f"action {siid}.{aiid} — a cycle likely STARTED. Stopping. **")
            print(f"  >>> action {siid}.{aiid} is a real command. Note it, "
                  "then stop the cycle from the app. <<<")
            return
    print("\nSweep complete. Actions that returned OK (exist): "
          + (", ".join(exists) if exists else "none"))
    print("None of these started a cycle with empty args — a starting action "
          "may need arguments, or lives outside the swept range.")


def events_mode(cloud: "MovaCloud", since_minutes: int = 240) -> None:
    """Sweep the device event/history log to find cat-visit style records.

    Litter boxes log per-use events (weight, duration, timestamp) rather than
    exposing them as live properties, so `--watch` won't catch a cat visit.
    This queries iotstatus/history across a grid of siid.eiid and prints any
    records found in the last `since_minutes`. Read-only.
    """
    rec = _first_device(cloud)
    did = str(rec.get("did"))
    since = int(time.time()) - since_minutes * 60
    print(f"Querying event history for {rec.get('model')} "
          f"({rec.get('customName')}) since {since_minutes} min ago "
          f"(uid={cloud.uid}) ...")

    out: dict[str, object] = {}
    found_any = False
    for siid in range(1, 9):
        for eiid in range(1, 16):
            resp = cloud.history(did, siid, eiid, kind="eiid",
                                 limit=20, since=since)
            data = resp.get("data") if isinstance(resp, dict) else None
            records = None
            if isinstance(data, dict):
                records = data.get("list") or data.get("records")
            elif isinstance(data, list):
                records = data
            if records:
                found_any = True
                out[f"event {siid}.{eiid}"] = records
                print(f"\n=== event {siid}.{eiid} : {len(records)} record(s) ===")
                for r in records[:5]:
                    print("   " + json.dumps(r, ensure_ascii=False)[:300])
            time.sleep(0.15)

    # Also try the app user-data blob (per-cat profiles live here on some models)
    ud = cloud.user_data(did)
    if isinstance(ud, dict) and ud.get("data"):
        out["user_data"] = ud["data"]
        print("\n=== iotuserdata/getDeviceData ===")
        print("   " + json.dumps(ud["data"], ensure_ascii=False)[:600])

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "mova_events_output.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    if not found_any and "user_data" not in out:
        print("\nNo event records found in that window. Try a larger window, "
              "e.g. --events 1440 (24h), soon after a confirmed cat visit.")
    print(f"\nSaved: {path}. Share it back.")


def _parse_scan_args(argv: list) -> tuple[int, int, int, int]:
    """Parse '--scan-actions [siid_lo siid_hi aiid_lo aiid_hi]'."""
    idx = argv.index("--scan-actions")
    rest = [a for a in argv[idx + 1:] if not a.startswith("-")]
    nums = [int(x) for x in rest[:4]] if rest else []
    if len(nums) == 4:
        return nums[0], nums[1], nums[2], nums[3]
    return 1, 6, 1, 8  # default sweep


def _parse_action_args(argv: list) -> tuple[int, int, list]:
    """Parse '--action SIID AIID [json-params]' from argv."""
    idx = argv.index("--action")
    rest = argv[idx + 1:]
    if len(rest) < 2:
        raise SystemExit(
            "Usage: mova_probe.py --action SIID AIID [JSON-PARAMS]\n"
            "  e.g. mova_probe.py --action 2 1\n"
            "       mova_probe.py --action 2 1 '[{\"piid\":1,\"value\":0}]'")
    try:
        siid = int(rest[0])
        aiid = int(rest[1])
    except ValueError:
        raise SystemExit("SIID and AIID must be integers.")
    params: list = []
    if len(rest) >= 3 and rest[2]:
        try:
            params = json.loads(rest[2])
        except ValueError as exc:
            raise SystemExit(f"Could not parse JSON params: {exc}")
        if not isinstance(params, list):
            raise SystemExit("JSON params must be a list, e.g. [{\"piid\":1,\"value\":0}].")
    return siid, aiid, params


def main() -> None:
    username = os.environ.get("MOVA_USERNAME")
    password = os.environ.get("MOVA_PASSWORD")
    country = os.environ.get("MOVA_COUNTRY", "eu")
    if not username or not password:
        raise SystemExit("Set MOVA_USERNAME and MOVA_PASSWORD env vars first.")

    if "--events" in sys.argv:
        idx = sys.argv.index("--events")
        mins = 240
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit():
            mins = int(sys.argv[idx + 1])
        cloud = MovaCloud(username, password, country)
        events_mode(cloud, mins)
        return

    if "--scan-actions" in sys.argv:
        lo_s, hi_s, lo_a, hi_a = _parse_scan_args(sys.argv)
        cloud = MovaCloud(username, password, country)
        scan_actions_mode(cloud, lo_s, hi_s, lo_a, hi_a)
        return

    if "--action" in sys.argv:
        siid, aiid, params = _parse_action_args(sys.argv)
        cloud = MovaCloud(username, password, country)
        action_mode(cloud, siid, aiid, params)
        return

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
            for item in ((resp or {}).get("data") or {}).get("result") or []:
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
            result = (resp.get("data") or {}).get("result") if isinstance(resp, dict) else None
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
