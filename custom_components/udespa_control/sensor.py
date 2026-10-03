"""Status, cleaning phase, timers, heating and the latest decision."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UdespaConfigEntry
from .const import CONF_SRC_HP_OUTLET, DOMAIN, CleaningPhase, Status, SyncStatus, Timer
from .controller import UdespaController
from .entity import UdespaEntity
from .hub import HUB_COPIES, RISE_KEY, HubCopySensor, HubDemandSensor, HubRiseSensor


async def async_setup_entry(
    hass: HomeAssistant, entry: UdespaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller = entry.runtime_data
    settings = controller.settings
    entities: list[SensorEntity] = [
        StatusSensor(controller),
        CleaningPhaseSensor(controller),
        TimerSensor(controller, Timer.FILTER),
        TimerSensor(controller, Timer.BATH_WATER),
        HeatingSensor(controller),
        LastActionSensor(controller),
        SyncStatusSensor(controller),
        HubDemandSensor(controller),
    ]
    for copy in HUB_COPIES:
        if source := copy.source(settings):
            entities.append(HubCopySensor(controller, copy, source))
        else:
            _forget(hass, entry, copy.key)
    if outlet := settings.sources.get(CONF_SRC_HP_OUTLET):
        entities.append(HubRiseSensor(controller, outlet))
    else:
        _forget(hass, entry, RISE_KEY)
    async_add_entities(entities)


def _forget(hass: HomeAssistant, entry: UdespaConfigEntry, key: str) -> None:
    """An emptied source: drop its copy from the registry too."""
    registry = er.async_get(hass)
    if entity_id := registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{key}"):
        registry.async_remove(entity_id)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


class StatusSensor(UdespaEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    def __init__(self, controller: UdespaController) -> None:
        super().__init__(controller, "status")
        self._attr_options = [status.value for status in Status]

    @property
    def native_value(self) -> str:
        return self.controller.status.value


class CleaningPhaseSensor(UdespaEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    def __init__(self, controller: UdespaController) -> None:
        super().__init__(controller, "cleaning_phase")
        self._attr_options = [phase.value for phase in CleaningPhase]

    @property
    def native_value(self) -> str:
        return self.controller.state.cleaning_phase.value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "started_at": _iso(self.controller.state.cleaning_started_at),
            "estimate_minutes": self.controller.settings.cleaning_estimate_min,
        }


class TimerSensor(UdespaEntity, SensorEntity):
    """Whole days since the last reset."""

    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_suggested_display_precision = 0

    def __init__(self, controller: UdespaController, timer: Timer) -> None:
        super().__init__(controller, f"{timer.value}_timer")
        self._timer = timer

    @property
    def native_value(self) -> int | None:
        return self.controller.timer_days(self._timer)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"reset_at": _iso(self.controller.timer_reset_at(self._timer))}


class HeatingSensor(UdespaEntity, SensorEntity):
    """Same values as the old "Udespa Varmer" template."""

    def __init__(self, controller: UdespaController) -> None:
        super().__init__(controller, "heating")

    @property
    def native_value(self) -> str:
        return "Varmer" if self.controller.heating else "Varmer ikke"


class LastActionSensor(UdespaEntity, SensorEntity):
    def __init__(self, controller: UdespaController) -> None:
        super().__init__(controller, "last_action")

    @property
    def native_value(self) -> str | None:
        return self.controller.last_action

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"at": _iso(self.controller.last_action_at)}


class SyncStatusSensor(UdespaEntity, SensorEntity):
    """A9′: is the heat pump's target the spa setpoint plus the offset?"""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, controller: UdespaController) -> None:
        super().__init__(controller, "temperature_sync")
        self._attr_options = [status.value for status in SyncStatus]

    @property
    def native_value(self) -> str:
        return self.controller.sync_status().value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.controller.sync_attributes()
