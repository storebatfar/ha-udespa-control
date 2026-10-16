"""I brug reminder: ask after a while, lower to rest if nobody answers.

When the status has been I brug for `in_use_reminder_h` hours, a push asks
whether the tub is still in use, with a confirm button. A confirmation (the
phone's button or the dashboard button) asks again `in_use_repeat_h` hours
later. No answer within `in_use_grace_min` minutes: the spa goes back to the
rest temperature. Leaving I brug cancels everything.

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

from .const import IN_USE_CONFIRM_ACTION, IN_USE_NOTIFY_TAG, Status
from .rules import fmt_c, fmt_num
from .settings import Settings
from .storage import StoredState

_TITLE = "Udespa i brug"


class InUseGuard:
    def __init__(
        self,
        hass: HomeAssistant,
        settings: Settings,
        *,
        state: Callable[[], StoredState],
        rest_temperature: Callable[[], float],
        notify: Callable[[str, str, dict[str, Any] | None], Awaitable[Any]],
        lower: Callable[[], Awaitable[Any]],
        record: Callable[[str], None],
        save: Callable[[], None],
        spawn: Callable[[Awaitable[Any], str], None],
    ) -> None:
        self._hass = hass
        self._s = settings
        self._state = state
        self._rest = rest_temperature
        self._notify = notify
        self._lower = lower
        self._record = record
        self._save = save
        self._spawn = spawn
        self._cancel: CALLBACK_TYPE | None = None

    # --- inputs ---------------------------------------------------------------

    @property
    def _enabled(self) -> bool:
        return self._s.in_use_reminder_h > 0

    def status_changed(self, status: Status) -> None:
        if status is Status.IN_USE and self._enabled:
            now = dt_util.utcnow()
            st = self._state()
            st.in_use_since = now
            self._set(due=now + timedelta(hours=self._s.in_use_reminder_h), asked=None)
        else:
            self._clear()

    def resume(self, status: Status) -> None:
        """At start-up: pick the stored wait up again, or start one."""
        st = self._state()
        if status is not Status.IN_USE or not self._enabled:
            self._clear()
            return
        if st.in_use_due_at is None and st.in_use_asked_at is None:
            # I brug began while we weren't watching: count from now.
            self.status_changed(status)
            return
        self._schedule()

    def confirm(self, status: Status, source: str) -> None:
        if status is not Status.IN_USE or not self._enabled:
            self._record(f"Stadig i brug ({source}): ignoreret, status er {status}")
            return
        st = self._state()
        due = dt_util.utcnow() + timedelta(hours=self._s.in_use_repeat_h)
        if st.in_use_asked_at is None and st.in_use_due_at and st.in_use_due_at > due:
            due = st.in_use_due_at  # a press before the question never shortens the wait
        self._set(due=due, asked=None)
        local = dt_util.as_local(due).strftime("%H:%M")
        self._record(f"Stadig i brug bekræftet ({source}): næste spørgsmål kl. {local}")

    @staticmethod
    def is_confirm_action(event_data: dict[str, Any]) -> bool:
        return event_data.get("action") == IN_USE_CONFIRM_ACTION

    def shutdown(self) -> None:
        if self._cancel is not None:
            self._cancel()
            self._cancel = None

    # --- timers ---------------------------------------------------------------

    def _set(self, *, due: datetime | None, asked: datetime | None) -> None:
        st = self._state()
        st.in_use_due_at = due
        st.in_use_asked_at = asked
        self._save()
        self._schedule()

    def _clear(self) -> None:
        self.shutdown()
        st = self._state()
        if st.in_use_due_at or st.in_use_asked_at or st.in_use_since:
            st.in_use_due_at = st.in_use_asked_at = st.in_use_since = None
            self._save()

    def _schedule(self) -> None:
        self.shutdown()
        st = self._state()
        now = dt_util.utcnow()
        if st.in_use_asked_at is not None:
            at = st.in_use_asked_at + timedelta(minutes=self._s.in_use_grace_min)
            action = self._answer_window_over
        elif st.in_use_due_at is not None:
            at, action = st.in_use_due_at, self._ask
        else:
            return
        self._cancel = async_call_later(
            self._hass, max(0.0, (at - now).total_seconds()), action
        )

    @callback
    def _ask(self, _now: Any) -> None:
        self._cancel = None
        st = self._state()
        since = st.in_use_since or dt_util.utcnow()
        hours = round((dt_util.utcnow() - since).total_seconds() / 3600)
        grace = fmt_num(self._s.in_use_grace_min)
        rest = fmt_c(self._rest())
        self._record(f"I brug-påmindelse: i brug i {hours} timer, venter {grace} min på svar")
        message = (
            f"Udespa har været i brug i {hours} timer. Bruger I den stadig? "
            f"Ellers sættes den ned til {rest} °C om {grace} min."
        )
        data = {
            "tag": IN_USE_NOTIFY_TAG,
            "actions": [{"action": IN_USE_CONFIRM_ACTION, "title": "Ja, stadig i brug"}],
        }
        self._spawn(self._notify(_TITLE, message, data), "in-use question")
        self._set(due=None, asked=dt_util.utcnow())

    @callback
    def _answer_window_over(self, _now: Any) -> None:
        self._cancel = None
        rest = fmt_c(self._rest())
        self._record(f"I brug-påmindelse ubesvaret: spaen sættes ned til {rest} °C")
        self._clear()
        self._spawn(self._lower(), "in-use lower")
        self._spawn(
            self._notify(
                _TITLE,
                f"Ingen svar: spaen er sat ned til {rest} °C.",
                {"tag": IN_USE_NOTIFY_TAG},
            ),
            "in-use lowered",
        )
