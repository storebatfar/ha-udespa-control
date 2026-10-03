"""Waits that follow Home Assistant's (test-controllable) clock."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant

from custom_components.udespa_control.waits import async_sleep, async_wait_for_state

from .common import advance, settle

PUMP = "fan.pump"


def _not_on(state):
    return state is None or state.state != "on"


async def test_sleep_wakes_after_the_delay(hass: HomeAssistant, freezer: FrozenDateTimeFactory):
    woke: list[bool] = []

    async def sleeper():
        await async_sleep(hass, 15)
        woke.append(True)

    hass.async_create_background_task(sleeper(), "sleeper")
    await advance(hass, freezer, 14)
    assert woke == []
    await advance(hass, freezer, 1)
    assert woke == [True]


async def test_cancelled_sleep_leaves_no_timer(hass: HomeAssistant, freezer: FrozenDateTimeFactory):
    task = hass.async_create_background_task(async_sleep(hass, 60), "sleeper")
    await settle(hass)
    task.cancel()
    await settle(hass)
    assert task.cancelled()
    # A lingering timer would fail this test at teardown.


async def test_wait_returns_true_once_the_state_has_held(hass: HomeAssistant, freezer: FrozenDateTimeFactory):
    hass.states.async_set(PUMP, "on")
    result: list[bool] = []

    async def waiter():
        result.append(await async_wait_for_state(hass, PUMP, _not_on, hold=5, timeout=600))

    hass.async_create_background_task(waiter(), "waiter")
    await advance(hass, freezer, 30)
    hass.states.async_set(PUMP, "off")
    await advance(hass, freezer, 4)
    assert result == []
    await advance(hass, freezer, 1)
    assert result == [True]


async def test_a_flicker_restarts_the_hold(hass: HomeAssistant, freezer: FrozenDateTimeFactory):
    hass.states.async_set(PUMP, "on")
    result: list[bool] = []

    async def waiter():
        result.append(await async_wait_for_state(hass, PUMP, _not_on, hold=5, timeout=600))

    hass.async_create_background_task(waiter(), "waiter")
    await settle(hass)
    hass.states.async_set(PUMP, "off")
    await advance(hass, freezer, 3)
    hass.states.async_set(PUMP, "on")
    await advance(hass, freezer, 1)
    hass.states.async_set(PUMP, "off")
    await advance(hass, freezer, 4)
    assert result == []
    await advance(hass, freezer, 1)
    assert result == [True]


async def test_wait_times_out(hass: HomeAssistant, freezer: FrozenDateTimeFactory):
    hass.states.async_set(PUMP, "on")
    result: list[bool] = []

    async def waiter():
        result.append(await async_wait_for_state(hass, PUMP, _not_on, hold=5, timeout=60))

    hass.async_create_background_task(waiter(), "waiter")
    await advance(hass, freezer, 60, step=5)
    assert result == [False]


async def test_already_true_counts_from_the_start(hass: HomeAssistant, freezer: FrozenDateTimeFactory):
    hass.states.async_set(PUMP, "off")
    result: list[bool] = []

    async def waiter():
        result.append(await async_wait_for_state(hass, PUMP, _not_on, hold=5, timeout=60))

    hass.async_create_background_task(waiter(), "waiter")
    await advance(hass, freezer, 5)
    assert result == [True]
