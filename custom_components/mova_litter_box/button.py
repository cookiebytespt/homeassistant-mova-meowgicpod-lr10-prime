"""Action buttons for the MOVA litter box."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MovaConfigEntry
from .const import ACTIONS, ActionDef
from .coordinator import MovaLitterBoxCoordinator
from .entity import MovaLitterBoxEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MovaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        MovaActionButton(coordinator, definition) for definition in ACTIONS
    )


class MovaActionButton(MovaLitterBoxEntity, ButtonEntity):
    def __init__(
        self, coordinator: MovaLitterBoxCoordinator, definition: ActionDef
    ) -> None:
        super().__init__(coordinator)
        self._definition = definition
        self._attr_unique_id = f"{coordinator.did}-{definition.key}"
        self._attr_translation_key = definition.key
        self._attr_icon = definition.icon
        self._attr_entity_registry_enabled_default = definition.confirmed

    async def async_press(self) -> None:
        await self.coordinator.async_call_action(
            self._definition.siid,
            self._definition.aiid,
            list(self._definition.params),
        )
