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

# Pet (cat) configuration — stored in entry.options. Visits are attributed to
# the configured pet whose weight is closest to the measured visit weight.
CONF_PETS = "pets"
MAX_PETS = 4
PET_MATCH_TOLERANCE_KG = 1.5

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
    # Optional value decoder:
    #   "schedule"    = packed 3-byte [days|0x80 enabled][hour][minute] hex
    #   "time_window" = 5-byte [days|0x80 enabled][sh][sm][eh][em] hex
    decoder: str | None = None
    # For numbers:
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None

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
# Fourth watch session confirmed the whole settings block:
#   2.10 = DND currently enabled (read-only mirror of DND controls)
#   3.4  = soft stool mode 0/1          3.5  = auto-clean DND 0/1
#   3.6  = auto-clean DND time window   3.8  = child lock 0/1
#   3.9  = key light 0/1
#   3.10 = key tone 0/1                 3.11 = clean delay minutes (1/5 seen)
#   3.15 = air purification during cleaning 0/1
#   3.16 = auto spray after cleaning 0/1
#   3.17 = air purification duration: 6 quick / 18 standard / 36 long
#   3.18 = auto spray duration (10 / 30 seen)
#   3.19 = air purification DND 0/1     3.20 = air purification DND window
#   Time windows: 5-byte hex [days|0x80 enabled][sh][sm][eh][em].
#   3.21 = litter-smoothing offset (see SMOOTHING_OPTIONS below).
#   2.2 = status flags bitmask? (seen = 128 while leveling paused, else 0).
#   Still unmapped: 2.6, 3.2, 3.12 (litter level / bin full candidates).
# Litter-smoothing offset (property 3.21). All values confirmed on a real
# device via --watch: 0 centered, 700/2000/3000 = offset left slightly/
# moderately/significantly, -700/-2000/-3000 = the symmetric offset right.
SMOOTHING_OPTIONS: dict[Any, str] = {
    3000: "left_significant",
    2000: "left_moderate",
    700: "left_slight",
    0: "centered",
    -700: "right_slight",
    -2000: "right_moderate",
    -3000: "right_significant",
}

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
    PropertyDef(
        key="dnd_active",
        siid=2,
        piid=10,
        kind="binary_sensor",
        entity_category="diagnostic",
        icon="mdi:sleep",
        confirmed=True,
    ),
    # ---- settings (fourth watch session) --------------------------------
    PropertyDef(
        key="soft_stool_mode",
        siid=3,
        piid=4,
        kind="switch",
        entity_category="config",
        icon="mdi:emoticon-poop",
        confirmed=True,
    ),
    PropertyDef(
        key="smoothing_offset",
        siid=3,
        piid=21,
        kind="select",
        entity_category="config",
        icon="mdi:arrow-left-right",
        # Litter-smoothing offset (app: "smoothing setting"). All 7 values
        # confirmed via watch (0, ±700/±2000/±3000).
        options=SMOOTHING_OPTIONS,
        confirmed=True,
    ),
    PropertyDef(
        key="auto_clean_dnd",
        siid=3,
        piid=5,
        kind="switch",
        entity_category="config",
        icon="mdi:sleep",
        confirmed=True,
    ),
    PropertyDef(
        key="auto_clean_dnd_window",
        siid=3,
        piid=6,
        kind="sensor",
        entity_category="diagnostic",
        icon="mdi:clock-outline",
        decoder="time_window",
        confirmed=True,
    ),
    PropertyDef(
        key="child_lock",
        siid=3,
        piid=8,
        kind="switch",
        entity_category="config",
        icon="mdi:lock",
        confirmed=True,
    ),
    PropertyDef(
        key="key_light",
        siid=3,
        piid=9,
        kind="switch",
        entity_category="config",
        icon="mdi:lightbulb-on-outline",
        confirmed=True,
    ),
    PropertyDef(
        key="key_tone",
        siid=3,
        piid=10,
        kind="switch",
        entity_category="config",
        icon="mdi:volume-high",
        confirmed=True,
    ),
    PropertyDef(
        key="cleaning_delay",
        siid=3,
        piid=11,
        kind="number",
        entity_category="config",
        icon="mdi:timer-outline",
        unit="min",
        min_value=1,
        max_value=30,  # bounds unverified; 1 and 5 observed
        step=1,
        confirmed=True,
    ),
    PropertyDef(
        key="air_purification_in_cleaning",
        siid=3,
        piid=15,
        kind="switch",
        entity_category="config",
        icon="mdi:air-filter",
        confirmed=True,
    ),
    PropertyDef(
        key="auto_spray",
        siid=3,
        piid=16,
        kind="switch",
        entity_category="config",
        icon="mdi:spray",
        confirmed=True,
    ),
    PropertyDef(
        key="air_purification_duration",
        siid=3,
        piid=17,
        kind="select",
        entity_category="config",
        icon="mdi:air-filter",
        options={6: "quick", 18: "standard", 36: "long_lasting"},
        confirmed=True,
    ),
    PropertyDef(
        key="auto_spray_duration",
        siid=3,
        piid=18,
        kind="select",
        entity_category="config",
        icon="mdi:spray",
        options={10: "short", 30: "long"},  # 10 and 30 observed
        confirmed=True,
    ),
    PropertyDef(
        key="air_purification_dnd",
        siid=3,
        piid=19,
        kind="switch",
        entity_category="config",
        icon="mdi:sleep",
        confirmed=True,
    ),
    PropertyDef(
        key="air_purification_dnd_window",
        siid=3,
        piid=20,
        kind="sensor",
        entity_category="diagnostic",
        icon="mdi:clock-outline",
        decoder="time_window",
        confirmed=True,
    ),
]

