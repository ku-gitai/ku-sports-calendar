from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def _unfold(text: str) -> list[str]:
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    for line in raw:
        if line.startswith((" ", "\t")) and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def dates_in_feed(path: str | Path, tz_name: str = "America/Chicago") -> set[date]:
    text = Path(path).read_text(encoding="utf-8")
    dates: set[date] = set()
    for line in _unfold(text):
        if line.startswith("DTSTART;VALUE=DATE:"):
            dates.add(datetime.strptime(line.split(":", 1)[1], "%Y%m%d").date())
        elif line.startswith("DTSTART:") and line.endswith("Z"):
            utc = datetime.strptime(line.split(":", 1)[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=ZoneInfo("UTC"))
            dates.add(utc.astimezone(ZoneInfo(tz_name)).date())
    return dates


def is_game_day(path: str | Path, *, now: datetime | None = None, tz_name: str = "America/Chicago") -> bool:
    now = now or datetime.now(ZoneInfo(tz_name))
    local_day = now.astimezone(ZoneInfo(tz_name)).date()
    return local_day in dates_in_feed(path, tz_name)
