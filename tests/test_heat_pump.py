"""The heat-pump job, verified on power."""

from __future__ import annotations

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant

from custom_components.udespa_control.actuators import Actuators
from custom_components.udespa_control.const import OPT_BACKUP, HeatAction
from custom_components.udespa_control.heat_pump import HeatPump
from custom_components.udespa_control.reader import TubReader
from custom_components.udespa_control.rules import (
    HEAD_START_OFF_FAILED_ALERT,
    Decision,
)
from custom_components.udespa_control.settings import Settings

from .common import ENTITY_DATA, HP, FakeTub, advance, settle

ON = Decision(HeatAction.ON, "spaen kalder på varme")
OFF = Decision(HeatAction.OFF, "spaen er varm nok (37,5 °C)")
HEAD_START = Decision(HeatAction.HEAD_START, "hurtigstart: cirkulation startet i I brug")


class Harness:
    def __init__(self, hass: HomeAssistant, **options) -> None:
        self.journal: list[str] = []
        self.failure = False
        self.active = True
        settings = Settings.from_mappings(ENTITY_DATA, options)
        actuators = Actuators(hass, settings, self.journal.append, lambda: self.active)
        self.hp = HeatPump(
            hass,
            settings,
            TubReader(hass, settings),
            actuators,
            record=self.journal.append,
            failure_open=lambda: self.failure,
            set_failure=self._set_failure,
        )

    def _set_failure(self, value: bool) -> None:
        self.failure = value


@pytest.fixture
async def harness(hass: HomeAssistant, tub: FakeTub):
    made: list[Harness] = []

    def _make(**options) -> Harness:
        made.append(Harness(hass, **options))
        return made[-1]

    yield _make
    for item in made:
        await item.hp.async_shutdown()


# --- On ---------------------------------------------------------------------------


