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

# --- Hub data sources (entry.data, settings section "sources") ----------------
CONF_SRC_HP_OUTLET: Final = "src_hp_outlet"
CONF_SRC_HP_COMPRESSOR: Final = "src_hp_compressor"
CONF_SRC_HP_AMBIENT: Final = "src_hp_ambient"
CONF_SRC_HP_COIL: Final = "src_hp_coil"
CONF_SRC_HP_EXHAUST: Final = "src_hp_exhaust"
CONF_SRC_HP_IPM: Final = "src_hp_ipm"
CONF_SRC_HP_FAN: Final = "src_hp_fan"
CONF_SRC_HP_EEV: Final = "src_hp_eev"
CONF_SRC_HP_COMPRESSOR_CURRENT: Final = "src_hp_compressor_current"
CONF_SRC_CIRCULATION_POWER: Final = "src_circulation_power"
CONF_SRC_WATER_PH: Final = "src_water_ph"
CONF_SRC_WATER_ORP: Final = "src_water_orp"
CONF_SRC_WATER_TDS: Final = "src_water_tds"
CONF_SRC_ONDILO_TEMPERATURE: Final = "src_ondilo_temperature"
CONF_SRC_ONDILO_BATTERY: Final = "src_ondilo_battery"

SOURCE_KEYS: Final = (
    CONF_SRC_HP_OUTLET,
    CONF_SRC_HP_COMPRESSOR,
    CONF_SRC_HP_AMBIENT,
    CONF_SRC_HP_COIL,
    CONF_SRC_HP_EXHAUST,
    CONF_SRC_HP_IPM,
    CONF_SRC_HP_FAN,
    CONF_SRC_HP_EEV,
    CONF_SRC_HP_COMPRESSOR_CURRENT,
    CONF_SRC_CIRCULATION_POWER,
    CONF_SRC_WATER_PH,
    CONF_SRC_WATER_ORP,
    CONF_SRC_WATER_TDS,
    CONF_SRC_ONDILO_TEMPERATURE,
    CONF_SRC_ONDILO_BATTERY,
)

# Today's entities. No TDS entity exists, so TDS has no suggestion.
SUGGESTED_SOURCES: Final[dict[str, str]] = {
    CONF_SRC_HP_OUTLET: "sensor.udespa_varmepumpe_outlet_temperature",
    CONF_SRC_HP_COMPRESSOR: "sensor.udespa_varmepumpe_compressor_strength",
    CONF_SRC_HP_AMBIENT: "sensor.udespa_varmepumpe_ambient_temperature",
    CONF_SRC_HP_COIL: "sensor.udespa_varmepumpe_coil_temperature",
    CONF_SRC_HP_EXHAUST: "sensor.udespa_varmepumpe_exhaust_temperature",
    CONF_SRC_HP_IPM: "sensor.udespa_varmepumpe_ipm_module",
    CONF_SRC_HP_FAN: "sensor.udespa_varmepumpe_fan_speed",
    CONF_SRC_HP_EEV: "sensor.udespa_varmepumpe_eev_step",
    CONF_SRC_HP_COMPRESSOR_CURRENT: "sensor.udespa_varmepumpe_compressor_current",
    CONF_SRC_CIRCULATION_POWER: "sensor.udespa_kwh_maler_power_phase_1",
    CONF_SRC_WATER_PH: "sensor.udespa_ph_korrigeret",
    CONF_SRC_WATER_ORP: "sensor.udespa_oxydo_reduction_potential",
    CONF_SRC_ONDILO_TEMPERATURE: "sensor.udespa_temperatur",
    CONF_SRC_ONDILO_BATTERY: "sensor.udespa_batteri",
}

SECTION_SOURCES: Final = "sources"

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
OPT_MODE_MAINTAINING: Final = "mode_maintaining"
OPT_MODE_IN_USE: Final = "mode_in_use"

OPT_HEAD_START: Final = "head_start"
OPT_BACKUP: Final = "backup_heater"
OPT_WATCHDOG: Final = "watchdog"
OPT_NOTIFICATIONS: Final = "notifications"
OPT_FAULT_STATUS: Final = "fault_status"
OPT_FILTER_STAY_ON: Final = "filter_stay_on"
OPT_OVERTEMP_MARGIN: Final = "overtemp_margin_c"
OPT_OVERTEMP_MINUTES: Final = "overtemp_minutes"

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
    OPT_OVERTEMP_MARGIN,
    OPT_OVERTEMP_MINUTES,
)
PRESET_KEYS: Final = (OPT_PRESET_QUIET, OPT_PRESET_SMART, OPT_PRESET_TURBO)
MODE_KEYS: Final = (OPT_MODE_MAINTAINING, OPT_MODE_IN_USE)
TOGGLE_KEYS: Final = (
    OPT_HEAD_START,
    OPT_BACKUP,
    OPT_WATCHDOG,
    OPT_NOTIFICATIONS,
    OPT_FAULT_STATUS,
    OPT_FILTER_STAY_ON,
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
    OPT_MODE_MAINTAINING: "Lydløs",
    OPT_MODE_IN_USE: "Smart",
    OPT_HEAD_START: True,
    OPT_BACKUP: True,
    OPT_WATCHDOG: True,
    OPT_NOTIFICATIONS: True,
    OPT_FAULT_STATUS: True,
    OPT_FILTER_STAY_ON: True,
    OPT_OVERTEMP_MARGIN: 1.0,
    OPT_OVERTEMP_MINUTES: 5,
}

SECTION_ENTITIES: Final = "entities"
SECTION_NUMBERS: Final = "numbers"
SECTION_TOGGLES: Final = "toggles"
ALL_SECTIONS: Final = (SECTION_ENTITIES, SECTION_NUMBERS, SECTION_TOGGLES, SECTION_SOURCES)

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

OFFSET_VALUES: Final = (0.0, 0.5, 1.0)
SYNC_TOLERANCE: Final = 0.05
# B12′: the heat pump can drop a preset change at power-on (seen 2026-10-04).
MODE_CHECK_S: Final = 10
MODE_ATTEMPTS: Final = 3
# Rule F: the filter-cycle sensor must hold "on" this long before the heat
# pump is switched on, so the circulation state has caught up.
FILTER_START_DELAY_S: Final = 10
DEFAULT_HP_LIMITS: Final = (6.0, 41.0)

DEMAND_LABELS: Final[dict[str, str]] = {
    "heating": "Kalder på varme",
    "idle": "Flowtjek",
    "off": "Ingen efterspørgsel",
}

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
    FILTER_START = "filter_start"  # a filter cycle has been on for FILTER_START_DELAY_S


class BackupKind(StrEnum):
    RETRY = "retry"  # A5: end of the on-job's retry window
    WATCHDOG = "watchdog"  # A6


class Timer(StrEnum):
    FILTER = "filter"
    BATH_WATER = "bath_water"


class SyncStatus(StrEnum):
    """Heat-pump target against spa setpoint + offset (A9′)."""

    IN_SYNC = "I sync"
    DIFFERS = "Afviger"
    UNKNOWN = "Ukendt"
