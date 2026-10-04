"""Settings built from a config entry's data and options."""

from __future__ import annotations

from custom_components.udespa_control.const import (
    CONF_CIRCULATION,
    CONF_CLEANING_PUMP,
    CONF_HEAT_PUMP,
    CONF_HEAT_PUMP_POWER,
    CONF_HEATER,
    CONF_HEATER_POWER,
    CONF_NOTIFY,
    CONF_OUTDOOR,
    CONF_OUTDOOR_ATTRIBUTE,
    CONF_SPA,
    CONF_SRC_HP_OUTLET,
    CONF_SRC_WATER_TDS,
    DEFAULTS,
    OPT_FILTER_STAY_ON,
    OPT_MODE_IN_USE,
    OPT_MODE_MAINTAINING,
    OPT_OVERTEMP_MARGIN,
    OPT_OVERTEMP_MINUTES,
    OPT_PRESET_TURBO,
    OPT_RETRY_MINUTES,
    OPT_WATCHDOG,
    SOURCE_KEYS,
    SUGGESTED_SOURCES,
    Mode,
    Status,
)
from custom_components.udespa_control.settings import Settings

DATA = {
    CONF_SPA: "climate.udespa",
    CONF_CIRCULATION: "binary_sensor.udespa_circulation_pump",
    CONF_HEAT_PUMP: "climate.udespa_varmepumpe",
    CONF_HEAT_PUMP_POWER: "sensor.l3",
    CONF_HEATER: "switch.heater",
    CONF_HEATER_POWER: "sensor.l2",
    CONF_OUTDOOR: "sensor.vejrudsigt_hjemme",
    CONF_OUTDOOR_ATTRIBUTE: "now_temp",
    CONF_CLEANING_PUMP: "fan.udespa_pump_1",
    CONF_NOTIFY: "mobile_app_thomas_iphone_15",
}


def test_defaults_are_the_spec_values():
    s = Settings.from_mappings(DATA, {})
    assert (s.off_delay_s, s.head_start_timeout_s) == (5, 70)
    assert (s.hp_on_w, s.hp_off_w, s.heater_on_w) == (500, 400, 1000)
    assert (s.retry_minutes, s.backup_margin, s.backup_check_s) == (4, 0.5, 150)
    assert (s.watchdog_interval_min, s.watchdog_circulation_min) == (5, 10)
    assert (s.frost_limit, s.in_use_threshold) == (5, 0.25)
    assert (s.cleaning_max_min, s.cleaning_estimate_min) == (25, 30)
    assert s.presets == {Mode.QUIET: "quick", Mode.SMART: "smart", Mode.TURBO: "quiet"}
    assert s.head_start and s.backup_heater and s.watchdog
    assert s.notifications and s.fault_status


def test_options_override_defaults():
    s = Settings.from_mappings(
        DATA, {OPT_RETRY_MINUTES: 2, OPT_WATCHDOG: False, OPT_PRESET_TURBO: "turbo"}
    )
    assert s.retry_minutes == 2
    assert s.watchdog is False
    assert s.presets[Mode.TURBO] == "turbo"


def test_verify_attempts_cover_the_retry_window_in_15_s_steps():
    assert Settings.from_mappings(DATA, {}).verify_attempts == 16
    assert Settings.from_mappings(DATA, {OPT_RETRY_MINUTES: 1}).verify_attempts == 4


def test_optional_entities_default_to_none():
    s = Settings.from_mappings(DATA, {})
    assert s.filter_cycle_1 is None and s.filter_cycle_2 is None
    assert s.outdoor_attribute == "now_temp"


def test_blank_outdoor_attribute_means_state():
    s = Settings.from_mappings({**DATA, CONF_OUTDOOR_ATTRIBUTE: ""}, {})
    assert s.outdoor_attribute is None


def test_every_option_has_a_default():
    assert set(DEFAULTS) >= {OPT_RETRY_MINUTES, OPT_WATCHDOG, OPT_PRESET_TURBO}


def test_sources_hold_only_configured_keys():
    s = Settings.from_mappings(
        {**DATA, CONF_SRC_HP_OUTLET: "sensor.outlet", CONF_SRC_WATER_TDS: ""}, {}
    )
    assert s.sources == {CONF_SRC_HP_OUTLET: "sensor.outlet"}


def test_no_sources_by_default():
    assert Settings.from_mappings(DATA, {}).sources == {}


def test_suggested_sources_are_known_keys_without_tds():
    assert set(SUGGESTED_SOURCES) <= set(SOURCE_KEYS)
    assert CONF_SRC_WATER_TDS not in SUGGESTED_SOURCES
    assert len(SOURCE_KEYS) == 15


def test_modes_default_to_todays_pair():
    s = Settings.from_mappings(DATA, {})
    assert s.modes == {Status.MAINTAINING: Mode.QUIET, Status.IN_USE: Mode.SMART}


def test_modes_follow_the_options():
    s = Settings.from_mappings(DATA, {OPT_MODE_IN_USE: "Turbo", OPT_MODE_MAINTAINING: "Smart"})
    assert s.modes == {Status.MAINTAINING: Mode.SMART, Status.IN_USE: Mode.TURBO}


def test_an_unknown_mode_falls_back_to_the_default():
    s = Settings.from_mappings(DATA, {OPT_MODE_IN_USE: "Boost"})
    assert s.modes[Status.IN_USE] is Mode.SMART


def test_filter_cycle_defaults():
    s = Settings.from_mappings(DATA, {})
    assert s.filter_stay_on is True
    assert (s.overtemp_margin, s.overtemp_minutes) == (1.0, 5.0)


def test_filter_cycle_options():
    s = Settings.from_mappings(
        DATA, {OPT_FILTER_STAY_ON: False, OPT_OVERTEMP_MARGIN: 1.5, OPT_OVERTEMP_MINUTES: 10}
    )
    assert s.filter_stay_on is False
    assert (s.overtemp_margin, s.overtemp_minutes) == (1.5, 10.0)
