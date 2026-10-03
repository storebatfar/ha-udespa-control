"""Typed reads of the configured entities.

The one place that turns states and attributes into numbers, so
"unavailable" and "unknown" are handled the same everywhere: as None.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State

from .settings import Settings

_INVALID = (None, STATE_UNAVAILABLE, STATE_UNKNOWN, "")

DEFAULT_SPA_LIMITS = (26.5, 40.0)


def as_float(value: Any) -> float | None:
    if value in _INVALID or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class TubReader:
    def __init__(self, hass: HomeAssistant, settings: Settings) -> None:
        self._hass = hass
        self._s = settings

    def _state(self, entity_id: str | None) -> State | None:
        return self._hass.states.get(entity_id) if entity_id else None

    @staticmethod
    def attr(state: State | None, name: str) -> Any:
        return state.attributes.get(name) if state is not None else None

    @staticmethod
    def attr_float(state: State | None, name: str) -> float | None:
        return as_float(TubReader.attr(state, name))

    # --- circulation ----------------------------------------------------------

    def circulation_on(self) -> bool:
        state = self._state(self._s.circulation)
        return state is not None and state.state == STATE_ON

    def circulation_on_for(self, now: datetime) -> timedelta | None:
        state = self._state(self._s.circulation)
        if state is None or state.state != STATE_ON:
            return None
        return now - state.last_changed

    def filter_cycle(self) -> int | None:
        for number, entity_id in (
            (1, self._s.filter_cycle_1),
            (2, self._s.filter_cycle_2),
        ):
            state = self._state(entity_id)
            if state is not None and state.state == STATE_ON:
                return number
        return None

    # --- spa ------------------------------------------------------------------

    def _spa(self) -> State | None:
        return self._state(self._s.spa)

    def spa_available(self) -> bool:
        state = self._spa()
        return state is not None and state.state not in _INVALID

    def hvac_action(self) -> str | None:
        value = self.attr(self._spa(), "hvac_action")
        return value if isinstance(value, str) else None

    def spa_temperature(self) -> float | None:
        return self.attr_float(self._spa(), "current_temperature")

    def setpoint(self) -> float | None:
        return self.attr_float(self._spa(), "temperature")

    def spa_limits(self) -> tuple[float, float]:
        spa = self._spa()
        low = self.attr_float(spa, "min_temp")
        high = self.attr_float(spa, "max_temp")
        return (
            low if low is not None else DEFAULT_SPA_LIMITS[0],
            high if high is not None else DEFAULT_SPA_LIMITS[1],
        )

    # --- heat pump ------------------------------------------------------------

    def _hp(self) -> State | None:
        return self._state(self._s.heat_pump)

    def hp_hvac_mode(self) -> str | None:
        state = self._hp()
        return None if state is None or state.state in _INVALID else state.state

    def hp_preset(self) -> str | None:
        value = self.attr(self._hp(), "preset_mode")
        return value if isinstance(value, str) else None

    def hp_target(self) -> float | None:
        return self.attr_float(self._hp(), "temperature")

    def hp_power(self) -> float | None:
        state = self._state(self._s.heat_pump_power)
        return as_float(state.state) if state is not None else None

    # --- heater ---------------------------------------------------------------

    def heater_on(self) -> bool:
        state = self._state(self._s.heater)
        return state is not None and state.state == STATE_ON

    def heater_power(self) -> float | None:
        state = self._state(self._s.heater_power)
        return as_float(state.state) if state is not None else None

    # --- outdoor --------------------------------------------------------------

    def outdoor_value(self, state: State | None) -> float | None:
        """Outdoor temperature in a given state of the outdoor entity."""
        if state is None or state.entity_id != self._s.outdoor:
            return None
        if self._s.outdoor_attribute:
            return self.attr_float(state, self._s.outdoor_attribute)
        return as_float(state.state)

    def outdoor_temperature(self) -> float | None:
        return self.outdoor_value(self._state(self._s.outdoor))
