"""Test helpers shared by every module."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.udespa_control.const import (
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
)


async def settle(hass: HomeAssistant) -> None:
    """Let background jobs run until they block on their next wait.

    async_block_till_done does not wait for background tasks (that is the
    point of them), so give the loop a few turns first.
    """
    for _ in range(20):
        await asyncio.sleep(0)
    await hass.async_block_till_done()


async def advance(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    seconds: float,
    step: float = 1.0,
) -> None:
    """Move the clock forward, firing timers and letting jobs react each step.

    Settles first: state-change listeners run on the next loop turn, so an
    event set just before advance() must be handled at the current time,
    not one tick later.
    """
    await settle(hass)
    remaining = float(seconds)
    while remaining > 1e-9:
        tick = min(step, remaining)
        freezer.tick(timedelta(seconds=tick))
        async_fire_time_changed(hass)
        await settle(hass)
        remaining -= tick


SPA = "climate.udespa"
CIRCULATION = "binary_sensor.udespa_circulation_pump"
FILTER_1 = "binary_sensor.udespa_filter_cycle_1"
FILTER_2 = "binary_sensor.udespa_filter_cycle_2"
HP = "climate.udespa_varmepumpe"
HP_POWER = "sensor.udespa_kwh_maler_power_phase_3"
HEATER = "switch.varmelegeme"
HEATER_POWER = "sensor.udespa_kwh_maler_power_phase_2"
OUTDOOR = "sensor.vejrudsigt_hjemme"
PUMP = "fan.udespa_pump_1"
NOTIFY = "mobile_app_test"

ENTITY_DATA = {
    CONF_SPA: SPA,
    CONF_CIRCULATION: CIRCULATION,
    CONF_FILTER_1: FILTER_1,
    CONF_FILTER_2: FILTER_2,
    CONF_HEAT_PUMP: HP,
    CONF_HEAT_PUMP_POWER: HP_POWER,
    CONF_HEATER: HEATER,
    CONF_HEATER_POWER: HEATER_POWER,
    CONF_OUTDOOR: OUTDOOR,
    CONF_OUTDOOR_ATTRIBUTE: "now_temp",
    CONF_CLEANING_PUMP: PUMP,
    CONF_NOTIFY: NOTIFY,
}

_KEEP = object()


@dataclass
class Call:
    at: datetime
    domain: str
    service: str
    data: dict[str, Any]


class FakeTub:
    """Every device the integration talks to, behaving like the real ones.

    The heat pump's climate entity changes state the moment it is told to
    (tuya_local's optimistic write); its power does not. With
    model_compressor=True, power follows the measured delays: the compressor
    starts 90 s after "heat" and finishes its soft stop 69 s after "off".
    """

    COMPRESSOR_START_S = 90
    COMPRESSOR_STOP_S = 69
    RUNNING_W = 1500.0
    IDLE_W = 8.0

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.calls: list[Call] = []
        self.model_compressor = False
        self.fail_services: set[str] = set()
        self._compressor_timer: CALLBACK_TYPE | None = None

    def install(
        self,
        *,
        action: str = "off",
        temperature: float | None = 37.0,
        setpoint: float | None = 37.0,
        circulation: str = "off",
        hp_mode: str = "off",
        hp_preset: str = "quick",
        hp_power: float | str = 8.0,
        heater: str = "off",
        heater_power: float | str = 0.0,
        outdoor: float | None = 10.0,
        pump: str = "off",
    ) -> None:
        hass = self.hass
        hass.states.async_set(
            SPA,
            "heat",
            {
                "hvac_action": action,
                "current_temperature": temperature,
                "temperature": setpoint,
                "min_temp": 26.5,
                "max_temp": 40,
            },
        )
        hass.states.async_set(CIRCULATION, circulation)
        hass.states.async_set(FILTER_1, "off")
        hass.states.async_set(FILTER_2, "off")
        hass.states.async_set(
            HP,
            hp_mode,
            {
                "preset_mode": hp_preset,
                "preset_modes": ["quick", "smart", "quiet"],
                "temperature": setpoint,
            },
        )
        self.hp_power(hp_power)
        hass.states.async_set(HEATER, heater)
        self.heater_power(heater_power)
        self.outdoor(outdoor)
        hass.states.async_set(PUMP, pump)
        for domain, service in (
            ("climate", "set_hvac_mode"),
            ("climate", "set_preset_mode"),
            ("climate", "set_temperature"),
            ("switch", "turn_on"),
            ("switch", "turn_off"),
            ("fan", "turn_on"),
            ("fan", "turn_off"),
            ("notify", NOTIFY),
        ):
            hass.services.async_register(domain, service, self._handle)

    def shutdown(self) -> None:
        if self._compressor_timer is not None:
            self._compressor_timer()
            self._compressor_timer = None

    # --- setters --------------------------------------------------------------

    def spa(self, *, action=_KEEP, temperature=_KEEP, setpoint=_KEEP, state=_KEEP) -> None:
        current = self.hass.states.get(SPA)
        attrs = dict(current.attributes)
        for key, value in (
            ("hvac_action", action),
            ("current_temperature", temperature),
            ("temperature", setpoint),
        ):
            if value is not _KEEP:
                attrs[key] = value
        self.hass.states.async_set(
            SPA, current.state if state is _KEEP else state, attrs
        )

    def circulation(self, on: bool | str) -> None:
        value = on if isinstance(on, str) else ("on" if on else "off")
        self.hass.states.async_set(CIRCULATION, value)

    def filter_cycle(self, number: int, on: bool) -> None:
        self.hass.states.async_set(FILTER_1 if number == 1 else FILTER_2, "on" if on else "off")

    def hp_power(self, watts: float | str) -> None:
        self.hass.states.async_set(
            HP_POWER, str(watts), {"unit_of_measurement": "W", "device_class": "power"}
        )

    def heater_power(self, watts: float | str) -> None:
        self.hass.states.async_set(
            HEATER_POWER, str(watts), {"unit_of_measurement": "W", "device_class": "power"}
        )

    def outdoor(self, temperature: float | None) -> None:
        self.hass.states.async_set(
            OUTDOOR, dt_util.utcnow().isoformat(), {"now_temp": temperature}
        )

    def pump(self, state: str) -> None:
        self.hass.states.async_set(PUMP, state)

    # --- queries --------------------------------------------------------------

    def sent(self, domain: str, service: str | None = None) -> list[Call]:
        return [
            c for c in self.calls if c.domain == domain and service in (None, c.service)
        ]

    def hp_modes(self) -> list[str]:
        return [
            c.data["hvac_mode"]
            for c in self.sent("climate", "set_hvac_mode")
            if c.data["entity_id"] == HP
        ]

    def presets(self) -> list[str]:
        return [c.data["preset_mode"] for c in self.sent("climate", "set_preset_mode")]

    def heater_commands(self) -> list[str]:
        return [
            "on" if c.service == "turn_on" else "off"
            for c in self.sent("switch")
            if c.data["entity_id"] == HEATER
        ]

    def notifications(self) -> list[Call]:
        return self.sent("notify")

    # --- device behaviour -----------------------------------------------------

    def _power(self) -> float:
        try:
            return float(self.hass.states.get(HP_POWER).state)
        except ValueError:
            return 0.0

    def _compressor_follows(self, previous: str, mode: str) -> None:
        # Re-sending the mode the pump already has changes nothing on the device.
        if not self.model_compressor or mode == previous:
            return
        self.shutdown()
        running = self._power() > 500
        if mode == "heat" and not running:
            delay, watts = self.COMPRESSOR_START_S, self.RUNNING_W
        elif mode == "off" and running:
            delay, watts = self.COMPRESSOR_STOP_S, self.IDLE_W
        else:
            return

        @callback
        def _settled(_now: Any) -> None:
            self._compressor_timer = None
            self.hp_power(watts)

        self._compressor_timer = async_call_later(self.hass, delay, _settled)

    async def _handle(self, call: ServiceCall) -> None:
        self.calls.append(Call(dt_util.utcnow(), call.domain, call.service, dict(call.data)))
        if f"{call.domain}.{call.service}" in self.fail_services:
            raise HomeAssistantError(f"{call.domain}.{call.service} failed")
        if call.domain == "notify":
            return
        entity_id = call.data["entity_id"]
        if call.domain in ("switch", "fan"):
            self.hass.states.async_set(
                entity_id, "on" if call.service == "turn_on" else "off"
            )
            return
        current = self.hass.states.get(entity_id)
        attrs = dict(current.attributes)
        value = current.state
        if call.service == "set_hvac_mode":
            value = call.data["hvac_mode"]
            if entity_id == HP:
                self._compressor_follows(current.state, value)
        elif call.service == "set_preset_mode":
            attrs["preset_mode"] = call.data["preset_mode"]
        elif call.service == "set_temperature":
            attrs["temperature"] = call.data["temperature"]
        self.hass.states.async_set(entity_id, value, attrs)
