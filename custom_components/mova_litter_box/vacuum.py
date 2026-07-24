"""Vacuum-style entity for the MOVA litter box.

Exposes the box as a `vacuum` entity so it gets Home Assistant's native
device more-info dialog (device graphic + status + control row), the same
experience as a robot vacuum. Play = start a cleaning cycle (or resume when
paused), plus Pause and Stop. Emptying and levelling remain separate buttons.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MovaConfigEntry
from .coordinator import MovaLitterBoxCoordinator
from .entity import MovaLitterBoxEntity

# Action IDs on service 3 (all confirmed on real hardware).
ACTION_START_CLEANING = (3, 1)
ACTION_PAUSE = (3, 5)
ACTION_RESUME = (3, 6)
ACTION_STOP = (3, 4)

# Status enum (2.1) -> vacuum activity.
_ACTIVITY = {
    0: VacuumActivity.IDLE,          # standby
    1: VacuumActivity.CLEANING,      # cleaning
    2: VacuumActivity.PAUSED,        # cleaning paused
    3: VacuumActivity.CLEANING,      # emptying
    4: VacuumActivity.PAUSED,        # emptying paused
    5: VacuumActivity.CLEANING,      # leveling
    6: VacuumActivity.PAUSED,        # leveling paused
    7: VacuumActivity.CLEANING,      # canceling cleaning
    8: VacuumActivity.CLEANING,      # canceling emptying
    9: VacuumActivity.CLEANING,      # canceling leveling
    10: VacuumActivity.ERROR,
    11: VacuumActivity.ERROR,
    12: VacuumActivity.ERROR,
    13: VacuumActivity.ERROR,
    14: VacuumActivity.PAUSED,       # weighing protection (temporarily halted)
    15: VacuumActivity.ERROR,
    16: VacuumActivity.ERROR,
    17: VacuumActivity.IDLE,         # air purification (background)
    18: VacuumActivity.ERROR,        # safety escape
}

_PAUSED_STATES = {2, 4, 6, 14}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MovaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([MovaLitterBoxVacuum(entry.runtime_data)])


class MovaLitterBoxVacuum(MovaLitterBoxEntity, StateVacuumEntity):
    """The litter box as a vacuum-style device entity."""

    _attr_name = None  # use the device name as the entity name
    _attr_supported_features = (
        VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.STATE
    )

    def __init__(self, coordinator: MovaLitterBoxCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.did}-vacuum"

    @property
    def activity(self) -> VacuumActivity | None:
        status = self.coordinator.get_property(2, 1)
        if status is None:
            return None
        return _ACTIVITY.get(status, VacuumActivity.IDLE)

    async def async_start(self) -> None:
        """Play: resume if paused, otherwise start a cleaning cycle."""
        status = self.coordinator.get_property(2, 1)
        action = ACTION_RESUME if status in _PAUSED_STATES else ACTION_START_CLEANING
        await self.coordinator.async_call_action(*action)

    async def async_pause(self) -> None:
        await self.coordinator.async_call_action(*ACTION_PAUSE)

    async def async_stop(self, **kwargs: Any) -> None:
        await self.coordinator.async_call_action(*ACTION_STOP)
