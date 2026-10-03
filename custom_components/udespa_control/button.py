"""Buttons: setpoint up/down, cleaning start/stop, timer resets."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UdespaConfigEntry
from .const import SETPOINT_STEP, Timer
from .controller import UdespaController
from .entity import UdespaEntity


@dataclass(frozen=True, kw_only=True)
class UdespaButtonDescription(ButtonEntityDescription):
    press: Callable[[UdespaController], Awaitable[None]]


BUTTONS: tuple[UdespaButtonDescription, ...] = (
    UdespaButtonDescription(
        key="raise_temperature",
        press=lambda c: c.async_nudge_setpoint(SETPOINT_STEP),
    ),
    UdespaButtonDescription(
        key="lower_temperature",
        press=lambda c: c.async_nudge_setpoint(-SETPOINT_STEP),
    ),
    UdespaButtonDescription(key="start_cleaning", press=lambda c: c.async_start_cleaning()),
    UdespaButtonDescription(key="stop_cleaning", press=lambda c: c.async_stop_cleaning()),
    UdespaButtonDescription(
        key="reset_filter_timer", press=lambda c: c.async_reset_timer(Timer.FILTER)
    ),
    UdespaButtonDescription(
        key="reset_bath_water_timer",
        press=lambda c: c.async_reset_timer(Timer.BATH_WATER),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: UdespaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(UdespaButton(entry.runtime_data, d) for d in BUTTONS)


class UdespaButton(UdespaEntity, ButtonEntity):
    entity_description: UdespaButtonDescription

    def __init__(
        self, controller: UdespaController, description: UdespaButtonDescription
    ) -> None:
        super().__init__(controller, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        await self.entity_description.press(self.controller)
