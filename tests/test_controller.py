"""The controller, end to end on the fake tub."""

from __future__ import annotations

from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.udespa_control.const import (
    OPT_FAULT_STATUS,
    OPT_FILTER_STAY_ON,
    OPT_MODE_IN_USE,
    OPT_WATCHDOG,
    Mode,
    Status,
    SyncStatus,
    Timer,
)

from .common import (
    FILTER_1,
    FILTER_2,
    HEATER,
    HP,
    OUTDOOR,
    SPA,
    FakeTub,
    advance,
    settle,
)


def _spa_setpoints(tub: FakeTub) -> list[float]:
    return [
        c.data["temperature"]
        for c in tub.sent("climate", "set_temperature")
        if c.data["entity_id"] == SPA
    ]


# --- A1 / A3 ------------------------------------------------------------------


async def test_a_heat_call_switches_the_heat_pump_on(hass: HomeAssistant, tub: FakeTub, make_controller):
    await make_controller()
    tub.circulation(True)
    await settle(hass)  # in reality ~60 s apart
    tub.spa(action="heating")
    await settle(hass)
    assert tub.hp_modes() == ["heat"]


async def test_second_heating_after_idle_does_not_restart_the_job(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    tub.circulation(True)
    await settle(hass)  # in reality ~60 s apart
    tub.spa(action="heating")
    await advance(hass, freezer, 6)
    tub.spa(action="idle")
    await advance(hass, freezer, 4)
    tub.spa(action="heating")
    await settle(hass)
    assert tub.hp_modes() == ["heat"]


async def test_a_trigger_without_a_decision_does_not_cancel_the_job(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    tub.spa(temperature=35.0)
    tub.circulation(True)
    await settle(hass)  # in reality ~60 s apart
    tub.spa(action="heating")
    await advance(hass, freezer, 30)
    tub.spa(temperature=35.5)
    hass.states.async_set(FILTER_2, "unavailable")
    tub.spa(action="idle")
    await advance(hass, freezer, 370, step=5)
    assert tub.hp_modes() == ["heat"]
    assert tub.heater_commands() == ["on"]  # the job lived on to its backup


async def test_satisfied_switches_off_after_the_off_delay(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    tub.circulation(True)
    await settle(hass)  # in reality ~60 s apart
    tub.spa(action="heating")
    await settle(hass)
    tub.hp_power(1500)
    await advance(hass, freezer, 20)
    tub.spa(action="off", temperature=37.5)
    await advance(hass, freezer, 4)
    assert tub.hp_modes() == ["heat"]
    await advance(hass, freezer, 1)
    assert tub.hp_modes() == ["heat", "off"]


async def test_satisfied_timer_is_cancelled_when_the_spa_calls_again(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    tub.circulation(True)
    await settle(hass)  # in reality ~60 s apart
    tub.spa(action="heating")
    await settle(hass)
    tub.spa(action="off", temperature=37.5)
    await advance(hass, freezer, 3)
    tub.spa(action="heating")
    await advance(hass, freezer, 5)
    assert "off" not in tub.hp_modes()


async def test_circulation_stop_switches_off(hass: HomeAssistant, tub: FakeTub, make_controller):
    await make_controller()
    tub.circulation(True)
    await settle(hass)
    tub.circulation(False)
    await settle(hass)
    assert tub.hp_modes() == ["off"]


async def test_filter_cycle_without_call_switches_nothing_on(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller(**{OPT_FILTER_STAY_ON: False})
    tub.spa(temperature=38.0)
    tub.filter_cycle(1, True)
    tub.circulation(True)
    await advance(hass, freezer, 120, step=5)
    assert tub.hp_modes() == []


# --- A2 -----------------------------------------------------------------------


async def test_circulation_start_in_use_head_starts(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    tub.spa(setpoint=38.0)
    await advance(hass, freezer, 5)
    assert controller.status is Status.IN_USE
    tub.circulation(True)
    await settle(hass)
    assert tub.hp_modes() == ["heat"]


async def test_status_turning_in_use_during_circulation_head_starts(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    tub.circulation(True)
    tub.spa(setpoint=39.0)
    await advance(hass, freezer, 4)
    assert tub.hp_modes() == []
    await advance(hass, freezer, 1)
    assert tub.hp_modes() == ["heat"]


# --- A8 / E20 -----------------------------------------------------------------


async def test_startup_with_a_call_is_logged_in_watch_only(
    hass: HomeAssistant, tub: FakeTub, make_controller
):
    tub.circulation(True)
    await settle(hass)  # in reality ~60 s apart
    tub.spa(action="heating")
    controller = await make_controller(active=False)
    assert tub.hp_modes() == []
    assert "(kun overvågning) Varmepumpe tændt: opstart: spaen kalder på varme" in controller.recent


async def test_activating_control_takes_over_at_once(hass: HomeAssistant, tub: FakeTub, make_controller):
    tub.circulation(True)
    await settle(hass)  # in reality ~60 s apart
    tub.spa(action="heating")
    controller = await make_controller(active=False)
    await controller.async_set_active(True)
    await settle(hass)
    assert tub.hp_modes() == ["heat"]


async def test_watch_only_sends_nothing_but_own_sensors_update(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller(active=False)
    tub.circulation(True)
    tub.spa(action="heating", setpoint=38.5)
    await advance(hass, freezer, 30)
    assert tub.calls == []
    assert controller.status is Status.IN_USE
    assert controller.heating is True
    assert controller.last_action.startswith("(kun overvågning) ")


# --- A9 -----------------------------------------------------------------------


async def test_heat_pump_target_follows_the_spa_setpoint(hass: HomeAssistant, tub: FakeTub, make_controller):
    await make_controller()
    tub.spa(setpoint=38.5)
    await settle(hass)
    assert hass.states.get(HP).attributes["temperature"] == 38.5


# --- A6 / A7 / B11 --------------------------------------------------------------


async def test_watchdog_fires_after_ten_minutes_of_cold_silent_circulation(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    tub.spa(temperature=35.0)
    tub.circulation(True)
    await advance(hass, freezer, 595, step=5)
    assert tub.heater_commands() == []
    await advance(hass, freezer, 5)
    assert tub.heater_commands() == ["on"]
    await advance(hass, freezer, 150, step=5)
    assert len(tub.notifications()) == 1
    assert controller.failure_open
    assert controller.status is Status.FAULT


async def test_watchdog_toggle_off(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller(**{OPT_WATCHDOG: False})
    tub.spa(temperature=35.0)
    tub.circulation(True)
    await advance(hass, freezer, 900, step=30)
    assert tub.heater_commands() == []


async def test_power_returning_clears_the_failure(hass: HomeAssistant, tub: FakeTub, make_controller):
    controller = await make_controller()
    controller.set_failure(True)
    assert controller.status is Status.FAULT
    tub.hp_power(1500)
    await settle(hass)
    assert not controller.failure_open
    assert controller.status is Status.MAINTAINING


async def test_fault_status_toggle_off_keeps_the_status(hass: HomeAssistant, tub: FakeTub, make_controller):
    controller = await make_controller(**{OPT_FAULT_STATUS: False})
    controller.set_failure(True)
    assert controller.status is Status.MAINTAINING


# --- B10 ----------------------------------------------------------------------


async def test_status_follows_the_setpoint_after_five_seconds(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    tub.spa(setpoint=38.0)
    await advance(hass, freezer, 4)
    assert controller.status is Status.MAINTAINING
    await advance(hass, freezer, 1)
    assert controller.status is Status.IN_USE


async def test_status_delay_does_not_restart_on_further_steps(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    """2026-10-02 21:21:38: 37.5, 38, 38.5, then 39 at +7.5 s; I brug came at +5 s."""
    controller = await make_controller()
    tub.spa(setpoint=37.5)
    await advance(hass, freezer, 1)
    tub.spa(setpoint=38.0)
    tub.spa(setpoint=38.5)
    await advance(hass, freezer, 3)
    assert controller.status is Status.MAINTAINING
    await advance(hass, freezer, 1)
    assert controller.status is Status.IN_USE
    tub.spa(setpoint=39.0)
    await advance(hass, freezer, 6)
    assert controller.status is Status.IN_USE


async def test_setpoint_back_within_the_delay_cancels(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    tub.spa(setpoint=38.0)
    await advance(hass, freezer, 3)
    tub.spa(setpoint=37.0)
    await advance(hass, freezer, 10)
    assert controller.status is Status.MAINTAINING


async def test_rest_temperature_change_reevaluates(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    await controller.async_set_rest_temperature(36.0)
    await advance(hass, freezer, 5)
    assert controller.status is Status.IN_USE
    assert controller.state.rest_temperature == 36.0


async def test_setpoint_changes_never_overwrite_fault(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    controller.set_failure(True)
    tub.spa(setpoint=39.0)
    await advance(hass, freezer, 10)
    assert controller.status is Status.FAULT


async def test_missing_setpoint_keeps_the_status(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    tub.spa(setpoint=None)
    await advance(hass, freezer, 10)
    assert controller.status is Status.MAINTAINING


# --- B12 ----------------------------------------------------------------------


async def test_mode_follows_the_status(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    tub.spa(setpoint=38.0)
    await advance(hass, freezer, 5)
    assert tub.presets() == ["smart"]
    tub.spa(setpoint=37.0)
    await advance(hass, freezer, 5)
    assert tub.presets() == ["smart", "quick"]


async def test_automatic_mode_is_only_logged_in_watch_only_but_a_manual_pick_acts(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller(active=False)
    tub.spa(setpoint=38.0)
    await advance(hass, freezer, 5)
    assert tub.presets() == []
    assert any("(kun overvågning) Varmepumpe tilstand smart" in line for line in controller.recent)
    await controller.async_select_mode(Mode.TURBO)
    await settle(hass)
    assert tub.presets() == ["quiet"]


async def test_mode_mirrors_a_preset_changed_on_the_heat_pump(
    hass: HomeAssistant, tub: FakeTub, make_controller
):
    controller = await make_controller()
    pushes: list[int] = []
    controller.add_listener(lambda: pushes.append(1))
    hass.states.async_set(HP, "off", {**hass.states.get(HP).attributes, "preset_mode": "quiet"})
    await settle(hass)
    assert controller.mode is Mode.TURBO
    assert pushes


# --- B13 ----------------------------------------------------------------------


async def test_nudge_raises_lowers_and_clamps(hass: HomeAssistant, tub: FakeTub, make_controller):
    controller = await make_controller()
    await controller.async_nudge_setpoint(0.5)
    assert _spa_setpoints(tub) == [37.5]
    tub.spa(setpoint=40.0)
    await controller.async_nudge_setpoint(0.5)
    assert _spa_setpoints(tub) == [37.5]
    await controller.async_nudge_setpoint(-0.5)
    assert _spa_setpoints(tub) == [37.5, 39.5]


async def test_nudge_ignored_while_the_spa_is_unavailable(hass: HomeAssistant, tub: FakeTub, make_controller):
    controller = await make_controller()
    tub.spa(state="unavailable")
    await controller.async_nudge_setpoint(0.5)
    assert _spa_setpoints(tub) == []
    assert "ikke tilgængelig" in controller.last_action


async def test_nudge_works_in_watch_only(hass: HomeAssistant, tub: FakeTub, make_controller):
    controller = await make_controller(active=False)
    await controller.async_nudge_setpoint(-0.5)
    assert _spa_setpoints(tub) == [36.5]


# --- C14 / C15 ------------------------------------------------------------------


async def test_frost_crossings_switch_the_heater(hass: HomeAssistant, tub: FakeTub, make_controller):
    await make_controller()
    tub.outdoor(6.0)
    tub.outdoor(4.0)
    await settle(hass)
    tub.outdoor(6.0)
    await settle(hass)
    assert tub.heater_commands() == ["on", "off"]


async def test_frost_protection_off_pauses_the_rule(hass: HomeAssistant, tub: FakeTub, make_controller):
    controller = await make_controller()
    await controller.async_set_frost_protection(False)
    tub.outdoor(4.0)
    await settle(hass)
    assert tub.heater_commands() == []


async def test_frost_off_crossing_keeps_backup_heater_during_failure(
    hass: HomeAssistant, tub: FakeTub, make_controller
):
    controller = await make_controller()
    tub.outdoor(4.0)
    await settle(hass)
    hass.states.async_set(HEATER, "on")
    controller.set_failure(True)
    tub.outdoor(6.0)
    await settle(hass)
    assert tub.heater_commands() == ["on"]
    assert "backup" in controller.last_action


# --- D19 ----------------------------------------------------------------------


async def test_timers_count_whole_days_and_reset(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    assert controller.timer_days(Timer.FILTER) == 0
    pushes: list[int] = []
    controller.add_listener(lambda: pushes.append(1))
    await advance(hass, freezer, 2 * 24 * 3600, step=6 * 3600)
    assert controller.timer_days(Timer.FILTER) == 2
    assert pushes
    await controller.async_reset_timer(Timer.FILTER)
    assert controller.timer_days(Timer.FILTER) == 0
    assert controller.timer_reset_at(Timer.FILTER) == dt_util.utcnow()
    assert controller.timer_days(Timer.BATH_WATER) == 2


async def test_state_survives_a_restart(hass: HomeAssistant, tub: FakeTub, make_controller):
    first = await make_controller()
    await first.async_set_rest_temperature(36.5)
    await first.async_shutdown()
    second = await make_controller(active=False, entry=first.entry)
    assert second.state.rest_temperature == 36.5
    assert second.state.active is True
    assert second.timer_reset_at(Timer.FILTER) is not None
    assert timedelta(0) <= dt_util.utcnow() - second.timer_reset_at(Timer.FILTER)


async def test_watchdog_waits_while_a_heat_job_is_verifying(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    """Setpoint raised late in a long filter cycle: the tick lands mid compressor start."""
    controller = await make_controller()
    tub.spa(temperature=35.0)
    tub.circulation(True)
    await advance(hass, freezer, 590, step=10)
    tub.spa(action="heating")
    await advance(hass, freezer, 20, step=5)
    tub.hp_power(1500)
    await advance(hass, freezer, 200, step=10)
    assert tub.heater_commands() == []
    assert tub.notifications() == []
    assert not controller.failure_open


async def test_frost_crossing_during_the_backup_check_keeps_the_heater_on(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    tub.spa(temperature=35.0)
    tub.circulation(True)
    await advance(hass, freezer, 600, step=10)
    assert tub.heater_commands() == ["on"]  # the watchdog's backup
    tub.outdoor(4.0)
    await settle(hass)
    tub.outdoor(6.0)
    await advance(hass, freezer, 150, step=10)
    assert "off" not in tub.heater_commands()


# --- A9′ offset and sync status ----------------------------------------------


def _hp_target(hass):
    return hass.states.get(HP).attributes["temperature"]


async def test_offset_adds_to_the_heat_pump_target(hass: HomeAssistant, tub: FakeTub, make_controller):
    controller = await make_controller()
    await controller.async_set_offset(1.0)
    await settle(hass)
    assert _hp_target(hass) == 38.0
    tub.spa(setpoint=39.5)
    await settle(hass)
    assert _hp_target(hass) == 40.5
    tub.spa(setpoint=40.5)
    await settle(hass)
    assert _hp_target(hass) == 41
    assert controller.sync_attributes()["capped"] is True
    assert controller.sync_status() is SyncStatus.IN_SYNC


async def test_offset_snaps_to_half_degrees(hass: HomeAssistant, tub: FakeTub, make_controller):
    controller = await make_controller()
    await controller.async_set_offset(0.7)
    assert controller.state.offset == 0.5


async def test_sync_status_reports_but_never_fights_an_external_change(
    hass: HomeAssistant, tub: FakeTub, make_controller
):
    controller = await make_controller()
    assert controller.sync_status() is SyncStatus.IN_SYNC
    hass.states.async_set(HP, "off", {**hass.states.get(HP).attributes, "temperature": 35.0})
    await settle(hass)
    assert controller.sync_status() is SyncStatus.DIFFERS
    assert tub.sent("climate", "set_temperature") == []


async def test_no_sync_while_the_heat_pump_is_unavailable(
    hass: HomeAssistant, tub: FakeTub, make_controller
):
    controller = await make_controller()
    hass.states.async_set(HP, "unavailable", {})
    tub.spa(setpoint=38.0)
    await settle(hass)
    assert controller.sync_status() is SyncStatus.UNKNOWN
    assert tub.sent("climate", "set_temperature") == []


async def test_startup_and_activation_resync_a_wrong_target(
    hass: HomeAssistant, tub: FakeTub, make_controller
):
    hass.states.async_set(HP, "off", {**hass.states.get(HP).attributes, "temperature": 35.0})
    controller = await make_controller(active=False)
    assert any(
        line.startswith("(kun overvågning) Varmepumpe mål 37,0 °C: opstart")
        for line in controller.recent
    )
    assert controller.sync_attributes()["last_sync"] is not None
    await controller.async_set_active(True)
    await settle(hass)
    assert _hp_target(hass) == 37.0


async def test_watch_only_logs_the_offset_sync(hass: HomeAssistant, tub: FakeTub, make_controller):
    controller = await make_controller(active=False)
    await controller.async_set_offset(1.0)
    await settle(hass)
    assert tub.sent("climate", "set_temperature") == []
    assert "(kun overvågning) Varmepumpe mål 38,0 °C: offset ændret" in controller.recent
    assert controller.state.offset == 1.0
    assert controller.sync_status() is SyncStatus.DIFFERS


async def test_sync_attributes(hass: HomeAssistant, tub: FakeTub, make_controller):
    controller = await make_controller()
    await controller.async_set_offset(0.5)
    await settle(hass)
    attrs = controller.sync_attributes()
    assert attrs["spa_setpoint"] == 37.0
    assert attrs["offset"] == 0.5
    assert attrs["expected_target"] == 37.5
    assert attrs["heat_pump_target"] == 37.5
    assert attrs["capped"] is False
    assert attrs["last_sync"]


async def test_offset_survives_a_restart(hass: HomeAssistant, tub: FakeTub, make_controller):
    first = await make_controller()
    await first.async_set_offset(0.5)
    await first.async_shutdown()
    second = await make_controller(active=False, entry=first.entry)
    assert second.state.offset == 0.5


async def test_the_chosen_in_use_mode_is_sent(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller(**{OPT_MODE_IN_USE: "Turbo"})
    tub.spa(setpoint=38.0)
    await advance(hass, freezer, 5)
    assert tub.presets() == ["quiet"]


async def test_replay_20261004_smart_survives_the_power_on(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    """11:18:20: status I brug sent "heat" and "smart" together; "quick" came back 6 s later."""
    controller = await make_controller()
    tub.drop_presets = 1
    tub.circulation(True)
    await settle(hass)
    tub.spa(setpoint=39.0)
    await advance(hass, freezer, 5)
    assert tub.hp_modes() == ["heat"]
    await advance(hass, freezer, 40, step=2)
    assert hass.states.get(HP).attributes["preset_mode"] == "smart"
    assert tub.presets() == ["smart", "smart"]
    assert controller.mode is Mode.SMART


async def test_watch_only_keeper_only_logs(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller(active=False)
    tub.spa(setpoint=38.0)
    await advance(hass, freezer, 6)
    # the old automation sets Smart, as it does during the trial
    hass.states.async_set(HP, "off", {**hass.states.get(HP).attributes, "preset_mode": "smart"})
    await advance(hass, freezer, 40, step=2)
    assert tub.calls == []
    assert [line for line in controller.recent if "tilstand smart" in line] == [
        "(kun overvågning) Varmepumpe tilstand smart: status er I brug"
    ]
    assert not any("afviste" in line for line in controller.recent)


async def test_a_heat_pump_change_outside_the_window_is_adopted(
    hass: HomeAssistant, tub: FakeTub, make_controller
):
    controller = await make_controller()
    hass.states.async_set(HP, "off", {**hass.states.get(HP).attributes, "preset_mode": "quiet"})
    await settle(hass)
    assert controller.mode_keeper.wanted is Mode.TURBO


async def test_first_outdoor_reading_after_startup_is_no_crossing(
    hass: HomeAssistant, tub: FakeTub, make_controller
):
    """At HA start the forecast entity is created from nothing: not a frost crossing."""
    await make_controller()
    for temperature in (14.9, 3.0):
        hass.states.async_remove(OUTDOOR)
        await settle(hass)
        tub.outdoor(temperature)
        await settle(hass)
    assert tub.heater_commands() == []


async def test_return_from_unavailable_still_counts_as_a_crossing(
    hass: HomeAssistant, tub: FakeTub, make_controller
):
    await make_controller()
    hass.states.async_set(OUTDOOR, "unavailable", {})
    await settle(hass)
    tub.outdoor(3.0)
    await settle(hass)
    assert tub.heater_commands() == ["on"]


# --- Rule F: filter cycles ---------------------------------------------------


async def _filter_cycle_running(hass, freezer, tub):
    """Circulation, then a filter cycle; the heat pump is on 10 s later and running at 100 s.

    The compressor is modelled so the on-job's verification passes and no
    backup-heater alert muddies the assertions.
    """
    tub.model_compressor = True
    tub.circulation(True)
    await settle(hass)
    tub.filter_cycle(1, True)
    await advance(hass, freezer, 10)
    await advance(hass, freezer, 90)  # the compressor is running (L3 power)


def _safety_stops(tub: FakeTub) -> int:
    return sum(c.data["message"].startswith("Sikkerhedsstop") for c in tub.notifications())


async def test_filter_cycle_switches_the_heat_pump_on_after_10_s(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    tub.circulation(True)
    await settle(hass)
    tub.filter_cycle(1, True)
    await advance(hass, freezer, 9)
    assert tub.hp_modes() == []
    await advance(hass, freezer, 1)
    assert tub.hp_modes() == ["heat"]


async def test_filter_start_without_circulation_does_nothing(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    tub.filter_cycle(1, True)
    await advance(hass, freezer, 15)
    assert tub.hp_modes() == []


async def test_circulation_and_filter_in_one_instant(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    """I brug + both sensors at once: rule F wins, so no head start (and no 70 s off)."""
    tub.model_compressor = True
    controller = await make_controller()
    tub.spa(setpoint=38.0)
    await advance(hass, freezer, 5)
    assert controller.status is Status.IN_USE
    tub.circulation(True)
    tub.filter_cycle(1, True)
    await advance(hass, freezer, 180, step=5)
    assert tub.hp_modes()[0] == "heat"
    assert "off" not in tub.hp_modes()
    assert not any("hurtigstart" in line for line in controller.recent)


async def test_filter_sensor_a_moment_after_circulation_cancels_the_head_start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    """The other order: the head start runs, then the filter start replaces its job."""
    tub.model_compressor = True
    controller = await make_controller()
    tub.spa(setpoint=38.0)
    await advance(hass, freezer, 5)
    tub.circulation(True)
    await advance(hass, freezer, 3)
    tub.filter_cycle(1, True)
    await advance(hass, freezer, 180, step=5)
    assert any("hurtigstart" in line for line in controller.recent)
    assert tub.hp_modes()[0] == "heat"
    assert "off" not in tub.hp_modes()


async def test_satisfied_during_a_filter_cycle_keeps_it_on(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    await _filter_cycle_running(hass, freezer, tub)
    tub.spa(action="heating")
    await settle(hass)
    tub.spa(action="off", temperature=37.5)
    await advance(hass, freezer, 30)
    assert "off" not in tub.hp_modes()
    tub.circulation(False)
    await settle(hass)
    assert tub.hp_modes()[-1] == "off"


async def test_startup_mid_cycle_switches_on(hass: HomeAssistant, tub: FakeTub, make_controller):
    tub.circulation(True)
    tub.filter_cycle(1, True)
    controller = await make_controller(active=False)
    assert (
        "(kun overvågning) Varmepumpe tændt: filtercyklus: varmepumpen står tændt hele cyklussen"
        in controller.recent
    )


async def test_overtemp_stops_after_five_minutes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    await _filter_cycle_running(hass, freezer, tub)
    tub.spa(temperature=38.0)
    await advance(hass, freezer, 299, step=10)
    assert "off" not in tub.hp_modes()
    await advance(hass, freezer, 1)
    assert tub.hp_modes()[-1] == "off"
    assert _safety_stops(tub) == 1


async def test_a_short_blip_is_no_overtemp(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    await _filter_cycle_running(hass, freezer, tub)
    tub.spa(temperature=38.0)
    await advance(hass, freezer, 44)
    tub.spa(temperature=37.5)
    await advance(hass, freezer, 600, step=30)
    assert "off" not in tub.hp_modes()
    assert _safety_stops(tub) == 0


async def test_half_a_degree_over_is_no_overtemp(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    await _filter_cycle_running(hass, freezer, tub)
    tub.spa(temperature=37.5)
    await advance(hass, freezer, 900, step=30)
    assert "off" not in tub.hp_modes()
    assert _safety_stops(tub) == 0


async def test_overtemp_only_during_a_filter_cycle(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    tub.model_compressor = True
    await make_controller()
    tub.circulation(True)
    await settle(hass)
    tub.spa(action="heating")
    await settle(hass)
    tub.spa(temperature=38.0)
    await advance(hass, freezer, 600, step=30)
    assert "off" not in tub.hp_modes()
    assert _safety_stops(tub) == 0


async def test_missing_temperature_is_no_overtemp(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    await _filter_cycle_running(hass, freezer, tub)
    tub.spa(temperature=None)
    await advance(hass, freezer, 600, step=30)
    assert _safety_stops(tub) == 0


async def test_overtemp_needs_the_heat_pump_in_heat(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    await _filter_cycle_running(hass, freezer, tub)
    await advance(hass, freezer, 120, step=10)  # the on-job has verified and ended
    hass.states.async_set(HP, "unavailable", {})
    tub.spa(temperature=38.0)
    await advance(hass, freezer, 600, step=30)
    assert _safety_stops(tub) == 0
    assert controller.state.overtemp_since is None


async def test_overtemp_cancelled_when_the_cycle_ends(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    await _filter_cycle_running(hass, freezer, tub)
    tub.spa(temperature=38.0)
    await advance(hass, freezer, 120, step=10)
    tub.filter_cycle(1, False)
    await advance(hass, freezer, 600, step=30)
    assert _safety_stops(tub) == 0
    assert controller.state.overtemp_since is None


async def test_overtemp_timer_survives_a_restart(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    first = await make_controller()
    await _filter_cycle_running(hass, freezer, tub)
    tub.spa(temperature=38.0)
    await advance(hass, freezer, 180, step=10)
    assert first.state.overtemp_since is not None
    await first.async_shutdown()
    second = await make_controller(active=False, entry=first.entry)
    await advance(hass, freezer, 119, step=7)
    assert not any("sikkerhedsstop" in line for line in second.recent)
    await advance(hass, freezer, 1)
    assert sum("Varmepumpe slukket: sikkerhedsstop" in line for line in second.recent) == 1
    await advance(hass, freezer, 600, step=30)
    assert sum("Varmepumpe slukket: sikkerhedsstop" in line for line in second.recent) == 1


# --- final-review fixes ------------------------------------------------------


async def test_a_warm_tub_after_a_bath_is_no_overtemp(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    """38.5 over 37 after a bath: the heat pump is on but never runs, so it isn't overheating."""
    tub.spa(temperature=38.5)
    await make_controller()
    tub.circulation(True)
    await settle(hass)
    tub.filter_cycle(1, True)
    await advance(hass, freezer, 600, step=10)
    assert tub.hp_modes() == ["heat"]
    assert _safety_stops(tub) == 0


async def test_an_unavailable_blip_keeps_the_hold(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    await _filter_cycle_running(hass, freezer, tub)
    tub.spa(temperature=38.0)
    await advance(hass, freezer, 240, step=10)
    attributes = dict(hass.states.get(HP).attributes)
    hass.states.async_set(HP, "unavailable", {})
    await advance(hass, freezer, 5)
    hass.states.async_set(HP, "heat", attributes)
    await advance(hass, freezer, 54)
    assert _safety_stops(tub) == 0
    await advance(hass, freezer, 1)
    assert _safety_stops(tub) == 1


async def test_restart_with_the_heat_pump_not_yet_connected_resumes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    first = await make_controller()
    await _filter_cycle_running(hass, freezer, tub)
    tub.spa(temperature=38.0)
    await advance(hass, freezer, 180, step=10)
    await first.async_shutdown()
    attributes = dict(hass.states.get(HP).attributes)
    hass.states.async_set(HP, "unavailable", {})
    tub.fail_services.add("climate.set_hvac_mode")  # tuya_local not connected yet
    second = await make_controller(active=False, entry=first.entry)
    await advance(hass, freezer, 20)
    tub.fail_services.clear()
    hass.states.async_set(HP, "heat", attributes)
    await advance(hass, freezer, 99)
    assert not any("sikkerhedsstop" in line for line in second.recent)
    await advance(hass, freezer, 1)
    assert sum("Varmepumpe slukket: sikkerhedsstop" in line for line in second.recent) == 1


async def test_a_long_shutdown_starts_the_hold_over(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    first = await make_controller()
    await _filter_cycle_running(hass, freezer, tub)
    tub.spa(temperature=38.0)
    await advance(hass, freezer, 180, step=10)
    await first.async_shutdown()
    freezer.tick(timedelta(hours=3))
    second = await make_controller(active=False, entry=first.entry)
    await advance(hass, freezer, 299, step=13)
    assert not any("sikkerhedsstop" in line for line in second.recent)
    await advance(hass, freezer, 1)
    assert sum("Varmepumpe slukket: sikkerhedsstop" in line for line in second.recent) == 1


@pytest.mark.parametrize("disturbance", ["attribute update", "other sensor blip"])
async def test_a_filter_sensor_event_does_not_lose_the_filter_start(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    tub: FakeTub,
    make_controller,
    disturbance: str,
):
    """Head start first, then the filter cycle: an unrelated sensor event mustn't
    cancel the filter start, or the head start's 70 s off leaves it off all cycle."""
    tub.model_compressor = True
    await make_controller()
    tub.spa(setpoint=38.0)
    await advance(hass, freezer, 5)
    tub.circulation(True)
    await advance(hass, freezer, 3)
    tub.filter_cycle(1, True)
    await advance(hass, freezer, 5)
    if disturbance == "attribute update":
        hass.states.async_set(FILTER_1, "on", {"friendly_name": "Filtercyklus 1"})
    else:
        hass.states.async_set(FILTER_2, "unavailable")
    await advance(hass, freezer, 180, step=5)
    assert tub.hp_modes()[0] == "heat"
    assert "off" not in tub.hp_modes()


# --- 2026.10.7: one safety stop per cycle, filter-start skip ---------------


async def test_watch_only_logs_one_safety_stop_per_cycle(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    """The old automation keeps the heat pump in heat; the log must not repeat every 5 min."""
    controller = await make_controller(active=False)
    tub.model_compressor = True
    tub.circulation(True)
    await settle(hass)
    tub.filter_cycle(1, True)
    hass.states.async_set(HP, "heat", dict(hass.states.get(HP).attributes))
    tub.hp_power(1500)
    tub.spa(temperature=38.0)
    for i in range(50):  # L3 reports every few seconds in reality
        tub.hp_power(1500 + i % 2)
        await advance(hass, freezer, 30, step=10)
    stops = [
        line
        for line in controller.recent
        if "slukket: sikkerhedsstop" in line and "forsøg" not in line
    ]
    assert len(stops) == 1


async def test_a_filter_sensor_flap_after_a_safety_stop_does_not_switch_on(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    await _filter_cycle_running(hass, freezer, tub)
    tub.spa(temperature=38.0)
    await advance(hass, freezer, 300, step=10)
    assert tub.hp_modes()[-1] == "off"
    hass.states.async_set(FILTER_1, "unavailable")
    await advance(hass, freezer, 5)
    tub.filter_cycle(1, True)
    await advance(hass, freezer, 60, step=5)
    assert tub.hp_modes()[-1] == "off"
    assert _safety_stops(tub) == 1


async def test_the_next_filter_cycle_is_normal_again(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    await _filter_cycle_running(hass, freezer, tub)
    tub.spa(temperature=38.0)
    await advance(hass, freezer, 300, step=10)
    tub.filter_cycle(1, False)
    tub.circulation(False)
    tub.spa(temperature=37.0)
    await advance(hass, freezer, 600, step=30)
    assert controller.state.overtemp_stopped is False
    tub.circulation(True)
    await settle(hass)
    tub.filter_cycle(2, True)
    await advance(hass, freezer, 10)
    assert tub.hp_modes()[-1] == "heat"


async def test_the_safety_stop_latch_survives_a_restart(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    first = await make_controller()
    await _filter_cycle_running(hass, freezer, tub)
    tub.spa(temperature=38.0)
    await advance(hass, freezer, 300, step=10)
    await first.async_shutdown()
    tub.calls.clear()
    second = await make_controller(active=False, entry=first.entry)
    assert second.state.overtemp_stopped is True
    assert not any("filtercyklus: varmepumpen står tændt" in line for line in second.recent)


async def test_a_manual_off_does_not_block_the_filter_start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    """last_action is ON from an earlier heat call, but the heat pump was switched off by hand."""
    tub.model_compressor = True
    await make_controller()
    tub.spa(temperature=36.0)
    tub.circulation(True)
    await settle(hass)
    tub.spa(action="heating")
    await advance(hass, freezer, 120, step=10)
    assert tub.hp_modes() == ["heat"]
    hass.states.async_set(HP, "off", dict(hass.states.get(HP).attributes))
    tub.hp_power(8)
    tub.spa(action="idle")
    await advance(hass, freezer, 30)
    tub.filter_cycle(1, True)
    await advance(hass, freezer, 10)
    assert tub.hp_modes()[-1] == "heat"
    assert len(tub.hp_modes()) == 2
