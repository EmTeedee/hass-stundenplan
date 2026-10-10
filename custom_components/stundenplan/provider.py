"""Shared lesson provider used by the calendar and sensor entities of one calendar entry."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
import time as time_mod

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .schedule import LessonEvent, Timetable, build_events, holiday_dates_from_events

_LOGGER = logging.getLogger(__name__)

HOLIDAY_CACHE_SECONDS = 3600


class LessonProvider:
    """Builds lesson events for one or more timetables, honouring holiday calendars."""

    def __init__(self, hass: HomeAssistant, sources: list[tuple[Timetable, str | None]]) -> None:
        self.hass = hass
        self.sources = sources
        self._holiday_cache: dict[str, tuple[float, date, date, set[date]]] = {}

    @property
    def multiple(self) -> bool:
        """True if this calendar combines several timetables."""
        return len(self.sources) > 1

    async def async_events(self, first: date, last: date, cached: bool = False) -> list[LessonEvent]:
        """All lessons from first to last (inclusive), sorted by start time."""
        events: list[LessonEvent] = []
        for timetable, holiday_entity in self.sources:
            holidays = await self._async_holidays(holiday_entity, first, last, cached)
            events.extend(build_events(timetable, first, last, holidays))
        events.sort(key=lambda e: (e.start, e.end, e.subject))
        return events

    async def _async_holidays(
        self, entity_id: str | None, first: date, last: date, cached: bool
    ) -> set[date]:
        """Dates covered by the holiday calendar (lessons are hidden on these)."""
        if not entity_id:
            return set()
        if cached and (hit := self._holiday_cache.get(entity_id)):
            fetched, c_first, c_last, days = hit
            if (
                time_mod.monotonic() - fetched < HOLIDAY_CACHE_SECONDS
                and c_first <= first
                and c_last >= last
            ):
                return days
        tz = dt_util.get_default_time_zone()
        try:
            response = await self.hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": entity_id,
                    "start_date_time": datetime.combine(first, datetime.min.time(), tz),
                    "end_date_time": datetime.combine(
                        last + timedelta(days=1), datetime.min.time(), tz
                    ),
                },
                blocking=True,
                return_response=True,
            )
            days = holiday_dates_from_events(response.get(entity_id, {}).get("events", []))
        except Exception as err:  # noqa: BLE001 - never break the timetable over holidays
            _LOGGER.warning("Could not read holiday calendar %s: %s", entity_id, err)
            return set()
        self._holiday_cache[entity_id] = (time_mod.monotonic(), first, last, days)
        return days
