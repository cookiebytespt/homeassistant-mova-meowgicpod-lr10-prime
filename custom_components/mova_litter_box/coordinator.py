"""Data update coordinator for the MOVA litter box."""

from __future__ import annotations

import logging
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
    UPDATE_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


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
        return {"properties": cleaned, "record": self.device_record}

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
