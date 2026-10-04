"""B12′: the heat pump's mode, sent and verified."""

from __future__ import annotations

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant

from custom_components.udespa_control.actuators import Actuators
from custom_components.udespa_control.const import Mode
from custom_components.udespa_control.mode import ModeKeeper
from custom_components.udespa_control.reader import TubReader
from custom_components.udespa_control.settings import Settings

from .common import ENTITY_DATA, HP, FakeTub, advance, settle


class Harness:
    def __init__(self, hass: HomeAssistant) -> None:
        self.journal: list[str] = []
        self.active = True
        settings = Settings.from_mappings(ENTITY_DATA, {})
        actuators = Actuators(hass, settings, self.journal.append, lambda: self.active)
        self.keeper = ModeKeeper(
            hass, settings, TubReader(hass, settings), actuators, self.journal.append
        )


@pytest.fixture
async def harness(hass: HomeAssistant, tub: FakeTub):
    made: list[Harness] = []

    def _make() -> Harness:
        made.append(Harness(hass))
        return made[-1]

    yield _make
    for item in made:
        await item.keeper.async_shutdown()


def _preset(hass) -> str:
    return hass.states.get(HP).attributes["preset_mode"]


async def test_a_mode_that_sticks_is_sent_once(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    h = harness()
    h.keeper.apply(Mode.SMART, "status er I brug")
    await advance(hass, freezer, 40, step=2)
    assert tub.presets() == ["smart"]
    assert not h.keeper.in_window
    assert h.keeper.wanted is Mode.SMART


async def test_already_in_the_mode_sends_nothing(hass: HomeAssistant, tub: FakeTub, harness):
    h = harness()
    h.keeper.apply(Mode.QUIET, "status er Vedligeholder")  # the fake starts on quick
    await settle(hass)
    assert tub.presets() == []
    assert h.keeper.wanted is Mode.QUIET


async def test_a_dropped_mode_is_resent_and_sticks(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.drop_presets = 1
    h = harness()
    h.keeper.apply(Mode.SMART, "status er I brug")
    await advance(hass, freezer, 40, step=2)
    assert tub.presets() == ["smart", "smart"]
    assert _preset(hass) == "smart"
    assert not any("afviste" in line for line in h.journal)


async def test_a_mode_dropped_three_times_is_recorded(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.drop_presets = 10
    h = harness()
    h.keeper.apply(Mode.SMART, "status er I brug")
    await advance(hass, freezer, 60, step=2)
    assert tub.presets() == ["smart", "smart", "smart"]
    assert h.journal[-1] == "Varmepumpen afviste Smart efter 3 forsøg"
    await advance(hass, freezer, 60, step=5)
    assert len(tub.presets()) == 3


async def test_new_apply_cancels_the_old_check(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.drop_presets = 1
    h = harness()
    h.keeper.apply(Mode.SMART, "status er I brug")
    await advance(hass, freezer, 3)
    h.keeper.apply(Mode.TURBO, "valgt manuelt", deliberate=True)
    await advance(hass, freezer, 40, step=2)
    assert tub.presets().count("smart") == 1  # the stale mode is never resent
    assert _preset(hass) == "quiet"
    assert h.keeper.wanted is Mode.TURBO


async def test_unavailable_heat_pump_during_check(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    h = harness()
    h.keeper.apply(Mode.SMART, "status er I brug")
    await settle(hass)
    tub.fail_services.add("climate.set_preset_mode")
    hass.states.async_set(HP, "unavailable", {})
    await advance(hass, freezer, 40, step=2)
    assert h.journal[-1] == "Varmepumpen afviste Smart efter 3 forsøg"
    assert len(tub.presets()) == 3


async def test_reassert_without_wanted_mode_does_nothing(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    h = harness()
    h.keeper.reassert("efter tænd")
    await advance(hass, freezer, 30, step=2)
    assert tub.presets() == []
    assert h.journal == []


async def test_reassert_resends_a_mode_dropped_at_power_on(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    h = harness()
    h.keeper.apply(Mode.SMART, "status er I brug")
    await advance(hass, freezer, 40, step=2)
    hass.states.async_set(HP, "heat", {**hass.states.get(HP).attributes, "preset_mode": "quick"})
    h.keeper.reassert("efter tænd")
    await advance(hass, freezer, 30, step=2)
    assert tub.presets() == ["smart", "smart"]
    assert _preset(hass) == "smart"


async def test_change_outside_the_window_is_adopted(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.drop_presets = 10
    h = harness()
    h.keeper.apply(Mode.SMART, "status er I brug")
    h.keeper.adopt("quick")  # inside the window: ignored
    assert h.keeper.wanted is Mode.SMART
    await advance(hass, freezer, 40, step=2)  # refused, window closed
    h.keeper.adopt("quick")
    assert h.keeper.wanted is Mode.QUIET
    h.keeper.reassert("efter tænd")
    await advance(hass, freezer, 30, step=2)
    assert len(tub.presets()) == 3  # nothing more: the heat pump is in the adopted mode


async def test_watch_only_logs_automatic_sends_but_a_manual_pick_acts(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    h = harness()
    h.active = False
    h.keeper.apply(Mode.SMART, "status er I brug")
    await settle(hass)
    assert tub.presets() == []
    assert h.journal[0] == "(kun overvågning) Varmepumpe tilstand smart: status er I brug"
    h.keeper.apply(Mode.TURBO, "valgt manuelt", deliberate=True)
    await advance(hass, freezer, 15, step=5)
    assert tub.presets() == ["quiet"]


async def test_a_late_drop_is_caught_not_adopted(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    """The first check can still read the optimistic write; the mode must hold twice."""
    tub.PRESET_REPORT_S = 12
    tub.drop_presets = 1
    h = harness()
    h.keeper.apply(Mode.SMART, "status er I brug")
    await advance(hass, freezer, 50, step=2)
    assert tub.presets() == ["smart", "smart"]
    assert _preset(hass) == "smart"
    assert h.keeper.wanted is Mode.SMART


async def test_watch_only_mismatch_is_marked_as_watch_only(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    h = harness()
    h.active = False
    h.keeper.apply(Mode.SMART, "status er I brug")
    await advance(hass, freezer, 40, step=2)
    assert tub.presets() == []
    assert h.journal[-1] == "(kun overvågning) Varmepumpen står ikke i Smart efter 3 forsøg"


async def test_reassert_leaves_a_running_check_for_the_wanted_mode(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    """A logged-only switch-on must not turn a manual pick's real check into logs."""
    tub.drop_presets = 1
    h = harness()
    h.active = False
    h.keeper.apply(Mode.TURBO, "valgt manuelt", deliberate=True)
    await advance(hass, freezer, 3)
    h.keeper.reassert("efter tænd")
    await advance(hass, freezer, 40, step=2)
    assert tub.presets() == ["quiet", "quiet"]
    assert _preset(hass) == "quiet"


async def test_same_mode_apply_keeps_the_running_check(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, harness
):
    tub.drop_presets = 1
    h = harness()
    h.keeper.apply(Mode.SMART, "valgt manuelt", deliberate=True)
    await advance(hass, freezer, 3)
    h.keeper.apply(Mode.SMART, "status er I brug")  # the optimistic "smart" matches
    await advance(hass, freezer, 40, step=2)
    assert tub.presets() == ["smart", "smart"]
    assert _preset(hass) == "smart"
