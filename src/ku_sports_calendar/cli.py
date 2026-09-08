from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .gameday import is_game_day
from .update import update_calendar
from .validate import validate_file


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ku-sports-calendar")
    sub = parser.add_subparsers(dest="command", required=True)

    p_update = sub.add_parser("update")
    p_update.add_argument("--config", default="config/football.json")

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("path", nargs="?", default="docs/ku-football.ics")

    p_day = sub.add_parser("is-game-day")
    p_day.add_argument("path", nargs="?", default="docs/ku-football.ics")

    args = parser.parse_args(argv)
    if args.command == "update":
        changed, count = update_calendar(args.config)
        print(f"{'updated' if changed else 'unchanged'}: {count} events")
        return 0
    if args.command == "validate":
        result = validate_file(args.path)
        print(f"valid: {result.event_count} events, {len(set(result.uids))} unique UIDs")
        return 0
    if args.command == "is-game-day":
        today = datetime.now(ZoneInfo("America/Chicago")).date()
        yes = is_game_day(args.path)
        print(f"game_day={'true' if yes else 'false'} date={today.isoformat()}")
        return 0 if yes else 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
