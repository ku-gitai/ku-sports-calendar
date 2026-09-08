# Testing Status

Research/build date: **2026-09-07**

## Successfully tested locally

Automated suite currently passes **17 tests**.

Validated behaviors include:

- Current KU text-schedule table shape parses to 12 football games.
- Current-style Game Center links attach the expected source IDs.
- TV parsing recognizes FOX and `ESPN+` without mistaking KU's generic site navigation for a game assignment.
- Missing required source fields fail instead of silently publishing bad data.
- Cross-year season date logic is ready for a later basketball config.
- UIDs stay stable when date/time/network/location changes.
- Timed games convert from `America/Chicago` to UTC correctly.
- Neutral/away games use KU's published Central-time clock value rather than incorrectly treating it as venue-local time.
- TBA all-day events convert to timed events under the same UID with incremented `SEQUENCE`.
- An unchanged regeneration is byte-for-byte unchanged.
- Duplicate UIDs are rejected.
- Source failure does not overwrite an existing feed.
- A schedule/media change updates one existing event rather than creating a duplicate.
- Game-day gating uses the Central calendar date.
- Checked-in `docs/ku-football.ics` validates with 12 events and 12 unique UIDs.
- Physical ICS lines are at most 75 octets and the file uses RFC-style CRLF endings.

The current KU schedule and early TV assignments were independently cross-checked through live web access during development. The execution sandbox itself cannot resolve external DNS, so the Python HTTP client could not be end-to-end integration-tested directly against `kuathletics.com` from the local runtime.

## Cannot test until GitHub deployment / iPhone setup

- GitHub Actions actually running on GitHub's hosted runners.
- Repository write permissions for the Actions bot.
- GitHub Pages serving the `.ics` file at the final public HTTPS URL.
- Apple/iPhone subscription acceptance and display details.
- Apple's refresh/cache interval in real use.
- A controlled production update propagating from KU/GitHub Pages to an already-subscribed iPhone event.

## Validation command

```bash
PYTHONPATH=src pytest -q
PYTHONPATH=src python -m ku_sports_calendar validate docs/ku-football.ics
```
