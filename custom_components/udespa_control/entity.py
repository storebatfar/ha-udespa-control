"""Shared base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .controller import UdespaController


class UdespaEntity(Entity):
    """Holds no logic: entities are views over the controller, pushed on change."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: UdespaController, key: str) -> None:
        self.controller = controller
        self._attr_translation_key = key
        self._attr_unique_id = f"{controller.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller.entry.entry_id)},
            name=controller.entry.title,
            manufacturer="storebatfar",
            model="Udespa Control",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.controller.add_listener(self.async_write_ha_state))
