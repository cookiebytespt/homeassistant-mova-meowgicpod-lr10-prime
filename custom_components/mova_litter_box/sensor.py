"""Sensors for the MOVA litter box."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
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

    entities: list[SensorEntity] = [
        MovaPropertySensor(coordinator, definition)
        for definition in PROPERTIES
        if definition.kind == "sensor"
    ]

    # Raw discovery sensors: one per property the cloud reports that is not
    # covered by the curated map. Disabled by default; enable them to help
    # identify what each siid.piid means on your unit.
    known = {d.prop_key for d in PROPERTIES}
    seen: set[str] = set()

    @callback
    def _sync_discovered() -> None:
        new: list[SensorEntity] = []
        for key in (coordinator.data or {}).get("properties", {}):
            if key in known or key in seen:
                continue
            seen.add(key)
            new.append(MovaRawPropertySensor(coordinator, key))
        if new:
            async_add_entities(new)

    _sync_discovered()
    entry.async_on_unload(coordinator.async_add_listener(_sync_discovered))
    async_add_entities(entities)


class MovaPropertySensor(MovaLitterBoxEntity, SensorEntity):
    """A curated, human-named property sensor."""

    def __init__(
        self, coordinator: MovaLitterBoxCoordinator, definition: PropertyDef
    ) -> None:
        super().__init__(coordinator)
        self._definition = definition
        self._attr_unique_id = f"{coordinator.did}-{definition.key}"
        self._attr_translation_key = definition.key
        self._attr_icon = definition.icon
        self._attr_native_unit_of_measurement = definition.unit
        self._attr_entity_registry_enabled_default = (
            definition.enabled_default and definition.confirmed
        )
        if definition.entity_category == "diagnostic":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if definition.device_class == "enum" and definition.options:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = sorted(set(definition.options.values()))
        elif definition.device_class:
            self._attr_device_class = SensorDeviceClass(definition.device_class)
        if definition.state_class:
            self._attr_state_class = definition.state_class

    @property
    def native_value(self) -> Any:
        value = self.coordinator.get_property(
            self._definition.siid, self._definition.piid
        )
        if (
            value is not None
            and self._attr_device_class == SensorDeviceClass.TIMESTAMP
        ):
            try:
                return datetime.fromtimestamp(int(value), tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                return None
        if value is not None and self._definition.options:
            mapped = self._definition.options.get(value)
            if mapped is None and self._attr_device_class == SensorDeviceClass.ENUM:
                # Unknown enum value: don't crash the entity, expose raw in
                # attributes instead.
                return None
            return mapped if mapped is not None else str(value)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._definition.options:
            return None
        return {
            "raw_value": self.coordinator.get_property(
                self._definition.siid, self._definition.piid
            )
        }


class MovaRawPropertySensor(MovaLitterBoxEntity, SensorEntity):
    """Fallback sensor exposing an unmapped raw property."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:code-json"

    def __init__(self, coordinator: MovaLitterBoxCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.did}-raw-{key}"
        self._attr_name = f"Raw property {key}"

    @property
    def native_value(self) -> Any:
        value = (self.coordinator.data or {}).get("properties", {}).get(self._key)
        if isinstance(value, (dict, list)):
            value = str(value)
        if isinstance(value, str) and len(value) > 255:
            value = value[:252] + "..."
        return value
