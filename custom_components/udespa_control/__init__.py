"""Udespa Control: the Udespa hot-tub rules in one integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, SUGGESTED_SOURCES
from .controller import UdespaController
from .storage import UdespaStore

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type UdespaConfigEntry = ConfigEntry[UdespaController]


async def async_setup_entry(hass: HomeAssistant, entry: UdespaConfigEntry) -> bool:
    controller = UdespaController(hass, entry)
    await controller.async_setup()
    entry.runtime_data = controller
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: UdespaConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: UdespaConfigEntry) -> None:
    """Deleting the integration deletes its stored state too."""
    await UdespaStore(hass, entry.entry_id).async_remove()


async def async_migrate_entry(hass: HomeAssistant, entry: UdespaConfigEntry) -> bool:
    """1.1 → 1.2: fill the new data sources with today's entities that exist.

    Looks in the entity registry as well as the state machine: at HA start the
    source integrations may not have loaded yet, so their states can be missing.
    A source already chosen is never overwritten. A minor bump, so 2026.10.1
    still loads the entry after a rollback; a future major version is refused.
    """
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        registry = er.async_get(hass)
        found = {
            key: entity_id
            for key, entity_id in SUGGESTED_SOURCES.items()
            if registry.async_get(entity_id) is not None
            or hass.states.get(entity_id) is not None
        }
        hass.config_entries.async_update_entry(
            entry, data={**found, **entry.data}, minor_version=2
        )
    return True
