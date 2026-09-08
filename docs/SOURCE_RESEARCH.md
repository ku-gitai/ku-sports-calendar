# Source Research — KU Football

Research date: **2026-09-07**

## Decision

Use KU Athletics itself as the source of truth through its current SIDEARM-backed, server-rendered pages:

1. `https://kuathletics.com/sports/football/schedule/text` — primary schedule rows: date, time, home/away/neutral, opponent, location, tournament/result.
2. `https://kuathletics.com/sports/football/schedule/` — source-native Game Center links and IDs.
3. `https://kuathletics.com/game-center/<id>` — TV network and watch/stream link when KU displays them.
4. KU's official current schedule PDF — initial venue-name cross-check/seed only, not an automated dependency.

No stable, documented public JSON API was identified during inspection of the current KU site. The `/schedule/text` route is preferred over scraping visual cards because its table has explicit semantic columns and much less presentation markup.

## Why this source

- Official KU Athletics data remains the source of truth.
- The text route is simple and deterministic to parse.
- Game Center IDs are stable source-native identifiers and make strong ICS UID inputs.
- Per-game Game Center pages expose current TV data for upcoming games.
- It avoids dependence on an unofficial schedule provider when KU already exposes the needed information.

## Current 2026 data cross-check

At research time the live KU schedule contained 12 games. The published early-season media assignments were:

- LIU — September 4 — 7 p.m. CT — ESPNU (official KU announcement/current schedule PDF; the completed Game Center no longer displays the network)
- Missouri — September 11 — 7 p.m. CT — FOX
- Arizona State — September 19 — 11 a.m. CT — FS1

The remaining games were TBA at research time.

The initial `data/initial-football-2026.json` records the researched snapshot used to bootstrap `docs/ku-football.ics`.

## Venue handling

The text schedule provides city/location, but not a reliable stadium field. The current official KU schedule PDF was used to seed 2026 venue names in `config/football.json` keyed by Game Center ID.

A venue override is only applied if the live KU city/location still matches the configured expected location. This prevents an obviously moved game from retaining an old stadium, but a venue change within the same city would require updating the config or adding a better official structured venue source later.

## TV and streaming handling

The parser scopes network recognition to the Game Center's game-information area so a generic ESPN+ navigation link elsewhere on KU's site does not become a false TV assignment. Known labels such as FOX, FS1, ESPN/ESPN2/ESPNU/ESPN+, ABC, CBS, NBC, CBSSN, BTN, TNT/TBS, The CW, and Peacock are recognized.

If KU provides a game-specific Watch/Video/Stream link, the feed stores that link and a streaming label. A failure of one Game Center page does not invalidate the underlying schedule; the game remains in the feed without that optional media field.

For already-completed games, the updater preserves a previously published TV/stream label if KU's Game Center stops displaying it after the final. It does not preserve removed media labels for future games.

## Failure strategy

The updater is fail-closed for the core schedule:

- HTTP requests retry transient 429/5xx/connect/read failures.
- Missing expected schedule columns raises an error.
- Zero games raises an error.
- Football currently refuses publication if fewer than 10 games parse.
- ICS is validated before an atomic file replacement.

This makes a stale feed preferable to a corrupted/empty one during a KU outage or markup break.

## Known source fragility

This remains HTML parsing because no better public structured KU endpoint was identified. SIDEARM can change markup. The parser minimizes that risk by depending on table header names and `/game-center/<id>` links rather than CSS presentation classes.
