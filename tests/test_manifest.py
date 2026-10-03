"""Manifest sanity checks."""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.udespa_control.const import DOMAIN

MANIFEST = Path("custom_components/udespa_control/manifest.json")


def test_manifest_domain_matches_const():
    assert json.loads(MANIFEST.read_text())["domain"] == DOMAIN


def test_manifest_declares_config_flow():
    assert json.loads(MANIFEST.read_text())["config_flow"] is True


def test_manifest_version_is_calver():
    year, month, number = json.loads(MANIFEST.read_text())["version"].split(".")
    assert len(year) == 4 and 1 <= int(month) <= 12 and int(number) >= 1


def test_hacs_json_floor_is_the_tested_core():
    hacs = json.loads(Path("hacs.json").read_text())
    assert "filename" not in hacs
    # pytest-homeassistant-custom-component 0.13.316 pins HA 2026.2.3.
    assert hacs["homeassistant"] == "2026.2.0"
