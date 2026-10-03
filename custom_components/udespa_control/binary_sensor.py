"""An open heat-pump failure (replaces input_boolean.udespa_varmepumpe_fejl)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UdespaConfigEntry
from .controller import UdespaController
from .entity import UdespaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: UdespaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([HeatPumpFailureSensor(entry.runtime_data)])


class HeatPumpFailureSensor(UdespaEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, controller: UdespaController) -> None:
        super().__init__(controller, "heat_pump_failure")

    @property
    def is_on(self) -> bool:
        return self.controller.failure_open
