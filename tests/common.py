"""Test helpers shared by every module."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed


async def settle(hass: HomeAssistant) -> None:
    """Let background jobs run until they block on their next wait.

    async_block_till_done does not wait for background tasks (that is the
    point of them), so give the loop a few turns first.
    """
    for _ in range(20):
        await asyncio.sleep(0)
    await hass.async_block_till_done()


async def advance(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    seconds: float,
    step: float = 1.0,
) -> None:
    """Move the clock forward, firing timers and letting jobs react each step.

    Settles first: state-change listeners run on the next loop turn, so an
    event set just before advance() must be handled at the current time,
    not one tick later.
    """
    await settle(hass)
    remaining = float(seconds)
    while remaining > 1e-9:
        tick = min(step, remaining)
        freezer.tick(timedelta(seconds=tick))
        async_fire_time_changed(hass)
        await settle(hass)
        remaining -= tick
