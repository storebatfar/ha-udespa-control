"""Rest temperature: the setpoint the tub rests at between uses."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UdespaConfigEntry
from .controller import UdespaController
from .entity import UdespaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: UdespaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([RestTemperatureNumber(entry.runtime_data)])


class RestTemperatureNumber(UdespaEntity, NumberEntity):
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 26.5
    _attr_native_max_value = 40.0
    _attr_native_step = 0.5
    _attr_mode = NumberMode.SLIDER

    def __init__(self, controller: UdespaController) -> None:
        super().__init__(controller, "rest_temperature")

    @property
    def native_value(self) -> float:
        return self.controller.state.rest_temperature

    async def async_set_native_value(self, value: float) -> None:
        await self.controller.async_set_rest_temperature(value)
