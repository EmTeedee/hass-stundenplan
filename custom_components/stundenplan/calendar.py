"""Calendar platform: a named calendar showing one or more timetables."""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import StundenplanConfigEntry
from .const import DOMAIN
from .provider import LessonProvider
from .schedule import LessonEvent

SCAN_INTERVAL = timedelta(minutes=1)
LOOKAHEAD_DAYS = 70  # "next event" may be after long holidays


async def async_setup_entry(
    hass: HomeAssistant, entry: StundenplanConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the calendar entity."""
    async_add_entities([StundenplanCalendar(entry)], update_before_add=True)


class StundenplanCalendar(CalendarEntity):
    """Calendar with the lessons of one or more timetables."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = True

    def __init__(self, entry: StundenplanConfigEntry) -> None:
        self._provider: LessonProvider = entry.runtime_data
        self._event: CalendarEvent | None = None
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
        events = await self._provider.async_events(
            today, today + timedelta(days=LOOKAHEAD_DAYS), cached=True
        )
        naive_now = now.replace(tzinfo=None)
        self._event = next((self._to_event(e) for e in events if e.end > naive_now), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        start, end = dt_util.as_local(start_date), dt_util.as_local(end_date)
        lessons = await self._provider.async_events(start.date(), end.date())
        return [
            ev
            for ev in map(self._to_event, lessons)
            if ev.end_datetime_local > start and ev.start_datetime_local < end
        ]

    def _to_event(self, lesson: LessonEvent) -> CalendarEvent:
        tz = dt_util.get_default_time_zone()
        lines = [line for line in (lesson.teacher, lesson.description) if line]
        if self._provider.multiple:
            lines.insert(0, lesson.timetable)
        return CalendarEvent(
            start=lesson.start.replace(tzinfo=tz),
            end=lesson.end.replace(tzinfo=tz),
            summary=lesson.subject,  # plain name keeps keyword rules (e.g. in Timetable Card) simple
            location=lesson.location or None,
            description="\n".join(lines) or None,
        )
