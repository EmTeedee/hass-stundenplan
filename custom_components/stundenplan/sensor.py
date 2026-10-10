"""Sensors with all lessons of today and tomorrow, for dashboards and automations."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import StundenplanConfigEntry
from .const import DOMAIN
from .provider import LessonProvider

SCAN_INTERVAL = timedelta(minutes=1)


async def async_setup_entry(
    hass: HomeAssistant, entry: StundenplanConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the today / tomorrow sensors."""
    async_add_entities(
        [DaySensor(entry, "today", 0), DaySensor(entry, "tomorrow", 1)], update_before_add=True
    )


class DaySensor(SensorEntity):
    """State: number of lessons that day. Attributes: subjects and full lesson list."""

    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_icon = "mdi:school"
    _unrecorded_attributes = frozenset({"lessons"})

    def __init__(self, entry: StundenplanConfigEntry, key: str, offset: int) -> None:
        self._provider: LessonProvider = entry.runtime_data
        self._offset = offset
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )
        self._attr_native_value = 0
        self._attr_extra_state_attributes: dict[str, Any] = {}

    async def async_update(self) -> None:
        tz = dt_util.get_default_time_zone()
        day = dt_util.now().date() + timedelta(days=self._offset)
        lessons = await self._provider.async_events(day, day, cached=True)
        subjects = list(dict.fromkeys(e.subject for e in lessons))  # unique, in time order
        self._attr_native_value = len(lessons)
        self._attr_extra_state_attributes = {
            "date": day.isoformat(),
            "subjects": subjects,
            "first_start": lessons[0].start.replace(tzinfo=tz).isoformat() if lessons else None,
            "last_end": max(e.end for e in lessons).replace(tzinfo=tz).isoformat() if lessons else None,
            "lessons": [
                {
                    "subject": e.subject,
                    "teacher": e.teacher,
                    "location": e.location,
                    "description": e.description,
                    "timetable": e.timetable,
                    "start": e.start.replace(tzinfo=tz).isoformat(),
                    "end": e.end.replace(tzinfo=tz).isoformat(),
                }
                for e in lessons
            ],
        }
