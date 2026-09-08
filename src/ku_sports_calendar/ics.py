from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .identity import stable_uid
from .models import Game

CRLF = "\r\n"


def escape_text(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def unescape_text(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def fold_line(line: str, limit: int = 75) -> list[str]:
    """RFC 5545 line folding at 75 octets, preserving UTF-8 characters."""
    out: list[str] = []
    current = ""
    current_bytes = 0
    first = True
    for ch in line:
        b = len(ch.encode("utf-8"))
        max_bytes = limit if first else limit - 1  # continuation line gets a leading space
        if current and current_bytes + b > max_bytes:
            out.append(current if first else " " + current)
            first = False
            current = ch
            current_bytes = b
        else:
            current += ch
            current_bytes += b
    if current or not out:
        out.append(current if first else " " + current)
    return out


def _prop(name: str, value: str) -> list[str]:
    return fold_line(f"{name}:{value}")


def _utc_stamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _game_payload(game: Game, cfg: dict) -> dict:
    location = game.location
    if game.venue:
        location = f"{game.venue} — {game.location}" if game.location else game.venue
    return {
        "opponent": game.opponent,
        "date": game.date.isoformat(),
        "time": game.start_time.isoformat(timespec="minutes") if game.start_time else None,
        "site": game.site,
        "location": location,
        "network": game.network,
        "streaming_service": game.streaming_service,
        "streaming_url": game.streaming_url,
        "tournament": game.tournament,
        "result": game.result,
        "game_center_url": game.game_center_url,
        "duration_minutes": int(cfg.get("default_duration_minutes", 240)),
    }


def content_hash(game: Game, cfg: dict) -> str:
    payload = json.dumps(_game_payload(game, cfg), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def title_for(game: Game, cfg: dict) -> str:
    relation = "at" if game.site == "Away" else "vs."
    title = f"{cfg.get('team_name', 'Kansas')} {relation} {game.opponent}"
    if cfg.get("include_network_in_title") and game.network:
        title += f" — {game.network}"
    return title


def description_for(game: Game) -> str:
    lines = [f"KU {game.sport}", f"Site: {game.site}"]
    if game.start_time:
        lines.append(f"Kickoff: {game.start_time.strftime('%-I:%M %p')} CT")
    else:
        lines.append("Kickoff: TBA")
    if game.network:
        lines.append(f"TV: {game.network}")
    if game.streaming_service:
        stream = f"Streaming: {game.streaming_service}"
        if game.streaming_url:
            stream += f" ({game.streaming_url})"
        lines.append(stream)
    if game.tournament:
        lines.append(f"Event: {game.tournament}")
    if game.result:
        lines.append(f"Result: {game.result}")
    if game.game_center_url:
        lines.append(f"KU Game Center: {game.game_center_url}")
    return "\n".join(lines)


def parse_existing_metadata(text: str) -> dict[str, dict[str, str]]:
    if not text:
        return {}
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines: list[str] = []
    for line in raw_lines:
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    events: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current and "UID" in current:
                events[current["UID"]] = current
            current = None
            continue
        if current is None or ":" not in line:
            continue
        left, value = line.split(":", 1)
        key = left.split(";", 1)[0]
        current[key] = value
    return events


def _event_lines(game: Game, cfg: dict, previous: dict[str, str] | None, now: datetime) -> list[str]:
    uid = stable_uid(game, cfg["key"], cfg.get("uid_domain", "ku-sports-calendar.local"))
    new_hash = content_hash(game, cfg)
    unchanged = previous is not None and previous.get("X-KU-CONTENT-HASH") == new_hash
    prev_seq = int(previous.get("SEQUENCE", "0")) if previous else -1
    sequence = prev_seq if unchanged else max(0, prev_seq + 1)
    stamp = previous.get("DTSTAMP") if unchanged and previous else None
    modified = previous.get("LAST-MODIFIED") if unchanged and previous else None
    stamp = stamp or _utc_stamp(now)
    modified = modified or _utc_stamp(now)

    lines = ["BEGIN:VEVENT"]
    lines += _prop("UID", uid)
    lines += _prop("DTSTAMP", stamp)
    lines += _prop("LAST-MODIFIED", modified)
    lines += _prop("SEQUENCE", str(sequence))

    if game.start_time is None:
        next_day = game.date + timedelta(days=1)
        lines += _prop("DTSTART;VALUE=DATE", game.date.strftime("%Y%m%d"))
        lines += _prop("DTEND;VALUE=DATE", next_day.strftime("%Y%m%d"))
        lines += _prop("X-KU-TIME-STATUS", "TBA")
    else:
        local = datetime.combine(game.date, game.start_time, ZoneInfo(game.source_timezone))
        end = local + timedelta(minutes=int(cfg.get("default_duration_minutes", 240)))
        lines += _prop("DTSTART", _utc_stamp(local))
        lines += _prop("DTEND", _utc_stamp(end))
        lines += _prop("X-KU-TIME-STATUS", "CONFIRMED")
        lines += _prop("X-KU-SOURCE-TZ", game.source_timezone)

    lines += _prop("SUMMARY", escape_text(title_for(game, cfg)))
    lines += _prop("DESCRIPTION", escape_text(description_for(game)))
    location = game.location
    if game.venue:
        location = f"{game.venue} — {game.location}" if game.location else game.venue
    if location:
        lines += _prop("LOCATION", escape_text(location))
    if game.game_center_url:
        lines += _prop("URL", game.game_center_url)
    lines += _prop("CATEGORIES", escape_text(f"KU,{game.sport}"))
    lines += _prop("TRANSP", "TRANSPARENT")
    lines += _prop("X-KU-SITE", game.site)
    if game.network:
        lines += _prop("X-KU-NETWORK", escape_text(game.network))
    if game.streaming_service:
        lines += _prop("X-KU-STREAMING", escape_text(game.streaming_service))
    lines += _prop("X-KU-CONTENT-HASH", new_hash)
    lines.append("END:VEVENT")
    return lines


def generate_calendar(games: list[Game], cfg: dict, previous_text: str = "", now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    previous = parse_existing_metadata(previous_text)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//KU Sports Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_text(cfg.get('calendar_name', 'KU ' + cfg.get('sport_name', 'Sports')))}",
        f"X-WR-TIMEZONE:{cfg.get('source_timezone', 'America/Chicago')}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    for game in sorted(games, key=lambda g: (g.date, g.start_time or datetime.min.time(), g.opponent)):
        uid = stable_uid(game, cfg["key"], cfg.get("uid_domain", "ku-sports-calendar.local"))
        lines.extend(_event_lines(game, cfg, previous.get(uid), now))
    lines.append("END:VCALENDAR")
    return CRLF.join(lines) + CRLF


def write_calendar(path: str | Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8", newline="")
    temp.replace(path)
