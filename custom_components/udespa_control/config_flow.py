"""One settings screen in three sections: entities, numbers, on/off.

Shown at first setup and as the options flow (Configure). Reconfigure shows
the entities section alone, for swapping a device without losing anything.
Entities are stored in entry.data, everything else in entry.options.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .const import (
    ALL_SECTIONS,
    CONF_CIRCULATION,
    CONF_CLEANING_PUMP,
    CONF_FILTER_1,
    CONF_FILTER_2,
    CONF_HEAT_PUMP,
    CONF_HEAT_PUMP_POWER,
    CONF_HEATER,
    CONF_HEATER_POWER,
    CONF_NOTIFY,
    CONF_OUTDOOR,
    CONF_OUTDOOR_ATTRIBUTE,
    CONF_SPA,
    DEFAULTS,
    DOMAIN,
    MODE_KEYS,
    OPT_BACKUP_CHECK,
    OPT_BACKUP_MARGIN,
    OPT_CLEANING_ESTIMATE,
    OPT_CLEANING_MAX,
    OPT_FROST_LIMIT,
    OPT_HEAD_START_TIMEOUT,
    OPT_HEATER_ON_W,
    OPT_HP_OFF_W,
    OPT_HP_ON_W,
    OPT_IN_USE_THRESHOLD,
    OPT_OFF_DELAY,
    OPT_RETRY_MINUTES,
    OPT_WATCHDOG_CIRCULATION,
    OPT_WATCHDOG_INTERVAL,
    PRESET_KEYS,
    SECTION_ENTITIES,
    SECTION_NUMBERS,
    SECTION_SOURCES,
    SECTION_TOGGLES,
    SOURCE_KEYS,
    SUGGESTED_ENTITIES,
    SUGGESTED_SOURCES,
    TOGGLE_KEYS,
    Mode,
)


def _entity(**config: str) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(**config))


def _number(low: float, high: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=low,
            max=high,
            step=step,
            unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


# (key, required, selector)
ENTITY_FIELDS: tuple[tuple[str, bool, Any], ...] = (
    (CONF_SPA, True, _entity(domain="climate")),
    (CONF_CIRCULATION, True, _entity(domain="binary_sensor")),
    (CONF_FILTER_1, False, _entity(domain="binary_sensor")),
    (CONF_FILTER_2, False, _entity(domain="binary_sensor")),
    (CONF_HEAT_PUMP, True, _entity(domain="climate")),
    (CONF_HEAT_PUMP_POWER, True, _entity(domain="sensor", device_class="power")),
    (CONF_HEATER, True, _entity(domain="switch")),
    (CONF_HEATER_POWER, True, _entity(domain="sensor", device_class="power")),
    (CONF_OUTDOOR, True, _entity()),
    (CONF_OUTDOOR_ATTRIBUTE, False, selector.TextSelector()),
    (CONF_CLEANING_PUMP, True, _entity(domain="fan")),
    (CONF_NOTIFY, True, selector.TextSelector()),
)

# Hub data sources: all optional; an empty field means no copy.
SOURCE_FIELDS: tuple[tuple[str, bool, Any], ...] = tuple(
    (key, False, _entity(domain="sensor")) for key in SOURCE_KEYS
)

NUMBER_FIELDS: dict[str, Any] = {
    OPT_OFF_DELAY: _number(0, 120, 1, "s"),
    OPT_HEAD_START_TIMEOUT: _number(10, 300, 1, "s"),
    OPT_HP_ON_W: _number(10, 5000, 10, "W"),
    OPT_HP_OFF_W: _number(10, 5000, 10, "W"),
    OPT_RETRY_MINUTES: _number(1, 15, 1, "min"),
    OPT_BACKUP_MARGIN: _number(0, 5, 0.1, "°C"),
    OPT_BACKUP_CHECK: _number(30, 900, 10, "s"),
    OPT_HEATER_ON_W: _number(10, 10000, 10, "W"),
    OPT_WATCHDOG_INTERVAL: _number(1, 60, 1, "min"),
    OPT_WATCHDOG_CIRCULATION: _number(1, 120, 1, "min"),
    OPT_FROST_LIMIT: _number(-20, 20, 0.5, "°C"),
    OPT_IN_USE_THRESHOLD: _number(0.05, 5, 0.05, "°C"),
    OPT_CLEANING_MAX: _number(1, 120, 1, "min"),
    OPT_CLEANING_ESTIMATE: _number(1, 120, 1, "min"),
}


def _optional_entities_schema(
    fields: tuple[tuple[str, bool, Any], ...], values: Mapping[str, Any]
) -> vol.Schema:
    schema: dict[Any, Any] = {}
    for key, required, field_selector in fields:
        marker = vol.Required if required else vol.Optional
        value = values.get(key)
        description = {"suggested_value": value} if value else None
        schema[marker(key, description=description)] = field_selector
    return vol.Schema(schema)


def _entities_schema(values: Mapping[str, Any]) -> vol.Schema:
    return _optional_entities_schema(ENTITY_FIELDS, values)


def _sources_schema(values: Mapping[str, Any]) -> vol.Schema:
    return _optional_entities_schema(SOURCE_FIELDS, values)


def _numbers_schema(values: Mapping[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(key, default=values.get(key, DEFAULTS[key])): field_selector
        for key, field_selector in NUMBER_FIELDS.items()
    }
    for key in PRESET_KEYS:
        fields[vol.Required(key, default=values.get(key, DEFAULTS[key]))] = (
            selector.TextSelector()
        )
    for key in MODE_KEYS:
        fields[vol.Required(key, default=values.get(key, DEFAULTS[key]))] = (
            selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[mode.value for mode in Mode],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        )
    return vol.Schema(fields)


def _toggles_schema(values: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(key, default=bool(values.get(key, DEFAULTS[key]))): (
                selector.BooleanSelector()
            )
            for key in TOGGLE_KEYS
        }
    )


_BUILDERS = {
    SECTION_ENTITIES: (_entities_schema, False),
    SECTION_NUMBERS: (_numbers_schema, True),
    SECTION_TOGGLES: (_toggles_schema, True),
    SECTION_SOURCES: (_sources_schema, True),
}


def build_schema(values: Mapping[str, Any], sections: Iterable[str]) -> vol.Schema:
    """The settings form, with the given sections, pre-filled from values."""
    return vol.Schema(
        {
            vol.Required(name): section(
                _BUILDERS[name][0](values), {"collapsed": _BUILDERS[name][1]}
            )
            for name in sections
        }
    )


def normalize_notify(value: str) -> str:
    """Accept "notify.x" or "x"; store "x"."""
    return value.strip().removeprefix("notify.")


def flatten(user_input: Mapping[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for name in ALL_SECTIONS:
        flat.update(user_input.get(name, {}))
    return flat


def split(user_input: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """(entry.data, entry.options) from a submitted form."""
    data = {
        key: value
        for name in (SECTION_ENTITIES, SECTION_SOURCES)
        for key, value in user_input.get(name, {}).items()
        if value not in (None, "")
    }
    if CONF_NOTIFY in data:
        data[CONF_NOTIFY] = normalize_notify(data[CONF_NOTIFY])
    options = {
        **user_input.get(SECTION_NUMBERS, {}),
        **user_input.get(SECTION_TOGGLES, {}),
    }
    return data, options


def validate(
    hass: HomeAssistant, user_input: Mapping[str, Any], heat_pump: str
) -> dict[str, str]:
    errors: dict[str, str] = {}
    entities = user_input.get(SECTION_ENTITIES)
    if entities is not None and not hass.services.has_service(
        "notify", normalize_notify(entities[CONF_NOTIFY])
    ):
        errors["base"] = "notify_not_found"
    numbers = user_input.get(SECTION_NUMBERS)
    if numbers is not None:
        if numbers[OPT_HP_OFF_W] >= numbers[OPT_HP_ON_W]:
            errors["base"] = "power_thresholds"
        state = hass.states.get(heat_pump)
        modes = state.attributes.get("preset_modes") if state is not None else None
        if modes and any(numbers[key] not in modes for key in PRESET_KEYS):
            errors["base"] = "unknown_preset"
    return errors


class UdespaControlConfigFlow(ConfigFlow, domain=DOMAIN):
    # Additive changes bump MINOR_VERSION only, so an older release still loads
    # the entry after a rollback.
    VERSION = 1
    MINOR_VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            heat_pump = user_input[SECTION_ENTITIES][CONF_HEAT_PUMP]
            errors = validate(self.hass, user_input, heat_pump)
            if not errors:
                data, options = split(user_input)
                await self.async_set_unique_id(data[CONF_SPA])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Udespa", data=data, options=options)
        values = flatten(user_input) if user_input else {**SUGGESTED_ENTITIES, **SUGGESTED_SOURCES, **DEFAULTS}
        return self.async_show_form(
            step_id="user", data_schema=build_schema(values, ALL_SECTIONS), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Swap devices; entity IDs, options and stored state survive."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            heat_pump = user_input[SECTION_ENTITIES][CONF_HEAT_PUMP]
            errors = validate(self.hass, user_input, heat_pump)
            if not errors:
                data, _ = split(user_input)
                # Reconfigure doesn't show Datakilder; keep what it doesn't show.
                data = {
                    **{k: v for k, v in entry.data.items() if k in SOURCE_KEYS},
                    **data,
                }
                return self.async_update_reload_and_abort(entry, data=data)
        values = flatten(user_input) if user_input else dict(entry.data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=build_schema(values, (SECTION_ENTITIES,)),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> UdespaControlOptionsFlow:
        return UdespaControlOptionsFlow()


class UdespaControlOptionsFlow(OptionsFlowWithReload):
    """The one settings screen. Saving reloads the entry once."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            heat_pump = user_input[SECTION_ENTITIES][CONF_HEAT_PUMP]
            errors = validate(self.hass, user_input, heat_pump)
            if not errors:
                data, options = split(user_input)
                self.hass.config_entries.async_update_entry(entry, data=data)
                return self.async_create_entry(data=options)
        values = (
            flatten(user_input)
            if user_input
            else {**entry.data, **DEFAULTS, **entry.options}
        )
        return self.async_show_form(
            step_id="init", data_schema=build_schema(values, ALL_SECTIONS), errors=errors
        )
