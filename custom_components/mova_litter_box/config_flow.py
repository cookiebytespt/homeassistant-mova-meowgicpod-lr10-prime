"""Config flow for the MOVA litter box integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import MovaAuthError, MovaCloudClient, MovaCloudError
from .const import (
    CONF_BIND_DOMAIN,
    CONF_COUNTRY,
    CONF_DID,
    CONF_MODEL,
    CONF_PETS,
    COUNTRIES,
    DEFAULT_COUNTRY,
    DOMAIN,
    MAX_PETS,
    SUPPORTED_MODEL_KEYWORDS,
)

_LOGGER = logging.getLogger(__name__)


def pets_from_options(options: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the configured pets [{name, weight}] from entry options."""
    pets = options.get(CONF_PETS)
    if not isinstance(pets, list):
        return []
    result: list[dict[str, Any]] = []
    for pet in pets:
        if isinstance(pet, dict) and pet.get("name") and pet.get("weight"):
            result.append({"name": str(pet["name"]), "weight": float(pet["weight"])})
    return result

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_COUNTRY, default=DEFAULT_COUNTRY): SelectSelector(
            SelectSelectorConfig(
                options=COUNTRIES, mode=SelectSelectorMode.DROPDOWN
            )
        ),
    }
)


def _looks_like_litter_box(record: dict[str, Any]) -> bool:
    model = str(record.get("model", "")).lower()
    return any(keyword in model for keyword in SUPPORTED_MODEL_KEYWORDS)


def _device_label(record: dict[str, Any]) -> str:
    name = record.get("customName") or record.get("deviceName") or ""
    model = record.get("model", "unknown")
    online = "online" if record.get("online") else "offline"
    label = f"{name} ({model}, {online})" if name else f"{model} ({online})"
    return label


class MovaLitterBoxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the MOVA account + device selection flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, Any] = {}
        self._devices: list[dict[str, Any]] = []

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MovaOptionsFlow:
        return MovaOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = MovaCloudClient(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                user_input[CONF_COUNTRY],
            )
            try:
                devices = await self.hass.async_add_executor_job(
                    self._login_and_list, client
                )
            except MovaAuthError:
                errors["base"] = "invalid_auth"
            except MovaCloudError:
                errors["base"] = "cannot_connect"
            else:
                self._credentials = dict(user_input)
                self._devices = devices
                if not devices:
                    errors["base"] = "no_devices"
                else:
                    return await self.async_step_device()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    def _login_and_list(client: MovaCloudClient) -> list[dict[str, Any]]:
        client.login()
        try:
            return client.get_devices()
        finally:
            client.close()

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        # Prefer litter box models but let the user pick any device: the
        # model catalogue is still being mapped.
        litter = [r for r in self._devices if _looks_like_litter_box(r)]
        candidates = litter or self._devices

        if user_input is not None:
            record = next(
                (
                    r
                    for r in self._devices
                    if str(r.get("did")) == user_input[CONF_DID]
                ),
                None,
            )
            if record is None:
                return self.async_abort(reason="device_not_found")

            did = str(record["did"])
            await self.async_set_unique_id(did)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=record.get("customName")
                or record.get("model", "MOVA litter box"),
                data={
                    **self._credentials,
                    CONF_DID: did,
                    CONF_MODEL: record.get("model"),
                    CONF_BIND_DOMAIN: record.get("bindDomain"),
                },
            )

        options = {
            str(r["did"]): _device_label(r) for r in candidates if r.get("did")
        }
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({vol.Required(CONF_DID): vol.In(options)}),
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            client = MovaCloudClient(
                entry.data[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                entry.data.get(CONF_COUNTRY, DEFAULT_COUNTRY),
            )
            try:
                await self.hass.async_add_executor_job(client.login)
            except MovaAuthError:
                errors["base"] = "invalid_auth"
            except MovaCloudError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
            finally:
                await self.hass.async_add_executor_job(client.close)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )


class MovaOptionsFlow(config_entries.OptionsFlow):
    """Configure pet names and weights for visit attribution."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            pets: list[dict[str, Any]] = []
            for i in range(1, MAX_PETS + 1):
                name = (user_input.get(f"pet_{i}_name") or "").strip()
                weight = user_input.get(f"pet_{i}_weight")
                if name and weight:
                    pets.append({"name": name, "weight": float(weight)})
                elif name and not weight:
                    errors["base"] = "weight_required"
            if not errors:
                return self.async_create_entry(
                    title="", data={CONF_PETS: pets}
                )

        current = pets_from_options(self.config_entry.options)
        schema: dict[Any, Any] = {}
        for i in range(1, MAX_PETS + 1):
            existing = current[i - 1] if i <= len(current) else None
            name_default = existing["name"] if existing else ""
            weight_default = existing["weight"] if existing else None
            schema[vol.Optional(
                f"pet_{i}_name",
                description={"suggested_value": name_default},
            )] = str
            schema[vol.Optional(
                f"pet_{i}_weight",
                description={"suggested_value": weight_default},
            )] = vol.All(vol.Coerce(float), vol.Range(min=0.1, max=25))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            errors=errors,
        )
