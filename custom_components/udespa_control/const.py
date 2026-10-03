"""Constants for Udespa Control."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Final

DOMAIN: Final = "udespa_control"
STORAGE_VERSION: Final = 1

# --- Entities (entry.data) ---------------------------------------------------
CONF_SPA: Final = "spa"
CONF_CIRCULATION: Final = "circulation"
CONF_FILTER_1: Final = "filter_cycle_1"
CONF_FILTER_2: Final = "filter_cycle_2"
CONF_HEAT_PUMP: Final = "heat_pump"
CONF_HEAT_PUMP_POWER: Final = "heat_pump_power"
CONF_HEATER: Final = "heater"
CONF_HEATER_POWER: Final = "heater_power"
CONF_OUTDOOR: Final = "outdoor"
CONF_OUTDOOR_ATTRIBUTE: Final = "outdoor_attribute"
CONF_CLEANING_PUMP: Final = "cleaning_pump"
CONF_NOTIFY: Final = "notify"

ENTITY_KEYS: Final = (
    CONF_SPA,
    CONF_CIRCULATION,
    CONF_FILTER_1,
    CONF_FILTER_2,
    CONF_HEAT_PUMP,
    CONF_HEAT_PUMP_POWER,
    CONF_HEATER,
    CONF_HEATER_POWER,
    CONF_OUTDOOR,
    CONF_OUTDOOR_ATTRIBUTE,
    CONF_CLEANING_PUMP,
    CONF_NOTIFY,
)

# Today's entities, offered as suggestions on first setup.
SUGGESTED_ENTITIES: Final[dict[str, str]] = {
    CONF_SPA: "climate.udespa",
    CONF_CIRCULATION: "binary_sensor.udespa_circulation_pump",
    CONF_FILTER_1: "binary_sensor.udespa_filter_cycle_1",
    CONF_FILTER_2: "binary_sensor.udespa_filter_cycle_2",
    CONF_HEAT_PUMP: "climate.udespa_varmepumpe",
    CONF_HEAT_PUMP_POWER: "sensor.udespa_kwh_maler_power_phase_3",
    CONF_HEATER: "switch.shelly_1_plus_varmelegeme_udespa_switch_0",
    CONF_HEATER_POWER: "sensor.udespa_kwh_maler_power_phase_2",
    CONF_OUTDOOR: "sensor.vejrudsigt_hjemme",
    CONF_OUTDOOR_ATTRIBUTE: "now_temp",
    CONF_CLEANING_PUMP: "fan.udespa_pump_1",
    CONF_NOTIFY: "notify.mobile_app_thomas_iphone_15",
}

# --- Numbers and toggles (entry.options) --------------------------------------
OPT_OFF_DELAY: Final = "off_delay_s"
OPT_HEAD_START_TIMEOUT: Final = "head_start_timeout_s"
OPT_HP_ON_W: Final = "heat_pump_on_w"
OPT_HP_OFF_W: Final = "heat_pump_off_w"
OPT_RETRY_MINUTES: Final = "retry_minutes"
OPT_BACKUP_MARGIN: Final = "backup_margin_c"
OPT_BACKUP_CHECK: Final = "backup_check_s"
OPT_HEATER_ON_W: Final = "heater_on_w"
OPT_WATCHDOG_INTERVAL: Final = "watchdog_interval_min"
OPT_WATCHDOG_CIRCULATION: Final = "watchdog_circulation_min"
OPT_FROST_LIMIT: Final = "frost_limit_c"
OPT_IN_USE_THRESHOLD: Final = "in_use_threshold_c"
OPT_CLEANING_MAX: Final = "cleaning_max_min"
OPT_CLEANING_ESTIMATE: Final = "cleaning_estimate_min"
OPT_PRESET_QUIET: Final = "preset_quiet"
OPT_PRESET_SMART: Final = "preset_smart"
OPT_PRESET_TURBO: Final = "preset_turbo"

OPT_HEAD_START: Final = "head_start"
OPT_BACKUP: Final = "backup_heater"
OPT_WATCHDOG: Final = "watchdog"
OPT_NOTIFICATIONS: Final = "notifications"
OPT_FAULT_STATUS: Final = "fault_status"

NUMBER_KEYS: Final = (
    OPT_OFF_DELAY,
    OPT_HEAD_START_TIMEOUT,
    OPT_HP_ON_W,
    OPT_HP_OFF_W,
    OPT_RETRY_MINUTES,
    OPT_BACKUP_MARGIN,
    OPT_BACKUP_CHECK,
    OPT_HEATER_ON_W,
    OPT_WATCHDOG_INTERVAL,
    OPT_WATCHDOG_CIRCULATION,
    OPT_FROST_LIMIT,
    OPT_IN_USE_THRESHOLD,
    OPT_CLEANING_MAX,
    OPT_CLEANING_ESTIMATE,
)
PRESET_KEYS: Final = (OPT_PRESET_QUIET, OPT_PRESET_SMART, OPT_PRESET_TURBO)
TOGGLE_KEYS: Final = (
    OPT_HEAD_START,
    OPT_BACKUP,
    OPT_WATCHDOG,
    OPT_NOTIFICATIONS,
    OPT_FAULT_STATUS,
)

# Today's values (spec, "Tal" and "Til/fra").
DEFAULTS: Final[dict[str, Any]] = {
    OPT_OFF_DELAY: 5,
    OPT_HEAD_START_TIMEOUT: 70,
    OPT_HP_ON_W: 500,
    OPT_HP_OFF_W: 400,
    OPT_RETRY_MINUTES: 4,
    OPT_BACKUP_MARGIN: 0.5,
    OPT_BACKUP_CHECK: 150,
    OPT_HEATER_ON_W: 1000,
    OPT_WATCHDOG_INTERVAL: 5,
    OPT_WATCHDOG_CIRCULATION: 10,
    OPT_FROST_LIMIT: 5,
    OPT_IN_USE_THRESHOLD: 0.25,
    OPT_CLEANING_MAX: 25,
    OPT_CLEANING_ESTIMATE: 30,
    OPT_PRESET_QUIET: "quick",
    OPT_PRESET_SMART: "smart",
    OPT_PRESET_TURBO: "quiet",
    OPT_HEAD_START: True,
    OPT_BACKUP: True,
    OPT_WATCHDOG: True,
    OPT_NOTIFICATIONS: True,
    OPT_FAULT_STATUS: True,
}

SECTION_ENTITIES: Final = "entities"
SECTION_NUMBERS: Final = "numbers"
SECTION_TOGGLES: Final = "toggles"
ALL_SECTIONS: Final = (SECTION_ENTITIES, SECTION_NUMBERS, SECTION_TOGGLES)

# --- Fixed timings (measured; not settings) -----------------------------------
VERIFY_POLL_S: Final = 15  # one verification step; retry window / 15 = attempts
HEAD_START_OFF_ATTEMPTS: Final = 3
# The compressor starts 85-96 s after "on". A head-start off at 70 s is checked
# 40 s later, past compressor start, or low power would prove nothing.
HEAD_START_OFF_SETTLE_S: Final = 40
CLEANING_OFF_HOLD_S: Final = 5
STATUS_DELAY_S: Final = 5
SETPOINT_STEP: Final = 0.5
SERVICE_TIMEOUT_S: Final = 10
LAST_ACTION_MAX: Final = 255
WATCH_ONLY_PREFIX: Final = "(kun overvågning) "

# --- Legacy helpers, read once on first load so nothing restarts from zero ----
LEGACY_FILTER_TIMER: Final = "input_datetime.udespa_filter_timer"
LEGACY_BATH_TIMER: Final = "input_datetime.udespa_badevand_timer"
LEGACY_REST_TEMPERATURE: Final = "input_number.udespa_hviletemperatur"
LEGACY_FROST_AUTOMATION: Final = "automation.udespa_taend_sluk_varmelegeme"
DEFAULT_REST_TEMPERATURE: Final = 37.0

SPA_CALLING: Final = frozenset({"heating", "idle"})


class Status(StrEnum):
    """Udespa status. Values are the Danish strings dashboards compare against."""

    IN_USE = "I brug"
    MAINTAINING = "Vedligeholder"
    CLEANING = "Rengøring"
    FAULT = "Fejl"


class Mode(StrEnum):
    """Heat-pump mode as shown in the select."""

    QUIET = "Lydløs"
    SMART = "Smart"
    TURBO = "Turbo"


class CleaningPhase(StrEnum):
    IDLE = "Inaktiv"
    CYCLE_1 = "Cyklus 1"
    CYCLE_2 = "Cyklus 2"


class HeatAction(StrEnum):
    ON = "on"
    HEAD_START = "head_start"
    OFF = "off"


class Trigger(StrEnum):
    """What happened, as far as the heat-pump rules care."""

    SPA_HEATING = "spa_heating"  # hvac_action became "heating"
    CIRCULATION_ON = "circulation_on"
    CIRCULATION_OFF = "circulation_off"
    SPA_SATISFIED = "spa_satisfied"  # hvac_action has been "off" for the off delay
    IN_USE = "in_use"  # status became I brug
    STARTUP = "startup"


class BackupKind(StrEnum):
    RETRY = "retry"  # A5: end of the on-job's retry window
    WATCHDOG = "watchdog"  # A6


class Timer(StrEnum):
    FILTER = "filter"
    BATH_WATER = "bath_water"
