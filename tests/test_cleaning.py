"""Pipe cleaning: two cycles, double presses, stop, restart."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.udespa_control.const import CleaningPhase, Status

from .common import FakeTub, advance, settle


def _pump_ons(tub: FakeTub) -> int:
    return len(tub.sent("fan", "turn_on"))


async def _in_use(hass, freezer, tub, controller) -> None:
    tub.spa(setpoint=38.0)
    await advance(hass, freezer, 5)
    assert controller.status is Status.IN_USE


async def test_two_cycles_then_the_status_comes_back(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    await _in_use(hass, freezer, tub, controller)

    await controller.async_start_cleaning()
    await settle(hass)
    assert controller.status is Status.CLEANING
    assert controller.state.cleaning_phase is CleaningPhase.CYCLE_1
    assert controller.state.cleaning_started_at == dt_util.utcnow()
    assert _pump_ons(tub) == 1

    await advance(hass, freezer, 900, step=30)  # the spa stops its pump after 15 min
    tub.pump("off")
    await advance(hass, freezer, 5)
    assert controller.state.cleaning_phase is CleaningPhase.CYCLE_2
    assert _pump_ons(tub) == 2

    await advance(hass, freezer, 900, step=30)
    tub.pump("off")
    await advance(hass, freezer, 5)
    assert controller.state.cleaning_phase is CleaningPhase.IDLE
    assert controller.state.cleaning_started_at is None
    assert controller.status is Status.IN_USE


async def test_a_pump_that_never_stops_is_capped(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    await controller.async_start_cleaning()
    await advance(hass, freezer, 25 * 60, step=30)
    assert controller.state.cleaning_phase is CleaningPhase.CYCLE_2
    assert any("kørte stadig efter 25 min" in line for line in controller.recent)
    await advance(hass, freezer, 25 * 60, step=30)
    assert controller.state.cleaning_phase is CleaningPhase.IDLE
    assert controller.status is Status.MAINTAINING


async def test_a_double_press_cannot_lock_the_status_on_cleaning(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    await _in_use(hass, freezer, tub, controller)
    await controller.async_start_cleaning()
    await settle(hass)
    await controller.async_start_cleaning()
    await settle(hass)
    assert controller.state.saved_status == "I brug"
    assert controller.state.cleaning_phase is CleaningPhase.CYCLE_1
    await controller.async_stop_cleaning()
    assert controller.status is Status.IN_USE


async def test_stop_cancels_before_switching_the_pump_off(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    """Otherwise the pump going off would advance the cycle to Cyklus 2."""
    controller = await make_controller()
    await controller.async_start_cleaning()
    await advance(hass, freezer, 60)
    await controller.async_stop_cleaning()
    await advance(hass, freezer, 30 * 60, step=60)
    assert _pump_ons(tub) == 1
    assert hass.states.get("fan.udespa_pump_1").state == "off"
    assert controller.state.cleaning_phase is CleaningPhase.IDLE
    assert controller.status is Status.MAINTAINING


async def test_stop_when_idle_only_switches_the_pump_off(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    await _in_use(hass, freezer, tub, controller)
    await controller.async_stop_cleaning()
    assert controller.status is Status.IN_USE
    assert len(tub.sent("fan", "turn_off")) == 1


async def test_restart_mid_cleaning_restores_the_status(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    first = await make_controller()
    await _in_use(hass, freezer, tub, first)
    await first.async_start_cleaning()
    await settle(hass)
    await first.async_shutdown()  # HA restarts mid-cleaning

    second = await make_controller(active=False, entry=first.entry)
    assert second.state.cleaning_phase is CleaningPhase.IDLE
    assert second.status is Status.IN_USE
    assert second.state.saved_status is None


async def test_restore_after_cleaning_resolves_fault_against_current_failure(
    hass: HomeAssistant, tub: FakeTub, make_controller
):
    controller = await make_controller()

    # Saved "Fejl", failure cleared during cleaning -> not stuck on Fejl.
    controller.set_failure(True)
    assert controller.status is Status.FAULT
    await controller.async_start_cleaning()
    await settle(hass)
    controller.set_failure(False)
    assert controller.status is Status.CLEANING
    await controller.async_stop_cleaning()
    assert controller.status is Status.MAINTAINING

    # Saved "Vedligeholder", failure opened during cleaning -> Fejl.
    await controller.async_start_cleaning()
    await settle(hass)
    controller.set_failure(True)
    assert controller.status is Status.CLEANING
    await controller.async_stop_cleaning()
    assert controller.status is Status.FAULT


async def test_cleaning_runs_in_watch_only(hass: HomeAssistant, tub: FakeTub, make_controller):
    controller = await make_controller(active=False)
    await controller.async_start_cleaning()
    await settle(hass)
    assert _pump_ons(tub) == 1
    assert controller.status is Status.CLEANING
