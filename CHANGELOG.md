# Changelog

## 0.3.0 — 2026-07-23

Meet the cats. 🐱

### Added

- **Cat visit sensors** — Last cat weight, Last visit (timestamp), Last
  visit duration, and Visits (24 h), decoded from the device's toilet-visit
  event log.
- **Configurable pet names** — name your cats and set each one's typical
  weight in the integration's Options. Visits are attributed to the closest
  weight, adding a **Last cat** sensor plus per-cat **last visit** and
  **visits (24 h)** sensors. Editing pets reloads the entry automatically.

## 0.2.0 — 2026-07-23

Full device control. 🎮🐱

### Added

- **Action buttons** — Start cleaning, Empty waste, Level litter, Pause,
  Resume, and Stop. All six are confirmed against real hardware (they live
  on service 3) and verified by the resulting status transition, so they
  work across every cycle type.
- **Control services** — `mova_litter_box.send_action`,
  `mova_litter_box.set_property`, and `mova_litter_box.refresh` for
  triggering or probing any action/property directly from Home Assistant.

### Changed

- Coordinator now passes its config entry explicitly (HA 2026.8+ ready).

### Fixed

- Probe (`tools/mova_probe.py`) is hardened against `null` data fields in
  cloud responses, and decodes MIoT short error codes; adds `--action` and
  `--scan-actions` discovery modes.

## 0.1.0 — 2026-07-22

First release. 🐱🍪

Cloud integration for the **MOVA MeowgicPod LR10 Prime**
(`mova.litterbox.q2504w`) self-cleaning cat litter box, talking to the MOVA
cloud with the same protocol as the MOVAhome app.

### Added

- **MOVA cloud client** — login with automatic token refresh, device
  discovery, live property polling over the app command channel, and
  set-property / action commands.
- **Config flow** — sign in with your MOVAhome account (email, password,
  region), pick your device, with re-authentication support.
- **Status sensor** — full device state enum (Standby, Cleaning,
  Emptying, Leveling, their paused/canceling variants, Weighing
  protection, Air purification, Safety escape mode, Device abnormal).
- **Binary sensors** — air purification running, deodorizing spray active,
  do-not-disturb active.
- **Switches** — child lock, key light, key tone, soft stool mode,
  auto-clean DND, air purification during cleaning, auto spray after
  cleaning, air purification DND.
- **Selects** — cleaning mode (automatic/manual), air purification
  duration (quick/standard/long-lasting), auto-spray duration.
- **Number** — cleaning delay (minutes).
- **Diagnostic sensors** — firmware build, serial number, decoded cleaning
  schedule and DND time windows, device clock, plus raw fallback sensors
  for every property the cloud reports.
- **Brand icon**, HACS metadata, and hassfest/HACS validation workflows.

### Known limitations / next up

- Cat visit detection, litter level, and waste bin state are not yet
  mapped (reverse engineering in progress).
- No Clean/Empty/Level action buttons yet (action IDs still to be found).
- State is polled every 60s; MQTT push is planned.

See the [roadmap](README.md#-roadmap) for what's next.
