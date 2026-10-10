"""The Stundenplan integration: school timetables as calendars.

Two kinds of config entries exist:
* ``timetable``: holds the timetable data, creates no entities itself.
* ``calendar``: a named calendar entity that shows the lessons of one or more
  timetables. A timetable can be used by any number of calendars (n:m).
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_ENTRY_TYPE, TYPE_CALENDAR

PLATFORMS = [Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a timetable or calendar entry."""
    if entry.data.get(CONF_ENTRY_TYPE) == TYPE_CALENDAR:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if entry.data.get(CONF_ENTRY_TYPE) == TYPE_CALENDAR:
        return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)
