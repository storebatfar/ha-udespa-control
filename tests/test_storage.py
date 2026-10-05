"""Stored state and first-load seeding."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.udespa_control.const import (
    LEGACY_BATH_TIMER,
    LEGACY_FILTER_TIMER,
    LEGACY_FROST_AUTOMATION,
    LEGACY_REST_TEMPERATURE,
    CleaningPhase,
    Status,
)
from custom_components.udespa_control.storage import (
    StoredState,
    UdespaStore,
    seed_from_legacy,
)


async def test_first_load_seeds_from_the_old_helpers(hass: HomeAssistant):
    hass.states.async_set(
        LEGACY_FILTER_TIMER, "2026-09-13 17:40:22", {"timestamp": 1789314022}
    )
    hass.states.async_set(
        LEGACY_BATH_TIMER, "2026-09-13 17:40:20", {"timestamp": 1789314020}
    )
    hass.states.async_set(LEGACY_REST_TEMPERATURE, "36.5")
    hass.states.async_set(LEGACY_FROST_AUTOMATION, "off")

    state = await UdespaStore(hass, "entry1").async_load()

    assert state.filter_reset_at == datetime.fromtimestamp(1789314022, tz=UTC)
    assert state.bath_water_reset_at == datetime.fromtimestamp(1789314020, tz=UTC)
    assert state.filter_reset_at.tzinfo is not None
    assert state.rest_temperature == 36.5
    assert state.frost_protection is False
    assert state.active is False  # Aktiv styring is off on first install


async def test_first_load_without_old_helpers_uses_defaults(hass: HomeAssistant):
    before = dt_util.utcnow()
    state = seed_from_legacy(hass)
    assert state.rest_temperature == 37.0
    assert state.frost_protection is True
    assert state.filter_reset_at >= before
    assert state.status is Status.MAINTAINING


async def test_unavailable_old_helpers_fall_back(hass: HomeAssistant):
    hass.states.async_set(LEGACY_REST_TEMPERATURE, "unavailable")
    hass.states.async_set(LEGACY_FILTER_TIMER, "unknown", {})
    state = seed_from_legacy(hass)
    assert state.rest_temperature == 37.0
    assert state.filter_reset_at is not None


async def test_round_trip(hass: HomeAssistant):
    store = UdespaStore(hass, "entry1")
    saved = StoredState(
        active=True,
        frost_protection=False,
        rest_temperature=36.0,
        status=Status.CLEANING,
        saved_status="I brug",
        failure_open=True,
        cleaning_phase=CleaningPhase.CYCLE_2,
        cleaning_started_at=datetime(2026, 10, 2, 19, 0, tzinfo=UTC),
        filter_reset_at=datetime(2026, 9, 13, 15, 40, tzinfo=UTC),
        bath_water_reset_at=datetime(2026, 9, 13, 15, 40, tzinfo=UTC),
    )
    await store.async_save(saved)
    assert await UdespaStore(hass, "entry1").async_load() == saved


def test_from_dict_tolerates_junk():
    state = StoredState.from_dict(
        {
            "status": "nonsense",
            "cleaning_phase": 7,
            "rest_temperature": "warm",
            "filter_reset_at": "not a date",
            "active": "yes",
        }
    )
    assert state.status is Status.MAINTAINING
    assert state.cleaning_phase is CleaningPhase.IDLE
    assert state.rest_temperature == 37.0
    assert state.filter_reset_at is None
    assert state.active is False


async def test_remove_deletes_the_file(hass: HomeAssistant, hass_storage):
    store = UdespaStore(hass, "entry1")
    await store.async_save(StoredState())
    assert "udespa_control.entry1" in hass_storage
    await store.async_remove()
    assert "udespa_control.entry1" not in hass_storage


def test_offset_round_trips_and_snaps():
    assert StoredState.from_dict({"offset": 1.0}).offset == 1.0
    assert StoredState.from_dict({"offset": 0.7}).offset == 0.5
    assert StoredState.from_dict({}).offset == 0.0
    assert StoredState(offset=0.5).to_dict()["offset"] == 0.5


