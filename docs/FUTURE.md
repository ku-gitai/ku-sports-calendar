# Future Work

## KU men's basketball

Add `config/basketball.json` and `docs/ku-basketball.ics` after football is proven in production. Reuse the current Game model, UID logic, ICS generator, validator, updater, publisher layout, and SIDEARM adapter where the basketball site shape permits.

Basketball will probably need more frequent checks (for example daily during season, plus an optional game-day confirmation). Decide the exact cadence from real schedule behavior rather than adding it prematurely.

## Pregame briefing

Do not couple this to the calendar engine.

A later separate feature should create a short pregame rundown covering key injuries/availability, matchups, players to watch, recent form, analytical/game projections, media/analyst sentiment, useful fan/community sentiment, and late-breaking news.

At that phase, evaluate whether ChatGPT automation, GitHub Actions, free sports data APIs, web research, or a small combination is the simplest personal/free implementation. The output should remain a concise briefing rather than a long article.
