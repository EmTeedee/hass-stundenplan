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
    CONF_END_PERIOD,
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
from .schedule import format_periods, parse_periods, parse_time, parse_weeks

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_LABELS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _hhmm(value: str) -> str:
    return value[:5]


def _text(multiline: bool = False) -> TextSelector:
    return TextSelector(TextSelectorConfig(multiline=multiline))


def _select(options: list[SelectOptionDict], **kwargs: Any) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN, **kwargs)
    )


def _suggest(value: Any) -> dict[str, Any] | None:
    """Prefill an optional field without making the empty value a default."""
    return {"suggested_value": value} if value else None


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
        return await self.async_step_timetables()

    async def async_step_timetables(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = self.config_entry.options.get(CONF_TIMETABLES, [])
        if user_input is not None:
            if not user_input[CONF_TIMETABLES]:
                errors["base"] = "no_timetable_selected"
            else:
                return self.async_create_entry(data={CONF_TIMETABLES: user_input[CONF_TIMETABLES]})
        valid = {o["value"] for o in _timetable_options(self.hass)}
        return self.async_show_form(
            step_id="timetables",
            data_schema=_timetables_schema(self.hass, [t for t in current if t in valid]),
            errors=errors,
        )


class TimetableOptionsFlow(OptionsFlow):
    """Edit a timetable: settings, time grid, subjects and lessons."""

    def __init__(self) -> None:
        self._opts: dict[str, Any] | None = None
        self._edit_idx: int | None = None

    @property
    def opts(self) -> dict[str, Any]:
        if self._opts is None:
            self._opts = deepcopy(dict(self.config_entry.options))
            self._sort_all(self._opts)
        return self._opts

    @staticmethod
    def _sort_all(opts: dict[str, Any]) -> None:
        """Keep lists ordered: periods by start time, subjects by name, lessons by day and time."""
        opts[CONF_PERIODS].sort(key=lambda p: (p[CONF_PERIOD_START], p[CONF_PERIOD_NAME]))
        opts[CONF_SUBJECTS].sort(key=lambda s: s[CONF_SUBJECT_NAME].casefold())
        starts = {p[CONF_PERIOD_NAME]: p[CONF_PERIOD_START] for p in opts[CONF_PERIODS]}
        opts[CONF_LESSONS].sort(
            key=lambda x: (
                x[CONF_WEEKDAY],
                starts.get(x[CONF_PERIOD], "99:99"),
                x[CONF_SUBJECT].casefold(),
            )
        )

    def _weekday_labels(self) -> list[str]:
        if self.hass.config.language.startswith("de"):
            return WEEKDAY_LABELS_DE
        return WEEKDAY_LABELS

    # -- menus: top level and one sub menu per topic ----------------------
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["settings", "periods", "subjects", "lessons", "save"]
        )

    async def async_step_periods(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="periods",
            menu_options=[
                "add_period",
                "edit_period",
                "remove_period",
                "export_periods",
                "import_periods",
                "back",
            ],
            description_placeholders={"overview": self._overview(self._period_lines())},
        )

    async def async_step_subjects(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="subjects",
            menu_options=["add_subject", "edit_subject", "remove_subject", "back"],
            description_placeholders={"overview": self._overview(self._subject_lines())},
        )

    async def async_step_lessons(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="lessons",
            menu_options=["add_lesson", "edit_lesson", "remove_lesson", "back"],
            description_placeholders={
                "overview": self._overview([o["label"] for o in self._lesson_options()])
            },
        )

    async def async_step_back(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self.async_step_init()

    @staticmethod
    def _overview(lines: list[str]) -> str:
        return "\n".join(f"- {line}" for line in lines) if lines else "-"

    def _period_lines(self) -> list[str]:
        return [
            f"{p[CONF_PERIOD_NAME]}: {p[CONF_PERIOD_START]}-{p[CONF_PERIOD_END]}"
            for p in self.opts[CONF_PERIODS]
        ]

    def _subject_lines(self) -> list[str]:
        return [
            f"{s[CONF_SUBJECT_NAME]} ({s[CONF_TEACHER]})" if s.get(CONF_TEACHER) else s[CONF_SUBJECT_NAME]
            for s in self.opts[CONF_SUBJECTS]
        ]

    def _commit(self) -> None:
        """Store the current state right away (closing the dialog loses nothing)."""
        self._sort_all(self.opts)
        self.hass.config_entries.async_update_entry(
            self.config_entry, options=deepcopy(self.opts)
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
                self._commit()
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
        self._edit_idx = None
        return await self._period_form("add_period", user_input)

    async def async_step_edit_period(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            if "item" not in user_input:
                return await self.async_step_periods()
            self._edit_idx = int(user_input["item"])
            return await self.async_step_edit_period_form()
        options = [
            SelectOptionDict(value=str(i), label=line) for i, line in enumerate(self._period_lines())
        ]
        return self._show_pick("edit_period", options)

    async def async_step_edit_period_form(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._period_form("edit_period_form", user_input)

    async def _period_form(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Add a period, or edit the one at self._edit_idx (renames follow into lessons)."""
        idx = self._edit_idx
        periods = self.opts[CONF_PERIODS]
        current = periods[idx] if idx is not None else {}
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_PERIOD_NAME].strip()
            start, end = _hhmm(user_input[CONF_PERIOD_START]), _hhmm(user_input[CONF_PERIOD_END])
            if any(p[CONF_PERIOD_NAME] == name for i, p in enumerate(periods) if i != idx):
                errors["base"] = "duplicate_name"
            elif parse_time(end) <= parse_time(start):
                errors["base"] = "end_before_start_time"
            else:
                new = {CONF_PERIOD_NAME: name, CONF_PERIOD_START: start, CONF_PERIOD_END: end}
                if idx is None:
                    periods.append(new)
                else:
                    old_name = periods[idx][CONF_PERIOD_NAME]
                    periods[idx] = new
                    for lesson in self.opts[CONF_LESSONS]:
                        if lesson[CONF_PERIOD] == old_name:
                            lesson[CONF_PERIOD] = name
                        if lesson.get(CONF_END_PERIOD) == old_name:
                            lesson[CONF_END_PERIOD] = name
                periods.sort(key=lambda p: p[CONF_PERIOD_START])
                self._commit()
                self._edit_idx = None
                return await self.async_step_periods()

        def _time_default(key: str) -> Any:
            return f"{current[key]}:00" if key in current else vol.UNDEFINED

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PERIOD_NAME, default=current.get(CONF_PERIOD_NAME, vol.UNDEFINED)
                    ): _text(),
                    vol.Required(CONF_PERIOD_START, default=_time_default(CONF_PERIOD_START)): TimeSelector(),
                    vol.Required(CONF_PERIOD_END, default=_time_default(CONF_PERIOD_END)): TimeSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_remove_period(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            gone = set(user_input.get("items", []))
            self.opts[CONF_PERIODS] = [
                p for p in self.opts[CONF_PERIODS] if p[CONF_PERIOD_NAME] not in gone
            ]
            # lessons that used a removed period are dropped
            self.opts[CONF_LESSONS] = [
                item
                for item in self.opts[CONF_LESSONS]
                if item[CONF_PERIOD] not in gone and item.get(CONF_END_PERIOD) not in gone
            ]
            self._commit()
            return await self.async_step_periods()
        options = [
            SelectOptionDict(value=p[CONF_PERIOD_NAME], label=line)
            for p, line in zip(self.opts[CONF_PERIODS], self._period_lines())
        ]
        return self._show_remove("remove_period", options)

    # -- subjects (+ teacher) ---------------------------------------------
    async def async_step_add_subject(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._edit_idx = None
        return await self._subject_form("add_subject", user_input)

    async def async_step_edit_subject(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            if "item" not in user_input:
                return await self.async_step_subjects()
            self._edit_idx = int(user_input["item"])
            return await self.async_step_edit_subject_form()
        options = [
            SelectOptionDict(
                value=str(i),
                label=f"{s[CONF_SUBJECT_NAME]} ({s.get(CONF_TEACHER) or '-'})",
            )
            for i, s in enumerate(self.opts[CONF_SUBJECTS])
        ]
        return self._show_pick("edit_subject", options)

    async def async_step_edit_subject_form(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._subject_form("edit_subject_form", user_input)

    async def _subject_form(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Add a subject, or edit the one at self._edit_idx (renames follow into lessons)."""
        idx = self._edit_idx
        subjects = self.opts[CONF_SUBJECTS]
        current = subjects[idx] if idx is not None else {}
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_SUBJECT_NAME].strip()
            teacher = user_input.get(CONF_TEACHER, "").strip()
            if any(s[CONF_SUBJECT_NAME] == name for i, s in enumerate(subjects) if i != idx):
                errors["base"] = "duplicate_name"
            else:
                new = {CONF_SUBJECT_NAME: name, CONF_TEACHER: teacher}
                if idx is None:
                    subjects.append(new)
                else:
                    old_name = subjects[idx][CONF_SUBJECT_NAME]
                    subjects[idx] = new
                    for lesson in self.opts[CONF_LESSONS]:
                        if lesson[CONF_SUBJECT] == old_name:
                            lesson[CONF_SUBJECT] = name
                self._commit()
                self._edit_idx = None
                return await self.async_step_subjects()
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SUBJECT_NAME, default=current.get(CONF_SUBJECT_NAME, vol.UNDEFINED)
                    ): _text(),
                    vol.Optional(
                        CONF_TEACHER, description=_suggest(current.get(CONF_TEACHER))
                    ): _text(),
                }
            ),
            errors=errors,
        )

    async def async_step_remove_subject(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            gone = set(user_input.get("items", []))
            self.opts[CONF_SUBJECTS] = [
                s for s in self.opts[CONF_SUBJECTS] if s[CONF_SUBJECT_NAME] not in gone
            ]
            self.opts[CONF_LESSONS] = [
                item for item in self.opts[CONF_LESSONS] if item[CONF_SUBJECT] not in gone
            ]
            self._commit()
            return await self.async_step_subjects()
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
        self._edit_idx = None
        return await self._lesson_form("add_lesson", user_input)

    async def async_step_edit_lesson(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            if "item" not in user_input:
                return await self.async_step_lessons()
            self._edit_idx = int(user_input["item"])
            return await self.async_step_edit_lesson_form()
        return self._show_pick("edit_lesson", self._lesson_options())

    async def async_step_edit_lesson_form(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._lesson_form("edit_lesson_form", user_input)

    async def _lesson_form(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Add a lesson, or edit the one at self._edit_idx."""
        if not self.opts[CONF_SUBJECTS] or not self.opts[CONF_PERIODS]:
            if user_input is not None:
                return await self.async_step_lessons()
            return self.async_show_form(
                step_id=step_id,
                data_schema=vol.Schema({}),
                errors={"base": "need_subjects_and_periods"},
            )
        idx = self._edit_idx
        lessons = self.opts[CONF_LESSONS]
        current = lessons[idx] if idx is not None else {}
        errors: dict[str, str] = {}
        if user_input is not None:
            weeks = user_input.get(CONF_WEEKS, "").strip()
            end_period = user_input.get(CONF_END_PERIOD) or ""
            starts = {p[CONF_PERIOD_NAME]: p[CONF_PERIOD_START] for p in self.opts[CONF_PERIODS]}
            try:
                parse_weeks(weeks)
            except ValueError:
                errors[CONF_WEEKS] = "invalid_weeks"
            if end_period and starts[end_period] <= starts[user_input[CONF_PERIOD]]:
                errors[CONF_END_PERIOD] = "end_period_before_start"
            if not errors:
                lesson = {
                    CONF_SUBJECT: user_input[CONF_SUBJECT],
                    CONF_WEEKDAY: int(user_input[CONF_WEEKDAY]),
                    CONF_PERIOD: user_input[CONF_PERIOD],
                    CONF_END_PERIOD: end_period,
                    CONF_LOCATION: user_input.get(CONF_LOCATION, "").strip(),
                    CONF_DESCRIPTION: user_input.get(CONF_DESCRIPTION, "").strip(),
                    CONF_WEEKS: weeks or "all",
                }
                if idx is None:
                    lessons.append(lesson)
                else:
                    lessons[idx] = lesson
                self._commit()
                self._edit_idx = None
                return await self.async_step_lessons()
        period_options = [
            SelectOptionDict(
                value=p[CONF_PERIOD_NAME],
                label=f"{p[CONF_PERIOD_NAME]} ({p[CONF_PERIOD_START]}-{p[CONF_PERIOD_END]})",
            )
            for p in self.opts[CONF_PERIODS]
        ]
        end_options = [
            SelectOptionDict(
                value=p[CONF_PERIOD_NAME], label=f"{p[CONF_PERIOD_NAME]} (-{p[CONF_PERIOD_END]})"
            )
            for p in self.opts[CONF_PERIODS]
        ]
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SUBJECT, default=current.get(CONF_SUBJECT, vol.UNDEFINED)): _select(
                        [SelectOptionDict(value=s[CONF_SUBJECT_NAME], label=s[CONF_SUBJECT_NAME])
                         for s in self.opts[CONF_SUBJECTS]]
                    ),
                    vol.Required(CONF_WEEKDAY, default=str(current.get(CONF_WEEKDAY, 0))): SelectSelector(
                        SelectSelectorConfig(
                            options=[str(i) for i in range(len(WEEKDAYS))],
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key="weekday",
                        )
                    ),
                    vol.Required(CONF_PERIOD, default=current.get(CONF_PERIOD, vol.UNDEFINED)): _select(
                        period_options
                    ),
                    vol.Optional(
                        CONF_END_PERIOD, description=_suggest(current.get(CONF_END_PERIOD))
                    ): _select(end_options),
                    vol.Optional(
                        CONF_LOCATION, description=_suggest(current.get(CONF_LOCATION))
                    ): _text(),
                    vol.Optional(
                        CONF_DESCRIPTION, description=_suggest(current.get(CONF_DESCRIPTION))
                    ): _text(multiline=True),
                    vol.Optional(CONF_WEEKS, default=current.get(CONF_WEEKS, "all")): _text(),
                }
            ),
            errors=errors,
        )

    def _lesson_options(self) -> list[SelectOptionDict]:
        """Lessons as picker options (value = index), sorted by weekday and period."""
        lessons = self.opts[CONF_LESSONS]
        return [
            SelectOptionDict(
                value=str(i),
                label=(
                    f"{self._weekday_labels()[x[CONF_WEEKDAY]]} {x[CONF_PERIOD]}"
                    + (f"-{x[CONF_END_PERIOD]}" if x.get(CONF_END_PERIOD) else "")
                    + f": {x[CONF_SUBJECT]}"
                    + (f" [{x[CONF_WEEKS]}]" if x.get(CONF_WEEKS, "all") != "all" else "")
                ),
            )
            for i, x in enumerate(lessons)  # stored sorted by weekday and start time
        ]

    async def async_step_remove_lesson(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        lessons = self.opts[CONF_LESSONS]
        if user_input is not None:
            gone = {int(i) for i in user_input.get("items", [])}
            self.opts[CONF_LESSONS] = [x for i, x in enumerate(lessons) if i not in gone]
            self._commit()
            return await self.async_step_lessons()
        return self._show_remove("remove_lesson", self._lesson_options())

    # -- export / import the time grid ------------------------------------
    async def async_step_export_periods(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the time grid as text to copy into other timetables."""
        if user_input is not None:
            return await self.async_step_periods()
        return self.async_show_form(
            step_id="export_periods",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "periods",
                        description={"suggested_value": format_periods(self.opts[CONF_PERIODS])},
                    ): _text(multiline=True)
                }
            ),
        )

    async def async_step_import_periods(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace the time grid with another timetable's grid or pasted text."""
        errors: dict[str, str] = {}
        others = _timetable_options(self.hass, exclude=self.config_entry.entry_id)
        if user_input is not None:
            periods = None
            if source_id := user_input.get("source"):
                source = self.hass.config_entries.async_get_entry(source_id)
                periods = deepcopy(source.options.get(CONF_PERIODS, [])) if source else []
                if not periods:
                    errors["base"] = "invalid_periods"
            elif text := user_input.get("periods", "").strip():
                try:
                    periods = parse_periods(text)
                except ValueError:
                    errors["periods"] = "invalid_periods"
            else:
                errors["base"] = "no_import_source"
            if not errors and periods is not None:
                names = {p[CONF_PERIOD_NAME] for p in periods}
                self.opts[CONF_PERIODS] = periods
                # lessons whose periods no longer exist cannot be shown
                self.opts[CONF_LESSONS] = [
                    x
                    for x in self.opts[CONF_LESSONS]
                    if x[CONF_PERIOD] in names
                    and (not x.get(CONF_END_PERIOD) or x[CONF_END_PERIOD] in names)
                ]
                self._commit()
                return await self.async_step_periods()
        schema: dict[Any, Any] = {}
        if others:
            schema[vol.Optional("source")] = _select(others)
        schema[vol.Optional("periods")] = _text(multiline=True)
        return self.async_show_form(
            step_id="import_periods", data_schema=vol.Schema(schema), errors=errors
        )

    def _show_pick(self, step_id: str, options: list[SelectOptionDict]) -> ConfigFlowResult:
        if not options:
            return self.async_show_form(
                step_id=step_id, data_schema=vol.Schema({}), errors={"base": "nothing_to_edit"}
            )
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({vol.Required("item"): _select(options)}),
        )

    def _show_remove(self, step_id: str, options: list[SelectOptionDict]) -> ConfigFlowResult:
        if not options:
            return self.async_show_form(
                step_id=step_id, data_schema=vol.Schema({}), errors={"base": "nothing_to_remove"}
            )
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({vol.Required("items", default=[]): _select(options, multiple=True)}),
        )
