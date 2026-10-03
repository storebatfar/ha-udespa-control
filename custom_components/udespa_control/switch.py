"""Frostsikring and Aktiv styring. Both are kept in the integration's storage."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UdespaConfigEntry
from .controller import UdespaController
from .entity import UdespaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: UdespaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller = entry.runtime_data
    async_add_entities([FrostProtectionSwitch(controller), ActiveControlSwitch(controller)])


class FrostProtectionSwitch(UdespaEntity, SwitchEntity):
    """C14 on/off. Replaces toggling the old automation from the dashboards."""

    def __init__(self, controller: UdespaController) -> None:
        super().__init__(controller, "frost_protection")

    @property
    def is_on(self) -> bool:
        return self.controller.state.frost_protection

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.controller.async_set_frost_protection(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.controller.async_set_frost_protection(False)


class ActiveControlSwitch(UdespaEntity, SwitchEntity):
    """Off = watch only (E20). Off on first install."""

    def __init__(self, controller: UdespaController) -> None:
        super().__init__(controller, "active_control")

    @property
    def is_on(self) -> bool:
        return self.controller.state.active

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.controller.async_set_active(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.controller.async_set_active(False)
