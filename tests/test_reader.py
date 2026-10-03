"""Typed reads of the configured entities."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.udespa_control.reader import TubReader, as_float
from custom_components.udespa_control.settings import Settings

from .common import ENTITY_DATA, OUTDOOR, FakeTub


def _reader(hass, **data) -> TubReader:
    return TubReader(hass, Settings.from_mappings({**ENTITY_DATA, **data}, {}))


@pytest.mark.parametrize(
    "value,expected",
    [("12.5", 12.5), (7, 7.0), (None, None), ("unavailable", None), ("unknown", None), ("abc", None)],
)
def test_as_float(value, expected):
    assert as_float(value) == expected


async def test_spa_reads(hass: HomeAssistant, tub: FakeTub):
    tub.spa(action="heating", temperature=36.5, setpoint=38.0)
    reader = _reader(hass)
    assert reader.hvac_action() == "heating"
    assert reader.spa_temperature() == 36.5
    assert reader.setpoint() == 38.0
    assert reader.spa_limits() == (26.5, 40.0)
    assert reader.spa_available()


async def test_unavailable_spa(hass: HomeAssistant, tub: FakeTub):
    tub.spa(state="unavailable")
    assert not _reader(hass).spa_available()


async def test_power_unavailable_reads_none(hass: HomeAssistant, tub: FakeTub):
    tub.hp_power("unavailable")
    assert _reader(hass).hp_power() is None


async def test_outdoor_from_attribute_or_state(hass: HomeAssistant, tub: FakeTub):
    tub.outdoor(3.5)
    assert _reader(hass).outdoor_temperature() == 3.5
    hass.states.async_set("sensor.ude", "4.5")
    reader = _reader(hass, outdoor="sensor.ude", outdoor_attribute="")
    assert reader.outdoor_temperature() == 4.5
    assert reader.outdoor_value(hass.states.get(OUTDOOR)) is None


async def test_circulation_on_for(hass: HomeAssistant, tub: FakeTub):
    reader = _reader(hass)
    assert reader.circulation_on_for(dt_util.utcnow()) is None
    tub.circulation(True)
    later = dt_util.utcnow() + timedelta(minutes=11)
    assert reader.circulation_on_for(later) >= timedelta(minutes=11)


async def test_filter_cycle(hass: HomeAssistant, tub: FakeTub):
    reader = _reader(hass)
    assert reader.filter_cycle() is None
    tub.filter_cycle(2, True)
    assert reader.filter_cycle() == 2
