"""What must survive a restart, and where it starts from on first install."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_REST_TEMPERATURE,
    DOMAIN,
    LEGACY_BATH_TIMER,
    LEGACY_FILTER_TIMER,
    LEGACY_FROST_AUTOMATION,
    LEGACY_REST_TEMPERATURE,
    STORAGE_VERSION,
    CleaningPhase,
    Status,
)
from .rules import snap_offset

_DATETIME_FIELDS = (
    "cleaning_started_at",
    "filter_reset_at",
    "bath_water_reset_at",
    "overtemp_since",
    "overtemp_seen",
)


@dataclass
class StoredState:
    active: bool = False
    frost_protection: bool = True
    rest_temperature: float = DEFAULT_REST_TEMPERATURE
    offset: float = 0.0
    status: Status = Status.MAINTAINING
    saved_status: str | None = None
    failure_open: bool = False
    cleaning_phase: CleaningPhase = CleaningPhase.IDLE
    cleaning_started_at: datetime | None = None
    filter_reset_at: datetime | None = None
    bath_water_reset_at: datetime | None = None
    overtemp_since: datetime | None = None
    overtemp_seen: datetime | None = None  # last reading that confirmed the hold
    overtemp_stopped: bool = False  # F5 fired: rule F is off for the rest of this cycle

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["cleaning_phase"] = self.cleaning_phase.value
        for key in _DATETIME_FIELDS:
            value = data[key]
            data[key] = value.isoformat() if value is not None else None
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StoredState:
        """Build from stored data, falling back to defaults for anything invalid."""
        default = cls()

        def _bool(key: str) -> bool:
            value = data.get(key)
            return value if isinstance(value, bool) else getattr(default, key)

        def _dt(key: str) -> datetime | None:
            value = data.get(key)
            if not isinstance(value, str):
                return None
            parsed = dt_util.parse_datetime(value)
            if parsed is None or parsed.tzinfo is None:
                return None
            return parsed

        try:
            status = Status(data.get("status"))
        except ValueError:
            status = default.status
        try:
            phase = CleaningPhase(data.get("cleaning_phase"))
        except ValueError:
            phase = default.cleaning_phase
        rest = data.get("rest_temperature")
        saved = data.get("saved_status")
        return cls(
            active=_bool("active"),
            frost_protection=_bool("frost_protection"),
            rest_temperature=float(rest)
            if isinstance(rest, int | float) and not isinstance(rest, bool)
            else default.rest_temperature,
            offset=snap_offset(data.get("offset", 0.0)),
            status=status,
            saved_status=saved if isinstance(saved, str) else None,
            failure_open=_bool("failure_open"),
            cleaning_phase=phase,
            cleaning_started_at=_dt("cleaning_started_at"),
            filter_reset_at=_dt("filter_reset_at"),
            bath_water_reset_at=_dt("bath_water_reset_at"),
            overtemp_since=_dt("overtemp_since"),
            overtemp_seen=_dt("overtemp_seen"),
            overtemp_stopped=_bool("overtemp_stopped"),
        )


def _legacy_datetime(hass: HomeAssistant, entity_id: str) -> datetime:
    """An input_datetime as an aware UTC datetime, or now if unusable.

    Reads the timestamp attribute: the state string is naive local time,
    which is exactly the bug the old template had.
    """
    state = hass.states.get(entity_id)
    timestamp = state.attributes.get("timestamp") if state else None
    if isinstance(timestamp, int | float):
        return dt_util.utc_from_timestamp(timestamp)
    return dt_util.utcnow()


def _legacy_float(hass: HomeAssistant, entity_id: str, default: float) -> float:
    state = hass.states.get(entity_id)
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return default
    try:
        return float(state.state)
    except ValueError:
        return default


def seed_from_legacy(hass: HomeAssistant) -> StoredState:
    """First-install state, continuing from the old helpers where they exist."""
    frost = hass.states.get(LEGACY_FROST_AUTOMATION)
    return StoredState(
        frost_protection=frost.state == STATE_ON if frost is not None else True,
        rest_temperature=_legacy_float(
            hass, LEGACY_REST_TEMPERATURE, DEFAULT_REST_TEMPERATURE
        ),
        filter_reset_at=_legacy_datetime(hass, LEGACY_FILTER_TIMER),
        bath_water_reset_at=_legacy_datetime(hass, LEGACY_BATH_TIMER),
    )


class UdespaStore:
    """One storage file per config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )

    async def async_load(self) -> StoredState:
        data = await self._store.async_load()
        if data is None:
            state = seed_from_legacy(self._hass)
            await self.async_save(state)
            return state
        return StoredState.from_dict(data)

    def save_soon(self, state: StoredState) -> None:
        self._store.async_delay_save(state.to_dict, 1)

    async def async_save(self, state: StoredState) -> None:
        await self._store.async_save(state.to_dict())

    async def async_remove(self) -> None:
        await self._store.async_remove()
