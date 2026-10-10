# Stundenplan – school timetables as Home Assistant calendars

[![Tests](https://github.com/EmTeedee/hass-stundenplan/actions/workflows/tests.yml/badge.svg)](https://github.com/EmTeedee/hass-stundenplan/actions/workflows/tests.yml)
[![Hassfest](https://github.com/EmTeedee/hass-stundenplan/actions/workflows/hassfest.yml/badge.svg)](https://github.com/EmTeedee/hass-stundenplan/actions/workflows/hassfest.yml)
[![HACS validation](https://github.com/EmTeedee/hass-stundenplan/actions/workflows/hacs.yml/badge.svg)](https://github.com/EmTeedee/hass-stundenplan/actions/workflows/hacs.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

Custom integration (HACS-compatible). Requires a recent Home Assistant (2026.8 or newer).

## Installation

### Option A: HACS (custom repository)

1. In Home Assistant open **HACS → ⋮ (top right) → Custom repositories**.
2. Add the URL of this GitHub repository, category **Integration**.
3. Search for **Stundenplan** in HACS, click **Download** (a published release is needed;
   otherwise HACS downloads the default branch).
4. **Restart Home Assistant** (*Settings → System → Restart*).

### Option B: Manual

1. Download the repository (or the `stundenplan.zip` from a release).
2. Copy the folder `custom_components/stundenplan` into your Home Assistant config
   directory, so you get `<config>/custom_components/stundenplan/manifest.json`.
   (With a release zip: extract it *into* `<config>/custom_components/stundenplan/`.)
   The config directory is the one containing `configuration.yaml`; with the
   Samba/SSH/File editor add-ons it is `/config`.
3. **Restart Home Assistant.**

### Add the integration

1. *Settings → Devices & services → Add integration* → search **Stundenplan**.
2. Choose **Timetable**, enter a name and the active date range (and optionally a holiday
   calendar), then submit.
3. Open the new timetable entry and click **Configure** to define time grid, subjects and
   lessons (see below). Remember to choose **Save & close**.
4. Add the integration again, choose **Calendar**, name it and select the timetable(s) it
   should show. The calendar entity then appears under *Calendar* in the sidebar and can be
   used in dashboards and automations.

For a holiday calendar, install any integration that provides one first (for example
*Schulferien*/*Holiday* integrations or a school calendar via CalDAV/iCal) and select its
`calendar.*` entity in the timetable settings.

## Concepts (n:m)

* **Timetable** – the data: active date range, time grid, subjects with teachers, lessons,
  optional holiday calendar. Creates no entity by itself.
* **Calendar** – a named `calendar.*` entity that shows one **or more** timetables.
  A timetable can be used by any number of calendars (e.g. "Anna" = Anna's timetable,
  "Family" = Anna's + Ben's; with several timetables the timetable name is added to the event description).

Add both via *Settings → Devices & services → Add integration → Stundenplan*.
Edit with **Configure** (timetable: menu; calendar: choose timetables). Editing a timetable
reloads all calendars that use it.

## Timetable setup (Configure on a timetable)

The configuration is a two-level menu: **Date range & holiday calendar**, **Periods**,
**Subjects**, **Lessons** and **Done**. Each of Periods / Subjects / Lessons opens a sub menu
that lists what is defined so far and offers *Add*, *Edit*, *Remove* and *Back*.

* **Date range & holiday calendar** – lessons only exist inside the range. Any HA calendar
  entity can be the holiday calendar (e.g. school holidays/public holidays integration):
  on every day it has an event, no lessons are shown.
* **Periods** (time grid, common to all days) – named slots such as `1st lesson 08:00–08:45`,
  listed by start time. Renaming a period updates the lessons that use it. *Export time grid*
  shows the grid as text (one `Name | HH:MM-HH:MM` line per period); *Import time grid* in
  another timetable copies it (pick a timetable or paste the text). Importing replaces the
  grid and drops lessons whose periods vanish.
* **Subjects** – subject with its teacher, listed alphabetically. Renaming a subject updates
  its lessons.
* **Lessons** – subject + weekday + period, optional location and description, and **weeks**,
  listed by weekday and start time:
  * empty / `all` – every week
  * `odd` / `even` – parity of the ISO calendar week number
  * week numbers/ranges: `1-10, 15, 40-52` (a range like `45-5` wraps over new year)

  A lesson can span several periods (double lesson): choose the first period and the
  **last period**. It shows as **one** event from the start of the first to the end of the last.
  *Edit lesson* changes any field, e.g. moves a misentered lesson from Monday to Tuesday.

Every change is stored immediately; **Done** just closes the dialog. Removing a period or
subject also removes the lessons that use it.

## Entities per calendar

Each calendar creates a device with:

| Entity | Content |
|---|---|
| `calendar.<name>` | all lessons (state `on` during a lesson; next/current lesson as attributes) |
| `sensor.<name>_today` | state = number of lessons today |
| `sensor.<name>_tomorrow` | state = number of lessons tomorrow |

The sensors have attributes `date`, `subjects` (unique, in time order), `first_start`,
`last_end` and `lessons` (a list with `subject`, `teacher`, `location`, `description`,
`timetable`, `start`, `end`). Holidays are respected, so on a holiday the sensors show 0.

### Automation examples

Morning announcement when a subject is on today's timetable:

```yaml
automation:
  - alias: "Helena - bring PE bag"
    trigger:
      - platform: time
        at: "07:00:00"
    condition:
      - condition: template
        value_template: >
          {{ 'Sport' in state_attr('sensor.helena_today', 'subjects') }}
    action:
      - service: tts.speak
        target:
          entity_id: tts.home_assistant_cloud
        data:
          media_player_entity_id: media_player.kitchen
          message: "Helena, Sportbeutel nicht vergessen!"
```

Evening reminder for tomorrow: same, with `sensor.helena_tomorrow` and e.g. `at: "19:00:00"`.

Alternatively react to the lesson itself with HA's calendar trigger (here 30 minutes
before every lesson with the title `Sport`):

```yaml
trigger:
  - platform: calendar
    event: start
    offset: "-0:30:0"
    entity_id: calendar.helena
condition:
  - condition: template
    value_template: "{{ trigger.calendar_event.summary == 'Sport' }}"
```

## Blueprint: calendar reminder

`blueprints/automation/stundenplan/calendar_reminder.yaml` is an automation blueprint that
works with **any** calendar entity (these calendars, WebUntis, iCal, ...). Copy it to
`<config>/blueprints/automation/stundenplan/` (HACS does not install blueprints).

It looks at today or tomorrow, and for each rule (`calendar`, `match` regex, `text`) that
finds a matching event it adds an entry to a list. The entries are joined into a message
(`Einpacken: {items}`) and your actions run, e.g. a phone notification and a TTS
announcement using `{{ message }}`. If no rule matches, nothing happens.

## Use with the Timetable Card

The calendars work well with [Timetable Card](https://github.com/KingDando8430/HA-Timetable-Card)
(install it via HACS). Event title = subject, location = room, description = teacher
(+ your description, and the timetable name if a calendar combines several timetables), so
the card's `show_location`, `show_notes` and keyword rules work out of the box.

Tip: create **one calendar per child** (plus an optional combined one) and give each its own
colour in the card:

```yaml
type: custom:timetable-card
title: Timetable
entities:
  - id: calendar.anna
    color: "#03a9f4"
  - id: calendar.ben
    color: "#4CAF50"
weekdays: [Mon, Tue, Wed, Thu, Fri]
show_location: true
show_notes: true
time_range:
  start: "07:45"
  end: "16:00"
keywords:
  - keyword: Math
    color: "#1f76f7"
    exact_match: true
    color_mode: border
```

Lessons are separate events per period, so the card's `event_based` time grid shows your
school's real bell times.

## Notes

* Holiday events are treated as whole days, whatever their time.
* Teacher and description go into the event description, location into the location field.

## Tests

`python -m pytest tests` (covers the pure logic in `schedule.py`).

## License & contributing

MIT licensed, see [LICENSE](LICENSE). Contributors sign the MIT contributor agreement once
(a comment on their first pull request), see [CONTRIBUTING.md](CONTRIBUTING.md).
