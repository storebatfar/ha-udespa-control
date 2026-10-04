"""B12′: the heat pump's mode, sent and verified.

The heat pump can drop a preset change it receives as it powers on (seen
2026-10-04 11:18: "smart" sent with "heat", "quick" reported 6 s later). So a
mode is sent, checked after MODE_CHECK_S and resent up to MODE_ATTEMPTS sends
in total. Within that check window a different report is a dropped command;
outside it, a change made on the heat pump itself is adopted, not fought.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Coroutine
from typing import Any

from homeassistant.core import HomeAssistant

from .actuators import Actuators
from .const import DOMAIN, MODE_ATTEMPTS, MODE_CHECK_S, Mode
from .reader import TubReader
from .rules import mode_for_preset
from .settings import Settings
from .waits import async_sleep


class ModeKeeper:
    def __init__(
        self,
        hass: HomeAssistant,
        settings: Settings,
        reader: TubReader,
        actuators: Actuators,
        record: Callable[[str], None],
    ) -> None:
        self._hass = hass
        self._s = settings
        self._reader = reader
        self._actuators = actuators
        self._record = record
        self.wanted: Mode | None = None  # unknown after a restart
        self._task: asyncio.Task[None] | None = None

    @property
    def in_window(self) -> bool:
        return self._task is not None and not self._task.done()

    def apply(self, mode: Mode, reason: str, *, deliberate: bool = False) -> None:
        """Want this mode now. A newer intent always replaces an older check."""
        self.wanted = mode
        if not deliberate and self._reader.hp_preset() == self._s.presets[mode]:
            self._cancel()
            return
        self._start(self._async_run(mode, reason, deliberate, send_first=True))

    def reassert(self, reason: str) -> None:
        """After switching on: check the wanted mode survived, resend if not."""
        if self.wanted is None:
            return
        self._start(self._async_run(self.wanted, reason, False, send_first=False))

    def adopt(self, preset: str | None) -> None:
        """A change made on the heat pump itself, outside a check window."""
        if self.in_window:
            return
        if (mode := mode_for_preset(preset, self._s.presets)) is not None:
            self.wanted = mode

    async def async_shutdown(self) -> None:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _cancel(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None

    def _start(self, coro: Coroutine[Any, Any, None]) -> None:
        self._cancel()
        self._task = self._hass.async_create_background_task(coro, f"{DOMAIN} mode")

    async def _async_run(
        self, mode: Mode, reason: str, deliberate: bool, *, send_first: bool
    ) -> None:
        preset = self._s.presets[mode]
        if send_first:
            await self._actuators.heat_pump_preset(preset, reason, deliberate=deliberate)
        for check in range(MODE_ATTEMPTS):
            await async_sleep(self._hass, MODE_CHECK_S)
            if self._reader.hp_preset() == preset:
                return
            if check < MODE_ATTEMPTS - 1:
                await self._actuators.heat_pump_preset(
                    preset, f"{reason} (forsøg {check + 2})", deliberate=deliberate
                )
        self._record(f"Varmepumpen afviste {mode} efter {MODE_ATTEMPTS} forsøg")
