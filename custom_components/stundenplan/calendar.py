"""Calendar platform: a named calendar showing one or more timetables."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
import time as time_mod

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_HOLIDAY_CALENDAR, CONF_TIMETABLES, DOMAIN
from .schedule import LessonEvent, Timetable, build_events, holiday_dates_from_events

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1)
LOOKAHEAD_DAYS = 70  # "next event" may be after long holidays
HOLIDAY_CACHE_SECONDS = 3600


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the calendar entity and follow changes of its timetables."""
    sources: list[tuple[Timetable, str | None]] = []
    for timetable_id in entry.options.get(CONF_TIMETABLES, []):
        tt_entry = hass.config_entries.async_get_entry(timetable_id)
        if tt_entry is None:
            _LOGGER.warning("Timetable %s of calendar %s no longer exists", timetable_id, entry.title)
            continue
        try:
            timetable = Timetable.from_options(tt_entry.title, tt_entry.options)
        except (KeyError, ValueError) as err:
            _LOGGER.error("Timetable %s is invalid: %s", tt_entry.title, err)
            continue
        sources.append((timetable, tt_entry.options.get(CONF_HOLIDAY_CALENDAR)))
        # Reload this calendar whenever one of its timetables is edited.
        entry.async_on_unload(tt_entry.add_update_listener(_reload_calendar(entry.entry_id)))
    async_add_entities([StundenplanCalendar(entry, sources)], update_before_add=True)


def _reload_calendar(calendar_entry_id: str):
    async def _listener(hass: HomeAssistant, _timetable_entry: ConfigEntry) -> None:
        hass.config_entries.async_schedule_reload(calendar_entry_id)

    return _listener


class StundenplanCalendar(CalendarEntity):
    """Calendar with the lessons of one or more timetables."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = True

    def __init__(self, entry: ConfigEntry, sources: list[tuple[Timetable, str | None]]) -> None:
        self._sources = sources
        self._event: CalendarEvent | None = None
        self._holiday_cache: dict[str, tuple[float, date, date, set[date]]] = {}
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Current or next lesson."""
        return self._event

    async def async_update(self) -> None:
        now = dt_util.now()
        today = now.date()
        events = await self._async_events(today, today + timedelta(days=LOOKAHEAD_DAYS), cached=True)
        naive_now = now.replace(tzinfo=None)
        self._event = next((self._to_event(e) for e in events if e.end > naive_now), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        start, end = dt_util.as_local(start_date), dt_util.as_local(end_date)
        lessons = await self._async_events(start.date(), end.date())
        return [
            ev
            for ev in map(self._to_event, lessons)
            if ev.end_datetime_local > start and ev.start_datetime_local < end
        ]

    async def _async_events(self, first: date, last: date, cached: bool = False) -> list[LessonEvent]:
        events: list[LessonEvent] = []
        for timetable, holiday_entity in self._sources:
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
            if time_mod.monotonic() - fetched < HOLIDAY_CACHE_SECONDS and c_first <= first and c_last >= last:
                return days
        tz = dt_util.get_default_time_zone()
        try:
            response = await self.hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": entity_id,
                    "start_date_time": datetime.combine(first, datetime.min.time(), tz),
                    "end_date_time": datetime.combine(last + timedelta(days=1), datetime.min.time(), tz),
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

    def _to_event(self, lesson: LessonEvent) -> CalendarEvent:
        tz = dt_util.get_default_time_zone()
        multiple = len(self._sources) > 1
        lines = [line for line in (lesson.teacher, lesson.description) if line]
        if multiple:
            lines.insert(0, lesson.timetable)
        return CalendarEvent(
            start=lesson.start.replace(tzinfo=tz),
            end=lesson.end.replace(tzinfo=tz),
            summary=f"{lesson.subject} ({lesson.timetable})" if multiple else lesson.subject,
            location=lesson.location or None,
            description="\n".join(lines) or None,
        )
