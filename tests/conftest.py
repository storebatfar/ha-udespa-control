"""Shared fixtures."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.udespa_control.const import DEFAULTS, DOMAIN
from custom_components.udespa_control.controller import UdespaController

from .common import ENTITY_DATA, SPA, FakeTub, settle

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in every test."""
    return


@pytest.fixture
async def tub(hass):
    """The fake tub, installed with a calm default state."""
    fake = FakeTub(hass)
    fake.install()
    yield fake
    fake.shutdown()


@pytest.fixture
async def make_controller(hass, tub):
    """Build controllers on the fake tub; shut them all down afterwards.

    active=True switches Aktiv styring on (it defaults off) and then forgets
    the commands that start-up sent, so each test sees only its own.
    """
    made: list[UdespaController] = []

    async def _make(
        *, active: bool = True, entry: MockConfigEntry | None = None, **options
    ) -> UdespaController:
        """Pass entry= to "restart" on the same storage; options then don't apply."""
        if entry is None:
            entry = MockConfigEntry(
                domain=DOMAIN,
                title="Udespa",
                unique_id=SPA,
                data=ENTITY_DATA,
                options={**DEFAULTS, **options},
            )
            entry.add_to_hass(hass)
        controller = UdespaController(hass, entry)
        await controller.async_setup()
        made.append(controller)
        await settle(hass)
        if active:
            await controller.async_set_active(True)
            await settle(hass)
        tub.calls.clear()
        return controller

    yield _make
    for controller in made:
        await controller.async_shutdown()
