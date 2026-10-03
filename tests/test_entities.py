"""Entities over a fully set-up config entry.

Setting up our switch platform loads HA's switch component, which replaces
the fake tub's switch.turn_on/off. Heater commands are therefore not asserted
here; test_controller.py covers them.
"""

from __future__ import annotations

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.udespa_control.const import DEFAULTS, DOMAIN

from .common import ENTITY_DATA, SPA, FakeTub, advance, settle


@pytest.fixture
async def entry(hass: HomeAssistant, tub: FakeTub):
    entry = MockConfigEntry(
        domain=DOMAIN, title="Udespa", unique_id=SPA, data=ENTITY_DATA, options=dict(DEFAULTS)
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await settle(hass)
    yield entry
    if entry.state is ConfigEntryState.LOADED:
        assert await hass.config_entries.async_unload(entry.entry_id)


def eid(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id is not None, f"{platform}.{key} not registered"
    return entity_id


def state(hass, entry, platform, key):
    return hass.states.get(eid(hass, entry, platform, key))


async def test_initial_states(hass: HomeAssistant, entry):
    assert state(hass, entry, "sensor", "status").state == "Vedligeholder"
    assert state(hass, entry, "select", "heat_pump_mode").state == "Lydløs"
    assert float(state(hass, entry, "number", "rest_temperature").state) == 37.0
    assert state(hass, entry, "switch", "active_control").state == "off"
    assert state(hass, entry, "switch", "frost_protection").state == "on"
    assert state(hass, entry, "sensor", "cleaning_phase").state == "Inaktiv"
    assert state(hass, entry, "sensor", "filter_timer").state == "0"
    assert state(hass, entry, "sensor", "bath_water_timer").attributes["reset_at"]
    assert state(hass, entry, "sensor", "heating").state == "Varmer ikke"
    assert state(hass, entry, "binary_sensor", "heat_pump_failure").state == "off"
    assert state(hass, entry, "sensor", "last_action").state.startswith("(kun overvågning)")


async def test_entity_ids_come_from_the_device_and_english_names(hass: HomeAssistant, entry):
    assert eid(hass, entry, "sensor", "status") == "sensor.udespa_status"
    assert eid(hass, entry, "switch", "active_control") == "switch.udespa_active_control"
    assert state(hass, entry, "sensor", "status").attributes["friendly_name"] == "Udespa Status"


async def test_active_control_switch(hass: HomeAssistant, entry):
    entity_id = eid(hass, entry, "switch", "active_control")
    await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
    await settle(hass)
    assert hass.states.get(entity_id).state == "on"
    assert entry.runtime_data.state.active is True


async def test_frost_protection_switch(hass: HomeAssistant, entry):
    entity_id = eid(hass, entry, "switch", "frost_protection")
    await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
    assert entry.runtime_data.state.frost_protection is False


async def test_mode_select_sends_the_preset(hass: HomeAssistant, tub: FakeTub, entry):
    entity_id = eid(hass, entry, "select", "heat_pump_mode")
    await hass.services.async_call(
        "select", "select_option", {"entity_id": entity_id, "option": "Turbo"}, blocking=True
    )
    await settle(hass)
    assert tub.presets() == ["quiet"]
    assert hass.states.get(entity_id).state == "Turbo"


async def test_rest_temperature_number_moves_the_status(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, entry
):
    entity_id = eid(hass, entry, "number", "rest_temperature")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 36.0}, blocking=True
    )
    await advance(hass, freezer, 5)
    assert float(hass.states.get(entity_id).state) == 36.0
    assert state(hass, entry, "sensor", "status").state == "I brug"


async def _press(hass, entry, key):
    await hass.services.async_call(
        "button", "press", {"entity_id": eid(hass, entry, "button", key)}, blocking=True
    )
    await settle(hass)


async def test_setpoint_buttons(hass: HomeAssistant, entry):
    await _press(hass, entry, "raise_temperature")
    assert hass.states.get(SPA).attributes["temperature"] == 37.5
    await _press(hass, entry, "lower_temperature")
    await _press(hass, entry, "lower_temperature")
    assert hass.states.get(SPA).attributes["temperature"] == 36.5


async def test_cleaning_buttons(hass: HomeAssistant, entry):
    await _press(hass, entry, "start_cleaning")
    assert state(hass, entry, "sensor", "status").state == "Rengøring"
    phase = state(hass, entry, "sensor", "cleaning_phase")
    assert phase.state == "Cyklus 1"
    assert phase.attributes["started_at"]
    assert phase.attributes["estimate_minutes"] == 30
    await _press(hass, entry, "stop_cleaning")
    assert state(hass, entry, "sensor", "cleaning_phase").state == "Inaktiv"
    assert state(hass, entry, "sensor", "status").state == "Vedligeholder"


async def test_timer_reset_buttons(hass: HomeAssistant, entry):
    before = state(hass, entry, "sensor", "filter_timer").attributes["reset_at"]
    await _press(hass, entry, "reset_filter_timer")
    await _press(hass, entry, "reset_bath_water_timer")
    after = state(hass, entry, "sensor", "filter_timer").attributes["reset_at"]
    assert after >= before
    assert state(hass, entry, "sensor", "bath_water_timer").state == "0"


async def test_heating_sensor_follows_the_spa(hass: HomeAssistant, tub: FakeTub, entry):
    tub.spa(action="heating")
    await settle(hass)
    assert state(hass, entry, "sensor", "heating").state == "Varmer"


async def test_failure_binary_sensor_and_status(hass: HomeAssistant, entry):
    entry.runtime_data.set_failure(True)
    await settle(hass)
    assert state(hass, entry, "binary_sensor", "heat_pump_failure").state == "on"
    assert state(hass, entry, "sensor", "status").state == "Fejl"


async def test_state_survives_a_reload(hass: HomeAssistant, entry):
    entity_id = eid(hass, entry, "number", "rest_temperature")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 36.5}, blocking=True
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await settle(hass)
    assert float(hass.states.get(entity_id).state) == 36.5


async def test_removing_the_entry_deletes_its_storage(hass: HomeAssistant, entry, hass_storage):
    await hass.async_block_till_done()
    key = f"{DOMAIN}.{entry.entry_id}"
    await entry.runtime_data.async_shutdown()  # flushes the store
    assert key in hass_storage
    assert await hass.config_entries.async_remove(entry.entry_id)
    assert key not in hass_storage
