"""B12′: the heat pump's mode, sent and verified.

The heat pump can drop a preset change it receives as it powers on (seen
2026-10-04 11:18: "smart" sent with "heat", "quick" reported 6 s later). So a
mode is sent, checked every MODE_CHECK_S and resent up to MODE_ATTEMPTS sends
in total; it counts as confirmed once it holds on two checks in a row. Within that check window a different report is a dropped command;
outside it, a change made on the heat pump itself is adopted, not fought.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Coroutine
from typing import Any

from homeassistant.core import HomeAssistant

from .actuators import Actuators
from .const import DOMAIN, MODE_ATTEMPTS, MODE_CHECK_S, WATCH_ONLY_PREFIX, Mode
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
        self._checking: Mode | None = None  # the mode the running check is for
        self._deliberate = False  # sticky for the running check

    @property
    def in_window(self) -> bool:
        return self._task is not None and not self._task.done()

    def apply(self, mode: Mode, reason: str, *, deliberate: bool = False) -> None:
        """Want this mode now. A newer intent replaces a check for another mode."""
        self.wanted = mode
        if self.in_window and self._checking is mode:
            # Already being sent and verified: keep that check, don't restart it
            # on an optimistic match. A deliberate pick stays deliberate.
            self._deliberate = self._deliberate or deliberate
            return
        if not deliberate and self._reader.hp_preset() == self._s.presets[mode]:
            self._cancel()
            return
        self._start(mode, deliberate, self._async_run(reason, send_first=True))

    def reassert(self, reason: str) -> None:
        """After switching on: check the wanted mode survived, resend if not."""
        if self.wanted is None:
            return
        if self.in_window and self._checking is self.wanted:
            return  # the running check already verifies it
        self._start(self.wanted, False, self._async_run(reason, send_first=False))

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
        self._checking = None

    def _start(
        self, mode: Mode, deliberate: bool, coro: Coroutine[Any, Any, None]
    ) -> None:
        self._cancel()
        self._checking = mode
        self._deliberate = deliberate
        self._task = self._hass.async_create_background_task(coro, f"{DOMAIN} mode")

    async def _send(self, preset: str, reason: str) -> None:
        await self._actuators.heat_pump_preset(
            preset, reason, deliberate=self._deliberate
        )

    async def _async_run(self, reason: str, *, send_first: bool) -> None:
        mode = self._checking
        preset = self._s.presets[mode]
        sends = 0
        if send_first:
            sends = 1
            await self._send(preset, reason)
        held = 0
        while True:
            await async_sleep(self._hass, MODE_CHECK_S)
            if self._reader.hp_preset() == preset:
                # The first match may still be tuya_local's optimistic write; the
                # mode only counts once it holds on two checks in a row.
                held += 1
                if held >= 2:
                    return
                continue
            held = 0
            if sends >= MODE_ATTEMPTS:
                break
            sends += 1
            await self._send(preset, reason if sends == 1 else f"{reason} (forsøg {sends})")
        if self._actuators.would_send(deliberate=self._deliberate):
            self._record(f"Varmepumpen afviste {mode} efter {MODE_ATTEMPTS} forsøg")
        else:
            self._record(
                f"{WATCH_ONLY_PREFIX}Varmepumpen står ikke i {mode} "
                f"efter {MODE_ATTEMPTS} forsøg"
            )
