"""Diagnostics support: dump everything needed to extend the property map."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import MovaConfigEntry

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME, "did", "uid", "mac", "sn", "bindDomain"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MovaConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "model": coordinator.model,
        "device_record": async_redact_data(
            coordinator.device_record or {}, TO_REDACT
        ),
        "properties": (coordinator.data or {}).get("properties", {}),
    }
