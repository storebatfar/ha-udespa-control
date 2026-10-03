# Udespa Control

A Home Assistant integration that runs the Udespa hot tub: the heat pump follows the
spa's own heat demand, with a backup heater, a watchdog, frost protection, status and
mode handling, pipe cleaning and filter/bath-water timers. It works only through
existing entities (Balboa spa, Tuya Local heat pump, a heater switch, a kWh meter)
and never talks to hardware directly.

Built for one tub; nothing is generalised for other setups.

## Install

HACS → Integrations → ⋮ → Custom repositories → `https://github.com/storebatfar/ha-udespa-control`
(category Integration) → download → restart Home Assistant → Settings → Devices & services →
Add integration → Udespa Control.

## Settings

One screen in three sections: **Entities**, **Numbers** (timings, power thresholds, presets;
defaults are measured values) and **On/off** (head start, backup heater, watchdog,
notifications, status Fejl). Change them later under Configure. Reconfigure swaps devices
without losing entity IDs or stored state.

## Watch-only first

**Active control** is off after installation. Every rule still runs, and what it *would*
do appears in **Last action** prefixed `(kun overvågning)`; nothing is sent to the heat
pump, heater or spa, and no alerts go out. Buttons and a manual mode pick still act.
Switch Active control on when the decisions match what you expect.

## The data hub

The Udespa device gathers the tub's data in one place: water temperature, setpoint,
heat demand and circulation; heat-pump inlet, outlet, temperature rise, compressor,
power and ambient (plus diagnostics); heater and circulation power; water quality
from the Ondilo. Each copy follows a source chosen under Configure → Datakilder;
an empty field means no copy.

**Varmepumpe offset** (0 / 0.5 / 1.0 °C) adds a little extra: the heat pump's target
is the spa setpoint plus the offset, capped at the heat pump's maximum.
**Temperatursynk** shows whether the heat pump's target matches (`I sync`), differs
(`Afviger`) or can't be read (`Ukendt`).

## The rules

Every rule is a pure function in `custom_components/udespa_control/rules.py`, documented
there. The heat pump's own reported state is never trusted (Tuya Local writes it
optimistically); only power on the meter confirms on and off.

## Development

    python3.13 -m venv .venv && .venv/bin/pip install -r requirements-test.txt
    .venv/bin/pytest tests -q && .venv/bin/ruff check custom_components tests scripts
    .venv/bin/python scripts/build_translations.py   # after changing UI text
