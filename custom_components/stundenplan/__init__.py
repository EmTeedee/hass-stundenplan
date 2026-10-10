"""The Stundenplan integration: school timetables as calendars.

Two kinds of config entries exist:
* ``timetable``: holds the timetable data, creates no entities itself.
* ``calendar``: a named calendar entity  that shows
  the lessons of one or more timetables. A timetable can be used by any number of
  calendars (n:m).
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_ENTRY_TYPE, CONF_HOLIDAY_CALENDAR, CONF_TIMETABLES, TYPE_CALENDAR
from .provider import LessonProvider
from .schedule import Timetable

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CALENDAR, Platform.SENSOR]

type StundenplanConfigEntry = ConfigEntry[LessonProvider]


def _reload_calendar(calendar_entry_id: str):
    async def _listener(hass: HomeAssistant, _timetable_entry: ConfigEntry) -> None:
        hass.config_entries.async_schedule_reload(calendar_entry_id)

    return _listener


async def async_setup_entry(hass: HomeAssistant, entry: StundenplanConfigEntry) -> bool:
    """Set up a timetable or calendar entry."""
    if entry.data.get(CONF_ENTRY_TYPE) != TYPE_CALENDAR:
        return True

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

    entry.runtime_data = LessonProvider(hass, sources)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: StundenplanConfigEntry) -> bool:
    """Unload a config entry."""
    if entry.data.get(CONF_ENTRY_TYPE) == TYPE_CALENDAR:
        return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)
