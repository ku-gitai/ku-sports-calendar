#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ku_sports_calendar.config import load_config
from ku_sports_calendar.ics import generate_calendar, write_calendar
from ku_sports_calendar.models import Game
from ku_sports_calendar.validate import validate_ics_text


def main() -> int:
    cfg = load_config(ROOT / "config/football.json")
    data = json.loads((ROOT / "data/initial-football-2026.json").read_text(encoding="utf-8"))
    games = []
    for item in data["games"]:
        hhmm = item.get("time")
        start = time.fromisoformat(hhmm) if hhmm else None
        gcid = item["game_center_id"]
        games.append(Game(
            sport=cfg["sport_name"], season=cfg["season"], opponent=item["opponent"],
            date=date.fromisoformat(item["date"]), site=item["site"], location=item["location"],
            venue=item.get("venue", ""), start_time=start, source_timezone=cfg["source_timezone"],
            network=item.get("network", ""), tournament=item.get("tournament", ""), result=item.get("result", ""),
            game_center_id=gcid, game_center_url=f"https://kuathletics.com/game-center/{gcid}",
        ))
    captured = datetime.fromisoformat(data["captured_at"]).astimezone(timezone.utc)
    output = ROOT / cfg["output_path"]
    text = generate_calendar(games, cfg, previous_text="", now=captured)
    validate_ics_text(text)
    write_calendar(output, text)
    print(f"wrote {output}: {len(games)} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
