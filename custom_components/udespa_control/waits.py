"""Waits on Home Assistant's clock.

Built on async_call_later rather than asyncio.sleep, so tests can move time
with freezer + async_fire_time_changed, and so cancelling a job cancels its
timers with it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import async_call_later, async_track_state_change_event


async def async_sleep(hass: HomeAssistant, seconds: float) -> None:
    """Sleep on HA's clock. Cancelling the caller cancels the timer."""
    future: asyncio.Future[None] = hass.loop.create_future()

    @callback
    def _wake(_now: Any) -> None:
        if not future.done():
            future.set_result(None)

    cancel = async_call_later(hass, seconds, _wake)
    try:
        await future
    finally:
        cancel()


async def async_wait_for_state(
    hass: HomeAssistant,
    entity_id: str,
    predicate: Callable[[State | None], bool],
    *,
    hold: float,
    timeout: float,
) -> bool:
    """Wait until predicate(state) has held for `hold` seconds; False on timeout."""
    future: asyncio.Future[bool] = hass.loop.create_future()
    cancel_hold: CALLBACK_TYPE | None = None

    @callback
    def _finish(result: bool) -> None:
        if not future.done():
            future.set_result(result)

    @callback
    def _held(_now: Any) -> None:
        _finish(True)

    @callback
    def _evaluate(state: State | None) -> None:
        nonlocal cancel_hold
        if predicate(state):
            if cancel_hold is None:
                cancel_hold = async_call_later(hass, hold, _held)
        elif cancel_hold is not None:
            cancel_hold()
            cancel_hold = None

    @callback
    def _changed(event: Event[EventStateChangedData]) -> None:
        _evaluate(event.data["new_state"])

    @callback
    def _timed_out(_now: Any) -> None:
        _finish(False)

    unsub_state = async_track_state_change_event(hass, [entity_id], _changed)
    cancel_timeout = async_call_later(hass, timeout, _timed_out)
    _evaluate(hass.states.get(entity_id))
    try:
        return await future
    finally:
        unsub_state()
        cancel_timeout()
        if cancel_hold is not None:
            cancel_hold()
