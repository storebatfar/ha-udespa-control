"""Heat-pump mode, two-way with the heat pump's preset."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UdespaConfigEntry
from .const import Mode
from .controller import UdespaController
from .entity import UdespaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: UdespaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([HeatPumpModeSelect(entry.runtime_data)])


class HeatPumpModeSelect(UdespaEntity, SelectEntity):
    def __init__(self, controller: UdespaController) -> None:
        super().__init__(controller, "heat_pump_mode")
        self._attr_options = [mode.value for mode in Mode]

    @property
    def current_option(self) -> str | None:
        mode = self.controller.mode
        return mode.value if mode is not None else None

    async def async_select_option(self, option: str) -> None:
        await self.controller.async_select_mode(Mode(option))
