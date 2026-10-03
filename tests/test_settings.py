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
    DEFAULTS,
    OPT_PRESET_TURBO,
    OPT_RETRY_MINUTES,
    OPT_WATCHDOG,
    Mode,
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
