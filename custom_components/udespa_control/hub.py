"""Hub copies: the tub's data from other integrations, gathered on the Udespa device.

Each copy follows its own source entity, not the controller, and takes its unit
and classes from it. Climate attributes carry no unit, so the three copies read
from an attribute are fixed to °C.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import Event, EventStateChangedData, State, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util.unit_conversion import PowerConverter

from .const import (
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
    CONF_SRC_ONDILO_TEMPERATURE,
    CONF_SRC_WATER_ORP,
    CONF_SRC_WATER_PH,
    CONF_SRC_WATER_TDS,
    DEMAND_LABELS,
)
from .controller import UdespaController
from .entity import UdespaEntity
from .reader import TubReader, as_float
from .rules import demand_label, round_power, temperature_rise
from .settings import Settings

_INVALID = (STATE_UNAVAILABLE, STATE_UNKNOWN)


def _usable(state: State | None) -> bool:
    return state is not None and state.state not in _INVALID


def _source(key: str) -> Callable[[Settings], str | None]:
    return lambda settings: settings.sources.get(key)


@dataclass(frozen=True)
class HubCopy:
    """One copied value: where it comes from and how it is shown."""

    key: str
    source: Callable[[Settings], str | None]
    attribute: str | None = None  # read this attribute (°C) instead of the state
    power: bool = False  # whole watts
    diagnostic: bool = False


HUB_COPIES: tuple[HubCopy, ...] = (
    HubCopy("water_temperature", lambda s: s.spa, attribute="current_temperature"),
    HubCopy("setpoint", lambda s: s.spa, attribute="temperature"),
    HubCopy("hp_inlet", lambda s: s.heat_pump, attribute="current_temperature"),
    HubCopy("hp_outlet", _source(CONF_SRC_HP_OUTLET)),
    HubCopy("hp_compressor", _source(CONF_SRC_HP_COMPRESSOR)),
    HubCopy("hp_power", lambda s: s.heat_pump_power, power=True),
    HubCopy("hp_ambient", _source(CONF_SRC_HP_AMBIENT)),
    HubCopy("heater_power", lambda s: s.heater_power, power=True),
    HubCopy("circulation_power", _source(CONF_SRC_CIRCULATION_POWER), power=True),
    HubCopy("hp_coil", _source(CONF_SRC_HP_COIL), diagnostic=True),
    HubCopy("hp_exhaust", _source(CONF_SRC_HP_EXHAUST), diagnostic=True),
    HubCopy("hp_ipm", _source(CONF_SRC_HP_IPM), diagnostic=True),
    HubCopy("hp_fan", _source(CONF_SRC_HP_FAN), diagnostic=True),
    HubCopy("hp_eev", _source(CONF_SRC_HP_EEV), diagnostic=True),
    HubCopy(
        "hp_compressor_current", _source(CONF_SRC_HP_COMPRESSOR_CURRENT), diagnostic=True
    ),
    HubCopy("water_ph", _source(CONF_SRC_WATER_PH)),
    HubCopy("water_orp", _source(CONF_SRC_WATER_ORP)),
    HubCopy("water_tds", _source(CONF_SRC_WATER_TDS)),
    HubCopy("ondilo_temperature", _source(CONF_SRC_ONDILO_TEMPERATURE)),
    HubCopy("ondilo_battery", _source(CONF_SRC_ONDILO_BATTERY)),
)

RISE_KEY = "hp_temperature_rise"


def _device_class(value: Any) -> SensorDeviceClass | None:
    try:
        return SensorDeviceClass(value)
    except ValueError:
        return None


def _state_class(value: Any) -> SensorStateClass | None:
    try:
        return SensorStateClass(value)
    except ValueError:
        return None


class _SourceFollower(UdespaEntity):
    """Follows its source entities instead of the controller."""

    _sources: tuple[str, ...] = ()

    async def async_added_to_hass(self) -> None:
        self._refresh()
        self.async_on_remove(
            async_track_state_change_event(self.hass, list(self._sources), self._changed)
        )

    @callback
    def _changed(self, _event: Event[EventStateChangedData]) -> None:
        self._refresh()
        self.async_write_ha_state()

    def _refresh(self) -> None:
        raise NotImplementedError


class HubCopySensor(_SourceFollower, SensorEntity):
    def __init__(self, controller: UdespaController, copy: HubCopy, source: str) -> None:
        super().__init__(controller, copy.key)
        self._copy = copy
        self._sources = (source,)
        if copy.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if copy.attribute is not None:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_state_class = SensorStateClass.MEASUREMENT

    def _refresh(self) -> None:
        state = self.hass.states.get(self._sources[0])
        self._attr_available = _usable(state)
        if not self._attr_available:
            self._attr_native_value = None
            return
        copy = self._copy
        if copy.attribute is not None:
            self._attr_native_value = as_float(state.attributes.get(copy.attribute))
            return
        attrs = state.attributes
        self._attr_native_unit_of_measurement = attrs.get("unit_of_measurement")
        self._attr_device_class = _device_class(attrs.get("device_class"))
        self._attr_state_class = _state_class(attrs.get("state_class"))
        value = as_float(state.state)
        if copy.power:
            unit = self._attr_native_unit_of_measurement
            if value is not None and unit in PowerConverter.VALID_UNITS:
                # Whole watts whatever the meter reports in, so a kW meter
                # doesn't round to whole kilowatts.
                # round(…, 6): 1.2345 kW is 1234.4999… W in floating point.
                value = round(PowerConverter.convert(value, unit, UnitOfPower.WATT), 6)
                self._attr_native_unit_of_measurement = UnitOfPower.WATT
                self._attr_device_class = SensorDeviceClass.POWER
            value = round_power(value)
        self._attr_native_value = value


class HubDemandSensor(_SourceFollower, SensorEntity):
    """The spa's heat demand in words."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, controller: UdespaController) -> None:
        super().__init__(controller, "heat_demand")
        self._sources = (controller.settings.spa,)
        self._attr_options = list(DEMAND_LABELS.values())

    def _refresh(self) -> None:
        state = self.hass.states.get(self._sources[0])
        self._attr_available = _usable(state)
        self._attr_native_value = (
            demand_label(state.attributes.get("hvac_action"))
            if self._attr_available
            else None
        )


class HubRiseSensor(_SourceFollower, SensorEntity):
    """Outlet minus inlet: is the heat pump actually warming the water?"""

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, controller: UdespaController, outlet: str) -> None:
        super().__init__(controller, RISE_KEY)
        self._sources = (controller.settings.heat_pump, outlet)

    def _refresh(self) -> None:
        heat_pump = self.hass.states.get(self._sources[0])
        outlet = self.hass.states.get(self._sources[1])
        inlet_c = (
            TubReader.attr_float(heat_pump, "current_temperature")
            if _usable(heat_pump)
            else None
        )
        outlet_c = as_float(outlet.state) if _usable(outlet) else None
        rise = temperature_rise(inlet_c, outlet_c)
        self._attr_available = rise is not None
        self._attr_native_value = rise


class HubCirculationSensor(_SourceFollower, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, controller: UdespaController) -> None:
        super().__init__(controller, "circulation")
        self._sources = (controller.settings.circulation,)

    def _refresh(self) -> None:
        state = self.hass.states.get(self._sources[0])
        self._attr_available = _usable(state)
        self._attr_is_on = state.state == STATE_ON if self._attr_available else None
