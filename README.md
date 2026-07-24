# 🐱 MOVA Litter Box (MeowgicPod) for Home Assistant

<p align="center">
  <img src="https://oss.iot.dreame.tech/pub/pic/000002/ali_dreame/mova.litterbox.q2504w/2aa32a554231fae98adf088fc367841020250512081044.png" alt="MOVA MeowgicPod LR10 Prime" width="360" />
</p>

Custom Home Assistant integration for the **MOVA MeowgicPod LR10 Prime**
(`mova.litterbox.q2504w`) self-cleaning cat litter box. ☁️ It talks to the
MOVA cloud using the same protocol as the MOVAhome mobile app — no local
hacks or firmware changes required.

> 🙏 Protocol knowledge derived from the excellent
> [EvotecIT/homeassistant-dreamelawnmower](https://github.com/EvotecIT/homeassistant-dreamelawnmower)
> project (MOVA is a Dreame brand and shares its IoT cloud).

## ✨ What you get

🛰️ **Status** — live device state (Standby, Cleaning, Emptying, Leveling,
paused/canceling variants, Weighing protection, Safety escape mode...).

📊 **Sensors** — decoded cleaning schedule, DND time windows, firmware
build, serial number, plus raw diagnostic sensors for every property the
cloud reports.

🔔 **Binary sensors** — air purification running, deodorizing spray
active, do-not-disturb state.

🎛️ **Controls** — cleaning mode (automatic/manual), air purification
duration (quick/standard/long-lasting), auto-spray duration, cleaning
delay, and switches for child lock 🔒, key light 💡, key tone 🔊, soft
stool mode, auto-clean DND 😴, air purification options, and auto spray.

🚧 **Coming soon** — cat visit detection, litter level, waste bin state
(reverse engineering in progress), and Clean/Empty/Level buttons.

## 📦 Installation (HACS)

**1️⃣ Add the repository to HACS** — click the button, then install
**MOVA Litter Box (MeowgicPod)** and restart Home Assistant:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=cookiebytespt&repository=homeassistant-mova-litter-box&category=integration)

**2️⃣ Add the integration** — click the button and sign in with your
MOVAhome account (email + password + region), then pick your litter box 🐈:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=mova_litter_box)

<details>
<summary>Manual steps (if the buttons don't work)</summary>

1. HACS → Integrations → ⋮ → *Custom repositories*
2. Add this repository URL, category **Integration**
3. Install **MOVA Litter Box (MeowgicPod)** and restart Home Assistant
4. Settings → Devices & services → *Add integration* → **MOVA Litter Box**
5. Sign in with your MOVAhome account (email + password + region) and pick
   your litter box 🐈

</details>

## 🤖 Device entity (vacuum-style)

The integration also exposes a `vacuum` entity (e.g.
`vacuum.casota_dos_gatos`), so the box gets Home Assistant's **native device
more-info dialog** — the same big status view and control row you know from
robot vacuums. **Play** starts a cleaning cycle (or resumes when paused),
plus **Pause** and **Stop**. Emptying and levelling stay as their own
buttons (and in the card below). Note: HA renders a generic vacuum graphic
in that dialog — the litter-box actions map to Play/Pause/Stop only, since
the native popup's buttons are fixed.

> ⚠️ **Temporary approach.** Mapping the litter box onto the `vacuum` domain
> is a pragmatic way to get a native device dialog today, but it's not a
> perfect fit — the graphic is a vacuum and only Play/Pause/Stop map. We're
> keeping it until there's a cleaner solution (e.g. a dedicated appliance
> entity/card or a custom more-info), at which point this may change or be
> replaced.

## 🖥️ Dashboard card

A companion Lovelace card gives you a compact, vacuum-style control with
one-tap **Clean / Level / Empty** (plus Pause / Resume / Stop and the last
cat visit).

**Install the card resource:**

