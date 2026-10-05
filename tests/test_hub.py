"""Hub copies, the offset slider and the sync status sensor."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.udespa_control.const import (
    CONF_SRC_CIRCULATION_POWER,
    CONF_SRC_HP_AMBIENT,
    CONF_SRC_HP_COIL,
    CONF_SRC_HP_COMPRESSOR,
    CONF_SRC_HP_COMPRESSOR_CURRENT,
    CONF_SRC_HP_EEV,
    CONF_SRC_HP_EXHAUST,
    CONF_SRC_HP_FAN,
    CONF_SRC_HP_IPM,
    CONF_SRC_HP_OUTLET,
    CONF_SRC_ONDILO_BATTERY,
    CONF_SRC_WATER_ORP,
    CONF_SRC_WATER_PH,
    CONF_SRC_WATER_TDS,
    DEFAULTS,
    DOMAIN,
)

from .common import ENTITY_DATA, HP, HP_POWER, SPA, FakeTub, settle

SOURCES = {
    CONF_SRC_HP_OUTLET: ("sensor.src_outlet", "38.4", {"unit_of_measurement": "°C", "device_class": "temperature", "state_class": "measurement"}),
    CONF_SRC_HP_COMPRESSOR: ("sensor.src_compressor", "45", {"unit_of_measurement": "Hz", "device_class": "frequency"}),
    CONF_SRC_HP_AMBIENT: ("sensor.src_ambient", "12", {"unit_of_measurement": "°C", "device_class": "temperature"}),
    CONF_SRC_HP_COIL: ("sensor.src_coil", "5", {"unit_of_measurement": "°C", "device_class": "temperature"}),
    CONF_SRC_HP_EXHAUST: ("sensor.src_exhaust", "60", {"unit_of_measurement": "°C", "device_class": "temperature"}),
    CONF_SRC_HP_IPM: ("sensor.src_ipm", "30", {"unit_of_measurement": "°C", "device_class": "temperature"}),
    CONF_SRC_HP_FAN: ("sensor.src_fan", "450", {"unit_of_measurement": "rpm"}),
    CONF_SRC_HP_EEV: ("sensor.src_eev", "350", {}),
    CONF_SRC_HP_COMPRESSOR_CURRENT: ("sensor.src_current", "4.2", {"unit_of_measurement": "A", "device_class": "current"}),
    CONF_SRC_CIRCULATION_POWER: ("sensor.src_l1", "137.7", {"unit_of_measurement": "W", "device_class": "power"}),
    CONF_SRC_WATER_PH: ("sensor.src_ph", "7.4", {}),
    CONF_SRC_WATER_ORP: ("sensor.src_orp", "593", {"unit_of_measurement": "mV"}),
    CONF_SRC_WATER_TDS: ("sensor.src_tds", "900", {"unit_of_measurement": "ppm"}),
    CONF_SRC_ONDILO_BATTERY: ("sensor.src_battery", "63", {"unit_of_measurement": "%", "device_class": "battery"}),
}


async def _setup(hass: HomeAssistant, sources: dict) -> MockConfigEntry:
    for entity_id, state, attrs in sources.values():
        hass.states.async_set(entity_id, state, attrs)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Udespa",
        unique_id=SPA,
        data={**ENTITY_DATA, **{key: value[0] for key, value in sources.items()}},
        options=dict(DEFAULTS),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await settle(hass)
    return entry


@pytest.fixture
async def entry(hass: HomeAssistant, tub: FakeTub):
    entry = await _setup(hass, SOURCES)
    yield entry
    if entry.state is ConfigEntryState.LOADED:
        assert await hass.config_entries.async_unload(entry.entry_id)


def eid(hass, entry, platform, key):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")


def state(hass, entry, platform, key):
    entity_id = eid(hass, entry, platform, key)
    assert entity_id is not None, f"{platform}.{key} not registered"
    return hass.states.get(entity_id)


SENSOR_KEYS = (
    "temperature_sync", "water_temperature", "setpoint", "heat_demand", "hp_inlet",
    "hp_outlet", "hp_temperature_rise", "hp_compressor", "hp_power", "hp_ambient",
    "heater_power", "circulation_power", "hp_coil", "hp_exhaust", "hp_ipm", "hp_fan",
    "hp_eev", "hp_compressor_current", "water_ph", "water_orp", "water_tds",
    "ondilo_battery",
)


async def test_every_hub_entity_exists(hass: HomeAssistant, entry):
    for key in SENSOR_KEYS:
        assert eid(hass, entry, "sensor", key), key
    assert eid(hass, entry, "binary_sensor", "circulation")
    assert eid(hass, entry, "number", "heat_pump_offset")


async def test_climate_attribute_copies_are_celsius(hass: HomeAssistant, tub: FakeTub, entry):
    tub.spa(temperature=36.5, setpoint=38.0)
    await settle(hass)
    water = state(hass, entry, "sensor", "water_temperature")
    assert float(water.state) == 36.5
    assert water.attributes["unit_of_measurement"] == "°C"
    assert water.attributes["device_class"] == "temperature"
    assert float(state(hass, entry, "sensor", "setpoint").state) == 38.0
    assert float(state(hass, entry, "sensor", "hp_inlet").state) == 35.0


async def test_copies_mirror_value_unit_and_class(hass: HomeAssistant, entry):
    ph = state(hass, entry, "sensor", "water_ph")
    assert ph.state == "7.4"
    battery = state(hass, entry, "sensor", "ondilo_battery")
    assert battery.attributes["unit_of_measurement"] == "%"
    assert battery.attributes["device_class"] == "battery"


async def test_power_copies_are_whole_watts(hass: HomeAssistant, tub: FakeTub, entry):
    tub.hp_power(1234.6)
    await settle(hass)
    power = state(hass, entry, "sensor", "hp_power")
    assert power.state == "1235"
    assert power.attributes["unit_of_measurement"] == "W"
    assert power.attributes["device_class"] == "power"
    assert state(hass, entry, "sensor", "circulation_power").state == "138"


async def test_copy_follows_a_unit_change(hass: HomeAssistant, tub: FakeTub, entry):
    hass.states.async_set(HP_POWER, "1.2345", {"unit_of_measurement": "kW", "device_class": "power"})
    await settle(hass)
    power = state(hass, entry, "sensor", "hp_power")
    assert power.attributes["unit_of_measurement"] == "W"  # converted, not rounded to whole kW
    assert power.state == "1235"


async def test_temperature_rise(hass: HomeAssistant, tub: FakeTub, entry):
    tub.circulation(True)
    await settle(hass)
    rise = state(hass, entry, "sensor", "hp_temperature_rise")
    assert float(rise.state) == 3.4  # 38.4 out - 35.0 in
    hass.states.async_set("sensor.src_outlet", "unavailable")
    await settle(hass)
    assert state(hass, entry, "sensor", "hp_temperature_rise").state == "unavailable"


async def test_unavailable_and_missing_sources(hass: HomeAssistant, entry):
    hass.states.async_set("sensor.src_orp", "unavailable")
    hass.states.async_remove("sensor.src_tds")
    await settle(hass)
    assert state(hass, entry, "sensor", "water_orp").state == "unavailable"
    assert state(hass, entry, "sensor", "water_tds").state == "unavailable"


async def test_copies_follow_their_source(hass: HomeAssistant, entry):
    hass.states.async_set("sensor.src_ph", "7.2", {})
    await settle(hass)
    assert state(hass, entry, "sensor", "water_ph").state == "7.2"


async def test_diagnostics_have_their_own_category(hass: HomeAssistant, entry):
    registry = er.async_get(hass)
    for key in ("hp_coil", "hp_exhaust", "hp_ipm", "hp_fan", "hp_eev", "hp_compressor_current"):
        assert registry.async_get(eid(hass, entry, "sensor", key)).entity_category is EntityCategory.DIAGNOSTIC
    assert registry.async_get(eid(hass, entry, "sensor", "hp_outlet")).entity_category is None


async def test_heat_demand_labels(hass: HomeAssistant, tub: FakeTub, entry):
    for action, label in (("heating", "Kalder på varme"), ("idle", "Flowtjek"), ("off", "Ingen efterspørgsel")):
        tub.spa(action=action)
        await settle(hass)
        assert state(hass, entry, "sensor", "heat_demand").state == label


async def test_circulation_copy(hass: HomeAssistant, tub: FakeTub, entry):
    assert state(hass, entry, "binary_sensor", "circulation").state == "off"
    tub.circulation(True)
    await settle(hass)
    circulation = state(hass, entry, "binary_sensor", "circulation")
    assert circulation.state == "on"
    assert circulation.attributes["device_class"] == "running"


async def test_offset_slider(hass: HomeAssistant, entry):
    entity_id = eid(hass, entry, "number", "heat_pump_offset")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 1.0}, blocking=True
    )
    await settle(hass)
    assert entry.runtime_data.state.offset == 1.0
    assert float(hass.states.get(entity_id).state) == 1.0


async def test_sync_status_sensor(hass: HomeAssistant, entry):
    sync = state(hass, entry, "sensor", "temperature_sync")
    assert sync.state == "I sync"
    assert sync.attributes["expected_target"] == 37.0
    assert sync.attributes["heat_pump_target"] == 37.0
    hass.states.async_set(HP, "off", {**hass.states.get(HP).attributes, "temperature": 35.0})
    await settle(hass)
    assert state(hass, entry, "sensor", "temperature_sync").state == "Afviger"


async def test_an_emptied_source_removes_its_copy(hass: HomeAssistant, entry):
    assert eid(hass, entry, "sensor", "water_ph")
    data = {k: v for k, v in entry.data.items() if k != CONF_SRC_WATER_PH}
    hass.config_entries.async_update_entry(entry, data=data)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await settle(hass)
    assert eid(hass, entry, "sensor", "water_ph") is None


async def test_temperature_rise_only_while_water_flows(hass: HomeAssistant, tub: FakeTub, entry):
    """With circulation off the inlet sensor reads standing water: no meaningful rise."""
    assert state(hass, entry, "sensor", "hp_temperature_rise").state == "unavailable"
    tub.circulation(True)
    await settle(hass)
    assert float(state(hass, entry, "sensor", "hp_temperature_rise").state) == 3.4
    tub.circulation(False)
    await settle(hass)
    assert state(hass, entry, "sensor", "hp_temperature_rise").state == "unavailable"


async def test_whole_numbers_stay_whole(hass: HomeAssistant, entry):
    assert state(hass, entry, "sensor", "ondilo_battery").state == "63"
    assert state(hass, entry, "sensor", "hp_eev").state == "350"
    assert state(hass, entry, "sensor", "water_ph").state == "7.4"


async def test_the_retired_ondilo_temperature_copy_is_removed(hass: HomeAssistant, tub: FakeTub):
    """2026.10.9: the Ondilo's temperature is not used for anything, so its copy goes,
    and an installation that had it loses the registry entry at start-up."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Udespa",
        unique_id=SPA,
        data={**ENTITY_DATA, "src_ondilo_temperature": "sensor.udespa_temperatur"},
        options=dict(DEFAULTS),
    )
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.udespa_temperatur", "36.8", {"unit_of_measurement": "°C"})
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_ondilo_temperature", config_entry=entry
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await settle(hass)
    assert registry.async_get(old.entity_id) is None
    assert eid(hass, entry, "sensor", "ondilo_temperature") is None
    assert await hass.config_entries.async_unload(entry.entry_id)
