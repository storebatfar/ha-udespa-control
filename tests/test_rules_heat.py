"""Heat-pump decisions and alert texts (pure)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from custom_components.udespa_control.const import (
    BackupKind,
    HeatAction,
    Status,
    Trigger,
)
from custom_components.udespa_control.rules import (
    HEAD_START_OFF_FAILED_ALERT,
    SpaView,
    backup_alert,
    backup_needed,
    fmt_c,
    fmt_num,
    heat_decision,
    heat_pump_running,
    heat_pump_stopped,
    heater_running,
    off_failed_alert,
    watchdog_should_act,
)


def spa(
    circulation=True,
    action="off",
    temperature=36.5,
    setpoint=37.0,
    status=Status.MAINTAINING,
) -> SpaView:
    return SpaView(circulation, action, temperature, setpoint, status)


def act(trigger, view, head_start=True, previous=None):
    decision = heat_decision(
        trigger, view, head_start=head_start, previous_action=previous
    )
    return None if decision is None else decision.action


# --- A1 -----------------------------------------------------------------------


def test_heating_with_circulation_switches_on():
    assert act(Trigger.SPA_HEATING, spa(action="heating"), previous="off") is HeatAction.ON


def test_second_heating_after_idle_is_the_same_call():
    """heating -> idle (90 s flow check) -> heating must not start a new job."""
    assert act(Trigger.SPA_HEATING, spa(action="heating"), previous="idle") is None


def test_heating_without_circulation_does_nothing():
    assert act(Trigger.SPA_HEATING, spa(circulation=False, action="heating")) is None


# --- Circulation start: A1 or A2 ------------------------------------------------


@pytest.mark.parametrize("action", ["heating", "idle"])
def test_circulation_start_with_a_call_switches_on(action):
    assert act(Trigger.CIRCULATION_ON, spa(action=action)) is HeatAction.ON


def test_circulation_start_in_use_without_call_head_starts():
    view = spa(status=Status.IN_USE)
    assert act(Trigger.CIRCULATION_ON, view) is HeatAction.HEAD_START


def test_head_start_toggle_off_means_no_head_start():
    view = spa(status=Status.IN_USE)
    assert act(Trigger.CIRCULATION_ON, view, head_start=False) is None


def test_filter_cycle_without_call_switches_nothing_on():
    """2026-10-02 14:00: circulation, Vedligeholder, spa at 38 over 37, no call."""
    view = spa(temperature=38.0, setpoint=37.0, status=Status.MAINTAINING)
    assert act(Trigger.CIRCULATION_ON, view) is None


def test_circulation_on_trigger_with_circulation_already_gone_does_nothing():
    assert act(Trigger.CIRCULATION_ON, spa(circulation=False, action="heating")) is None


# --- A3 -----------------------------------------------------------------------


def test_circulation_stop_switches_off():
    assert act(Trigger.CIRCULATION_OFF, spa(circulation=False)) is HeatAction.OFF


def test_satisfied_and_warm_enough_switches_off():
    decision = heat_decision(
        Trigger.SPA_SATISFIED, spa(temperature=37.5, setpoint=37.0), head_start=True
    )
    assert decision.action is HeatAction.OFF
    assert decision.reason == "spaen er varm nok (37,5 °C)"


def test_satisfied_at_exactly_setpoint_switches_off():
    assert act(Trigger.SPA_SATISFIED, spa(temperature=37.0, setpoint=37.0)) is HeatAction.OFF


def test_satisfied_below_setpoint_does_nothing():
    assert act(Trigger.SPA_SATISFIED, spa(temperature=36.5, setpoint=37.0)) is None


@pytest.mark.parametrize("temperature,setpoint", [(None, 37.0), (37.5, None)])
def test_satisfied_with_a_missing_temperature_never_switches_off(temperature, setpoint):
    view = spa(temperature=temperature, setpoint=setpoint)
    assert act(Trigger.SPA_SATISFIED, view) is None


# --- A2 via status --------------------------------------------------------------


def test_status_in_use_during_circulation_without_call_head_starts():
    view = spa(status=Status.IN_USE)
    assert act(Trigger.IN_USE, view) is HeatAction.HEAD_START


@pytest.mark.parametrize("action", ["heating", "idle", None])
def test_status_in_use_while_calling_or_unknown_does_nothing(action):
    assert act(Trigger.IN_USE, spa(action=action, status=Status.IN_USE)) is None


def test_status_in_use_without_circulation_does_nothing():
    assert act(Trigger.IN_USE, spa(circulation=False, status=Status.IN_USE)) is None


# --- A8 -----------------------------------------------------------------------


def test_startup_with_a_call_switches_on():
    assert act(Trigger.STARTUP, spa(action="idle")) is HeatAction.ON


def test_startup_in_use_without_call_head_starts():
    assert act(Trigger.STARTUP, spa(status=Status.IN_USE)) is HeatAction.HEAD_START


def test_startup_otherwise_switches_off():
    assert act(Trigger.STARTUP, spa(circulation=False)) is HeatAction.OFF
    assert act(Trigger.STARTUP, spa(status=Status.MAINTAINING)) is HeatAction.OFF


# --- A4 power -----------------------------------------------------------------


def test_power_thresholds():
    assert heat_pump_running(501, 500) and not heat_pump_running(500, 500)
    assert heat_pump_stopped(399, 400) and not heat_pump_stopped(400, 400)
    assert heater_running(1001, 1000) and not heater_running(1000, 1000)


def test_unknown_power_is_neither_running_nor_stopped():
    assert not heat_pump_running(None, 500)
    assert not heat_pump_stopped(None, 400)
    assert not heater_running(None, 1000)


# --- A5 gate --------------------------------------------------------------------


def test_backup_needed_below_setpoint_minus_margin():
    assert backup_needed(36.4, 37.0, 0.5)


def test_backup_not_needed_within_margin():
    assert not backup_needed(36.5, 37.0, 0.5)


def test_satisfied_is_not_failed():
    """Low power while the water is above setpoint is no failure."""
    assert not backup_needed(38.0, 37.0, 0.5)


@pytest.mark.parametrize("temperature,setpoint", [(None, 37.0), (30.0, None)])
def test_backup_never_fires_on_a_missing_temperature(temperature, setpoint):
    assert not backup_needed(temperature, setpoint, 0.5)


# --- A6 -----------------------------------------------------------------------

WATCH = {
    "failure_open": False,
    "circulation_on_for": timedelta(minutes=12),
    "min_circulation": timedelta(minutes=10),
    "temperature": 36.0,
    "setpoint": 37.0,
    "margin": 0.5,
    "hp_power": 8.0,
    "on_w": 500,
}


def test_watchdog_acts_on_a_silent_heat_pump():
    assert watchdog_should_act(**WATCH)


@pytest.mark.parametrize(
    "change",
    [
        {"failure_open": True},
        {"circulation_on_for": None},
        {"circulation_on_for": timedelta(minutes=9)},
        {"temperature": 36.6},
        {"temperature": None},
        {"setpoint": None},
        {"hp_power": 900.0},
        {"hp_power": None},
    ],
)
def test_watchdog_stays_quiet(change):
    assert not watchdog_should_act(**{**WATCH, **change})


# --- Texts --------------------------------------------------------------------


def test_number_formatting_is_danish():
    assert fmt_c(37.5) == "37,5"
    assert fmt_c(37) == "37,0"
    assert fmt_num(4.0) == "4"
    assert fmt_num(2.5) == "2,5"


def test_backup_alert_retry_with_heater_running():
    assert backup_alert(
        BackupKind.RETRY,
        heater_running=True,
        backup_enabled=True,
        retry_minutes=4,
        circulation_minutes=10,
    ) == (
        "Udespa Varmepumpe",
        ("Varmepumpen kom ikke i drift inden for 4 minutter, og vandet er under "
        "setpunkt. Varmelegemet er tændt som backup og trækker strøm."),
    )


def test_backup_alert_watchdog_with_heater_running():
    title, message = backup_alert(
        BackupKind.WATCHDOG,
        heater_running=True,
        backup_enabled=True,
        retry_minutes=4,
        circulation_minutes=10,
    )
    assert title == "Udespa Varmepumpe"
    assert message.startswith(
        "Varmepumpen trækker ikke strøm efter 10+ minutters cirkulation"
    )


@pytest.mark.parametrize("kind", list(BackupKind))
def test_backup_alert_no_heat_source(kind):
    title, message = backup_alert(
        kind,
        heater_running=False,
        backup_enabled=True,
        retry_minutes=4,
        circulation_minutes=10,
    )
    assert title == "⚠️ Udespa uden varmekilde"
    assert message.endswith("Spaen har ingen varmekilde — tjek den.")


def test_backup_alert_when_backup_is_disabled():
    title, message = backup_alert(
        BackupKind.RETRY,
        heater_running=False,
        backup_enabled=False,
        retry_minutes=4,
        circulation_minutes=10,
    )
    assert title == "⚠️ Udespa Varmepumpe"
    assert "Backup-varmelegemet er slået fra" in message


def test_off_failed_alert_depends_on_circulation():
    _, running = off_failed_alert(circulation=True, retry_minutes=4)
    _, stopped = off_failed_alert(circulation=False, retry_minutes=4)
    assert running.startswith("Spaen er varm nok, men varmepumpen kunne ikke slukkes inden for 4 minutter")
    assert "kører uden vandcirkulation" in stopped


def test_head_start_off_failed_alert_text():
    assert HEAD_START_OFF_FAILED_ALERT == (
        "⚠️ Udespa Varmepumpe",
        ("Hurtigstart: spaen kaldte ikke på varme, men varmepumpen kunne ikke "
        "slukkes igen og trækker strøm på L3."),
    )


# --- Rule F: filter cycles ---------------------------------------------------


def fspa(**changes) -> SpaView:
    values = {
        "circulation": True,
        "hvac_action": "off",
        "temperature": 37.0,
        "setpoint": 37.0,
        "status": Status.MAINTAINING,
        "filter_cycle": True,
    }
    values.update(changes)
    return SpaView(**values)


def fact(trigger, view, stay=True, previous=None):
    decision = heat_decision(
        trigger, view, head_start=True, previous_action=previous, filter_stay_on=stay
    )
    return None if decision is None else decision.action


def test_filter_start_with_circulation_switches_on():
    assert fact(Trigger.FILTER_START, fspa()) is HeatAction.ON


def test_filter_start_needs_circulation_the_toggle_and_a_cycle():
    assert fact(Trigger.FILTER_START, fspa(circulation=False)) is None
    assert fact(Trigger.FILTER_START, fspa(), stay=False) is None
    assert fact(Trigger.FILTER_START, fspa(filter_cycle=False)) is None


def test_satisfied_during_a_filter_cycle_never_switches_off():
    assert fact(Trigger.SPA_SATISFIED, fspa(temperature=38.0)) is None


def test_circulation_stop_still_switches_off_in_a_filter_cycle():
    assert fact(Trigger.CIRCULATION_OFF, fspa(circulation=False)) is HeatAction.OFF


def test_no_head_start_in_a_filter_cycle():
    assert fact(Trigger.IN_USE, fspa(status=Status.IN_USE)) is None
    assert fact(Trigger.CIRCULATION_ON, fspa(status=Status.IN_USE)) is HeatAction.ON


def test_startup_mid_cycle_switches_on():
    assert fact(Trigger.STARTUP, fspa()) is HeatAction.ON
    assert fact(Trigger.STARTUP, fspa(circulation=False)) is HeatAction.OFF


def test_spa_heating_in_a_filter_cycle_still_switches_on():
    assert fact(Trigger.SPA_HEATING, fspa(hvac_action="heating"), previous="off") is HeatAction.ON


def test_toggle_off_keeps_todays_behaviour():
    view = fspa(temperature=37.5)
    assert fact(Trigger.SPA_SATISFIED, view, stay=False) is HeatAction.OFF
    assert fact(Trigger.IN_USE, fspa(status=Status.IN_USE), stay=False) is HeatAction.HEAD_START


