"""Constants and property map for the MOVA MeowgicPod litter box integration.

The siid/piid map below is TENTATIVE until confirmed with a probe of a real
device (see tools/mova_probe.py in the repository root). Every property the
device reports but that is not in this map still shows up as a diagnostic
"raw" sensor (disabled by default) so mappings can be identified from the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DOMAIN = "mova_litter_box"

CONF_COUNTRY = "country"
CONF_DID = "did"
CONF_MODEL = "model"
CONF_BIND_DOMAIN = "bind_domain"

DEFAULT_COUNTRY = "eu"
COUNTRIES = ["eu", "us", "sg", "cn"]

UPDATE_INTERVAL_SECONDS = 60

# Models handled by this integration. Extend as probes confirm more.
# MOVA litter box models are expected to look like "mova.litter.*".
SUPPORTED_MODEL_KEYWORDS = ["litter", "meowgic", "lr10", "lb10"]


@dataclass(frozen=True)
class PropertyDef:
    """A device property we know how to interpret."""

    key: str  # entity key / translation key
    siid: int
    piid: int
    # kind: sensor | binary_sensor | switch | select | number
    kind: str = "sensor"
    device_class: str | None = None
    unit: str | None = None
    state_class: str | None = None
    entity_category: str | None = None
    icon: str | None = None
    # For selects / enum sensors: raw value -> option name
    options: dict[Any, str] = field(default_factory=dict)
    # For binary sensors / switches: raw value considered "on"
    on_value: Any = 1
    off_value: Any = 0
    enabled_default: bool = True
    confirmed: bool = False  # flipped to True once verified against a probe
    # Optional value decoder ("schedule" = packed 3-byte day/hour/minute
    # entries as hex).
    decoder: str | None = None

    @property
    def prop_key(self) -> str:
        return f"{self.siid}.{self.piid}"


@dataclass(frozen=True)
class ActionDef:
    """A device action exposed as a button."""

    key: str
    siid: int
    aiid: int
    icon: str | None = None
    params: list[Any] = field(default_factory=list)
    confirmed: bool = False


# --------------------------------------------------------------------------
# Property map for mova.litterbox.q2504w (MeowgicPod LR10 Prime).
# 2.1 is CONFIRMED via the cloud keyDefine JSON published for this model
# (device status translation table). Remaining entries are added as probes
# of real devices confirm them.
# --------------------------------------------------------------------------
# Status enum from the official keyDefine (values 10-16 are all "device
# abnormal" variants in the app).
STATUS_OPTIONS: dict[Any, str] = {
    0: "standby",
    1: "cleaning",
    2: "cleaning_paused",
    3: "emptying",
    4: "emptying_paused",
    5: "leveling",
    6: "leveling_paused",
    7: "canceling_cleaning",
    8: "canceling_emptying",
    9: "canceling_leveling",
    10: "device_abnormal",
    11: "device_abnormal",
    12: "device_abnormal",
    13: "device_abnormal",
    14: "weighing_protection",
    15: "device_abnormal",
    16: "device_abnormal",
    17: "air_purification",
    18: "safety_escape",
}

# Live property grid observed on a real q2504w (probe + watch, 2026-07):
#   1.4 = "1113" (firmware build)      1.5 = serial number
#   2.1 = status enum (confirmed via keyDefine + watch transitions)
#   2.5 = device clock, unix seconds, ticks continuously (confirmed)
#   3.1 = cleaning mode: 0 automatic, 2 manual (confirmed via watch;
#         value 1 unobserved — possibly a scheduled-only mode)
#   3.7 = cleaning schedule, packed hex entries of 3 bytes each:
#         [day bitmask | 0x80 enabled][hour][minute]; FF=every day
#         (confirmed via watch: "FF0B00" every day 11:00, "810A00" Mon 10:00)
#   3.13 = air purification running 0/1 (confirmed via watch)
#   3.14 = deodorizing spray running 0/1 (confirmed via watch)
#   3.6 / 3.20 = "FF00000800" — suspected time windows (enabled, 00:00-08:00),
#         probably DND and air purification schedule; unconfirmed
#   2.2, 2.6, 2.10, rest of 3.x = unmapped; exposed as raw sensors.
#   Correlate more with: tools/mova_probe.py --watch
PROPERTIES: list[PropertyDef] = [
    PropertyDef(
        key="device_status",
        siid=2,
        piid=1,
        kind="sensor",
        device_class="enum",
        icon="mdi:paw",
        options=STATUS_OPTIONS,
        confirmed=True,
    ),
    PropertyDef(
        key="firmware_build",
        siid=1,
        piid=4,
        kind="sensor",
        entity_category="diagnostic",
        icon="mdi:chip",
        confirmed=True,
    ),
    PropertyDef(
        key="serial_number",
        siid=1,
        piid=5,
        kind="sensor",
        entity_category="diagnostic",
        icon="mdi:identifier",
        confirmed=True,
    ),
    PropertyDef(
        key="fault_code",
        siid=2,
        piid=2,
        kind="sensor",
        entity_category="diagnostic",
        icon="mdi:alert-circle-outline",
        confirmed=False,  # exists on device; semantics unverified
    ),
    PropertyDef(
        key="device_time",
        siid=2,
        piid=5,
        kind="sensor",
        device_class="timestamp",
        entity_category="diagnostic",
        enabled_default=False,  # ticks every poll; noisy in the recorder
        confirmed=True,
    ),
    PropertyDef(
        key="cleaning_mode",
        siid=3,
        piid=1,
        kind="select",
        icon="mdi:robot",
        options={0: "automatic", 2: "manual"},
        confirmed=True,
    ),
    PropertyDef(
        key="cleaning_schedule",
        siid=3,
        piid=7,
        kind="sensor",
        entity_category="diagnostic",
        icon="mdi:calendar-clock",
        decoder="schedule",
        confirmed=True,
    ),
    PropertyDef(
        key="air_purification",
        siid=3,
        piid=13,
        kind="binary_sensor",
        device_class="running",
        icon="mdi:air-filter",
        confirmed=True,
    ),
    PropertyDef(
        key="deodorizing",
        siid=3,
        piid=14,
        kind="binary_sensor",
        device_class="running",
        icon="mdi:spray",
        confirmed=True,
    ),
]

# Properties that change constantly without carrying state (filtered from
# watch-mode diff logs and safe to ignore for automations).
NOISY_KEYS = {"2.5"}

ACTIONS: list[ActionDef] = [
    # Filled in after probe: e.g. start_clean, deodorize, level_litter...
]

# The sweep used when the curated map is empty/unconfirmed: every property
# discovered here becomes a raw diagnostic sensor.
DISCOVERY_SIIDS = range(1, 16)
DISCOVERY_PIIDS = range(1, 31)
