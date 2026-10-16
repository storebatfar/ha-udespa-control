"""I brug reminder: ask after a while, lower to rest if nobody answers.

When the tub has been in use for `in_use_reminder_h` hours, a push asks
whether it still is, with a confirm button. A confirmation (the phone's button
or the dashboard button) asks again `in_use_repeat_h` hours later. No answer
within `in_use_grace_min` minutes: the spa goes back to the rest temperature.

"In use" follows the setpoint (the status the setpoint gives), not the status
on display: a heat-pump fault (Fejl) doesn't hide it, and cleaning only pauses
it. It ends when the setpoint says Vedligeholder.

It only lowers after asking: a question that wasn't delivered (notifications
off, a failed push) never leads to lowering. Watch-only logs as if delivered.

The times live in storage, so a restart resumes the wait instead of starting
it over (the reason the Orangeri guard uses a timer helper, not a `for:`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import IN_USE_CONFIRM_ACTION, IN_USE_NOTIFY_TAG
from .rules import fmt_c, fmt_num
from .settings import Settings
from .storage import StoredState

_TITLE = "Udespa i brug"


def hours_text(hours: float) -> str:
    """1 -> '1 time', 2.5 -> '2,5 timer'."""
    value = fmt_num(round(hours * 2) / 2)
    return f"{value} time" if value == "1" else f"{value} timer"


class InUseGuard:
    def __init__(
        self,
        hass: HomeAssistant,
        settings: Settings,
        *,
        state: Callable[[], StoredState],
        in_use: Callable[[], bool],
        paused: Callable[[], bool],
        active: Callable[[], bool],
        rest_temperature: Callable[[], float],
        notify: Callable[[str, str, dict[str, Any] | None], Awaitable[bool]],
        lower: Callable[[], Awaitable[bool]],
        record: Callable[[str], None],
        save: Callable[[], None],
        spawn: Callable[[Awaitable[Any], str], None],
    ) -> None:
        self._hass = hass
        self._s = settings
        self._state = state
        self._in_use = in_use
        self._paused = paused
        self._active = active
        self._rest = rest_temperature
        self._notify = notify
        self._lower = lower
        self._record = record
        self._save = save
        self._spawn = spawn
        self._cancel: CALLBACK_TYPE | None = None

    @property
    def _enabled(self) -> bool:
        return self._s.in_use_reminder_h > 0

    # --- inputs ---------------------------------------------------------------

    def refresh(self) -> None:
        """Status changed, or start-up: start, resume, pause or end the wait."""
        st = self._state()
        if not self._enabled or not self._in_use():
            if self._paused() and self._enabled:
                self.shutdown()  # cleaning: keep the times
                return
            self._clear()
            return
        if self._paused():
            self.shutdown()
            return
        if st.in_use_due_at is None and st.in_use_asked_at is None:
            now = dt_util.utcnow()
            st.in_use_since = now
            self._set(due=now + timedelta(hours=self._s.in_use_reminder_h), asked=None)
            return
        self._schedule()

    def confirm(self, source: str) -> None:
        st = self._state()
        if not self._enabled:
            self._record(f"Stadig i brug ({source}): ignoreret, påmindelsen er slået fra")
            return
        if not self._in_use() or (st.in_use_due_at is None and st.in_use_asked_at is None):
            self._record(f"Stadig i brug ({source}): ignoreret, spaen er ikke i brug")
            return
        was_asked = st.in_use_asked_at is not None
        due = dt_util.utcnow() + timedelta(hours=self._s.in_use_repeat_h)
        if not was_asked and st.in_use_due_at and st.in_use_due_at > due:
            due = st.in_use_due_at  # a press before the question never shortens the wait
        self._set(due=due, asked=None)
        local = dt_util.as_local(due).strftime("%H:%M")
        self._record(f"Stadig i brug bekræftet ({source}): næste spørgsmål kl. {local}")
        if was_asked:
            self._spawn(self._clear_question(), "in-use clear question")

    @staticmethod
    def is_confirm_action(event_data: dict[str, Any]) -> bool:
        return event_data.get("action") == IN_USE_CONFIRM_ACTION

    def shutdown(self) -> None:
        if self._cancel is not None:
            self._cancel()
            self._cancel = None

    # --- state ----------------------------------------------------------------

    def _set(self, *, due: datetime | None, asked: datetime | None) -> None:
        st = self._state()
        st.in_use_due_at = due
        st.in_use_asked_at = asked
        self._save()
        self._schedule()

    def _clear(self) -> None:
        self.shutdown()
        st = self._state()
        was_asked = st.in_use_asked_at is not None
        if st.in_use_due_at or st.in_use_asked_at or st.in_use_since:
            st.in_use_due_at = st.in_use_asked_at = st.in_use_since = None
            self._save()
        if was_asked:
            self._spawn(self._clear_question(), "in-use clear question")

    def _schedule(self) -> None:
        self.shutdown()
        st = self._state()
        if st.in_use_asked_at is not None:
            at = st.in_use_asked_at + timedelta(minutes=self._s.in_use_grace_min)
            action = self._answer_window_over
        elif st.in_use_due_at is not None:
            at, action = st.in_use_due_at, self._ask
        else:
            return
        delay = max(0.0, (at - dt_util.utcnow()).total_seconds())
        self._cancel = async_call_later(self._hass, delay, action)

    def _rearm(self) -> None:
        self._set(due=dt_util.utcnow() + timedelta(hours=self._s.in_use_repeat_h), asked=None)

    def _still_applies(self) -> bool:
        if not self._enabled or not self._in_use():
            self._clear()
            return False
        # Cleaning: wait; refresh() reschedules when it ends.
        return not self._paused()

    # --- timers ---------------------------------------------------------------

    @callback
    def _ask(self, _now: Any) -> None:
        self._cancel = None
        if self._still_applies():
            self._spawn(self._async_ask(), "in-use question")

    async def _async_ask(self) -> None:
        st = self._state()
        since = st.in_use_since or dt_util.utcnow()
        hours = hours_text((dt_util.utcnow() - since).total_seconds() / 3600)
        grace = fmt_num(self._s.in_use_grace_min)
        rest = fmt_c(self._rest())
        message = (
            f"Udespa har været i brug i {hours}. Bruger I den stadig? "
            f"Ellers sættes den ned til {rest} °C om {grace} min."
        )
        data = {
            "tag": IN_USE_NOTIFY_TAG,
            "actions": [{"action": IN_USE_CONFIRM_ACTION, "title": "Ja, stadig i brug"}],
        }
        delivered = await self._notify(_TITLE, message, data)
        if not delivered and self._active():
            self._record(
                f"I brug-påmindelse kunne ikke sendes: spaen sænkes ikke, "
                f"ny påmindelse om {hours_text(self._s.in_use_repeat_h)}"
            )
            self._rearm()
            return
        self._record(f"I brug-påmindelse: i brug i {hours}, venter {grace} min på svar")
        self._set(due=None, asked=dt_util.utcnow())

    @callback
    def _answer_window_over(self, _now: Any) -> None:
        self._cancel = None
        if self._still_applies():
            self._spawn(self._async_lower(), "in-use lower")

    async def _async_lower(self) -> None:
        rest = fmt_c(self._rest())
        self._record(f"I brug-påmindelse ubesvaret: spaen sættes ned til {rest} °C")
        lowered = await self._lower()
        if lowered or not self._active():
            message = f"Ingen svar: spaen er sat ned til {rest} °C."
        else:
            message = (
                f"Ingen svar, men spaen kunne ikke sænkes til {rest} °C. "
                f"Jeg spørger igen om {hours_text(self._s.in_use_repeat_h)}."
            )
        # Re-arm either way: a real drop to Vedligeholder ends it through refresh().
        self._rearm()
        await self._notify(_TITLE, message, {"tag": IN_USE_NOTIFY_TAG})

    async def _clear_question(self) -> None:
        await self._notify("", "clear_notification", {"tag": IN_USE_NOTIFY_TAG})
