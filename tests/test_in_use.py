"""I brug reminder: ask after a while, lower to rest if nobody answers."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant

from custom_components.udespa_control.const import (
    IN_USE_CONFIRM_ACTION,
    OPT_IN_USE_REMINDER,
    Status,
)

from .common import SPA, FakeTub, advance, settle

HOUR = 3600


def _spa_setpoints(tub: FakeTub) -> list[float]:
    return [
        c.data["temperature"]
        for c in tub.sent("climate", "set_temperature")
        if c.data["entity_id"] == SPA
    ]


def _questions(tub: FakeTub) -> list:
    return [c for c in tub.notifications() if c.data.get("data", {}).get("actions")]


async def _start_in_use(hass, freezer, tub) -> None:
    tub.spa(setpoint=40.0)
    await advance(hass, freezer, 5)


async def test_asks_after_three_hours_and_lowers_without_an_answer(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    await _start_in_use(hass, freezer, tub)
    assert controller.status is Status.IN_USE
    await advance(hass, freezer, 3 * HOUR - 60, step=300)
    assert _questions(tub) == []
    await advance(hass, freezer, 60, step=30)
    question = _questions(tub)[0]
    assert question.data["data"]["actions"][0]["action"] == IN_USE_CONFIRM_ACTION
    assert "3 timer" in question.data["message"]
    await advance(hass, freezer, 30 * 60 - 60, step=60)
    assert _spa_setpoints(tub) == []
    await advance(hass, freezer, 60, step=30)
    assert _spa_setpoints(tub) == [37.0]  # the rest temperature (default 37)
    assert "Ingen svar" in tub.notifications()[-1].data["message"]
    await advance(hass, freezer, 10)
    assert controller.status is Status.MAINTAINING


async def test_confirming_on_the_phone_asks_again_an_hour_later(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller()
    await _start_in_use(hass, freezer, tub)
    await advance(hass, freezer, 3 * HOUR, step=300)
    assert len(_questions(tub)) == 1
    await advance(hass, freezer, 10 * 60, step=60)
    hass.bus.async_fire("mobile_app_notification_action", {"action": IN_USE_CONFIRM_ACTION})
    await settle(hass)
    await advance(hass, freezer, HOUR - 60, step=300)
    assert len(_questions(tub)) == 1
    assert _spa_setpoints(tub) == []
    await advance(hass, freezer, 60, step=30)
    assert len(_questions(tub)) == 2
    assert "4 timer" in _questions(tub)[-1].data["message"]


async def test_the_dashboard_button_confirms_too(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    await _start_in_use(hass, freezer, tub)
    await advance(hass, freezer, 3 * HOUR + 60, step=300)
    await controller.async_confirm_in_use()
    await advance(hass, freezer, 50 * 60, step=300)
    assert _spa_setpoints(tub) == []


async def test_a_confirmation_before_the_question_never_shortens_the_wait(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    await _start_in_use(hass, freezer, tub)
    await advance(hass, freezer, 30 * 60, step=300)
    await controller.async_confirm_in_use()
    await advance(hass, freezer, 2 * HOUR, step=300)
    assert _questions(tub) == []  # still 3 h from the start, not 1 h from the press


async def test_leaving_i_brug_cancels_the_reminder(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller()
    await _start_in_use(hass, freezer, tub)
    await advance(hass, freezer, HOUR, step=300)
    tub.spa(setpoint=37.0)
    await advance(hass, freezer, 10)
    assert controller.status is Status.MAINTAINING
    await advance(hass, freezer, 4 * HOUR, step=300)
    assert _questions(tub) == []
    assert _spa_setpoints(tub) == []


async def test_lowering_after_the_answer_window_ends_also_ends_the_question(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    """Leaving I brug while a question is open: no lowering afterwards."""
    await make_controller()
    await _start_in_use(hass, freezer, tub)
    await advance(hass, freezer, 3 * HOUR + 60, step=300)
    tub.spa(setpoint=37.0)
    await advance(hass, freezer, HOUR, step=300)
    assert _spa_setpoints(tub) == []


async def test_the_reminder_survives_a_restart(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    first = await make_controller()
    await _start_in_use(hass, freezer, tub)
    await advance(hass, freezer, 2 * HOUR, step=300)
    await first.async_shutdown()
    second = await make_controller(entry=first.entry)
    await advance(hass, freezer, HOUR - 60, step=300)
    assert _questions(tub) == []
    await advance(hass, freezer, 60, step=30)
    assert len(_questions(tub)) == 1
    assert second.status is Status.IN_USE


async def test_the_answer_window_survives_a_restart(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    first = await make_controller()
    await _start_in_use(hass, freezer, tub)
    await advance(hass, freezer, 3 * HOUR + 10 * 60, step=300)
    assert len(_questions(tub)) == 1
    await first.async_shutdown()
    await make_controller(entry=first.entry)
    await advance(hass, freezer, 19 * 60, step=60)
    assert _spa_setpoints(tub) == []
    await advance(hass, freezer, 2 * 60, step=30)
    assert _spa_setpoints(tub) == [37.0]


async def test_zero_hours_turns_the_reminder_off(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    await make_controller(**{OPT_IN_USE_REMINDER: 0})
    await _start_in_use(hass, freezer, tub)
    await advance(hass, freezer, 6 * HOUR, step=600)
    assert _questions(tub) == []
    assert _spa_setpoints(tub) == []


async def test_watch_only_logs_the_reminder_and_the_lowering(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, tub: FakeTub, make_controller
):
    controller = await make_controller(active=False)
    await _start_in_use(hass, freezer, tub)
    await advance(hass, freezer, 3 * HOUR + 31 * 60, step=300)
    assert tub.notifications() == []
    assert _spa_setpoints(tub) == []
    assert any("I brug-påmindelse" in line for line in controller.recent)
    assert any("(kun overvågning) Spa setpunkt 37,0 °C" in line for line in controller.recent)
