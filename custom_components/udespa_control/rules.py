"""Pure decision rules.

No Home Assistant imports: every rule is a function of plain values, so the
whole rulebook is unit-tested without HA. Reasons are Danish because they end
up in "Seneste handling".
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .const import (
    DEMAND_LABELS,
    OFFSET_VALUES,
    SPA_CALLING,
    SYNC_TOLERANCE,
    BackupKind,
    HeatAction,
    Mode,
    Status,
    SyncStatus,
    Trigger,
)


@dataclass(frozen=True)
class SpaView:
    """What the heat-pump rules need to know about the spa right now."""

    circulation: bool
    hvac_action: str | None
    temperature: float | None
    setpoint: float | None
    status: Status


@dataclass(frozen=True)
class Decision:
    action: HeatAction
    reason: str


def fmt_c(value: float) -> str:
    """37.5 -> '37,5'."""
    return f"{value:.1f}".replace(".", ",")


def fmt_num(value: float) -> str:
    """4.0 -> '4', 2.5 -> '2,5'."""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}".replace(".", ",")


def _head_start_allowed(spa: SpaView, head_start: bool) -> bool:
    return (
        head_start
        and spa.circulation
        and spa.status is Status.IN_USE
        and spa.hvac_action == "off"
    )


def heat_decision(
    trigger: Trigger,
    spa: SpaView,
    *,
    head_start: bool,
    previous_action: str | None = None,
) -> Decision | None:
    """A1-A3 and A8: what the heat pump should do after this trigger.

    None means "no decision", and the caller must then leave any running job
    alone: a trigger that leads nowhere must not cancel a retry loop.
    """
    calling = spa.hvac_action in SPA_CALLING

    if trigger is Trigger.SPA_HEATING:
        # The second "heating" after the 90 s "idle" flow check is the same call.
        if previous_action == "idle" or not spa.circulation:
            return None
        return Decision(HeatAction.ON, "spaen kalder på varme")

    if trigger is Trigger.CIRCULATION_ON:
        if not spa.circulation:
            return None
        if calling:
            return Decision(HeatAction.ON, "cirkulation startet, og spaen kalder på varme")
        if head_start and spa.status is Status.IN_USE:
            return Decision(HeatAction.HEAD_START, "hurtigstart: cirkulation startet i I brug")
        return None

    if trigger is Trigger.CIRCULATION_OFF:
        return Decision(HeatAction.OFF, "cirkulationen er stoppet")

    if trigger is Trigger.SPA_SATISFIED:
        if (
            spa.circulation
            and spa.temperature is not None
            and spa.setpoint is not None
            and spa.temperature >= spa.setpoint
        ):
            return Decision(
                HeatAction.OFF, f"spaen er varm nok ({fmt_c(spa.temperature)} °C)"
            )
        return None

    if trigger is Trigger.IN_USE:
        if _head_start_allowed(spa, head_start):
            return Decision(
                HeatAction.HEAD_START, "hurtigstart: status blev I brug under cirkulation"
            )
        return None

    # Trigger.STARTUP
    if spa.circulation and calling:
        return Decision(HeatAction.ON, "opstart: spaen kalder på varme")
    if _head_start_allowed(spa, head_start):
        return Decision(HeatAction.HEAD_START, "opstart: hurtigstart i I brug")
    return Decision(HeatAction.OFF, "opstart: intet varmekald")


def heat_pump_running(power: float | None, on_w: float) -> bool:
    return power is not None and power > on_w


def heat_pump_stopped(power: float | None, off_w: float) -> bool:
    """Unknown power is not "stopped": the off job keeps verifying."""
    return power is not None and power < off_w


def heater_running(power: float | None, on_w: float) -> bool:
    return power is not None and power > on_w


def backup_needed(
    temperature: float | None, setpoint: float | None, margin: float
) -> bool:
    """A5 gate. Low power alone means "failed" OR "done"; only cold water is failure."""
    return (
        temperature is not None
        and setpoint is not None
        and temperature < setpoint - margin
    )


def watchdog_should_act(
    *,
    failure_open: bool,
    circulation_on_for: timedelta | None,
    min_circulation: timedelta,
    temperature: float | None,
    setpoint: float | None,
    margin: float,
    hp_power: float | None,
    on_w: float,
) -> bool:
    """A6. circulation_on_for is None while circulation is off."""
    return (
        not failure_open
        and circulation_on_for is not None
        and circulation_on_for >= min_circulation
        and backup_needed(temperature, setpoint, margin)
        and hp_power is not None
        and hp_power < on_w
    )


_NO_HEAT_SOURCE_TITLE = "⚠️ Udespa uden varmekilde"
_HP_TITLE = "Udespa Varmepumpe"
_HP_WARNING_TITLE = "⚠️ Udespa Varmepumpe"


def backup_alert(
    kind: BackupKind,
    *,
    heater_running: bool,
    backup_enabled: bool,
    retry_minutes: float,
    circulation_minutes: float,
) -> tuple[str, str]:
    """(title, message) after the backup check. Texts are today's automations'."""
    if not backup_enabled:
        return (
            _HP_WARNING_TITLE,
            ("Varmepumpen kom ikke i drift, og vandet er under setpunkt. "
            "Backup-varmelegemet er slået fra i Udespa Control."),
        )
    if kind is BackupKind.RETRY:
        if heater_running:
            return (
                _HP_TITLE,
                (f"Varmepumpen kom ikke i drift inden for {fmt_num(retry_minutes)} "
                "minutter, og vandet er under setpunkt. Varmelegemet er tændt som "
                "backup og trækker strøm."),
            )
        return (
            _NO_HEAT_SOURCE_TITLE,
            ("Varmepumpen kom ikke i drift, vandet er under setpunkt, og varmelegemet "
            "trækker heller ikke strøm. Spaen har ingen varmekilde — tjek den."),
        )
    if heater_running:
        return (
            _HP_TITLE,
            (f"Varmepumpen trækker ikke strøm efter {fmt_num(circulation_minutes)}+ "
            "minutters cirkulation, og vandet er under setpunkt. Varmelegemet er "
            "tændt som backup og trækker strøm."),
        )
    return (
        _NO_HEAT_SOURCE_TITLE,
        ("Varmepumpen trækker ikke strøm, vandet er under setpunkt, og varmelegemet "
        "trækker heller ikke strøm. Spaen har ingen varmekilde — tjek den."),
    )


def off_failed_alert(*, circulation: bool, retry_minutes: float) -> tuple[str, str]:
    minutes = fmt_num(retry_minutes)
    if circulation:
        return (
            _HP_WARNING_TITLE,
            (f"Spaen er varm nok, men varmepumpen kunne ikke slukkes inden for "
            f"{minutes} minutter og trækker stadig strøm på L3."),
        )
    return (
        _HP_WARNING_TITLE,
        (f"Varmepumpen kunne ikke slukkes inden for {minutes} minutter og trækker "
        "stadig strøm på L3. Cirkulationspumpen er stoppet, så varmepumpen kører "
        "uden vandcirkulation."),
    )


HEAD_START_OFF_FAILED_ALERT: tuple[str, str] = (
    _HP_WARNING_TITLE,
    ("Hurtigstart: spaen kaldte ikke på varme, men varmepumpen kunne ikke slukkes "
    "igen og trækker strøm på L3."),
)
FOLLOWS_SETPOINT: frozenset[Status] = frozenset({Status.IN_USE, Status.MAINTAINING})


def desired_status(
    setpoint: float | None, rest: float | None, threshold: float
) -> Status | None:
    """B10: I brug when setpoint - rest > threshold. None keeps the current status."""
    if setpoint is None or rest is None:
        return None
    # Rounded so 37.3 - 37.0 = 0.2999... cannot fall the wrong side of 0.25.
    if round(setpoint - rest, 3) > threshold:
        return Status.IN_USE
    return Status.MAINTAINING


def resolve_status(
    current: Status,
    *,
    failure_open: bool,
    fault_status_enabled: bool,
    from_setpoint: Status | None,
) -> Status:
    """The status right now, without the B10 delay (B11 and restores)."""
    if current is Status.CLEANING:
        return current
    if failure_open and fault_status_enabled:
        return Status.FAULT
    if from_setpoint is not None:
        return from_setpoint
    if current is Status.FAULT:
        # Failure gone and no setpoint to read: never leave "Fejl" stuck.
        return Status.MAINTAINING
    return current


_MODE_FOR_STATUS: dict[Status, Mode] = {
    Status.MAINTAINING: Mode.QUIET,
    Status.IN_USE: Mode.SMART,
}


def mode_for_status(status: Status) -> Mode | None:
    """B12: Fejl and Rengøring leave the mode alone."""
    return _MODE_FOR_STATUS.get(status)


def mode_for_preset(preset: str | None, presets: Mapping[Mode, str]) -> Mode | None:
    for mode, value in presets.items():
        if value == preset:
            return mode
    return None


def nudged_setpoint(
    setpoint: float | None, delta: float, min_temp: float, max_temp: float
) -> float | None:
    """B13. None when there is nothing to send."""
    if setpoint is None:
        return None
    target = min(max(setpoint + delta, min_temp), max_temp)
    if target == setpoint:
        return None
    return target


def frost_action(old: float | None, new: float | None, limit: float) -> bool | None:
    """C14, at crossings only. An unknown old value counts as not matching."""
    if new is None:
        return None
    if new < limit and not (old is not None and old < limit):
        return True
    if new > limit and not (old is not None and old > limit):
        return False
    return None


def whole_days_since(reset_at: datetime, now: datetime) -> int:
    return max(0, (now - reset_at) // timedelta(days=1))


def restorable_status(saved: str | None) -> Status | None:
    """A saved status worth restoring after cleaning: valid and not Rengøring."""
    try:
        status = Status(saved)
    except ValueError:
        return None
    return None if status is Status.CLEANING else status


def snap_offset(value: Any) -> float:
    """The nearest allowed offset (0, 0.5, 1.0); anything unusable is 0."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    clamped = min(max(float(value), OFFSET_VALUES[0]), OFFSET_VALUES[-1])
    return round(clamped * 2) / 2


def heat_pump_target(
    setpoint: float | None, offset: float, min_temp: float, max_temp: float
) -> tuple[float, bool] | None:
    """A9′: (target, capped). None without a spa setpoint."""
    if setpoint is None:
        return None
    wanted = round(setpoint + offset, 1)
    target = min(max(wanted, min_temp), max_temp)
    return target, target != wanted


def sync_status(expected: float | None, actual: float | None) -> SyncStatus:
    if expected is None or actual is None:
        return SyncStatus.UNKNOWN
    if abs(expected - actual) <= SYNC_TOLERANCE:
        return SyncStatus.IN_SYNC
    return SyncStatus.DIFFERS


def temperature_rise(inlet: float | None, outlet: float | None) -> float | None:
    """How much the heat pump warms the water passing through it."""
    if inlet is None or outlet is None:
        return None
    return round(outlet - inlet, 1)


def round_power(value: float | None) -> int | None:
    """Whole watts, halves rounded up (Python's round() goes to even)."""
    return None if value is None else math.floor(value + 0.5)


def demand_label(action: Any) -> str | None:
    return DEMAND_LABELS.get(action) if isinstance(action, str) else None
