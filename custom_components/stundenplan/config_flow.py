"""Config flow for Stundenplan."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    DateSelector,
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TimeSelector,
)

from .const import (
    CONF_DESCRIPTION,
    CONF_END_DATE,
    CONF_ENTRY_TYPE,
    CONF_HOLIDAY_CALENDAR,
    CONF_LESSONS,
    CONF_LOCATION,
    CONF_PERIOD,
    CONF_PERIOD_END,
    CONF_PERIOD_NAME,
    CONF_PERIOD_START,
    CONF_PERIODS,
    CONF_START_DATE,
    CONF_SUBJECT,
    CONF_SUBJECT_NAME,
    CONF_SUBJECTS,
    CONF_TEACHER,
    CONF_TIMETABLES,
    CONF_WEEKDAY,
    CONF_WEEKS,
    DOMAIN,
    TYPE_CALENDAR,
    TYPE_TIMETABLE,
    WEEKDAYS,
)
from .schedule import parse_time, parse_weeks

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _hhmm(value: str) -> str:
    return value[:5]


def _text(multiline: bool = False) -> TextSelector:
    return TextSelector(TextSelectorConfig(multiline=multiline))


def _select(options: list[SelectOptionDict], **kwargs: Any) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN, **kwargs)
    )


def _timetable_options(hass, exclude: str | None = None) -> list[SelectOptionDict]:
    return [
        SelectOptionDict(value=e.entry_id, label=e.title)
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.data.get(CONF_ENTRY_TYPE) == TYPE_TIMETABLE and e.entry_id != exclude
    ]


def _timetables_schema(hass, default: list[str]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_TIMETABLES, default=default): _select(
                _timetable_options(hass), multiple=True
            )
        }
    )


class StundenplanConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create timetables and named calendars."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        if config_entry.data.get(CONF_ENTRY_TYPE) == TYPE_CALENDAR:
            return CalendarOptionsFlow()
        return TimetableOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["timetable", "calendar"])

    async def async_step_timetable(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a timetable (data only, no entity)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_END_DATE] < user_input[CONF_START_DATE]:
                errors["base"] = "end_before_start"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={CONF_ENTRY_TYPE: TYPE_TIMETABLE},
                    options={
                        CONF_START_DATE: user_input[CONF_START_DATE],
                        CONF_END_DATE: user_input[CONF_END_DATE],
                        CONF_HOLIDAY_CALENDAR: user_input.get(CONF_HOLIDAY_CALENDAR),
                        CONF_PERIODS: [],
                        CONF_SUBJECTS: [],
                        CONF_LESSONS: [],
                    },
                )
        return self.async_show_form(
            step_id="timetable",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_START_DATE): DateSelector(),
                    vol.Required(CONF_END_DATE): DateSelector(),
                    vol.Optional(CONF_HOLIDAY_CALENDAR): EntitySelector(
                        EntitySelectorConfig(domain="calendar")
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_calendar(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a named calendar from one or more timetables."""
        if not _timetable_options(self.hass):
            return self.async_abort(reason="no_timetables")
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_TIMETABLES]:
                errors["base"] = "no_timetable_selected"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={CONF_ENTRY_TYPE: TYPE_CALENDAR},
                    options={CONF_TIMETABLES: user_input[CONF_TIMETABLES]},
                )
        schema = _timetables_schema(self.hass, []).schema
        return self.async_show_form(
            step_id="calendar",
            data_schema=vol.Schema({vol.Required(CONF_NAME): str, **schema}),
            errors=errors,
        )


