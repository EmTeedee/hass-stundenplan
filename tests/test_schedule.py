"""Tests for the pure scheduling logic (run: python -m pytest tests)."""
import importlib.util
import pathlib
import sys
from datetime import date

import pytest

_path = pathlib.Path(__file__).parent.parent / "custom_components" / "stundenplan" / "schedule.py"
_spec = importlib.util.spec_from_file_location("schedule", _path)
schedule = importlib.util.module_from_spec(_spec)
sys.modules["schedule"] = schedule
_spec.loader.exec_module(schedule)

OPTS = {
    "start_date": "2026-09-01",
    "end_date": "2027-07-31",
    "periods": [
        {"name": "1", "start": "08:00", "end": "08:45"},
        {"name": "2", "start": "08:50", "end": "09:35"},
    ],
    "subjects": [{"name": "Math", "teacher": "Mr X"}, {"name": "Art", "teacher": ""}],
    "lessons": [
        {"subject": "Math", "weekday": 0, "period": "1", "location": "R1", "weeks": "all"},
        {"subject": "Art", "weekday": 0, "period": "2", "weeks": "odd"},
        {"subject": "Math", "weekday": 1, "period": "1", "weeks": "37-38"},
    ],
}


def tt():
    return schedule.Timetable.from_options("Anna", OPTS)


def test_weeks():
    assert schedule.week_matches("", 5)
    assert schedule.week_matches("odd", 5) and not schedule.week_matches("odd", 6)
    assert schedule.week_matches("1-3, 10", 10) and not schedule.week_matches("1-3, 10", 4)
    assert schedule.week_matches("50-2", 52) and schedule.week_matches("50-2", 1)
    with pytest.raises(ValueError):
        schedule.parse_weeks("abc")
    with pytest.raises(ValueError):
        schedule.parse_weeks("0-3")


def test_build_events_weeks_and_range():
    # Mon 2026-09-07 is ISO week 37 (odd): both Monday lessons; Tue week 37 matches
    ev = schedule.build_events(tt(), date(2026, 9, 7), date(2026, 9, 8))
    assert [(e.subject, e.start.hour) for e in ev] == [("Math", 8), ("Art", 8), ("Math", 8)]
    assert ev[0].teacher == "Mr X" and ev[0].location == "R1"
    # Week 38 (even): no Art
    ev = schedule.build_events(tt(), date(2026, 9, 14), date(2026, 9, 14))
    assert [e.subject for e in ev] == ["Math"]
    # outside active range
    assert schedule.build_events(tt(), date(2026, 8, 3), date(2026, 8, 31)) == []


def test_holidays_hide_lessons():
    ev = schedule.build_events(tt(), date(2026, 9, 7), date(2026, 9, 7), holidays={date(2026, 9, 7)})
    assert ev == []


def test_holiday_dates_from_events():
    days = schedule.holiday_dates_from_events(
        [
            {"start": "2026-10-05", "end": "2026-10-08"},  # all-day, end exclusive
            {"start": "2026-12-24T00:00:00+01:00", "end": "2026-12-26T00:00:00+01:00"},
        ]
    )
    assert days == {date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7),
                    date(2026, 12, 24), date(2026, 12, 25)}


def test_multi_period_lesson_is_one_event():
    opts = {**OPTS, "lessons": [{"subject": "Math", "weekday": 0, "period": "1", "end_period": "2"}]}
    ev = schedule.build_events(schedule.Timetable.from_options("Anna", opts), date(2026, 9, 7), date(2026, 9, 7))
    assert len(ev) == 1
    assert (ev[0].start.hour, ev[0].start.minute) == (8, 0)
    assert (ev[0].end.hour, ev[0].end.minute) == (9, 35)


def test_periods_export_import_roundtrip():
    text = schedule.format_periods(OPTS["periods"])
    assert text == "1 | 08:00-08:45\n2 | 08:50-09:35"
    assert schedule.parse_periods(text) == OPTS["periods"]
    assert schedule.parse_periods("1. Stunde|8:00 - 8:45")[0]["start"] == "08:00"
    for bad in ("", "x", "1 | 09:00-08:00", "a | 08:00-09:00\na | 09:00-10:00"):
        with pytest.raises(ValueError):
            schedule.parse_periods(bad)
