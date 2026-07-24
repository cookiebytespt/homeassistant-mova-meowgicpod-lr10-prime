"""The MOVA MeowgicPod litter box integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .api import MovaCloudClient
from .const import CONF_COUNTRY, DEFAULT_COUNTRY, DOMAIN
from .coordinator import MovaLitterBoxCoordinator
from .services import async_setup_services, async_unload_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.VACUUM,
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
    await async_setup_services(hass)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: MovaConfigEntry) -> None:
    """Reload the entry when options (e.g. pet names) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MovaConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await hass.async_add_executor_job(entry.runtime_data.client.close)
        # Drop the shared services once the last entry has unloaded.
        remaining = [
            other
            for other in hass.config_entries.async_loaded_entries(DOMAIN)
            if other.entry_id != entry.entry_id
        ]
        if not remaining:
            await async_unload_services(hass)
    return unload_ok
