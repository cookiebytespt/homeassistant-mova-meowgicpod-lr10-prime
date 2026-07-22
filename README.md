# MOVA Litter Box (MeowgicPod) for Home Assistant

Custom Home Assistant integration for the **MOVA MeowgicPod LR10 Prime**
self-cleaning cat litter box (and, potentially, other MOVA litter box
models). It talks to the MOVA cloud using the same protocol as the MOVAhome
mobile app — no local hacks or firmware changes required.

> Protocol knowledge derived from the excellent
> [EvotecIT/homeassistant-dreamelawnmower](https://github.com/EvotecIT/homeassistant-dreamelawnmower)
> project (MOVA is a Dreame brand and shares its IoT cloud).

## Status

Early development. The cloud transport (login, device discovery, property
polling, commands) is implemented; the **property map for the LR10 Prime is
still being confirmed** against real devices. Until then the integration
exposes every property the cloud reports as a disabled-by-default
"raw property" diagnostic sensor, which is how mappings get identified.

## Installation (HACS)

1. HACS → Integrations → ⋮ → *Custom repositories*
2. Add this repository URL, category **Integration**
3. Install **MOVA Litter Box (MeowgicPod)** and restart Home Assistant
4. Settings → Devices & services → *Add integration* → **MOVA Litter Box**
5. Sign in with your MOVAhome account (email + password + region) and pick
   your litter box

## Helping with the property map

Run `tools/mova_probe.py` (read-only) and open an issue with the output, or
enable the raw property sensors on your device page and note which value
changes when you e.g. start a clean cycle or empty the waste bin.

## Disclaimer

Not affiliated with MOVA or Dreame. Use at your own risk.
