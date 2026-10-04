"""Recorded sequences from 2026-10-02, replayed through the controller."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.udespa_control.const import Status

from .common import HP, FakeTub, advance, settle

Event = tuple[int, Callable[[FakeTub], None]]


async def play(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    tub: FakeTub,
    events: list[Event],
    until: int,
    step: float = 1.0,
) -> None:
    now = 0
    for at, action in events:
        if at > now:
            await advance(hass, freezer, at - now, step=step)
            now = at
        action(tub)
        await settle(hass)
    await advance(hass, freezer, until - now, step=step)


def hvac_timeline(tub: FakeTub, t0: datetime) -> list[tuple[int, str]]:
    return [
        (round((c.at - t0).total_seconds()), c.data["hvac_mode"])
        for c in tub.sent("climate", "set_hvac_mode")
        if c.data["entity_id"] == HP
    ]


def preset_timeline(tub: FakeTub, t0: datetime) -> list[tuple[int, str]]:
    return [
        (round((c.at - t0).total_seconds()), c.data["preset_mode"])
        for c in tub.sent("climate", "set_preset_mode")
    ]


def _calm_warm_tub(tub: FakeTub) -> None:
    tub.model_compressor = True
    tub.spa(action="off", temperature=38.0, setpoint=37.0)


# 2026-10-02 21:21:38: setpoint raised in steps, a heat call, setpoint back, done.
HEAT_CALL_2121: list[Event] = [
    (0, lambda t: t.circulation(True)),
    (0, lambda t: t.spa(setpoint=37.5)),
    (1, lambda t: t.spa(setpoint=38.0)),
    (1, lambda t: t.spa(setpoint=38.5)),
    (8, lambda t: t.spa(setpoint=39.0)),
    (60, lambda t: t.spa(temperature=36.5)),
    (60, lambda t: t.spa(action="heating")),
    (67, lambda t: t.spa(action="idle")),
    (157, lambda t: t.spa(action="heating")),
    (170, lambda t: t.spa(temperature=37.0)),
    (180, lambda t: t.spa(setpoint=38.5)),
    (181, lambda t: t.spa(setpoint=38.0)),
    (193, lambda t: t.spa(setpoint=37.5)),
    (195, lambda t: t.spa(setpoint=37.0)),
    (198, lambda t: t.spa(temperature=37.5)),
    (316, lambda t: t.spa(action="off", temperature=38.0)),
    (376, lambda t: t.circulation(False)),
]

# 2026-10-02 21:44:10: setpoint 39 with circulation; I brug head start, call, done.
HEAD_START_2144: list[Event] = [
    (0, lambda t: t.circulation(True)),
    (0, lambda t: t.spa(setpoint=39.0)),
    (60, lambda t: t.spa(temperature=36.5)),
    (60, lambda t: t.spa(action="heating")),
    (66, lambda t: t.spa(action="idle")),
    (67, lambda t: t.spa(temperature=37.0)),
    (117, lambda t: t.spa(temperature=36.5)),
    (120, lambda t: t.spa(temperature=37.0)),
    (156, lambda t: t.spa(action="heating")),
    (170, lambda t: t.spa(temperature=37.5)),
    (188, lambda t: t.spa(setpoint=37.0)),
    (245, lambda t: t.spa(action="off")),
    (255, lambda t: t.spa(temperature=38.0)),
    (302, lambda t: t.spa(temperature=37.5)),
    (305, lambda t: t.circulation(False)),
]

# 2026-10-02 14:00:26: filter cycle, spa at 38 over setpoint 37, never calls.
FILTER_CYCLE_1400: list[Event] = [
    (0, lambda t: t.filter_cycle(1, True)),
    (0, lambda t: t.circulation(True)),
    (60, lambda t: t.spa(temperature=38.0)),
    (119, lambda t: t.spa(temperature=38.5)),
    (234, lambda t: t.spa(temperature=38.0)),
]


async def test_2121_heat_call(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    _calm_warm_tub(tub)
    controller = await make_controller()
    t0 = dt_util.utcnow()
    await play(hass, freezer, tub, HEAT_CALL_2121, until=460)

    assert hvac_timeline(tub, t0) == [
        (5, "heat"),  # head start when the status turns I brug (old: 21:21:43)
        (60, "heat"),  # the spa calls: the on-job takes over
        (321, "off"),  # satisfied for 5 s at 38 >= 37
        (376, "off"),  # circulation stopped
    ]
    assert preset_timeline(tub, t0) == [(5, "smart"), (200, "quick")]
    assert hass.states.get(HP).attributes["temperature"] == 37.0
    assert tub.notifications() == []
    assert tub.heater_commands() == []
    assert controller.status is Status.MAINTAINING


async def test_2144_head_start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    _calm_warm_tub(tub)
    controller = await make_controller()
    t0 = dt_util.utcnow()
    await play(hass, freezer, tub, HEAD_START_2144, until=400)

    assert hvac_timeline(tub, t0) == [
        (5, "heat"),
        (60, "heat"),
        (250, "off"),
        (305, "off"),
    ]
    assert preset_timeline(tub, t0) == [(5, "smart"), (193, "quick")]
    assert tub.notifications() == []
    assert controller.status is Status.MAINTAINING


async def test_1400_filter_cycle_keeps_the_heat_pump_on(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    """Rule F: the heat pump stays on; the old overshoot (38-38.5 over 37) trips F5.

    The spa reads at least 1 grad over its setpoint from the start, so the
    safety stop fires after 5 minutes.
    """
    _calm_warm_tub(tub)
    await make_controller()
    t0 = dt_util.utcnow()
    await play(hass, freezer, tub, FILTER_CYCLE_1400, until=299)
    assert hvac_timeline(tub, t0) == [(0, "heat")]  # circulation started inside the cycle
    await advance(hass, freezer, 1)
    assert hvac_timeline(tub, t0) == [(0, "heat"), (300, "off")]
    assert [c.data["message"][:15] for c in tub.notifications()] == ["Sikkerhedsstop:"]
    assert tub.presets() == []
    assert tub.heater_commands() == []


async def test_2144_in_watch_only_sends_nothing_and_logs_every_decision(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    _calm_warm_tub(tub)
    controller = await make_controller(active=False)
    await play(hass, freezer, tub, HEAD_START_2144, until=400)
    assert tub.calls == []
    log = list(controller.recent)
    assert "(kun overvågning) Varmepumpe tændt: hurtigstart: status blev I brug under cirkulation" in log
    assert "(kun overvågning) Varmepumpe tændt: spaen kalder på varme" in log
    assert "(kun overvågning) Varmepumpe slukket: spaen er varm nok (37,5 °C)" in log
    assert "(kun overvågning) Varmepumpe slukket: cirkulationen er stoppet" in log


# 2026-10-04 14:10-15:30: the stay-on test (calibration 0). The spa never
# called; it read 37-38 while the heat pump regulated itself.
STAY_ON_TEST_1410: list[Event] = [
    (0, lambda t: t.filter_cycle(1, True)),
    (0, lambda t: t.circulation(True)),
    (150, lambda t: t.spa(temperature=37.5)),
    (190, lambda t: t.spa(temperature=38.0)),
    (234, lambda t: t.spa(temperature=37.5)),
    (272, lambda t: t.spa(temperature=37.0)),
    (620, lambda t: t.spa(temperature=37.5)),
    (1936, lambda t: t.spa(temperature=37.0)),
    (1982, lambda t: t.spa(temperature=37.5)),
    (4797, lambda t: t.filter_cycle(1, False)),
    (4797, lambda t: t.circulation(False)),
]


async def test_20261004_stay_on_test(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    tub.spa(action="off", temperature=37.0, setpoint=37.0)
    await make_controller()
    t0 = dt_util.utcnow()
    await play(hass, freezer, tub, STAY_ON_TEST_1410, until=4830, step=5)
    assert hvac_timeline(tub, t0) == [(0, "heat"), (4797, "off")]
    assert tub.notifications() == []
