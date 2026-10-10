"""Pure timetable logic (no Home Assistant imports, so it can be unit tested)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from typing import Any, Iterable

ALL_WEEKS = {"", "all", "alle"}
ODD_WEEKS = {"odd", "ungerade"}
EVEN_WEEKS = {"even", "gerade"}
_RANGE_RE = re.compile(r"^(\d{1,2})(?:\s*-\s*(\d{1,2}))?$")


@lru_cache(maxsize=256)
def parse_weeks(spec: str | None) -> str | frozenset[int]:
    """Parse a week specification.

    Accepted: "" / "all", "odd", "even" (ISO calendar week parity) or a list of
    ISO week numbers and ranges such as "1-10, 15, 40-52". A range whose start
    is larger than its end wraps over the new year ("45-5" = 45..53 and 1..5).

    Returns "all", "odd", "even" or a frozenset of week numbers.
    Raises ValueError for invalid input.
    """
    text = (spec or "").strip().lower()
    if text in ALL_WEEKS:
        return "all"
    if text in ODD_WEEKS:
        return "odd"
    if text in EVEN_WEEKS:
        return "even"
    weeks: set[int] = set()
    for part in text.split(","):
        match = _RANGE_RE.match(part.strip())
        if not match:
            raise ValueError(f"Invalid week specification: {part.strip()!r}")
        first = int(match.group(1))
        last = int(match.group(2)) if match.group(2) else first
        if not (1 <= first <= 53 and 1 <= last <= 53):
            raise ValueError("Week numbers must be between 1 and 53")
        if first <= last:
            weeks.update(range(first, last + 1))
        else:
            weeks.update(range(first, 54))
            weeks.update(range(1, last + 1))
    return frozenset(weeks)


def week_matches(spec: str | None, iso_week: int) -> bool:
    """Return True if the lesson takes place in the given ISO week."""
    parsed = parse_weeks(spec)
    if parsed == "all":
        return True
    if parsed == "odd":
        return iso_week % 2 == 1
    if parsed == "even":
        return iso_week % 2 == 0
    return iso_week in parsed


def parse_time(value: str) -> time:
    """Parse "HH:MM" or "HH:MM:SS"."""
    return time.fromisoformat(value)


@dataclass(frozen=True)
class Period:
    """A slot in the daily time grid (1st lesson, 2nd lesson, ...)."""

    name: str
    start: time
    end: time


@dataclass(frozen=True)
class Lesson:
    """A subject placed in a period on a weekday (0 = Monday)."""

    subject: str
    weekday: int
    period: str
    location: str = ""
    description: str = ""
    weeks: str = "all"
    end_period: str = ""  # last period of a multi-period lesson ("" = single period)


@dataclass(frozen=True)
class LessonEvent:
    """A concrete occurrence of a lesson (naive local datetimes)."""

    subject: str
    teacher: str
    period: str
    timetable: str
    start: datetime
    end: datetime
    location: str
    description: str


@dataclass
class Timetable:
    """A complete timetable."""

    name: str
    start_date: date
    end_date: date
    periods: dict[str, Period] = field(default_factory=dict)
    teachers: dict[str, str] = field(default_factory=dict)
    lessons: list[Lesson] = field(default_factory=list)

    @classmethod
    def from_options(cls, name: str, opts: dict[str, Any]) -> Timetable:
        """Build a timetable from the stored config entry options."""
        periods = {
            p["name"]: Period(p["name"], parse_time(p["start"]), parse_time(p["end"]))
            for p in opts.get("periods", [])
        }
        teachers = {s["name"]: s.get("teacher", "") for s in opts.get("subjects", [])}
        lessons = [
            Lesson(
                subject=item["subject"],
                weekday=int(item["weekday"]),
                period=item["period"],
                location=item.get("location", ""),
                description=item.get("description", ""),
                weeks=item.get("weeks", "all"),
                end_period=item.get("end_period", ""),
            )
            for item in opts.get("lessons", [])
        ]
        return cls(
            name=name,
            start_date=date.fromisoformat(opts["start_date"]),
            end_date=date.fromisoformat(opts["end_date"]),
            periods=periods,
            teachers=teachers,
            lessons=lessons,
        )


def build_events(
    timetable: Timetable,
    first: date,
    last: date,
    holidays: Iterable[date] = (),
) -> list[LessonEvent]:
    """Return all lesson events between first and last (inclusive).

    Days outside the timetable's active range and days in ``holidays`` are skipped.
    """
    holiday_set = set(holidays)
    day = max(first, timetable.start_date)
    stop = min(last, timetable.end_date)
    events: list[LessonEvent] = []
    while day <= stop:
        if day not in holiday_set:
            iso_week = day.isocalendar().week
            for lesson in timetable.lessons:
                if lesson.weekday != day.weekday():
                    continue
                period = timetable.periods.get(lesson.period)
                if period is None or not week_matches(lesson.weeks, iso_week):
                    continue
                last_period = timetable.periods.get(lesson.end_period) or period
                if last_period.end <= period.start:
                    last_period = period
                events.append(
                    LessonEvent(
                        subject=lesson.subject,
                        teacher=timetable.teachers.get(lesson.subject, ""),
                        period=period.name,
                        timetable=timetable.name,
                        start=datetime.combine(day, period.start),
                        end=datetime.combine(day, last_period.end),
                        location=lesson.location,
                        description=lesson.description,
                    )
                )
        day += timedelta(days=1)
    events.sort(key=lambda e: (e.start, e.end, e.subject))
    return events


def holiday_dates_from_events(events: Iterable[dict[str, Any]]) -> set[date]:
    """Convert calendar.get_events results into the set of covered dates.

    All-day events have date strings with an exclusive end. Timed events cover
    every date they touch (an end exactly at midnight does not touch that day).
    """
    days: set[date] = set()
    for event in events:
        start_raw, end_raw = str(event["start"]), str(event.get("end") or event["start"])
        if len(start_raw) == 10:  # all-day: YYYY-MM-DD
            start = date.fromisoformat(start_raw)
            end = date.fromisoformat(end_raw[:10])
            last = max(end - timedelta(days=1), start)
        else:
            start_dt = datetime.fromisoformat(start_raw)
            end_dt = datetime.fromisoformat(end_raw)
            start = start_dt.date()
            last = end_dt.date()
            if end_dt.time() == time.min and end_dt > start_dt:
                last -= timedelta(days=1)
        day = start
        while day <= last:
            days.add(day)
            day += timedelta(days=1)
    return days


_PERIOD_LINE_RE = re.compile(r"^(.+?)\s*\|\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})$")


def format_periods(periods: Iterable[dict[str, Any]]) -> str:
    """Time grid as text, one ``Name | HH:MM-HH:MM`` line per period."""
    return "\n".join(f"{p['name']} | {p['start']}-{p['end']}" for p in periods)


def parse_periods(text: str) -> list[dict[str, str]]:
    """Parse the text produced by :func:`format_periods`.

    Raises ValueError for malformed lines, duplicate names or end <= start.
    """
    periods: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = _PERIOD_LINE_RE.match(line.strip())
        if not match:
            raise ValueError(f"Invalid line: {line.strip()!r}")
        name, start, end = match.group(1).strip(), match.group(2), match.group(3)
        start, end = f"{int(start[:-3]):02d}:{start[-2:]}", f"{int(end[:-3]):02d}:{end[-2:]}"
        if parse_time(end) <= parse_time(start):
            raise ValueError(f"End before start: {line.strip()!r}")
        if any(p["name"] == name for p in periods):
            raise ValueError(f"Duplicate period: {name!r}")
        periods.append({"name": name, "start": start, "end": end})
    if not periods:
        raise ValueError("No periods")
    periods.sort(key=lambda p: p["start"])
    return periods
