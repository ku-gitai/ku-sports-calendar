from __future__ import annotations

import re
from datetime import date, datetime, time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..http import build_session, get_text
from ..models import Game

GAME_CENTER_RE = re.compile(r"/game-center/(\d+)")
TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\s*(?:CT|CST|CDT)?$", re.IGNORECASE)
MEDIA_TIME_RE = re.compile(
    r"(?<!\d)(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\s*(?:CT|CST|CDT)?\b",
    re.IGNORECASE,
)

TV_NETWORK_RE = re.compile(
    r"CBS Sports Network|ESPNU|ESPN2|ESPNEWS|ESPN(?!\+)|ABC|CBS|FOX|NBC|FS1|FS2|CBSSN|BTN|TNT|tru\s*TV|The CW",
    re.IGNORECASE,
)
STREAMING_RE = re.compile(
    r"Big 12 Now(?:\s*(?:/|on)\s*ESPN\+)?|ESPN\+|Peacock|Max",
    re.IGNORECASE,
)
RADIO_RE = re.compile(
    r"(?:Listen on\s+)?Jayhawk\s+(?:Sports|Radio)\s+Network",
    re.IGNORECASE,
)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_name(value: str) -> str:
    value = normalize_space(value).lower()
    value = re.sub(r"^#?\d+\s+", "", value)
    value = value.replace("university", "").replace("state university", "state")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _opponent_key(value: str) -> str:
    key = normalize_name(value)
    aliases = {
        "long island": "liu",
        "liu": "liu",
    }
    return aliases.get(key, key)


def _time_from_groups(match: re.Match[str]) -> time:
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    ampm = match.group(3).lower()
    if hour == 12:
        hour = 0
    if ampm == "p":
        hour += 12
    return time(hour, minute)


def parse_time(value: str) -> time | None:
    value = normalize_space(value)
    if not value or value.upper() in {"TBA", "TBD"}:
        return None
    value = value.replace("p.m.", "pm").replace("a.m.", "am").replace("p.m", "pm").replace("a.m", "am")
    m = TIME_RE.match(value)
    if not m:
        raise ValueError(f"Unrecognized KU kickoff time: {value!r}")
    return _time_from_groups(m)


def parse_media_time(value: str) -> time | None:
    """Extract a kickoff time from the Media Center TIME/RESULT field."""
    value = normalize_space(value)
    if not value:
        return None
    match = MEDIA_TIME_RE.search(value)
    if match:
        return _time_from_groups(match)
    if re.search(r"\b(?:TBA|TBD)\b", value, re.IGNORECASE):
        return None
    raise ValueError(f"Unrecognized KU Media Center time/result value: {value!r}")


def _canonical_network(value: str) -> str:
    compact = re.sub(r"\s+", " ", normalize_space(value)).lower()
    canonical = {
        "fox": "FOX",
        "fs1": "FS1",
        "fs2": "FS2",
        "espnu": "ESPNU",
        "espn": "ESPN",
        "espn2": "ESPN2",
