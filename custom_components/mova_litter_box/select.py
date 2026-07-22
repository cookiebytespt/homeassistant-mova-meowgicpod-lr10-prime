"""Select entities for the MOVA litter box."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MovaConfigEntry
from .const import PROPERTIES, PropertyDef
from .coordinator import MovaLitterBoxCoordinator
from .entity import MovaLitterBoxEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MovaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        MovaPropertySelect(coordinator, definition)
        for definition in PROPERTIES
        if definition.kind == "select"
    )


class MovaPropertySelect(MovaLitterBoxEntity, SelectEntity):
    """A writable enum property exposed as a select."""

    def __init__(
        self, coordinator: MovaLitterBoxCoordinator, definition: PropertyDef
    ) -> None:
        super().__init__(coordinator)
        self._definition = definition
        self._attr_unique_id = f"{coordinator.did}-{definition.key}"
        self._attr_translation_key = definition.key
        self._attr_icon = definition.icon
        self._attr_options = list(definition.options.values())
        self._reverse = {name: raw for raw, name in definition.options.items()}
        self._attr_entity_registry_enabled_default = definition.confirmed

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.get_property(
            self._definition.siid, self._definition.piid
        )
        return self._definition.options.get(value)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_property(
            self._definition.siid,
            self._definition.piid,
            self._reverse[option],
        )
