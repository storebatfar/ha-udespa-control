"""The controller, end to end on the fake tub."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.udespa_control.const import (
    OPT_FAULT_STATUS,
    OPT_MODE_IN_USE,
    OPT_WATCHDOG,
    Mode,
    Status,
    SyncStatus,
    Timer,
)

from .common import HEATER, HP, SPA, FakeTub, advance, settle


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
    tub.filter_cycle(1, True)
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
    await make_controller()
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