1. Copy `www/mova-litter-box-card.js` into your Home Assistant
   `config/www/` folder (so it's at `config/www/mova-litter-box-card.js`).
2. Settings → Dashboards → ⋮ → *Resources* → *Add resource*
   - URL: `/local/mova-litter-box-card.js`
   - Type: **JavaScript module**
3. Add the card to a dashboard (replace the entity ids with yours — they're
   based on your device name):

```yaml
type: custom:mova-litter-box-card
status: sensor.casota_dos_gatos_status
clean: button.casota_dos_gatos_start_cleaning
level: button.casota_dos_gatos_level_litter
empty: button.casota_dos_gatos_empty_waste
pause: button.casota_dos_gatos_pause        # optional
resume: button.casota_dos_gatos_resume      # optional
stop: button.casota_dos_gatos_stop          # optional
last_cat: sensor.casota_dos_gatos_last_cat  # optional
last_weight: sensor.casota_dos_gatos_last_cat_weight  # optional
```

<details>
<summary>No custom card? A built-in tile layout works too</summary>

```yaml
type: grid
columns: 3
square: false
cards:
  - type: tile
    entity: button.casota_dos_gatos_start_cleaning
    name: Clean
  - type: tile
    entity: button.casota_dos_gatos_level_litter
    name: Level
  - type: tile
    entity: button.casota_dos_gatos_empty_waste
    name: Empty
```

</details>

## 🗺️ Roadmap

|  | Feature | Status |
|:---:|:---|:---:|
| ☁️ | **MOVA cloud transport** — login, token refresh, device discovery, live property polling, and command channel | ✅ Done |
| ⚙️ | **Config flow** — sign in with your MOVAhome account, pick your device, re-authentication support | ✅ Done |
| 🎛️ | **Core entities** — status, settings switches, mode/duration selects, cleaning delay, decoded schedule and DND windows, diagnostics | ✅ Done |
| ▶️ | **Action buttons & control services** — Start cleaning, Empty waste, Level litter, Pause, Resume, Stop, plus `send_action` / `set_property` / `refresh` | ✅ Done |
| 🐈 | **Cat visits** — last cat weight, last visit time, visit duration, and a 24-hour visit count, from the toilet-event log | ✅ Done |
| 🏷️ | **Name your cats** — configure each cat's name and weight; per-cat "last visit" / "visits (24 h)" sensors and a "Last cat" sensor | ✅ Done |
| 🧴 | **Consumables** — remaining life and reset for the air purification filter, deodorizing liquid, and waste bag | 🔜 Planned |
| 🌀 | **Smoothing setting** — litter-smoothing offset select: centered, or offset left/right by slight / moderate / significant | ✅ Done |
| 🆙 | **Firmware updates** — surface the firmware-upgrade check and trigger as an HA `update` entity | 🔜 Planned |
| ⚖️ | **Weight unit switch** — toggle kg / lb to match the app | 🔜 Planned |
| 🔧 | **Tune remaining properties** — the last unmapped values (`2.2`, `2.6`, `3.2`, `3.12`, `3.21`); litter level and waste bin state | 🧪 Investigating |
| 🤖 | **Device entity** — a `vacuum` entity giving HA's native more-info popup (Play = Clean / Resume, Pause, Stop) | ✅ Done |
| 🖥️ | **Dashboard card** — vacuum-style Lovelace card with Clean / Level / Empty | ✅ Done |
| 📡 | **Push updates** — switch from polling to MQTT for real-time state | 💡 Idea |

Want to help? See below. 👇

## 🔬 Helping with the property map

Run `tools/mova_probe.py` (read-only) to dump your device's properties, or
`tools/mova_probe.py --watch` to log live changes while you use the app —
then open an issue with the output. Every unmapped property also shows up
in Home Assistant as a disabled-by-default "raw property" sensor.

## ⚠️ Disclaimer

Not affiliated with MOVA or Dreame. Use at your own risk.

---

## 🐾 Credits

Built with warmth at [CookieBytes](https://cookiebytes.pt) 🍪 — where the
[four animals run the place](https://cookiebytes.pt/#about).

- 🛠️ Done by **Billy** 🐶 — *Chief Disruption Officer*
- 👀 Reviewed by **Peggy** 🐱 — *Director of Silent Reviews*
- 🧨 Reviewed by **Rocky** 🐱 — *Head of Chaos Engineering*

Field testing by Peggy and Rocky, the primary users of the litter box in
question. Cookie 🐕 supervised from a safe distance.
