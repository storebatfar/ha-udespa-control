"""The controller: listens, asks the rules, hands decisions on.

Thin by design. Decisions live in rules.py, the heat-pump job in
heat_pump.py, commands in actuators.py, cleaning in cleaning.py.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from .actuators import Actuators
from .cleaning import Cleaning
from .const import (
    DOMAIN,
    FILTER_START_DELAY_S,
    LAST_ACTION_MAX,
    STATUS_DELAY_S,
    CleaningPhase,
    HeatAction,
    Mode,
    Status,
    SyncStatus,
    Timer,
    Trigger,
)
from .heat_pump import HeatPump
from .mode import ModeKeeper
from .reader import TubReader, as_float
from .rules import (
    FOLLOWS_SETPOINT,
    OVERTEMP_ALERT,
    Decision,
    SpaView,
    desired_status,
    fmt_c,
    fmt_num,
    frost_action,
    heat_decision,
    heat_pump_running,
    heat_pump_target,
    mode_for_preset,
    mode_for_status,
    nudged_setpoint,
    overtemp,
    resolve_status,
    snap_offset,
    watchdog_should_act,
    whole_days_since,
)
from .rules import sync_status as rule_sync_status
from .settings import Settings
from .storage import StoredState, UdespaStore

_LOGGER = logging.getLogger(__name__)


class UdespaController:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.settings = Settings.from_mappings(entry.data, entry.options)
        self.reader = TubReader(hass, self.settings)
        self.state = StoredState()
        self.last_action: str | None = None
        self.last_action_at: datetime | None = None
        self.last_sync_at: datetime | None = None
        # The last 50 records, in memory: handy when comparing watch-only output.
        self.recent: deque[str] = deque(maxlen=50)
        self.actuators = Actuators(
            hass, self.settings, self.record, lambda: self.state.active
        )
        self.mode_keeper = ModeKeeper(
            hass, self.settings, self.reader, self.actuators, self.record
        )
        self.heat_pump = HeatPump(
            hass,
            self.settings,
            self.reader,
            self.actuators,
            record=self.record,
            failure_open=lambda: self.state.failure_open,
            set_failure=self.set_failure,
            on_switched_on=lambda: self.mode_keeper.reassert("efter tænd"),
        )
        self._store = UdespaStore(hass, entry.entry_id)
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._tasks: set[asyncio.Task[Any]] = set()
        self._cancel_satisfied: CALLBACK_TYPE | None = None
        self._cancel_filter: CALLBACK_TYPE | None = None
        self._cancel_overtemp: CALLBACK_TYPE | None = None
        self._cancel_status: CALLBACK_TYPE | None = None
        self._pending_status: Status | None = None
        self._timer_days: tuple[int | None, int | None] = (None, None)
        self._shut_down = False
        self.cleaning = Cleaning(self)

    # --- lifecycle ----------------------------------------------------------

    async def async_setup(self) -> None:
        self.state = await self._store.async_load()
        s = self.settings
        watched = [
            s.spa,
            s.circulation,
            s.heat_pump,
            s.heat_pump_power,
            s.outdoor,
            *(e for e in (s.filter_cycle_1, s.filter_cycle_2) if e),
        ]
        self._unsubs.append(
            async_track_state_change_event(self.hass, watched, self._handle_change)
        )
        # A fixed interval, not a `for:` duration: restarts and unavailable
        # blips cannot swallow it.
        self._unsubs.append(
            async_track_time_interval(
                self.hass,
                self._watchdog_tick,
                timedelta(minutes=s.watchdog_interval_min),
            )
        )
        self._unsubs.append(
            async_track_time_interval(self.hass, self._timer_tick, timedelta(minutes=1))
        )
        self._timer_days = self._current_timer_days()
        self._unsubs.append(async_at_started(self.hass, self._async_started))

    async def _async_started(self, _hass: HomeAssistant) -> None:
        """D18 then A8, once HA is running (or at once, on a reload)."""
        self.cleaning.recover_after_restart()
        self._resolve_status_now("opstart")
        self._decide(Trigger.STARTUP)
        if self._sync_needed():
            self._spawn(self._async_sync_target("opstart"), "temperature sync")
        self._evaluate_overtemp()

    async def async_shutdown(self) -> None:
        if self._shut_down:
            return
        self._shut_down = True
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self._cancel_satisfied_timer()
        self._cancel_status_timer()
        for cancel in (self._cancel_filter, self._cancel_overtemp):
            if cancel is not None:
                cancel()
        self._cancel_filter = self._cancel_overtemp = None
        await self.cleaning.async_shutdown()
        await self.heat_pump.async_shutdown()
        await self.mode_keeper.async_shutdown()
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._store.async_save(self.state)

    # --- plumbing -----------------------------------------------------------

    def add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(update)

        def remove() -> None:
            if update in self._listeners:
                self._listeners.remove(update)

        return remove

    def _notify_listeners(self) -> None:
        for update in list(self._listeners):
            update()

    def _save(self) -> None:
        self._store.save_soon(self.state)

    def _spawn(self, coro: Coroutine[Any, Any, Any], name: str) -> None:
        task = self.hass.async_create_background_task(coro, f"{DOMAIN} {name}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @callback
    def record(self, text: str) -> None:
        """Write "Seneste handling"; the logbook keeps the history."""
        _LOGGER.info("%s", text)
        self.last_action = text[:LAST_ACTION_MAX]
        self.last_action_at = dt_util.utcnow()
        self.recent.append(text)
        self._notify_listeners()

    # --- entity-facing state ------------------------------------------------

    @property
    def status(self) -> Status:
        return self.state.status

    @property
    def mode(self) -> Mode | None:
        return mode_for_preset(self.reader.hp_preset(), self.settings.presets)

    @property
    def heating(self) -> bool:
        return self.reader.hvac_action() == "heating"

    @property
    def failure_open(self) -> bool:
        return self.state.failure_open

    def timer_reset_at(self, timer: Timer) -> datetime | None:
        if timer is Timer.FILTER:
            return self.state.filter_reset_at
        return self.state.bath_water_reset_at

    def timer_days(self, timer: Timer) -> int | None:
        reset_at = self.timer_reset_at(timer)
        if reset_at is None:
            return None
        return whole_days_since(reset_at, dt_util.utcnow())

    # --- entity-facing actions ----------------------------------------------

    async def async_set_active(self, active: bool) -> None:
        self.state.active = active
        self._save()
        if active:
            self.record("Aktiv styring slået til")
            # Take over the current situation now, not at the next trigger.
            self._decide(Trigger.STARTUP)
            if self._sync_needed():
                self._spawn(
                    self._async_sync_target("aktiv styring slået til"), "temperature sync"
                )
        else:
            self.record("Aktiv styring slået fra: kun overvågning")

    async def async_set_frost_protection(self, on: bool) -> None:
        self.state.frost_protection = on
        self._save()
        self.record("Frostsikring slået til" if on else "Frostsikring slået fra")

    async def async_set_rest_temperature(self, value: float) -> None:
        self.state.rest_temperature = value
        self._save()
        self._notify_listeners()
        self._evaluate_status_soon()

    async def async_select_mode(self, mode: Mode) -> None:
        """A manual pick is deliberate: it acts, and is verified, even in watch-only."""
        self.mode_keeper.apply(mode, "valgt manuelt", deliberate=True)

    async def async_nudge_setpoint(self, delta: float) -> None:
        """B13."""
        if not self.reader.spa_available():
            self.record("Hæv/sænk ignoreret: spaen er ikke tilgængelig")
            return
        setpoint = self.reader.setpoint()
        if setpoint is None:
            self.record("Hæv/sænk ignoreret: spaens setpunkt er ukendt")
            return
        low, high = self.reader.spa_limits()
        target = nudged_setpoint(setpoint, delta, low, high)
        if target is None:
            self.record(f"Hæv/sænk ignoreret: {fmt_c(setpoint)} °C er grænsen")
            return
        await self.actuators.spa_setpoint(target, "hævet" if delta > 0 else "sænket")

    async def async_reset_timer(self, timer: Timer) -> None:
        now = dt_util.utcnow()
        if timer is Timer.FILTER:
            self.state.filter_reset_at = now
        else:
            self.state.bath_water_reset_at = now
        self._save()
        self._timer_days = self._current_timer_days()
        self.record(
            "Filter timer nulstillet"
            if timer is Timer.FILTER
            else "Badevand timer nulstillet"
        )

    async def async_start_cleaning(self) -> None:
        await self.cleaning.async_start()

    async def async_stop_cleaning(self) -> None:
        await self.cleaning.async_stop()

    def set_cleaning_phase(self, phase: CleaningPhase) -> None:
        self.state.cleaning_phase = phase
        self.state.cleaning_started_at = (
            dt_util.utcnow() if phase is not CleaningPhase.IDLE else None
        )
        self._save()
        self._notify_listeners()

    def restore_status(self, saved: Status | None, reason: str) -> None:
        """After cleaning: the saved status, re-checked against failure and setpoint."""
        base = saved if saved is not None else Status.MAINTAINING
        self.set_status(
            resolve_status(
                base,
                failure_open=self.state.failure_open,
                fault_status_enabled=self.settings.fault_status,
                from_setpoint=self._desired_status(),
            ),
            reason,
        )

    # --- temperature sync (A9′) ---------------------------------------------

    def expected_target(self) -> tuple[float, bool] | None:
        low, high = self.reader.hp_limits()
        return heat_pump_target(self.reader.setpoint(), self.state.offset, low, high)

    def sync_status(self) -> SyncStatus:
        expected = self.expected_target()
        return rule_sync_status(
            expected[0] if expected is not None else None, self.reader.hp_target()
        )

    def sync_attributes(self) -> dict[str, Any]:
        expected = self.expected_target()
        return {
            "spa_setpoint": self.reader.setpoint(),
            "offset": self.state.offset,
            "expected_target": expected[0] if expected is not None else None,
            "heat_pump_target": self.reader.hp_target(),
            "capped": expected[1] if expected is not None else False,
            "last_sync": self.last_sync_at.isoformat() if self.last_sync_at else None,
        }

    def _sync_needed(self) -> bool:
        """Only a known difference syncs; an unavailable heat pump never does."""
        return self.sync_status() is SyncStatus.DIFFERS

    async def _async_sync_target(self, reason: str) -> None:
        expected = self.expected_target()
        if expected is None:
            return
        self.last_sync_at = dt_util.utcnow()
        await self.actuators.heat_pump_temperature(expected[0], reason)
        self._notify_listeners()

    async def async_set_offset(self, value: float) -> None:
        """The user's handle for a little extra; stored even in watch-only."""
        self.state.offset = snap_offset(value)
        self._save()
        self.record(f"Varmepumpe offset {fmt_c(self.state.offset)} °C")
        if self._sync_needed():
            await self._async_sync_target("offset ændret")

    # --- status (B10-B12) ---------------------------------------------------

    def _desired_status(self) -> Status | None:
        return desired_status(
            self.reader.setpoint(),
            self.state.rest_temperature,
            self.settings.in_use_threshold,
        )

    def set_status(self, new: Status, reason: str) -> None:
        if new is self.state.status:
            return
        self._cancel_status_timer()
        self.state.status = new
        self._save()
        self.record(f"Status {new}: {reason}")
        if (mode := mode_for_status(new, self.settings.modes)) is not None:
            self.mode_keeper.apply(mode, f"status er {new}")
        if new is Status.IN_USE:
            self._decide(Trigger.IN_USE)

    def _resolve_status_now(self, reason: str) -> None:
        self.set_status(
            resolve_status(
                self.state.status,
                failure_open=self.state.failure_open,
                fault_status_enabled=self.settings.fault_status,
                from_setpoint=self._desired_status(),
            ),
            reason,
        )

    @callback
    def _evaluate_status_soon(self) -> None:
        """B10 with its delay, counted from the first crossing."""
        desired = self._desired_status()
        if (
            desired is None
            or self.state.status not in FOLLOWS_SETPOINT
            or desired is self.state.status
        ):
            self._cancel_status_timer()
            return
        if desired is self._pending_status:
            return
        self._cancel_status_timer()
        self._pending_status = desired
        self._cancel_status = async_call_later(
            self.hass, STATUS_DELAY_S, self._status_timer_fired
        )

    @callback
    def _status_timer_fired(self, _now: Any) -> None:
        pending = self._pending_status
        self._cancel_status = None
        self._pending_status = None
        if (
            pending is not None
            and pending is self._desired_status()
            and self.state.status in FOLLOWS_SETPOINT
        ):
            setpoint = self.reader.setpoint()
            self.set_status(
                pending,
                f"setpunkt {fmt_c(setpoint)} °C, hvile "
                f"{fmt_c(self.state.rest_temperature)} °C",
            )

    def _cancel_status_timer(self) -> None:
        if self._cancel_status is not None:
            self._cancel_status()
            self._cancel_status = None
        self._pending_status = None

    # --- failure (A5-A7, B11) -----------------------------------------------

    def set_failure(self, failure_open: bool) -> None:
        if self.state.failure_open is failure_open:
            return
        self.state.failure_open = failure_open
        self._save()
        self._resolve_status_now(
            "varmepumpefejl" if failure_open else "varmepumpefejl ryddet"
        )
        self._notify_listeners()

    # --- events -------------------------------------------------------------

    @callback
    def _handle_change(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        old = event.data["old_state"]
        new = event.data["new_state"]
        s = self.settings
        if entity_id == s.spa:
            self._on_spa(old, new)
        elif entity_id == s.circulation:
            self._on_circulation(old, new)
        elif entity_id == s.heat_pump_power:
            self._on_heat_pump_power(new)
        elif entity_id == s.heat_pump:
            self.mode_keeper.adopt(self.reader.hp_preset())
        elif entity_id in (s.filter_cycle_1, s.filter_cycle_2):
            self._on_filter_cycle(old, new)
        elif entity_id == s.outdoor:
            self._on_outdoor(old, new)
        self._evaluate_overtemp()
        self._notify_listeners()

    def _on_spa(self, old: State | None, new: State | None) -> None:
        old_action = TubReader.attr(old, "hvac_action")
        new_action = TubReader.attr(new, "hvac_action")
        if new_action != old_action:
            self._cancel_satisfied_timer()
            if new_action == "off":
                self._cancel_satisfied = async_call_later(
                    self.hass, self.settings.off_delay_s, self._satisfied_timer_fired
                )
            elif new_action == "heating":
                self._decide(Trigger.SPA_HEATING, previous_action=old_action)

        old_setpoint = TubReader.attr_float(old, "temperature")
        new_setpoint = TubReader.attr_float(new, "temperature")
        if new_setpoint is not None and new_setpoint != old_setpoint:
            if self._sync_needed():
                self._spawn(
                    self._async_sync_target("følger spaens setpunkt"),
                    "temperature sync",
                )
            self._evaluate_status_soon()
        elif new_setpoint is None and old_setpoint is not None:
            self._evaluate_status_soon()

    @callback
    def _satisfied_timer_fired(self, _now: Any) -> None:
        self._cancel_satisfied = None
        if self.reader.hvac_action() == "off":
            self._decide(Trigger.SPA_SATISFIED)

    def _cancel_satisfied_timer(self) -> None:
        if self._cancel_satisfied is not None:
            self._cancel_satisfied()
            self._cancel_satisfied = None

    def _on_circulation(self, old: State | None, new: State | None) -> None:
        old_value = old.state if old is not None else None
        new_value = new.state if new is not None else None
        if new_value == old_value:
            return
        if new_value == STATE_ON:
            self._decide(Trigger.CIRCULATION_ON)
        elif new_value == STATE_OFF:
            self._decide(Trigger.CIRCULATION_OFF)

    def _on_heat_pump_power(self, new: State | None) -> None:
        """A7 outside a job: the pump came back by itself."""
        power = as_float(new.state) if new is not None else None
        if self.state.failure_open and heat_pump_running(power, self.settings.hp_on_w):
            self._spawn(self.heat_pump.async_recover(), "recover")

    def _on_outdoor(self, old: State | None, new: State | None) -> None:
        """C14/C15."""
        if not self.state.frost_protection:
            return
        if old is None:
            # The entity was just created (HA or the integration starting):
            # its first reading is no crossing. unavailable → value still is.
            return
        limit = self.settings.frost_limit
        temperature = self.reader.outdoor_value(new)
        action = frost_action(self.reader.outdoor_value(old), temperature, limit)
        if action is None or temperature is None:
            return
        outside = f"{fmt_c(temperature)} °C ude"
        if action:
            self._spawn(
                self.actuators.heater(
                    True, f"frostsikring: {outside}, under {fmt_num(limit)} °C"
                ),
                "frost",
            )
        elif self.state.failure_open or self.heat_pump.backup_running:
            self.record(
                f"Frostsikring: {outside}, men varmelegemet bliver tændt som backup "
                "for varmepumpen"
            )
        else:
            self._spawn(
                self.actuators.heater(
                    False, f"frostsikring: {outside}, over {fmt_num(limit)} °C"
                ),
                "frost",
            )

    # --- filter cycles (rule F) ---------------------------------------------

    def _on_filter_cycle(self, old: State | None, new: State | None) -> None:
        """F1: a filter cycle that holds for FILTER_START_DELAY_S switches on.

        Only the cycle ending cancels a pending start: an attribute update or
        a blip on the other sensor must not lose it.
        """
        if self.reader.filter_cycle() is None:
            if self._cancel_filter is not None:
                self._cancel_filter()
                self._cancel_filter = None
            return
        was_on = old is not None and old.state == STATE_ON
        if new is not None and new.state == STATE_ON and not was_on:
            if self._cancel_filter is not None:
                self._cancel_filter()
            self._cancel_filter = async_call_later(
                self.hass, FILTER_START_DELAY_S, self._filter_start_fired
            )

    @callback
    def _filter_start_fired(self, _now: Any) -> None:
        self._cancel_filter = None
        if self.reader.filter_cycle() is None:
            return
        if self.heat_pump.last_action is HeatAction.ON:
            return  # already on: circulation started inside the cycle, or a heat call
        self._decide(Trigger.FILTER_START)

    def _overtemp_reading(self) -> bool | None:
        """F5's condition: True over, False known not over, None unknown.

        Over means the compressor is actually running (L3 power) with the spa
        at least the margin over its setpoint. A warm tub after a bath, with
        the heat pump in heat but resting, is not the heat pump overheating it.
        """
        s = self.settings
        if not s.filter_stay_on:
            return False
        if self.reader.filter_cycle() is None:
            sensors = [self.hass.states.get(e) for e in (s.filter_cycle_1, s.filter_cycle_2) if e]
            if all(state is not None and state.state == STATE_OFF for state in sensors):
                return False
            return None
        mode = self.reader.hp_hvac_mode()
        if mode is None:
            return None
        if mode != "heat":
            return False
        power = self.reader.hp_power()
        temperature = self.reader.spa_temperature()
        setpoint = self.reader.setpoint()
        if power is None or temperature is None or setpoint is None:
            return None
        return heat_pump_running(power, s.hp_on_w) and overtemp(
            temperature, setpoint, s.overtemp_margin
        )

    @callback
    def _evaluate_overtemp(self) -> None:
        """F5: start, resume or cancel the safety-stop timer.

        The start time lives in storage, so a restart resumes the remaining
        time instead of starting the 5 minutes over.
        """
        reading = self._overtemp_reading()
        if reading is not True:
            if self._cancel_overtemp is not None:
                self._cancel_overtemp()
                self._cancel_overtemp = None
            # Unknown (a blip, tuya_local reconnecting after a restart) pauses
            # the hold; only a known "not over" ends it.
            if reading is False and self.state.overtemp_since is not None:
                self.state.overtemp_since = self.state.overtemp_seen = None
                self._save()
            return
        now = dt_util.utcnow()
        hold_s = self.settings.overtemp_minutes * 60
        seen = self.state.overtemp_seen
        if (
            self.state.overtemp_since is None
            or seen is None
            or (now - seen).total_seconds() > hold_s
        ):
            self.state.overtemp_since = now  # new hold, or unconfirmed for too long
        self.state.overtemp_seen = now
        self._save()
        if self._cancel_overtemp is None:
            held = (now - self.state.overtemp_since).total_seconds()
            remaining = max(0.0, hold_s - held)
            self._cancel_overtemp = async_call_later(
                self.hass, remaining, self._overtemp_fired
            )

    @callback
    def _overtemp_fired(self, _now: Any) -> None:
        self._cancel_overtemp = None
        if self._overtemp_reading() is not True:
            self._evaluate_overtemp()
            return
        s = self.settings
        temperature = self.reader.spa_temperature()
        self.state.overtemp_since = self.state.overtemp_seen = None
        self._save()
        self._spawn(self.actuators.notify(*OVERTEMP_ALERT), "overtemp alert")
        self.heat_pump.start(
            Decision(
                HeatAction.OFF,
                f"sikkerhedsstop: spaen {fmt_c(temperature)} °C, mindst "
                f"{fmt_num(s.overtemp_margin)} grad over setpunkt i "
                f"{fmt_num(s.overtemp_minutes)} min under filtercyklus",
            )
        )

    # --- decisions ----------------------------------------------------------

    def _view(self) -> SpaView:
        return SpaView(
            circulation=self.reader.circulation_on(),
            hvac_action=self.reader.hvac_action(),
            temperature=self.reader.spa_temperature(),
            setpoint=self.reader.setpoint(),
            status=self.state.status,
            filter_cycle=self.reader.filter_cycle() is not None,
        )

    def _decide(self, trigger: Trigger, previous_action: str | None = None) -> None:
        decision = heat_decision(
            trigger,
            self._view(),
            head_start=self.settings.head_start,
            previous_action=previous_action,
            filter_stay_on=self.settings.filter_stay_on,
        )
        if decision is None:
            return  # no decision never cancels a running job
        if trigger is Trigger.CIRCULATION_ON and (
            cycle := self.reader.filter_cycle()
        ) is not None:
            decision = replace(decision, reason=f"{decision.reason} (filtercyklus {cycle})")
        self.heat_pump.start(decision)

    # --- timers -------------------------------------------------------------

    @callback
    def _watchdog_tick(self, now: datetime) -> None:
        """A6."""
        s = self.settings
        # A running on/head-start job owns verification and has its own A5;
        # ticking now would catch a healthy compressor mid-start.
        if not s.watchdog or self.heat_pump.busy:
            return
        if watchdog_should_act(
            failure_open=self.state.failure_open,
            circulation_on_for=self.reader.circulation_on_for(now),
            min_circulation=timedelta(minutes=s.watchdog_circulation_min),
            temperature=self.reader.spa_temperature(),
            setpoint=self.reader.setpoint(),
            margin=s.backup_margin,
            hp_power=self.reader.hp_power(),
            on_w=s.hp_on_w,
        ):
            self.heat_pump.start_watchdog_backup(
                f"varmepumpen trækker ikke strøm efter "
                f"{fmt_num(s.watchdog_circulation_min)}+ minutters cirkulation"
            )

    def _current_timer_days(self) -> tuple[int | None, int | None]:
        return (self.timer_days(Timer.FILTER), self.timer_days(Timer.BATH_WATER))

    @callback
    def _timer_tick(self, _now: datetime) -> None:
        days = self._current_timer_days()
        if days != self._timer_days:
            self._timer_days = days
            self._notify_listeners()
