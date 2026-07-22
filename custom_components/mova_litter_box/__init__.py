"""The MOVA MeowgicPod litter box integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .api import MovaCloudClient
from .const import CONF_COUNTRY, DEFAULT_COUNTRY
from .coordinator import MovaLitterBoxCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

MovaConfigEntry = ConfigEntry[MovaLitterBoxCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: MovaConfigEntry) -> bool:
    """Set up the litter box from a config entry."""
    client = MovaCloudClient(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_COUNTRY, DEFAULT_COUNTRY),
    )
    coordinator = MovaLitterBoxCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MovaConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await hass.async_add_executor_job(entry.runtime_data.client.close)
    return unload_ok
