# KU Sports Calendar

Personal, auto-updating subscribed calendars for University of Kansas sports. The first implementation is **KU Football (2026)**. The code is intentionally structured so KU men's basketball can be added later with a new config/source-specific adjustments rather than a second calendar engine.

## Current output

- Calendar feed: `docs/ku-football.ics`
- 12 current 2026 KU football games
- Stable event UIDs based on KU's source-native Game Center IDs
- TBA games are all-day placeholders and become timed events under the same UID
- TV/streaming data is read from KU Game Center when KU publishes it
- Times from KU are interpreted as Central Time and emitted as UTC in the ICS
- Home/away/neutral site and venue/city are included

The initial feed was researched and generated on **2026-09-07** from the then-current KU Athletics schedule.

## Data source

Primary official URLs:

- `https://kuathletics.com/sports/football/schedule/`
- `https://kuathletics.com/sports/football/schedule/text`
- Per-game `https://kuathletics.com/game-center/<id>` pages

KU Athletics is powered by SIDEARM. No stable, documented public JSON API was identified during current-site inspection. The implementation therefore uses KU's official server-rendered schedule endpoints, with the text table as the least-fragile schedule representation and the canonical schedule page only to discover Game Center IDs/links. Game Center pages provide TV/streaming details when displayed.

See `docs/SOURCE_RESEARCH.md` for the source decision and limitations.

## Repository layout

```text
config/                         Sport configuration
src/ku_sports_calendar/         Shared calendar/update code
src/ku_sports_calendar/sources/ KU/SIDEARM source adapter
scripts/                        Snapshot/bootstrap utility
tests/                          Automated tests + source-shaped fixtures
docs/                           GitHub Pages content + published ICS
.github/workflows/              Scheduled update workflows
data/                           Researched initial football snapshot
```

## Local use

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -r requirements-dev.txt
PYTHONPATH=src pytest -q
PYTHONPATH=src python -m ku_sports_calendar validate docs/ku-football.ics
PYTHONPATH=src python -m ku_sports_calendar update --config config/football.json
```

The updater writes the calendar atomically only after successful parsing and validation. If KU is unavailable or the parsed schedule is suspiciously short, the existing feed is left untouched.

## Event behavior

### UID and updates

The preferred UID is based on KU's Game Center ID, for example:

`ku-football-2026-20530@ku-sports-calendar.local`

Date, kickoff, TV, location, and other mutable data are deliberately excluded from the UID. A changed game increments ICS `SEQUENCE` while retaining the UID, so a subscriber can update the existing event rather than receiving a duplicate.

### TBA games

A TBA kickoff is represented as an all-day event for the scheduled date. When KU announces a kickoff, the same UID changes to a timed UTC event and `SEQUENCE` increments.

### Time zones

KU's current football schedule labels its displayed times as Central Time, including away and neutral games. The source time is interpreted in `America/Chicago`, including daylight-saving rules, then emitted as UTC. This avoids depending on the iPhone's current time zone and correctly handles the London neutral-site game from KU's Central-time listing.

### Event title

Default: `Kansas vs. Missouri` / `Kansas at Utah`.

TV/streaming belongs in the description by default. This keeps iPhone Calendar list/month displays scannable and prevents network changes from cluttering the event title. Set `include_network_in_title` to `true` in a sport config if a more visible network label is preferred.

## Automation

Two GitHub Actions workflows are prepared:

- `update-football.yml`: Tuesday and Thursday source checks.
- `football-gameday.yml`: runs every morning but exits without a source update unless the existing feed says KU plays that Central-Time date.

GitHub cron uses UTC. The chosen morning times are 14:17/14:23 UTC, which are 9:17/9:23 a.m. CDT and 8:17/8:23 a.m. CST. Exact local wall-clock time shifts by one hour after daylight-saving time ends, but remains a Central-time morning check without maintaining duplicated seasonal cron rules.

Only a changed, validated `docs/ku-football.ics` is committed. The automation is intentionally split into two jobs: source parsing and Python dependencies run with a read-only repository token; only a small second job can write, and that job runs no project code or PyPI packages. GitHub Actions are pinned to immutable full commit SHAs and runtime Python dependencies are version-pinned.

## Security model

This project needs no personal API keys, passwords, SSH keys, or personal access tokens. Scheduled workflows use GitHub's short-lived repository-scoped `GITHUB_TOKEN`. Keep the repository's default workflow permission **read-only**; the workflow files explicitly grant `contents: write` only to the isolated job that commits the already-validated calendar file.

The repository also includes credential/private-key patterns in `.gitignore`, full-SHA pins for GitHub Actions, exact runtime dependency versions, and Dependabot configuration for reviewed dependency updates. See `SECURITY.md`.

## GitHub Pages target

After personal GitHub setup, configure Pages to deploy from the repository's `main` branch and `/docs` folder. The expected subscription URL will be:

`https://<USERNAME>.github.io/<REPOSITORY>/ku-football.ics`

Use that HTTPS URL as an **iPhone Subscribed Calendar**, not as a one-time imported file.

Deployment is deliberately not performed yet because it requires the owner's personal GitHub account and iPhone.

## Tests

Run:

```bash
PYTHONPATH=src pytest -q
```

Coverage includes current schedule-shape parsing, Game Center IDs, network/streaming extraction, stable UIDs, duplicate rejection, TBA-to-timed updates, Central-to-UTC conversion, neutral-site behavior, unchanged-feed byte stability, schedule-change sequencing, source-failure preservation, malformed source handling, game-day gating, and validation of the checked-in 12-event feed.

See `docs/TESTING.md` for what has and has not been tested.

## Future phases

- KU men's basketball feed (`ku-basketball.ics`) using the same calendar/update engine. Cross-year season date handling is already supported through `season_start_month`.
- A basketball-appropriate, probably more frequent, update schedule.
- A separate short pregame briefing feature for injuries, matchups, projections, media/fan sentiment, and late news. It is intentionally not coupled to calendar generation.

No employer/business website, domain, GitHub account, hosting, server, or other work infrastructure is required or intended.
