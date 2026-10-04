"""Every command the integration sends, in one place.

Enforces watch-only mode (Aktiv styring off): automatic commands are only
written to "Seneste handling", prefixed "(kun overvågning)". Deliberate ones
(buttons, a manual mode pick) still act. A failed command never raises.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant

from .const import SERVICE_TIMEOUT_S, WATCH_ONLY_PREFIX
from .rules import fmt_c
from .settings import Settings

_LOGGER = logging.getLogger(__name__)


class Actuators:
    def __init__(
        self,
        hass: HomeAssistant,
        settings: Settings,
        record: Callable[[str], None],
        is_active: Callable[[], bool],
    ) -> None:
        self._hass = hass
        self._s = settings
        self._record = record
        self._is_active = is_active

    def would_send(self, *, deliberate: bool = False) -> bool:
        """Whether a command would really be sent, or only logged (watch-only)."""
        return deliberate or self._is_active()

    async def heat_pump_mode(self, hvac_mode: str, reason: str) -> bool:
        label = "Varmepumpe tændt" if hvac_mode == "heat" else "Varmepumpe slukket"
        return await self._send(
            f"{label}: {reason}",
            "climate",
            "set_hvac_mode",
            {ATTR_ENTITY_ID: self._s.heat_pump, "hvac_mode": hvac_mode},
        )

    async def heat_pump_preset(
        self, preset: str, reason: str, *, deliberate: bool = False
    ) -> bool:
        return await self._send(
            f"Varmepumpe tilstand {preset}: {reason}",
            "climate",
            "set_preset_mode",
            {ATTR_ENTITY_ID: self._s.heat_pump, "preset_mode": preset},
            deliberate=deliberate,
        )

    async def heat_pump_temperature(self, temperature: float, reason: str) -> bool:
        return await self._send(
            f"Varmepumpe mål {fmt_c(temperature)} °C: {reason}",
            "climate",
            "set_temperature",
            {ATTR_ENTITY_ID: self._s.heat_pump, "temperature": temperature},
        )

    async def heater(self, on: bool, reason: str) -> bool:
        label = "Varmelegeme tændt" if on else "Varmelegeme slukket"
        return await self._send(
            f"{label}: {reason}",
            "switch",
            "turn_on" if on else "turn_off",
            {ATTR_ENTITY_ID: self._s.heater},
        )

    async def spa_setpoint(self, temperature: float, reason: str) -> bool:
        return await self._send(
            f"Spa setpunkt {fmt_c(temperature)} °C: {reason}",
            "climate",
            "set_temperature",
            {ATTR_ENTITY_ID: self._s.spa, "temperature": temperature},
            deliberate=True,
        )

    async def cleaning_pump(self, on: bool, reason: str) -> bool:
        label = "Rengøringspumpe tændt" if on else "Rengøringspumpe slukket"
        return await self._send(
            f"{label}: {reason}",
            "fan",
            "turn_on" if on else "turn_off",
            {ATTR_ENTITY_ID: self._s.cleaning_pump},
            deliberate=True,
        )

    async def notify(self, title: str, message: str) -> bool:
        text = f"Notifikation: {title} — {message}"
        if not self._s.notifications:
            self._record(f"{text} (ikke sendt: notifikationer er slået fra)")
            return False
        return await self._send(
            text, "notify", self._s.notify, {"title": title, "message": message}
        )

    async def _send(
        self,
        text: str,
        domain: str,
        service: str,
        data: dict[str, Any],
        *,
        deliberate: bool = False,
    ) -> bool:
        if not deliberate and not self._is_active():
            self._record(f"{WATCH_ONLY_PREFIX}{text}")
            return False
        try:
            async with asyncio.timeout(SERVICE_TIMEOUT_S):
                await self._hass.services.async_call(
                    domain, service, data, blocking=True
                )
        except Exception as err:  # noqa: BLE001 - a failed command must never break control
            _LOGGER.warning("%s failed: %s", text, err)
            self._record(f"{text} — fejlede: {err}")
            return False
        self._record(text)
        return True
