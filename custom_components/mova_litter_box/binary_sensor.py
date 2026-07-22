"""Binary sensors for the MOVA litter box."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.const import EntityCategory
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
        MovaPropertyBinarySensor(coordinator, definition)
        for definition in PROPERTIES
        if definition.kind == "binary_sensor"
    )


class MovaPropertyBinarySensor(MovaLitterBoxEntity, BinarySensorEntity):
    def __init__(
        self, coordinator: MovaLitterBoxCoordinator, definition: PropertyDef
    ) -> None:
        super().__init__(coordinator)
        self._definition = definition
        self._attr_unique_id = f"{coordinator.did}-{definition.key}"
        self._attr_translation_key = definition.key
        self._attr_icon = definition.icon
        self._attr_entity_registry_enabled_default = (
            definition.enabled_default and definition.confirmed
        )
        if definition.entity_category == "diagnostic":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if definition.device_class:
            self._attr_device_class = BinarySensorDeviceClass(
                definition.device_class
            )

    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.get_property(
            self._definition.siid, self._definition.piid
        )
        if value is None:
            return None
        return value == self._definition.on_value or value is True
