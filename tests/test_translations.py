"""The generated UI text."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from custom_components.udespa_control.const import (
    ENTITY_KEYS,
    NUMBER_KEYS,
    PRESET_KEYS,
    TOGGLE_KEYS,
)

_spec = importlib.util.spec_from_file_location(
    "build_translations", Path("scripts/build_translations.py")
)
build_translations = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_translations)

STRINGS = Path("custom_components/udespa_control/strings.json")


def test_generated_files_are_up_to_date():
    assert build_translations.main(check=True) == 0


def test_every_setting_has_text_in_both_languages():
    expected = {*ENTITY_KEYS, *NUMBER_KEYS, *PRESET_KEYS, *TOGGLE_KEYS}
    assert set(build_translations.FIELDS) == expected
    for key, texts in build_translations.FIELDS.items():
        assert all(text.strip() for text in texts), key


def _all_strings(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _all_strings(value)
    elif isinstance(node, str):
        yield node


def test_no_placeholders_hide_in_the_text():
    """A stray brace would be read as a placeholder by the frontend."""
    for text in _all_strings(json.loads(STRINGS.read_text())):
        assert "{" not in text and "}" not in text, text
