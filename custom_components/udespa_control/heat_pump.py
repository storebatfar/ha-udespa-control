"""The heat-pump job (A1-A7): on, off or head start, verified on power.

One job runs at a time. start() cancels the running job and starts its own,
which is the old automation's `mode: restart`. The controller only calls
start() when a rule produced a decision, so a trigger that leads nowhere never
cancels a job.

The heat pump's own state is never evidence: tuya_local writes it
optimistically. Only power on the meter confirms anything.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable

from homeassistant.core import HomeAssistant

from .actuators import Actuators
from .const import (
    DOMAIN,
    HEAD_START_OFF_ATTEMPTS,
    HEAD_START_OFF_SETTLE_S,
    SPA_CALLING,
    VERIFY_POLL_S,
    BackupKind,
    HeatAction,
)
from .reader import TubReader
from .rules import (
    HEAD_START_OFF_FAILED_ALERT,
    Decision,
    backup_alert,
    backup_needed,
    fmt_c,
    fmt_num,
    heat_pump_running,
    heat_pump_stopped,
    heater_running,
    off_failed_alert,
)
from .settings import Settings
from .waits import async_sleep


class HeatPump:
    def __init__(
        self,
        hass: HomeAssistant,
        settings: Settings,
        reader: TubReader,
        actuators: Actuators,
        *,
        record: Callable[[str], None],
        failure_open: Callable[[], bool],
        set_failure: Callable[[bool], None],
    ) -> None:
        self._hass = hass
        self._s = settings
        self._reader = reader
        self._actuators = actuators
        self._record = record
        self._failure_open = failure_open
        self._set_failure = set_failure
        self._job: asyncio.Task[None] | None = None
        self._watchdog: asyncio.Task[None] | None = None

    @property
    def busy(self) -> bool:
        return self._job is not None and not self._job.done()

    def start(self, decision: Decision) -> None:
        """Replace whatever job is running with this decision's job."""
        if self._job is not None:
            self._job.cancel()
        job = {
            HeatAction.ON: self._async_on,
            HeatAction.OFF: self._async_off,
            HeatAction.HEAD_START: self._async_head_start,
        }[decision.action]
        self._job = self._hass.async_create_background_task(
            job(decision.reason), f"{DOMAIN} heat pump {decision.action}"
        )

    def start_watchdog_backup(self, reason: str) -> None:
        """A6. Independent of the job, like the old separate automation."""
        if self._watchdog is not None and not self._watchdog.done():
            return
        self._record(f"Vagthund: {reason}")
        self._watchdog = self._hass.async_create_background_task(
            self.async_backup(BackupKind.WATCHDOG), f"{DOMAIN} watchdog backup"
        )

    async def async_shutdown(self) -> None:
        for task in (self._job, self._watchdog):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._job = None
        self._watchdog = None

    # --- jobs ---------------------------------------------------------------

    def _running(self) -> bool:
        return heat_pump_running(self._reader.hp_power(), self._s.hp_on_w)

    def _stopped(self) -> bool:
        return heat_pump_stopped(self._reader.hp_power(), self._s.hp_off_w)

    @staticmethod
    def _attempt_reason(reason: str, attempt: int) -> str:
        return reason if attempt == 0 else f"{reason} (forsøg {attempt + 1})"

    async def _async_on(self, reason: str) -> None:
        for attempt in range(self._s.verify_attempts):
            if self._running():
                if attempt == 0:
                    self._record(f"Varmepumpe kører allerede: {reason}")
                await self.async_recover()
                return
            if attempt == 0 or self._reader.hp_hvac_mode() != "heat":
                await self._actuators.heat_pump_mode(
                    "heat", self._attempt_reason(reason, attempt)
                )
            await async_sleep(self._hass, VERIFY_POLL_S)

        if self._running():
            await self.async_recover()
            return
        if backup_needed(
            self._reader.spa_temperature(), self._reader.setpoint(), self._s.backup_margin
        ):
            await self.async_backup(BackupKind.RETRY)
        else:
            self._record(
                "Varmepumpe kom ikke i drift, men vandet er på eller over setpunkt: "
                "ingen handling"
            )

    async def _async_off(self, reason: str) -> None:
        for attempt in range(self._s.verify_attempts):
            # Command before verification: a pump standing still at setpoint
            # would otherwise never get its "off".
            if attempt == 0 or self._reader.hp_hvac_mode() != "off":
                await self._actuators.heat_pump_mode(
                    "off", self._attempt_reason(reason, attempt)
                )
            if self._stopped():
                return
            await async_sleep(self._hass, VERIFY_POLL_S)

        title, message = off_failed_alert(
            circulation=self._reader.circulation_on(),
            retry_minutes=self._s.retry_minutes,
        )
        await self._actuators.notify(title, message)

    async def _async_head_start(self, reason: str) -> None:
        await self._actuators.heat_pump_mode("heat", reason)
        await async_sleep(self._hass, self._s.head_start_timeout_s)
        if self._reader.hvac_action() in SPA_CALLING:
            self._record("Hurtigstart: spaen kalder på varme, tænd-reglen overtager")
            return

        off_reason = (
            f"hurtigstart: intet varmekald inden for "
            f"{fmt_num(self._s.head_start_timeout_s)} s"
        )
        for _ in range(HEAD_START_OFF_ATTEMPTS):
            await self._actuators.heat_pump_mode("off", off_reason)
            # Checked past compressor start (85-96 s after "on"), or low power
            # would prove nothing.
            await async_sleep(self._hass, HEAD_START_OFF_SETTLE_S)
            if self._stopped():
                return
        await self._actuators.notify(*HEAD_START_OFF_FAILED_ALERT)

    # --- shared actions -----------------------------------------------------

    async def async_backup(self, kind: BackupKind) -> None:
        """A5 action: heater on, check it after a while, alert once, mark failure."""
        if self._s.backup_heater:
            await self._actuators.heater(
                True, "backup: varmepumpen kører ikke, og vandet er under setpunkt"
            )
        await async_sleep(self._hass, self._s.backup_check_s)
        if not self._failure_open():
            title, message = backup_alert(
                kind,
                heater_running=heater_running(
                    self._reader.heater_power(), self._s.heater_on_w
                ),
                backup_enabled=self._s.backup_heater,
                retry_minutes=self._s.retry_minutes,
                circulation_minutes=self._s.watchdog_circulation_min,
            )
            await self._actuators.notify(title, message)
        self._set_failure(True)

    async def async_recover(self) -> None:
        """A7: the heat pump is confirmed running."""
        if self._failure_open():
            self._set_failure(False)
            self._record("Varmepumpe i drift igen: fejlen er ryddet")
        outdoor = self._reader.outdoor_temperature()
        if (
            self._reader.heater_on()
            and outdoor is not None
            and outdoor > self._s.frost_limit
        ):
            await self._actuators.heater(
                False, f"varmepumpen kører, og det er {fmt_c(outdoor)} °C ude"
            )