# Properties that change constantly without carrying state (filtered from
# watch-mode diff logs and safe to ignore for automations).
NOISY_KEYS = {"2.5"}

# --------------------------------------------------------------------------
# Action map for mova.litterbox.q2504w.
#
# Actions live on SERVICE 3 (discovered via tools/mova_probe.py --scan-actions:
# a sweep of siid 1-6 x aiid 1-8 returned -4003 "does not exist" for every
# candidate on services 1 and 2, and action 3.1 returned code 0 and moved
# status 2.1 from 0 -> 1, i.e. it started a cleaning cycle). Start actions take
# no arguments (empty `in`).
#
# ALL CONFIRMED on a real q2504w via tools/mova_probe.py --action, by the
# observed 2.1 transition (start actions take empty `in`):
#   3.1 start cleaning  (2.1 -> 1)
#   3.2 start emptying  (2.1 -> 3)
#   3.3 start leveling  (2.1 -> 5)
#   3.4 stop / cancel   (2.1 -> 7/8/9 canceling -> 0 standby)
#   3.5 pause           (2.1 running -> 2/4/6 paused)
#   3.6 resume          (2.1 paused -> 1/3/5 running)
ACTIONS: list[ActionDef] = [
    ActionDef(
        key="start_cleaning",
        siid=3,
        aiid=1,
        icon="mdi:broom",
        confirmed=True,
    ),
    ActionDef(
        key="start_emptying",
        siid=3,
        aiid=2,
        icon="mdi:delete-empty",
        confirmed=True,
    ),
    ActionDef(
        key="start_leveling",
        siid=3,
        aiid=3,
        icon="mdi:dots-horizontal",
        confirmed=True,
    ),
    ActionDef(
        key="pause",
        siid=3,
        aiid=5,
        icon="mdi:pause",
        confirmed=True,
    ),
    ActionDef(
        key="resume",
        siid=3,
        aiid=6,
        icon="mdi:play",
        confirmed=True,
    ),
    ActionDef(
        key="stop",
        siid=3,
        aiid=4,
        icon="mdi:stop",
        confirmed=True,
    ),
]

# The sweep used when the curated map is empty/unconfirmed: every property
# discovered here becomes a raw diagnostic sensor.
DISCOVERY_SIIDS = range(1, 16)
DISCOVERY_PIIDS = range(1, 31)
