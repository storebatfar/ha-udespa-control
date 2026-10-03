"""Pipe cleaning (D16-D18): two pump cycles, then the status comes back."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from homeassistant.const import STATE_ON
from homeassistant.core import State

from .const import CLEANING_OFF_HOLD_S, DOMAIN, CleaningPhase, Status
from .rules import fmt_num, restorable_status
from .waits import async_wait_for_state

if TYPE_CHECKING:
    from .controller import UdespaController


def _pump_stopped(state: State | None) -> bool:
    return state is None or state.state != STATE_ON


class Cleaning:
    def __init__(self, controller: UdespaController) -> None:
        self._ctl = controller
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def async_start(self) -> None:
        """D16. A second press restarts at Cyklus 1, as `mode: restart` did."""
        ctl = self._ctl
        await self._async_cancel()
        if ctl.state.status is not Status.CLEANING:
            # Not on a double press, or "Rengøring" would be saved and stuck.
            ctl.state.saved_status = ctl.state.status.value
        ctl.set_status(Status.CLEANING, "rengøring startet")
        self._task = ctl.hass.async_create_background_task(
            self._async_run(), f"{DOMAIN} cleaning"
        )

    async def _async_run(self) -> None:
        ctl = self._ctl
        s = ctl.settings
        for phase in (CleaningPhase.CYCLE_1, CleaningPhase.CYCLE_2):
            ctl.set_cleaning_phase(phase)
            await ctl.actuators.cleaning_pump(True, f"rengøring {phase.lower()}")
            # The spa stops the pump itself after 15 min; the cap is a backstop.
            finished = await async_wait_for_state(
                ctl.hass,
                s.cleaning_pump,
                _pump_stopped,
                hold=CLEANING_OFF_HOLD_S,
                timeout=s.cleaning_max_min * 60,
            )
            if not finished:
                ctl.record(
                    f"Rengøring {phase.lower()}: pumpen kørte stadig efter "
                    f"{fmt_num(s.cleaning_max_min)} min, fortsætter"
                )
        self._finish("rengøring færdig")

    async def async_stop(self) -> None:
        """D17. Cancel first, so the pump going off can't advance to Cyklus 2."""
        await self._async_cancel()
        await self._ctl.actuators.cleaning_pump(False, "rengøring stoppet")
        self._finish("rengøring stoppet")

    def recover_after_restart(self) -> None:
        """D18: a restart killed the cycle; don't leave the status on Rengøring."""
        state = self._ctl.state
        if state.cleaning_phase is not CleaningPhase.IDLE or state.status is Status.CLEANING:
            self._finish("genstart under rengøring")

    async def async_shutdown(self) -> None:
        await self._async_cancel()

    def _finish(self, reason: str) -> None:
        ctl = self._ctl
        ctl.set_cleaning_phase(CleaningPhase.IDLE)
        saved = restorable_status(ctl.state.saved_status)
        ctl.state.saved_status = None
        if ctl.state.status is Status.CLEANING:
            ctl.restore_status(saved, reason)

    async def _async_cancel(self) -> None:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
