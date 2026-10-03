"""Status, mode, frost, setpoint and timer rules (pure)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.udespa_control.const import Mode, Status
from custom_components.udespa_control.rules import (
    desired_status,
    frost_action,
    mode_for_preset,
    mode_for_status,
    nudged_setpoint,
    resolve_status,
    restorable_status,
    whole_days_since,
)

PRESETS = {Mode.QUIET: "quick", Mode.SMART: "smart", Mode.TURBO: "quiet"}

# --- B10 ----------------------------------------------------------------------


def test_setpoint_above_rest_by_more_than_threshold_is_in_use():
    assert desired_status(37.5, 37.0, 0.25) is Status.IN_USE


@pytest.mark.parametrize("setpoint", [37.0, 37.25, 36.0])
def test_setpoint_at_or_near_rest_is_maintaining(setpoint):
    assert desired_status(setpoint, 37.0, 0.25) is Status.MAINTAINING


def test_float_noise_does_not_flip_the_threshold():
    assert desired_status(37.3 - 0.05, 37.0, 0.25) is Status.MAINTAINING


def test_missing_setpoint_keeps_the_current_status():
    assert desired_status(None, 37.0, 0.25) is None


# --- B11 / resolve --------------------------------------------------------------


def test_cleaning_is_never_overwritten():
    assert (
        resolve_status(
            Status.CLEANING,
            failure_open=True,
            fault_status_enabled=True,
            from_setpoint=Status.IN_USE,
        )
        is Status.CLEANING
    )


def test_open_failure_means_fault():
    assert (
        resolve_status(
            Status.IN_USE,
            failure_open=True,
            fault_status_enabled=True,
            from_setpoint=Status.IN_USE,
        )
        is Status.FAULT
    )


def test_fault_status_toggle_off_ignores_failure():
    assert (
        resolve_status(
            Status.IN_USE,
            failure_open=True,
            fault_status_enabled=False,
            from_setpoint=Status.MAINTAINING,
        )
        is Status.MAINTAINING
    )


def test_cleared_failure_hands_back_to_the_setpoint():
    assert (
        resolve_status(
            Status.FAULT,
            failure_open=False,
            fault_status_enabled=True,
            from_setpoint=Status.IN_USE,
        )
        is Status.IN_USE
    )


def test_cleared_failure_without_setpoint_falls_back_to_maintaining():
    assert (
        resolve_status(
            Status.FAULT,
            failure_open=False,
            fault_status_enabled=True,
            from_setpoint=None,
        )
        is Status.MAINTAINING
    )


def test_no_setpoint_keeps_a_normal_status():
    assert (
        resolve_status(
            Status.IN_USE,
            failure_open=False,
            fault_status_enabled=True,
            from_setpoint=None,
        )
        is Status.IN_USE
    )


# --- B12 ----------------------------------------------------------------------


def test_modes_follow_status():
    assert mode_for_status(Status.MAINTAINING) is Mode.QUIET
    assert mode_for_status(Status.IN_USE) is Mode.SMART
    assert mode_for_status(Status.FAULT) is None
    assert mode_for_status(Status.CLEANING) is None


def test_preset_maps_back_to_mode():
    assert mode_for_preset("quiet", PRESETS) is Mode.TURBO
    assert mode_for_preset("quick", PRESETS) is Mode.QUIET
    assert mode_for_preset("eco", PRESETS) is None
    assert mode_for_preset(None, PRESETS) is None


# --- B13 ----------------------------------------------------------------------


def test_nudge_moves_half_a_degree():
    assert nudged_setpoint(37.0, 0.5, 26.5, 40.0) == 37.5
    assert nudged_setpoint(37.0, -0.5, 26.5, 40.0) == 36.5


def test_nudge_is_clamped_to_the_spa_limits():
    assert nudged_setpoint(39.8, 0.5, 26.5, 40.0) == 40.0
    assert nudged_setpoint(26.7, -0.5, 26.5, 40.0) == 26.5


def test_nudge_at_the_limit_or_unknown_does_nothing():
    assert nudged_setpoint(40.0, 0.5, 26.5, 40.0) is None
    assert nudged_setpoint(None, 0.5, 26.5, 40.0) is None


# --- C14 ----------------------------------------------------------------------


def test_crossing_below_the_frost_limit_switches_on():
    assert frost_action(5.4, 4.8, 5.0) is True


def test_crossing_above_switches_off():
    assert frost_action(4.8, 5.2, 5.0) is False


@pytest.mark.parametrize("old,new", [(3.0, 2.0), (8.0, 9.0), (4.0, 5.0), (6.0, 5.0)])
def test_no_crossing_no_action(old, new):
    """Only crossings act, as today; landing exactly on the limit is no crossing."""
    assert frost_action(old, new, 5.0) is None


def test_return_from_unavailable_counts_as_a_crossing():
    """Like HA's numeric_state trigger: unavailable -> 3 fires 'below'."""
    assert frost_action(None, 3.0, 5.0) is True
    assert frost_action(None, 9.0, 5.0) is False


def test_unknown_new_value_does_nothing():
    assert frost_action(3.0, None, 5.0) is None


# --- D19 / D16 ------------------------------------------------------------------


def test_whole_days_since_reset():
    reset = datetime(2026, 9, 13, 15, 40, tzinfo=UTC)
    assert whole_days_since(reset, reset + timedelta(days=19, hours=23)) == 19
    assert whole_days_since(reset, reset + timedelta(days=20)) == 20


def test_whole_days_never_negative():
    reset = datetime(2026, 9, 13, tzinfo=UTC)
    assert whole_days_since(reset, reset - timedelta(hours=1)) == 0


@pytest.mark.parametrize(
    "saved,expected",
    [
        ("I brug", Status.IN_USE),
        ("Vedligeholder", Status.MAINTAINING),
        ("Fejl", Status.FAULT),
        ("Rengøring", None),
        ("", None),
        (None, None),
        ("unknown", None),
    ],
)
def test_restorable_status(saved, expected):
    assert restorable_status(saved) is expected
