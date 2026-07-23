"""Sensors for the MOVA litter box."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MovaConfigEntry
from .const import PROPERTIES, PropertyDef
from .coordinator import MovaLitterBoxCoordinator
from .entity import MovaLitterBoxEntity

_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def decode_schedule(value: Any) -> list[str]:
    """Decode a packed schedule blob into human-readable entries.

    Format (confirmed on q2504w): concatenated 3-byte entries as hex —
    [day bitmask, bit 7 = enabled][hour][minute]. 0xFF = enabled + every day.
    """
    if not isinstance(value, str) or not value:
        return []
    entries: list[str] = []
    try:
        raw = bytes.fromhex(value)
    except ValueError:
        return []
    for offset in range(0, len(raw) - 2, 3):
        mask, hour, minute = raw[offset], raw[offset + 1], raw[offset + 2]
        enabled = bool(mask & 0x80)
        days = [d for i, d in enumerate(_DAYS) if mask & (1 << i)]
        day_text = "Every day" if len(days) == 7 else ",".join(days) or "?"
        entries.append(
            f"{day_text} {hour:02d}:{minute:02d}"
            + ("" if enabled else " (disabled)")
        )
    return entries


def decode_time_window(value: Any) -> str | None:
    """Decode a 5-byte time window: [days|0x80 enabled][sh][sm][eh][em]."""
    if not isinstance(value, str) or not value:
        return None
    try:
        raw = bytes.fromhex(value)
    except ValueError:
        return None
    if len(raw) < 5:
        return None
    mask, sh, sm, eh, em = raw[0], raw[1], raw[2], raw[3], raw[4]
    enabled = bool(mask & 0x80)
    days = [d for i, d in enumerate(_DAYS) if mask & (1 << i)]
    day_text = "Every day" if len(days) == 7 else ",".join(days) or "?"
    return (
        f"{day_text} {sh:02d}:{sm:02d}-{eh:02d}:{em:02d}"
        + ("" if enabled else " (disabled)")
    )


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

    entities.extend(
        MovaVisitSensor(coordinator, spec) for spec in VISIT_SENSORS
    )
    if coordinator.pets:
        entities.append(MovaLastPetSensor(coordinator))
        for pet in coordinator.pets:
            entities.append(MovaPetSensor(coordinator, pet["name"], "last_visit"))
            entities.append(MovaPetSensor(coordinator, pet["name"], "visits_24h"))
    async_add_entities(entities)


# Cat toilet-visit sensors, sourced from coordinator.data["visits"]
# (event 4.1 history). Each spec: key, data-field, device_class, unit, icon.
VISIT_SENSORS: tuple[dict[str, Any], ...] = (
    {
        "key": "last_cat_weight",
        "field": "last_weight_kg",
        "device_class": SensorDeviceClass.WEIGHT,
        "unit": "kg",
        "icon": "mdi:scale-bathroom",
    },
    {
        "key": "last_visit",
        "field": "last_timestamp",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "unit": None,
        "icon": "mdi:cat",
    },
    {
        "key": "last_visit_duration",
        "field": "last_duration_s",
        "device_class": SensorDeviceClass.DURATION,
        "unit": "s",
        "icon": "mdi:timer-sand",
    },
    {
        "key": "visits_24h",
        "field": "count_24h",
        "device_class": None,
        "unit": "visits",
        "icon": "mdi:counter",
    },
)


class MovaVisitSensor(MovaLitterBoxEntity, SensorEntity):
    """A sensor derived from the latest cat toilet-visit event."""

    def __init__(
        self, coordinator: MovaLitterBoxCoordinator, spec: dict[str, Any]
    ) -> None:
        super().__init__(coordinator)
        self._spec = spec
        self._attr_unique_id = f"{coordinator.did}-{spec['key']}"
        self._attr_translation_key = spec["key"]
        self._attr_icon = spec["icon"]
        self._attr_native_unit_of_measurement = spec["unit"]
        if spec["device_class"]:
            self._attr_device_class = spec["device_class"]
        if spec["field"] == "count_24h":
            self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> Any:
        value = (self.coordinator.data or {}).get("visits", {}).get(
            self._spec["field"]
        )
        if value is None:
            return None
        if self._attr_device_class == SensorDeviceClass.TIMESTAMP:
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                return None
        return value


class MovaLastPetSensor(MovaLitterBoxEntity, SensorEntity):
    """Which configured pet used the box most recently (by weight match)."""

    _attr_translation_key = "last_pet"
    _attr_icon = "mdi:cat"

    def __init__(self, coordinator: MovaLitterBoxCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.did}-last_pet"

    @property
    def native_value(self) -> Any:
        return (self.coordinator.data or {}).get("visits", {}).get("last_pet")


class MovaPetSensor(MovaLitterBoxEntity, SensorEntity):
    """Per-pet sensor: last visit time or 24h visit count."""

    def __init__(
        self, coordinator: MovaLitterBoxCoordinator, pet: str, kind: str
    ) -> None:
        super().__init__(coordinator)
        self._pet = pet
        self._kind = kind
        slug = pet.lower().replace(" ", "_")
        self._attr_unique_id = f"{coordinator.did}-pet-{slug}-{kind}"
        if kind == "last_visit":
            self._attr_name = f"{pet} last visit"
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
            self._attr_icon = "mdi:cat"
        else:
            self._attr_name = f"{pet} visits (24 h)"
            self._attr_native_unit_of_measurement = "visits"
            self._attr_state_class = SensorStateClass.TOTAL
            self._attr_icon = "mdi:counter"

    @property
    def native_value(self) -> Any:
        pet_data = (self.coordinator.data or {}).get("visits", {}).get(
            "pets", {}
        ).get(self._pet, {})
        if self._kind == "last_visit":
            ts = pet_data.get("last_timestamp")
            if ts is None:
                return None
            try:
                return datetime.fromtimestamp(float(ts), tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                return None
        return pet_data.get("count_24h", 0)


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
        if self._definition.decoder == "schedule":
            entries = decode_schedule(value)
            return "; ".join(entries)[:255] if entries else "none"
        if self._definition.decoder == "time_window":
            return decode_time_window(value) or "none"
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
        value = self.coordinator.get_property(
            self._definition.siid, self._definition.piid
        )
        if self._definition.decoder == "schedule":
            return {"raw_value": value, "entries": decode_schedule(value)}
        if self._definition.decoder == "time_window":
            return {"raw_value": value}
        if not self._definition.options:
            return None
        return {"raw_value": value}


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