class CalendarOptionsFlow(OptionsFlow):
    """Change which timetables a calendar shows."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = self.config_entry.options.get(CONF_TIMETABLES, [])
        if user_input is not None:
            if not user_input[CONF_TIMETABLES]:
                errors["base"] = "no_timetable_selected"
            else:
                return self.async_create_entry(data={CONF_TIMETABLES: user_input[CONF_TIMETABLES]})
        valid = {o["value"] for o in _timetable_options(self.hass)}
        return self.async_show_form(
            step_id="init",
            data_schema=_timetables_schema(self.hass, [t for t in current if t in valid]),
            errors=errors,
        )


class TimetableOptionsFlow(OptionsFlow):
    """Edit a timetable: settings, time grid, subjects and lessons."""

    def __init__(self) -> None:
        self._opts: dict[str, Any] | None = None

    @property
    def opts(self) -> dict[str, Any]:
        if self._opts is None:
            self._opts = deepcopy(dict(self.config_entry.options))
        return self._opts

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "settings",
                "add_period",
                "remove_period",
                "add_subject",
                "remove_subject",
                "add_lesson",
                "remove_lesson",
                "save",
            ],
        )

    async def async_step_save(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_create_entry(data=self.opts)

    # -- settings ---------------------------------------------------------
    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_END_DATE] < user_input[CONF_START_DATE]:
                errors["base"] = "end_before_start"
            else:
                self.opts[CONF_START_DATE] = user_input[CONF_START_DATE]
                self.opts[CONF_END_DATE] = user_input[CONF_END_DATE]
                self.opts[CONF_HOLIDAY_CALENDAR] = user_input.get(CONF_HOLIDAY_CALENDAR)
                return await self.async_step_init()
        holiday = self.opts.get(CONF_HOLIDAY_CALENDAR)
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_START_DATE, default=self.opts[CONF_START_DATE]): DateSelector(),
                    vol.Required(CONF_END_DATE, default=self.opts[CONF_END_DATE]): DateSelector(),
                    vol.Optional(
                        CONF_HOLIDAY_CALENDAR,
                        description={"suggested_value": holiday} if holiday else None,
                    ): EntitySelector(EntitySelectorConfig(domain="calendar")),
                }
            ),
            errors=errors,
        )

    # -- periods (time grid) ---------------------------------------------
    async def async_step_add_period(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_PERIOD_NAME].strip()
            start, end = _hhmm(user_input[CONF_PERIOD_START]), _hhmm(user_input[CONF_PERIOD_END])
            if any(p[CONF_PERIOD_NAME] == name for p in self.opts[CONF_PERIODS]):
                errors["base"] = "duplicate_name"
            elif parse_time(end) <= parse_time(start):
                errors["base"] = "end_before_start_time"
            else:
                self.opts[CONF_PERIODS].append(
                    {CONF_PERIOD_NAME: name, CONF_PERIOD_START: start, CONF_PERIOD_END: end}
                )
                self.opts[CONF_PERIODS].sort(key=lambda p: p[CONF_PERIOD_START])
                return await self.async_step_init()
        return self.async_show_form(
            step_id="add_period",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PERIOD_NAME): _text(),
                    vol.Required(CONF_PERIOD_START): TimeSelector(),
                    vol.Required(CONF_PERIOD_END): TimeSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_remove_period(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            gone = set(user_input["items"])
            self.opts[CONF_PERIODS] = [
                p for p in self.opts[CONF_PERIODS] if p[CONF_PERIOD_NAME] not in gone
            ]
            # lessons that used a removed period are dropped
            self.opts[CONF_LESSONS] = [
                item for item in self.opts[CONF_LESSONS] if item[CONF_PERIOD] not in gone
            ]
            return await self.async_step_init()
        options = [
            SelectOptionDict(
                value=p[CONF_PERIOD_NAME],
                label=f"{p[CONF_PERIOD_NAME]} ({p[CONF_PERIOD_START]}-{p[CONF_PERIOD_END]})",
            )
            for p in self.opts[CONF_PERIODS]
        ]
        return self._show_remove("remove_period", options)

    # -- subjects (+ teacher) ---------------------------------------------
    async def async_step_add_subject(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_SUBJECT_NAME].strip()
            if any(s[CONF_SUBJECT_NAME] == name for s in self.opts[CONF_SUBJECTS]):
                errors["base"] = "duplicate_name"
            else:
                self.opts[CONF_SUBJECTS].append(
                    {CONF_SUBJECT_NAME: name, CONF_TEACHER: user_input.get(CONF_TEACHER, "").strip()}
                )
                return await self.async_step_init()
        return self.async_show_form(
            step_id="add_subject",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SUBJECT_NAME): _text(),
                    vol.Optional(CONF_TEACHER): _text(),
                }
            ),
            errors=errors,
        )

    async def async_step_remove_subject(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            gone = set(user_input["items"])
            self.opts[CONF_SUBJECTS] = [
                s for s in self.opts[CONF_SUBJECTS] if s[CONF_SUBJECT_NAME] not in gone
            ]
            self.opts[CONF_LESSONS] = [
                item for item in self.opts[CONF_LESSONS] if item[CONF_SUBJECT] not in gone
            ]
            return await self.async_step_init()
        options = [
            SelectOptionDict(
                value=s[CONF_SUBJECT_NAME],
                label=f"{s[CONF_SUBJECT_NAME]} ({s.get(CONF_TEACHER) or '-'})",
            )
            for s in self.opts[CONF_SUBJECTS]
        ]
        return self._show_remove("remove_subject", options)

    # -- lessons ----------------------------------------------------------
    async def async_step_add_lesson(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if not self.opts[CONF_SUBJECTS] or not self.opts[CONF_PERIODS]:
            if user_input is not None:
                return await self.async_step_init()
            return self.async_show_form(
                step_id="add_lesson",
                data_schema=vol.Schema({}),
                errors={"base": "need_subjects_and_periods"},
            )
        errors: dict[str, str] = {}
        if user_input is not None:
            weeks = user_input.get(CONF_WEEKS, "").strip()
            try:
                parse_weeks(weeks)
            except ValueError:
                errors[CONF_WEEKS] = "invalid_weeks"
            else:
                self.opts[CONF_LESSONS].append(
                    {
                        CONF_SUBJECT: user_input[CONF_SUBJECT],
                        CONF_WEEKDAY: int(user_input[CONF_WEEKDAY]),
                        CONF_PERIOD: user_input[CONF_PERIOD],
                        CONF_LOCATION: user_input.get(CONF_LOCATION, "").strip(),
                        CONF_DESCRIPTION: user_input.get(CONF_DESCRIPTION, "").strip(),
                        CONF_WEEKS: weeks or "all",
                    }
                )
                return await self.async_step_init()
        return self.async_show_form(
            step_id="add_lesson",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SUBJECT): _select(
                        [SelectOptionDict(value=s[CONF_SUBJECT_NAME], label=s[CONF_SUBJECT_NAME])
                         for s in self.opts[CONF_SUBJECTS]]
                    ),
                    vol.Required(CONF_WEEKDAY, default="0"): SelectSelector(
                        SelectSelectorConfig(
                            options=[str(i) for i in range(len(WEEKDAYS))],
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key="weekday",
                        )
                    ),
                    vol.Required(CONF_PERIOD): _select(
                        [SelectOptionDict(
                            value=p[CONF_PERIOD_NAME],
                            label=f"{p[CONF_PERIOD_NAME]} ({p[CONF_PERIOD_START]}-{p[CONF_PERIOD_END]})",
                        ) for p in self.opts[CONF_PERIODS]]
                    ),
                    vol.Optional(CONF_LOCATION): _text(),
                    vol.Optional(CONF_DESCRIPTION): _text(multiline=True),
                    vol.Optional(CONF_WEEKS, default="all"): _text(),
                }
            ),
            errors=errors,
        )

    async def async_step_remove_lesson(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        lessons = self.opts[CONF_LESSONS]
        if user_input is not None:
            gone = {int(i) for i in user_input["items"]}
            self.opts[CONF_LESSONS] = [x for i, x in enumerate(lessons) if i not in gone]
            return await self.async_step_init()
        options = [
            SelectOptionDict(
                value=str(i),
                label=(
                    f"{WEEKDAY_LABELS[x[CONF_WEEKDAY]]} {x[CONF_PERIOD]}: {x[CONF_SUBJECT]}"
                    + (f" [{x[CONF_WEEKS]}]" if x.get(CONF_WEEKS, "all") != "all" else "")
                ),
            )
            for i, x in sorted(
                enumerate(lessons), key=lambda t: (t[1][CONF_WEEKDAY], t[1][CONF_PERIOD])
            )
        ]
        return self._show_remove("remove_lesson", options)

    def _show_remove(self, step_id: str, options: list[SelectOptionDict]) -> ConfigFlowResult:
        if not options:
            return self.async_show_form(
                step_id=step_id, data_schema=vol.Schema({}), errors={"base": "nothing_to_remove"}
            )
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({vol.Required("items"): _select(options, multiple=True)}),
        )
