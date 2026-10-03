"""Config, options and reconfigure flows."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.udespa_control.const import (
    CONF_HEATER,
    CONF_NOTIFY,
    DEFAULTS,
    DOMAIN,
    NUMBER_KEYS,
    OPT_HP_OFF_W,
    OPT_PRESET_TURBO,
    OPT_RETRY_MINUTES,
    OPT_WATCHDOG,
    PRESET_KEYS,
    SECTION_ENTITIES,
    SECTION_NUMBERS,
    SECTION_TOGGLES,
    TOGGLE_KEYS,
)

from .common import ENTITY_DATA, NOTIFY, SPA, FakeTub

SETUP = "custom_components.udespa_control.async_setup_entry"
UNLOAD = "custom_components.udespa_control.async_unload_entry"


def _input(entities=None, numbers=None, toggles=None) -> dict:
    return {
        SECTION_ENTITIES: {**ENTITY_DATA, CONF_NOTIFY: f"notify.{NOTIFY}", **(entities or {})},
        SECTION_NUMBERS: {
            **{k: DEFAULTS[k] for k in (*NUMBER_KEYS, *PRESET_KEYS)},
            **(numbers or {}),
        },
        SECTION_TOGGLES: {**{k: DEFAULTS[k] for k in TOGGLE_KEYS}, **(toggles or {})},
    }


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def test_the_form_has_three_sections(hass: HomeAssistant, tub: FakeTub):
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert [str(key) for key in result["data_schema"].schema] == [
        SECTION_ENTITIES,
        SECTION_NUMBERS,
        SECTION_TOGGLES,
    ]


async def test_user_flow_creates_the_entry(hass: HomeAssistant, tub: FakeTub):
    result = await _start(hass)
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _input()
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Udespa"
    assert result["data"][CONF_NOTIFY] == NOTIFY  # stored without "notify."
    assert result["data"][CONF_HEATER] == ENTITY_DATA[CONF_HEATER]
    assert result["options"][OPT_RETRY_MINUTES] == 4
    assert result["options"][OPT_WATCHDOG] is True
    assert result["result"].unique_id == SPA


@pytest.mark.parametrize(
    "user_input,error",
    [
        (_input(entities={CONF_NOTIFY: "notify.nobody"}), "notify_not_found"),
        (_input(numbers={OPT_HP_OFF_W: 600}), "power_thresholds"),
        (_input(numbers={OPT_PRESET_TURBO: "turbo"}), "unknown_preset"),
    ],
)
async def test_invalid_input_is_refused(hass: HomeAssistant, tub: FakeTub, user_input, error):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_a_spa_can_only_be_set_up_once(hass: HomeAssistant, tub: FakeTub):
    MockConfigEntry(domain=DOMAIN, unique_id=SPA, data=ENTITY_DATA).add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _input())
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def _loaded_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, title="Udespa", unique_id=SPA, data=ENTITY_DATA, options=dict(DEFAULTS)
    )
    entry.add_to_hass(hass)
    with patch(SETUP, return_value=True):
        assert await hass.config_entries.async_setup(entry.entry_id)
    return entry


async def test_options_flow_is_the_whole_settings_screen(hass: HomeAssistant, tub: FakeTub):
    entry = await _loaded_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert [str(key) for key in result["data_schema"].schema] == [
        SECTION_ENTITIES,
        SECTION_NUMBERS,
        SECTION_TOGGLES,
    ]
    hass.states.async_set("switch.new_heater", "off")
    with patch(SETUP, return_value=True), patch(UNLOAD, return_value=True):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            _input(entities={CONF_HEATER: "switch.new_heater"}, numbers={OPT_RETRY_MINUTES: 2}),
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[OPT_RETRY_MINUTES] == 2
    assert entry.data[CONF_HEATER] == "switch.new_heater"
    assert entry.data[CONF_NOTIFY] == NOTIFY


async def test_options_flow_refuses_invalid_input(hass: HomeAssistant, tub: FakeTub):
    entry = await _loaded_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _input(numbers={OPT_HP_OFF_W: 500})
    )
    assert result["errors"] == {"base": "power_thresholds"}


async def test_reconfigure_swaps_entities_only(hass: HomeAssistant, tub: FakeTub):
    entry = await _loaded_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert [str(key) for key in result["data_schema"].schema] == [SECTION_ENTITIES]
    with patch(SETUP, return_value=True), patch(UNLOAD, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {SECTION_ENTITIES: {**ENTITY_DATA, CONF_HEATER: "switch.other"}},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HEATER] == "switch.other"
    assert entry.options[OPT_RETRY_MINUTES] == 4
