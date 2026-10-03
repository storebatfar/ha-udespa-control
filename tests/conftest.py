"""Shared fixtures."""

from __future__ import annotations

import pytest

from .common import FakeTub

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
