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

## 🗺️ Roadmap

- ✅ **MOVA cloud transport** — login, token refresh, device discovery,
  live property polling, and command channel.
- ✅ **Config flow** — sign in with your MOVAhome account, pick your device,
  re-authentication support.
- ✅ **Core entities** — status, settings switches, mode/duration selects,
  cleaning delay, decoded schedule and DND windows, diagnostics.
- 🔧 **Tune the remaining device properties** — identify the last few
  unmapped values (`2.2`, `2.6`, `3.2`, `3.12`, `3.21`) and expose them as
  properly named entities.
- 🐈 **Map the cats** *(if possible)* — cat visit detection, per-cat
  weight, and toilet-habit tracking; litter level and waste bin state.
- 🎛️ **Action buttons** — Clean, Empty, and Level (pending discovery of
  the action IDs).
- 📡 **Push updates** — switch from polling to MQTT for real-time state.

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