async def test_on_job_sends_heat_and_stops_once_power_confirms(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    h = harness()
    h.hp.start(ON)
    await settle(hass)
    assert tub.hp_modes() == ["heat"]
    await advance(hass, freezer, 20)
    tub.hp_power(1500)
    await advance(hass, freezer, 15)
    assert not h.hp.busy
    assert tub.hp_modes() == ["heat"]
    assert h.journal[0] == "Varmepumpe tændt: spaen kalder på varme"


async def test_on_job_resends_only_when_the_entity_lost_the_mode(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    """tuya_local writes "heat" at once; a re-send only helps if it lapsed."""
    h = harness()
    h.hp.start(ON)
    await advance(hass, freezer, 31)
    assert tub.hp_modes() == ["heat"]
    hass.states.async_set(HP, "off", dict(hass.states.get(HP).attributes))
    await advance(hass, freezer, 15)
    assert tub.hp_modes() == ["heat", "heat"]
    assert "(forsøg" in h.journal[-1]


async def test_on_job_sends_first_even_if_the_entity_already_says_heat(
    hass: HomeAssistant, tub: FakeTub, harness
):
    hass.states.async_set(HP, "heat", dict(hass.states.get(HP).attributes))
    harness().hp.start(ON)
    await settle(hass)
    assert tub.hp_modes() == ["heat"]


async def test_already_running_still_gets_heat_and_recovers(
    hass: HomeAssistant, tub: FakeTub, harness
):
    tub.hp_power(1500)
    hass.states.async_set("switch.varmelegeme", "on")
    tub.outdoor(10.0)
    h = harness()
    h.failure = True
    h.hp.start(ON)
    await settle(hass)
    assert tub.hp_modes() == ["heat"]
    assert h.failure is False
    assert tub.heater_commands() == ["off"]


async def test_recovery_leaves_the_heater_on_below_the_frost_limit(
    hass: HomeAssistant, tub: FakeTub, harness
):
    tub.hp_power(1500)
    hass.states.async_set("switch.varmelegeme", "on")
    tub.outdoor(3.0)
    h = harness()
    h.failure = True
    await h.hp.async_recover()
    assert h.failure is False
    assert tub.heater_commands() == []


async def test_recovery_leaves_the_heater_alone_when_outdoor_is_unknown(
    hass: HomeAssistant, tub: FakeTub, harness
):
    hass.states.async_set("switch.varmelegeme", "on")
    tub.outdoor(None)
    await harness().hp.async_recover()
    assert tub.heater_commands() == []


# --- A5 backup ------------------------------------------------------------------


async def test_no_start_and_cold_water_fires_the_backup(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.spa(temperature=35.0, setpoint=37.0)
    h = harness()
    h.hp.start(ON)
    await advance(hass, freezer, 240, step=5)
    assert tub.heater_commands() == ["on"]
    tub.heater_power(2000)
    await advance(hass, freezer, 150, step=5)
    assert [n.data["title"] for n in tub.notifications()] == ["Udespa Varmepumpe"]
    assert h.failure is True
    assert not h.hp.busy


async def test_backup_without_heater_power_says_no_heat_source(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.spa(temperature=35.0, setpoint=37.0)
    harness().hp.start(ON)
    await advance(hass, freezer, 400, step=5)
    assert tub.notifications()[0].data["title"] == "⚠️ Udespa uden varmekilde"


async def test_no_start_but_warm_water_is_not_a_failure(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.spa(temperature=38.0, setpoint=37.0)
    h = harness()
    h.hp.start(ON)
    await advance(hass, freezer, 400, step=5)
    assert tub.heater_commands() == []
    assert tub.notifications() == []
    assert h.failure is False


async def test_missing_spa_temperature_never_fires_the_backup(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.spa(temperature=None, setpoint=37.0)
    h = harness()
    h.hp.start(ON)
    await advance(hass, freezer, 400, step=5)
    assert tub.heater_commands() == []
    assert h.failure is False


async def test_one_alert_per_failure(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.spa(temperature=35.0, setpoint=37.0)
    h = harness()
    h.failure = True
    h.hp.start(ON)
    await advance(hass, freezer, 400, step=5)
    assert tub.heater_commands() == ["on"]
    assert tub.notifications() == []


async def test_backup_toggle_off_alerts_without_the_heater(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.spa(temperature=35.0, setpoint=37.0)
    h = harness(**{OPT_BACKUP: False})
    h.hp.start(ON)
    await advance(hass, freezer, 400, step=5)
    assert tub.heater_commands() == []
    assert "Backup-varmelegemet er slået fra" in tub.notifications()[0].data["message"]
    assert h.failure is True


# --- Off --------------------------------------------------------------------------


async def test_off_job_sends_first_even_if_the_entity_shows_off(
    hass: HomeAssistant, tub: FakeTub, harness
):
    """Command before verification: a pump idling at setpoint still gets "off"."""
    h = harness()
    h.hp.start(OFF)
    await settle(hass)
    assert tub.hp_modes() == ["off"]
    assert not h.hp.busy


async def test_off_job_waits_for_power_to_drop(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.hp_power(1500)
    h = harness()
    h.hp.start(OFF)
    await advance(hass, freezer, 60)
    assert h.hp.busy
    tub.hp_power(8)
    await advance(hass, freezer, 15)
    assert not h.hp.busy
    assert tub.hp_modes() == ["off"]
    assert tub.notifications() == []


@pytest.mark.parametrize(
    "circulation,expected",
    [(True, "Spaen er varm nok"), (False, "kører uden vandcirkulation")],
)
async def test_off_job_alerts_when_power_never_drops(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    tub: FakeTub,
    harness,
    circulation,
    expected,
):
    tub.hp_power(1500)
    tub.circulation(circulation)
    harness().hp.start(OFF)
    await advance(hass, freezer, 250, step=5)
    assert expected in tub.notifications()[0].data["message"]


async def test_off_job_alerts_when_power_sensor_unavailable(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.hp_power("unavailable")
    h = harness()
    h.hp.start(OFF)
    await advance(hass, freezer, 250, step=5)
    assert len(tub.notifications()) == 1
    assert not h.hp.busy


# --- Head start -----------------------------------------------------------------


async def test_head_start_switches_off_again_without_a_call(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.circulation(True)
    h = harness()
    h.hp.start(HEAD_START)
    await advance(hass, freezer, 69)
    assert tub.hp_modes() == ["heat"]
    await advance(hass, freezer, 1)
    assert tub.hp_modes() == ["heat", "off"]
    await advance(hass, freezer, 40)
    assert not h.hp.busy
    assert tub.notifications() == []


async def test_head_start_off_waits_past_compressor_start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    """At 70 s the compressor has not started, so low power proves nothing yet."""
    tub.model_compressor = True
    h = harness()
    h.hp.start(HEAD_START)
    await advance(hass, freezer, 72)
    assert h.hp.busy  # an instant power check would already have declared success
    await advance(hass, freezer, 38)
    assert not h.hp.busy


async def test_head_start_alerts_when_the_off_is_lost(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.model_compressor = True
    h = harness()
    h.hp.start(HEAD_START)
    await settle(hass)
    tub.fail_services.add("climate.set_hvac_mode")  # every "off" goes missing
    await advance(hass, freezer, 70 + 3 * 40, step=5)
    assert [n.data["title"] for n in tub.notifications()] == [HEAD_START_OFF_FAILED_ALERT[0]]
    assert tub.notifications()[0].data["message"] == HEAD_START_OFF_FAILED_ALERT[1]


async def test_a_heat_call_during_head_start_takes_over(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    h = harness()
    h.hp.start(HEAD_START)
    await advance(hass, freezer, 55)
    h.hp.start(ON)
    await advance(hass, freezer, 40)
    tub.hp_power(1500)
    await advance(hass, freezer, 120, step=5)
    assert "off" not in tub.hp_modes()


async def test_head_start_stops_quietly_if_the_spa_is_calling_at_timeout(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    h = harness()
    h.hp.start(HEAD_START)
    await advance(hass, freezer, 30)
    tub.spa(action="idle")
    await advance(hass, freezer, 40)
    assert tub.hp_modes() == ["heat"]
    assert not h.hp.busy


# --- Concurrency and watchdog ---------------------------------------------------


async def test_a_new_decision_cancels_the_running_job(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.spa(temperature=35.0, setpoint=37.0)
    h = harness()
    h.hp.start(ON)
    await advance(hass, freezer, 30)
    h.hp.start(OFF)
    await advance(hass, freezer, 400, step=5)
    assert tub.hp_modes() == ["heat", "off"]
    assert tub.heater_commands() == []  # the cancelled on-job never reached its backup


async def test_watchdog_backup_runs_once_at_a_time(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    h = harness()
    h.hp.start_watchdog_backup("varmepumpen trækker ikke strøm")
    h.hp.start_watchdog_backup("varmepumpen trækker ikke strøm")
    await advance(hass, freezer, 150, step=5)
    assert tub.heater_commands() == ["on"]
    assert len(tub.notifications()) == 1
    assert h.failure is True


async def test_watchdog_backup_is_not_cancelled_by_a_job(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    h = harness()
    h.hp.start_watchdog_backup("varmepumpen trækker ikke strøm")
    await settle(hass)
    h.hp.start(OFF)
    await advance(hass, freezer, 150, step=5)
    assert h.failure is True


async def test_watch_only_runs_the_same_logic_but_sends_nothing(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.spa(temperature=35.0, setpoint=37.0)
    h = harness()
    h.active = False
    h.hp.start(ON)
    await advance(hass, freezer, 400, step=5)
    assert tub.calls == []
    assert any("Varmelegeme tændt" in line for line in h.journal)
    assert any(line.startswith("(kun overvågning) Notifikation") for line in h.journal)


async def test_shutdown_cancels_everything(hass: HomeAssistant, tub: FakeTub, harness):
    h = harness()
    h.hp.start(ON)
    h.hp.start_watchdog_backup("test")
    await settle(hass)
    await h.hp.async_shutdown()
    assert not h.hp.busy


async def test_a_call_during_the_soft_stop_still_sends_heat(
    hass: HomeAssistant, tub: FakeTub, harness
):
    """After "off" the compressor draws power for ~69 s; that is not "running"."""
    tub.hp_power(1500)
    h = harness()
    h.hp.start(ON)
    await settle(hass)
    assert tub.hp_modes() == ["heat"]


async def test_backup_stands_down_if_the_pump_starts_during_the_check(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.spa(temperature=35.0)
    h = harness()
    h.hp.start_watchdog_backup("varmepumpen trækker ikke strøm")
    await advance(hass, freezer, 60)
    tub.hp_power(1500)
    await advance(hass, freezer, 100, step=5)
    assert tub.notifications() == []
    assert h.failure is False


async def test_backup_running_is_visible_during_the_check(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    h = harness()
    h.hp.start_watchdog_backup("varmepumpen trækker ikke strøm")
    await advance(hass, freezer, 60)
    assert h.hp.backup_running
    await advance(hass, freezer, 100, step=5)
    assert not h.hp.backup_running


async def test_switching_on_tells_the_mode_keeper(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    calls: list[int] = []
    h = harness()
    h.hp._on_switched_on = lambda: calls.append(1)
    h.hp.start(ON)
    await settle(hass)
    assert calls == [1]
    h.hp.start(HEAD_START)
    await settle(hass)
    assert calls == [1, 1]
    await advance(hass, freezer, 31)  # re-sends of "heat" don't count as a new switch-on
    assert calls == [1, 1]
