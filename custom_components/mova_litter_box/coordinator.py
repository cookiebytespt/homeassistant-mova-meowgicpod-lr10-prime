"""Data update coordinator for the MOVA litter box."""

from __future__ import annotations

import json
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import MovaAuthError, MovaCloudClient, MovaCloudError
from .const import (
    CONF_BIND_DOMAIN,
    CONF_DID,
    CONF_MODEL,
    DISCOVERY_PIIDS,
    DISCOVERY_SIIDS,
    DOMAIN,
    PET_MATCH_TOLERANCE_KG,
    UPDATE_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

# Cat toilet-visit event log (discovered via mova_probe.py --events).
# Event 4.1 history args: piid1 weight (g), piid2 timestamp (unix s),
# piid3 duration (ms), piid5 = 3600 (constant, unknown).
VISIT_EVENT_SIID = 4
VISIT_EVENT_EIID = 1


def parse_visit(record: dict[str, Any]) -> dict[str, Any] | None:
    """Parse one 4.1 event record into a normalised visit dict."""
    raw = record.get("history")
    if not isinstance(raw, str):
        return None
    try:
        args = {a["piid"]: a["value"] for a in json.loads(raw)
                if isinstance(a, dict) and "piid" in a}
    except (ValueError, TypeError):
        return None
    ts = args.get(2)
    if ts is None:
        return None
    weight_g = args.get(1)
    duration_ms = args.get(3)
    return {
        "timestamp": float(ts),
        "weight_kg": round(weight_g / 1000, 2) if weight_g is not None else None,
        "duration_s": round(duration_ms / 1000, 1)
        if duration_ms is not None else None,
    }


class MovaLitterBoxCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the MOVA cloud for cached device properties.

    Data shape: {"properties": {"2.1": value, ...}, "record": {...}}
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: MovaCloudClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}-{entry.data[CONF_DID]}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.config_entry = entry
        self.client = client
        self.did: str = entry.data[CONF_DID]
        self.model: str = entry.data.get(CONF_MODEL, "unknown")
        self.bind_domain: str | None = entry.data.get(CONF_BIND_DOMAIN)
        self._discovery_keys = [
            (siid, piid)
            for siid in DISCOVERY_SIIDS
            for piid in DISCOVERY_PIIDS
        ]
        # Keys confirmed to exist on this device; discovered on first poll.
        self._live_keys: list[tuple[int, int]] | None = None
        self.device_record: dict[str, Any] = {}
        # Configured pets [{name, weight}] for visit attribution.
        from .config_flow import pets_from_options  # noqa: PLC0415

        self.pets = pets_from_options(dict(entry.options))

    def _match_pet(self, weight_kg: float | None) -> str | None:
        """Attribute a visit weight to the nearest configured pet."""
        if weight_kg is None or not self.pets:
            return None
        best = min(self.pets, key=lambda p: abs(p["weight"] - weight_kg))
        if abs(best["weight"] - weight_kg) <= PET_MATCH_TOLERANCE_KG:
            return best["name"]
        return None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.hass.async_add_executor_job(self._fetch)
        except MovaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MovaCloudError as err:
            raise UpdateFailed(str(err)) from err

    def _fetch(self) -> dict[str, Any]:
        # Refresh the device record occasionally for online state / firmware.
        try:
            for record in self.client.get_devices():
                if str(record.get("did")) == str(self.did):
                    self.device_record = record
                    if record.get("bindDomain"):
                        self.bind_domain = record["bindDomain"]
                    break
        except MovaCloudError as err:  # non-fatal; properties still useful
            _LOGGER.debug("Device list refresh failed: %s", err)

        # The MOVA litter box does not populate the cloud property cache
        # (iotstatus/props returns nothing for mova.litterbox.q2504w), so we
        # read live over the app command channel. On the first poll, sweep
        # the whole siid/piid grid once to learn which keys exist; afterwards
        # only poll the confirmed keys.
        if self._live_keys is None:
            properties = self.client.sweep_properties(
                self.did, self.bind_domain, self._discovery_keys
            )
            if properties:
                # Only lock in the key list when the sweep worked; otherwise
                # retry the full discovery on the next poll.
                self._live_keys = [
                    (int(key.split(".")[0]), int(key.split(".")[1]))
                    for key in properties
                ]
            _LOGGER.info(
                "Discovered %d properties on %s: %s",
                len(properties),
                self.model,
                sorted(properties),
            )
        else:
            properties = self.client.sweep_properties(
                self.did, self.bind_domain, self._live_keys, chunk_size=30
            )
        cleaned = {
            key: value
            for key, value in properties.items()
            if value is not None
        }

        visits = self._fetch_visits()
        return {
            "properties": cleaned,
            "record": self.device_record,
            "visits": visits,
        }

    def _fetch_visits(self) -> dict[str, Any]:
        """Fetch and summarise cat toilet-visit events (event 4.1)."""
        try:
            records = self.client.get_event_history(
                self.did, VISIT_EVENT_SIID, VISIT_EVENT_EIID, limit=50
            )
        except MovaCloudError as err:  # non-fatal
            _LOGGER.debug("Visit history fetch failed: %s", err)
            return {}

        parsed = [p for p in (parse_visit(r) for r in records) if p]
        if not parsed:
            return {"count_recent": 0, "pets": {}}
        parsed.sort(key=lambda v: v["timestamp"], reverse=True)
        for visit in parsed:
            visit["pet"] = self._match_pet(visit["weight_kg"])
        latest = parsed[0]
        now = time.time()
        day_ago = now - 86400

        # Per-pet rollup: latest visit time + 24h count for each configured pet.
        pets_summary: dict[str, dict[str, Any]] = {}
        for pet in self.pets:
            name = pet["name"]
            visits = [v for v in parsed if v.get("pet") == name]
            pets_summary[name] = {
                "last_timestamp": visits[0]["timestamp"] if visits else None,
                "count_24h": sum(1 for v in visits if v["timestamp"] >= day_ago),
            }

        return {
            "last_weight_kg": latest["weight_kg"],
            "last_timestamp": latest["timestamp"],
            "last_duration_s": latest["duration_s"],
            "last_pet": latest.get("pet"),
            "count_recent": len(parsed),
            "count_24h": sum(1 for v in parsed if v["timestamp"] >= day_ago),
            "pets": pets_summary,
        }

    # Helpers used by entities -------------------------------------------
    def get_property(self, siid: int, piid: int) -> Any:
        if not self.data:
            return None
        return self.data["properties"].get(f"{siid}.{piid}")

    async def async_set_property(self, siid: int, piid: int, value: Any) -> None:
        await self.hass.async_add_executor_job(
            self.client.set_property,
            self.did,
            self.bind_domain,
            siid,
            piid,
            value,
        )
        await self.async_request_refresh()

    async def async_call_action(
        self, siid: int, aiid: int, params: list[Any] | None = None
    ) -> None:
        await self.hass.async_add_executor_job(
            self.client.call_action,
            self.did,
            self.bind_domain,
            siid,
            aiid,
            params,
        )
        await self.async_request_refresh()

    @property
    def device_online(self) -> bool:
        online = self.device_record.get("online")
        if online is None:
            return True
        if isinstance(online, str):
            return online.lower() in ("true", "1", "online")
        return bool(online)
