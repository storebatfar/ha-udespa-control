"""Outgoing commands and the watch-only gate."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.udespa_control.actuators import Actuators
from custom_components.udespa_control.const import OPT_NOTIFICATIONS
from custom_components.udespa_control.settings import Settings

from .common import ENTITY_DATA, HEATER, HP, PUMP, SPA, FakeTub


def _actuators(hass, *, active=True, **options):
    journal: list[str] = []
    actuators = Actuators(
        hass,
        Settings.from_mappings(ENTITY_DATA, options),
        journal.append,
        lambda: active,
    )
    return actuators, journal


async def test_active_sends_and_records(hass: HomeAssistant, tub: FakeTub):
    actuators, journal = _actuators(hass)
    assert await actuators.heat_pump_mode("off", "spaen er varm nok (37,5 °C)")
    assert tub.hp_modes() == ["off"]
    assert journal == ["Varmepumpe slukket: spaen er varm nok (37,5 °C)"]


async def test_watch_only_sends_nothing_and_says_so(hass: HomeAssistant, tub: FakeTub):
    actuators, journal = _actuators(hass, active=False)
    assert not await actuators.heat_pump_mode("heat", "spaen kalder på varme")
    assert not await actuators.heater(True, "frost")
    assert not await actuators.heat_pump_temperature(38.0, "følger spaen")
    assert not await actuators.heat_pump_preset("smart", "status er I brug")
    assert not await actuators.notify("Udespa Varmepumpe", "tekst")
    assert tub.calls == []
    assert journal[0] == "(kun overvågning) Varmepumpe tændt: spaen kalder på varme"
    assert all(line.startswith("(kun overvågning) ") for line in journal)


async def test_deliberate_commands_act_even_in_watch_only(hass: HomeAssistant, tub: FakeTub):
    actuators, _ = _actuators(hass, active=False)
    assert await actuators.spa_setpoint(37.5, "hævet")
    assert await actuators.cleaning_pump(True, "rengøring cyklus 1")
    assert await actuators.heat_pump_preset("quiet", "valgt manuelt", deliberate=True)
    assert hass.states.get(SPA).attributes["temperature"] == 37.5
    assert hass.states.get(PUMP).state == "on"
    assert hass.states.get(HP).attributes["preset_mode"] == "quiet"


async def test_heater_and_temperature_targets(hass: HomeAssistant, tub: FakeTub):
    actuators, _ = _actuators(hass)
    await actuators.heater(True, "backup")
    await actuators.heat_pump_temperature(38.5, "følger spaens setpunkt")
    assert hass.states.get(HEATER).state == "on"
    assert hass.states.get(HP).attributes["temperature"] == 38.5


async def test_notifications_toggle_off(hass: HomeAssistant, tub: FakeTub):
    actuators, journal = _actuators(hass, **{OPT_NOTIFICATIONS: False})
    assert not await actuators.notify("Udespa Varmepumpe", "tekst")
    assert tub.notifications() == []
    assert "ikke sendt" in journal[-1]


async def test_notify_sends_title_and_message(hass: HomeAssistant, tub: FakeTub):
    actuators, _ = _actuators(hass)
    assert await actuators.notify("Udespa Varmepumpe", "tekst")
    assert tub.notifications()[0].data == {"title": "Udespa Varmepumpe", "message": "tekst"}


async def test_a_failing_service_never_raises(hass: HomeAssistant, tub: FakeTub):
    tub.fail_services.add("climate.set_hvac_mode")
    actuators, journal = _actuators(hass)
    assert not await actuators.heat_pump_mode("heat", "spaen kalder på varme")
    assert "fejlede" in journal[-1]


async def test_a_missing_service_never_raises(hass: HomeAssistant):
    actuators, journal = _actuators(hass)
    assert not await actuators.heater(True, "backup")
    assert "fejlede" in journal[-1]
