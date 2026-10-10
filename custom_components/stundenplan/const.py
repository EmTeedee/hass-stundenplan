"""Constants for the Stundenplan integration."""

DOMAIN = "stundenplan"

CONF_START_DATE = "start_date"
CONF_END_DATE = "end_date"
CONF_HOLIDAY_CALENDAR = "holiday_calendar"
CONF_PERIODS = "periods"
CONF_SUBJECTS = "subjects"
CONF_LESSONS = "lessons"

# Fields of a period / subject / lesson dict
CONF_PERIOD_NAME = "name"
CONF_PERIOD_START = "start"
CONF_PERIOD_END = "end"
CONF_SUBJECT_NAME = "name"
CONF_TEACHER = "teacher"
CONF_SUBJECT = "subject"
CONF_WEEKDAY = "weekday"
CONF_PERIOD = "period"
CONF_LOCATION = "location"
CONF_DESCRIPTION = "description"
CONF_WEEKS = "weeks"

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# A config entry is either a timetable (data) or a named calendar that
# combines any number of timetables (n:m).
CONF_ENTRY_TYPE = "entry_type"
TYPE_TIMETABLE = "timetable"
TYPE_CALENDAR = "calendar"
CONF_TIMETABLES = "timetables"  # list of timetable config entry ids
