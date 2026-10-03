"""Typed settings, built from a config entry's data and options.

Pure: takes plain mappings so rules and tests never need a config entry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .const import (
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
    OPT_BACKUP,
    OPT_BACKUP_CHECK,
    OPT_BACKUP_MARGIN,
    OPT_CLEANING_ESTIMATE,
    OPT_CLEANING_MAX,
    OPT_FAULT_STATUS,
    OPT_FROST_LIMIT,
    OPT_HEAD_START,
    OPT_HEAD_START_TIMEOUT,
    OPT_HEATER_ON_W,
    OPT_HP_OFF_W,
    OPT_HP_ON_W,
    OPT_IN_USE_THRESHOLD,
    OPT_NOTIFICATIONS,
    OPT_OFF_DELAY,
    OPT_PRESET_QUIET,
    OPT_PRESET_SMART,
    OPT_PRESET_TURBO,
    OPT_RETRY_MINUTES,
    OPT_WATCHDOG,
    OPT_WATCHDOG_CIRCULATION,
    OPT_WATCHDOG_INTERVAL,
    VERIFY_POLL_S,
    Mode,
)


@dataclass(frozen=True)
class Settings:
    spa: str
    circulation: str
    filter_cycle_1: str | None
    filter_cycle_2: str | None
    heat_pump: str
    heat_pump_power: str
    heater: str
    heater_power: str
    outdoor: str
    outdoor_attribute: str | None
    cleaning_pump: str
    notify: str

    off_delay_s: float
    head_start_timeout_s: float
    hp_on_w: float
    hp_off_w: float
    retry_minutes: float
    backup_margin: float
    backup_check_s: float
    heater_on_w: float
    watchdog_interval_min: float
    watchdog_circulation_min: float
    frost_limit: float
    in_use_threshold: float
    cleaning_max_min: float
    cleaning_estimate_min: float
    presets: Mapping[Mode, str]

    head_start: bool
    backup_heater: bool
    watchdog: bool
    notifications: bool
    fault_status: bool

    @property
    def verify_attempts(self) -> int:
        """Verification steps of VERIFY_POLL_S that fill the retry window."""
        return max(1, round(self.retry_minutes * 60 / VERIFY_POLL_S))

    @classmethod
    def from_mappings(
        cls, data: Mapping[str, Any], options: Mapping[str, Any]
    ) -> Settings:
        o = {**DEFAULTS, **options}
        return cls(
            spa=data[CONF_SPA],
            circulation=data[CONF_CIRCULATION],
            filter_cycle_1=data.get(CONF_FILTER_1) or None,
            filter_cycle_2=data.get(CONF_FILTER_2) or None,
            heat_pump=data[CONF_HEAT_PUMP],
            heat_pump_power=data[CONF_HEAT_PUMP_POWER],
            heater=data[CONF_HEATER],
            heater_power=data[CONF_HEATER_POWER],
            outdoor=data[CONF_OUTDOOR],
            outdoor_attribute=data.get(CONF_OUTDOOR_ATTRIBUTE) or None,
            cleaning_pump=data[CONF_CLEANING_PUMP],
            notify=data[CONF_NOTIFY],
            off_delay_s=float(o[OPT_OFF_DELAY]),
            head_start_timeout_s=float(o[OPT_HEAD_START_TIMEOUT]),
            hp_on_w=float(o[OPT_HP_ON_W]),
            hp_off_w=float(o[OPT_HP_OFF_W]),
            retry_minutes=float(o[OPT_RETRY_MINUTES]),
            backup_margin=float(o[OPT_BACKUP_MARGIN]),
            backup_check_s=float(o[OPT_BACKUP_CHECK]),
            heater_on_w=float(o[OPT_HEATER_ON_W]),
            watchdog_interval_min=float(o[OPT_WATCHDOG_INTERVAL]),
            watchdog_circulation_min=float(o[OPT_WATCHDOG_CIRCULATION]),
            frost_limit=float(o[OPT_FROST_LIMIT]),
            in_use_threshold=float(o[OPT_IN_USE_THRESHOLD]),
            cleaning_max_min=float(o[OPT_CLEANING_MAX]),
            cleaning_estimate_min=float(o[OPT_CLEANING_ESTIMATE]),
            presets={
                Mode.QUIET: str(o[OPT_PRESET_QUIET]),
                Mode.SMART: str(o[OPT_PRESET_SMART]),
                Mode.TURBO: str(o[OPT_PRESET_TURBO]),
            },
            head_start=bool(o[OPT_HEAD_START]),
            backup_heater=bool(o[OPT_BACKUP]),
            watchdog=bool(o[OPT_WATCHDOG]),
            notifications=bool(o[OPT_NOTIFICATIONS]),
            fault_status=bool(o[OPT_FAULT_STATUS]),
        )
