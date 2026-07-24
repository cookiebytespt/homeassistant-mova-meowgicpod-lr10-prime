# Proposal: `litter_box` entity platform

*Draft to post as a Discussion in
[home-assistant/architecture](https://github.com/home-assistant/architecture/discussions)
(category: Entity Platform). Written from the experience of building a custom
integration for the MOVA MeowgicPod litter box.*

## Summary

Add a new core entity platform, `litter_box`, for automatic / self-cleaning
cat litter boxes, with a matching more-info dialog and dashboard card in the
frontend. Today these devices are either shoe-horned into the `vacuum`
domain (poor semantic fit) or exposed as a loose pile of `sensor` / `button`
entities with no native device experience.

## Motivation

Smart self-cleaning litter boxes are now a common product category with
several cloud- or locally-connected models, e.g.:

- Whisker **Litter-Robot** (existing community integration)
- **PetKit** Pura series
- **MOVA** MeowgicPod (reference implementation for this proposal)
- Leo's Loo, Petsnowy, Neakasa, etc.

They share a consistent behaviour model that does not match any existing
domain:

- A small set of **maintenance cycles**: clean/scoop, empty the waste
  drawer, and (some models) level/smooth the litter.
- A **status** with running / paused / error states per cycle.
- **Consumable / capacity** data: waste-bin fullness, litter level, filter
  and deodorizer life.
- **Per-visit weighing**: cat weight and visit duration per use, often the
  headline feature users want in HA for automations and pet health.

### Why not `vacuum`?

`vacuum` is the closest existing fit and is what integrations reach for
today, but it is a stretch:

- Its control vocabulary is navigation-centric (return-to-base, locate,
  clean-spot, fan speed, battery, map) — none of which apply.
- It offers a single "start" action, whereas litter boxes have 2–3 distinct
  cycles (clean / empty / level) that deserve first-class controls.
- The native more-info renders a vacuum graphic and vacuum labels, which is
  misleading for a litter box.

`lawn_mower` and `valve` were also considered and are equally poor fits.

## Proposed entity: `LitterBoxEntity`

### State / activity

A `LitterBoxActivity` enum:

- `idle`
- `cleaning`
- `emptying`
- `leveling`
- `paused`
- `error`

(Plus the usual `unavailable` / `unknown`.)

### Supported-feature flags

`LitterBoxEntityFeature`:

- `START_CLEAN`
- `EMPTY`
- `LEVEL`
- `PAUSE`
- `STOP`

Integrations advertise only what the hardware supports (e.g. a box without a
levelling motor omits `LEVEL`).

### Services

- `litter_box.clean`
- `litter_box.empty`
- `litter_box.level`
- `litter_box.pause`
- `litter_box.stop`

Each targets a `litter_box` entity and is gated by the matching feature flag.

### Suggested standard attributes (optional, integration-provided)

- `waste_bin_level` (%) / `waste_bin_full` (bool)
- `litter_level` (%)
- `last_visit_weight` (kg) and `last_visit` (timestamp)
- Consumable life: `filter_life`, `deodorizer_life` (%)

These could also remain separate `sensor` entities; open for discussion (see
below). The core value of the new domain is the **state machine + controls +
native card**, not necessarily standardising every sensor.

## Frontend

- A `more-info-litter_box` dialog: status headline, an appropriate device
  graphic, and a control row for the supported cycles (Clean / Empty /
  Level) plus Pause / Stop.
- A `hui-litter-box-card` for dashboards.

## Alternatives considered

1. **Keep using `vacuum`** (status quo). Works, but semantically wrong and
   confusing in the UI, as described above.
2. **Sensors + buttons only.** No native device experience; every user
   rebuilds their own card.
3. **A broader `pet_appliance` domain** covering feeders, fountains, and
   litter boxes. More general but muddier state model; litter boxes,
   feeders and fountains have little behavioural overlap. A focused
   `litter_box` domain seems cleaner.

## Open questions

- Domain name: `litter_box` vs something broader.
- Whether standard consumable/visit attributes belong on the entity or stay
  as separate `sensor` entities.
- Naming of the "level/smooth litter" action across vendors.

## Reference implementation

A working custom integration for the MOVA MeowgicPod (cloud API) already
implements the full behaviour described here using `sensor` / `button` /
`select` / `switch` entities plus a stopgap `vacuum` entity and a custom
Lovelace card, and can serve as a concrete reference for the state model and
controls:

https://github.com/cookiebytespt/homeassistant-mova-litter-box
