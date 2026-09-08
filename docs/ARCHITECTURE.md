# Architecture

## Data flow

`KU schedule source -> source adapter -> Game model -> ICS generator/validator -> docs/*.ics -> GitHub Pages -> iPhone subscription`

GitHub Actions invokes the same updater used locally.

## Shared code

`src/ku_sports_calendar/` owns behavior that should be reused by later sports:

- `models.py` — normalized game model.
- `identity.py` — stable UID generation.
- `ics.py` — title/description formatting, TBA/timed events, sequence tracking, RFC 5545 escaping/folding, UTC conversion.
- `validate.py` — syntax/structure, line-length, required-property, and duplicate-UID checks.
- `update.py` — source -> generate -> validate -> atomic publish, plus prior-media preservation for completed games.
- `gameday.py` — Central-date gate for final game-day checks.
- `http.py` — low-frequency retrying HTTP session.
- `sources/` — source-specific adapters selected by `source_type`.

## Sport configuration

`config/football.json` contains football-specific values:

- sport/season identity
- schedule URLs
- output path
- update safety minimum
- default game duration
- source time zone
- optional venue overrides
- title preference

A basketball config can use the same engine. `season_start_month` already handles a season crossing January: a 2026 season with start month 7 maps January 2027 correctly.

## Stable identity

Preferred UID:

`ku-<sport>-<season>-<KU Game Center ID>@ku-sports-calendar.local`

Fallback identity (only if no Game Center ID is obtainable) hashes sport/season/opponent/site; it deliberately excludes date/time/network/location. The Game Center path is preferred because it is less collision-prone.

## Update semantics

Each event stores `X-KU-CONTENT-HASH`. On regeneration:

- unchanged content keeps the same `DTSTAMP`, `LAST-MODIFIED`, and `SEQUENCE`, making the entire feed byte-stable;
- changed content keeps UID, increments `SEQUENCE`, and refreshes modification timestamps;
- deleted source events disappear from the feed on the next successful full publication.

This makes Git commits occur only for meaningful calendar changes.

## TBA -> timed

A TBA kickoff is an all-day `VEVENT` with `X-KU-TIME-STATUS:TBA`. A later announced time turns it into a UTC timed event with `X-KU-TIME-STATUS:CONFIRMED` under the same UID.

## Time zones

KU's football source labels all listed times as Central. The generator treats the schedule clock value as `America/Chicago` and writes `DTSTART`/`DTEND` in UTC (`Z`). Daylight-saving conversion is handled by Python `zoneinfo`.

The event description retains a human-readable `CT` kickoff label because that is how KU publishes the source schedule.

## Publishing

The prepared GitHub Pages design is intentionally simple:

- repository `main` branch contains `docs/ku-football.ics`;
- Actions updates/commits that file only when content changes;
- Pages serves the `/docs` folder over HTTPS;
- iPhone subscribes once to the resulting HTTPS `.ics` URL.

No separate server, database, cloud function, paid sports API, or employer infrastructure is needed.
