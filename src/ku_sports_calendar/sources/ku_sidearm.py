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
        "espnews": "ESPNEWS",
        "cbs": "CBS",
        "cbs sports network": "CBS Sports Network",
        "nbc": "NBC",
        "abc": "ABC",
        "cbssn": "CBSSN",
        "btn": "BTN",
        "tnt": "TNT",
        "trutv": "truTV",
        "tru tv": "truTV",
        "the cw": "The CW",
    }
    return canonical.get(compact, normalize_space(value)) if value else ""


def _canonical_stream(value: str) -> str:
    compact = re.sub(r"\s+", " ", normalize_space(value)).lower()
    if "big 12 now" in compact:
        return "Big 12 Now on ESPN+" if "espn+" in compact else "Big 12 Now"
    canonical = {
        "espn+": "ESPN+",
        "peacock": "Peacock",
        "max": "Max",
    }
    return canonical.get(compact, normalize_space(value)) if value else ""


def _header_map(table) -> dict[str, int]:
    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        names = [normalize_space(cell.get_text(" ", strip=True)).lower() for cell in cells]
        mapping = {name: i for i, name in enumerate(names)}
        if "date" in mapping and any(key in mapping for key in ("opponent", "time", "time/result")):
            return mapping
    return {}


def _parse_month_day(value: str) -> tuple[int, int]:
    value = normalize_space(value).replace(".", "")
    match = re.search(r"([A-Za-z]{3,9})\s+(\d{1,2})", value)
    if not match:
        raise ValueError(f"Unrecognized KU date: {value!r}")
    month = datetime.strptime(match.group(1)[:3], "%b").month
    return month, int(match.group(2))


def _season_date(value: str, *, season: int, season_start_month: int) -> date:
    month, day = _parse_month_day(value)
    year = season + (1 if month < season_start_month else 0)
    return date(year, month, day)


def parse_text_schedule(
    html: str,
    *,
    sport_name: str,
    season: int,
    source_timezone: str,
    season_start_month: int = 1,
) -> list[Game]:
    """Parse KU's semantic /schedule/text table for secondary metadata.

    For football this is no longer the source of kickoff time or TV. It supplies
    home/away/neutral, location, tournament, result and a cross-check against the
    Media Center schedule.
    """
    soup = BeautifulSoup(html, "html.parser")
    target = None
    header: dict[str, int] = {}
    for table in soup.find_all("table"):
        hm = _header_map(table)
        if all(k in hm for k in ("date", "time", "at", "opponent", "location")):
            target = table
            header = hm
            break
    if target is None:
        raise ValueError("KU text schedule table with expected headers was not found")

    games: list[Game] = []
    for row in target.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if not cells or cells[0].name == "th":
            continue
        values = [normalize_space(c.get_text(" ", strip=True)) for c in cells]
        if len(values) <= max(header.values()):
            continue
        opponent = values[header["opponent"]]
        if not opponent or opponent.upper() == "BYE":
            continue
        game_date = _season_date(
            values[header["date"]], season=season, season_start_month=season_start_month
        )
        site_raw = values[header["at"]].title()
        if site_raw not in {"Home", "Away", "Neutral"}:
            raise ValueError(f"Unrecognized home/away value: {site_raw!r}")
        tournament = values[header.get("tournament", -1)] if "tournament" in header else ""
        result = values[header.get("result", -1)] if "result" in header else ""
        if result == "-":
            result = ""
        games.append(
            Game(
                sport=sport_name,
                season=season,
                opponent=opponent,
                date=game_date,
                site=site_raw,  # type: ignore[arg-type]
                location=values[header["location"]],
                start_time=parse_time(values[header["time"]]),
                source_timezone=source_timezone,
                tournament=tournament,
                result=result,
            )
        )
    if not games:
        raise ValueError("KU text schedule parsed zero games")
    return games


def _find_media_center_table(soup: BeautifulSoup, season: int):
    marker_re = re.compile(rf"\b{season}\s+Season\b", re.IGNORECASE)
    marker = soup.find(string=lambda value: bool(value and marker_re.search(normalize_space(value))))
    if marker is None:
        raise ValueError(f"KU Media Center section for {season} Season was not found")

    start = marker.parent
    for table in start.find_all_next("table"):
        header = _header_map(table)
        if all(k in header for k in ("date", "opponent", "time/result", "tv/radio")):
            return table, header
    raise ValueError(f"KU Media Center {season} schedule table with expected headers was not found")


def _clean_media_opponent(value: str) -> tuple[str, str]:
    value = normalize_space(value)
    site = "Home"
    if re.match(r"^at\s+", value, re.IGNORECASE):
        site = "Away"
        value = re.sub(r"^at\s+", "", value, flags=re.IGNORECASE)
    elif re.match(r"^vs\.?\s+", value, re.IGNORECASE):
        value = re.sub(r"^vs\.?\s+", "", value, flags=re.IGNORECASE)

    # Media Center sometimes appends neutral-site notes such as "(in London)".
    value = re.sub(r"\s*\([^)]*\)\s*$", "", value).strip()
    return value, site


def _cell_text_without_radio(cell) -> str:
    parts: list[str] = []
    for piece in cell.stripped_strings:
        text = normalize_space(piece)
        if not text or RADIO_RE.fullmatch(text):
            continue
        parts.append(text)
    value = normalize_space(" ".join(parts))
    value = RADIO_RE.sub("", value)
    return normalize_space(value)


def parse_tv_radio_cell(cell) -> tuple[str, str, str]:
    """Return TV network, streaming service, and stream URL from TV/RADIO.

    Jayhawk Sports Network is radio and is intentionally ignored. Multiple TV
    networks (for example TNT/truTV) are retained, while streaming-only services
    such as ESPN+ or Max are placed in the streaming field.
    """
    text = _cell_text_without_radio(cell)
    if not text or text.upper() in {"TBA", "TBD", "-"}:
        return "", "", ""

    networks: list[str] = []
    for match in TV_NETWORK_RE.finditer(text):
        network = _canonical_network(match.group(0))
        if network and network not in networks:
            networks.append(network)

    streaming: list[str] = []
    for match in STREAMING_RE.finditer(text):
        service = _canonical_stream(match.group(0))
        if service and service not in streaming:
            streaming.append(service)

    network_value = " / ".join(networks)
    streaming_value = " / ".join(streaming)

    stream_url = ""
    if streaming_value:
        for anchor in cell.find_all("a", href=True):
            label = normalize_space(anchor.get_text(" ", strip=True))
            if RADIO_RE.search(label):
                continue
            host = urlparse(anchor["href"]).netloc.lower()
            if any(token in host for token in ("espn.com", "peacocktv.com", "max.com")):
                stream_url = anchor["href"]
                break

    return network_value, streaming_value, stream_url


def _parse_media_result(value: str) -> str:
    value = normalize_space(value)
    match = re.search(r"\b([WLT])\s*,?\s*(\d+\s*[-–]\s*\d+)\b", value, re.IGNORECASE)
    if not match:
        return ""
    return f"{match.group(1).upper()} {re.sub(r'\s+', '', match.group(2)).replace('–', '-')}"


def parse_media_center_schedule(
    html: str,
    *,
    sport_name: str,
    season: int,
    source_timezone: str,
    season_start_month: int = 1,
) -> list[Game]:
    """Parse the current-season Kansas Football Media Center table.

    This is the authoritative football source for opponent, date, kickoff time,
    TV network and streaming service. The regular schedule is used only to enrich
    location/site/tournament/result and to attach stable Game Center IDs.
    """
    soup = BeautifulSoup(html, "html.parser")
    table, header = _find_media_center_table(soup, season)

    games: list[Game] = []
    seen_dates: set[date] = set()
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if not cells or cells[0].name == "th":
            continue

        # KU occasionally omits empty trailing cells (for example POSTGAME) on
        # future games.  Only require the columns we actually read; otherwise a
        # perfectly valid game can disappear merely because a later optional
        # column is absent from that row.
        required_indexes = [
            header["date"],
            header["opponent"],
            header["time/result"],
            header["tv/radio"],
        ]
        if len(cells) <= max(required_indexes):
            continue

        date_text = normalize_space(cells[header["date"]].get_text(" ", strip=True))
        opponent_text = normalize_space(cells[header["opponent"]].get_text(" ", strip=True))
        if not date_text or not opponent_text or opponent_text.upper() == "BYE":
            continue

        game_date = _season_date(date_text, season=season, season_start_month=season_start_month)
        if game_date in seen_dates:
            raise ValueError(f"KU Media Center contains duplicate football date {game_date.isoformat()}")
        seen_dates.add(game_date)

        opponent, site_hint = _clean_media_opponent(opponent_text)
        time_result = normalize_space(cells[header["time/result"]].get_text(" ", strip=True))
        network, streaming_service, streaming_url = parse_tv_radio_cell(cells[header["tv/radio"]])

        games.append(
            Game(
                sport=sport_name,
                season=season,
                opponent=opponent,
                date=game_date,
                site=site_hint,  # type: ignore[arg-type]
                start_time=parse_media_time(time_result),
                source_timezone=source_timezone,
                network=network,
                streaming_service=streaming_service,
                streaming_url=streaming_url,
                result=_parse_media_result(time_result),
            )
        )

    if not games:
        raise ValueError("KU Media Center parsed zero games")
    return games


def merge_schedule_metadata(primary_games: list[Game], metadata_games: list[Game]) -> None:
    """Enrich Media Center games with secondary regular-schedule metadata.

    Date is preferred for matching. Opponent matching is the fallback so a Media
    Center date move can still retain the original Game Center identity/location
    until the regular schedule catches up.
    """
    unmatched = set(range(len(metadata_games)))

    for game in primary_games:
        same_date = [i for i in unmatched if metadata_games[i].date == game.date]
        match_index: int | None = None

        if len(same_date) == 1:
            match_index = same_date[0]
        elif same_date:
            key = _opponent_key(game.opponent)
            exact = [i for i in same_date if _opponent_key(metadata_games[i].opponent) == key]
            if len(exact) == 1:
                match_index = exact[0]

        if match_index is None:
            key = _opponent_key(game.opponent)
            exact = [i for i in unmatched if _opponent_key(metadata_games[i].opponent) == key]
            if len(exact) == 1:
                match_index = exact[0]

        if match_index is None:
            raise ValueError(
                f"Media Center game could not be matched to KU schedule metadata: "
                f"{game.date.isoformat()} {game.opponent}"
            )

        metadata = metadata_games[match_index]
        unmatched.remove(match_index)
        game.site = metadata.site
        game.location = metadata.location
        game.tournament = metadata.tournament
        if metadata.result:
            game.result = metadata.result

    if unmatched:
        extras = ", ".join(
            f"{metadata_games[i].date.isoformat()} {metadata_games[i].opponent}"
            for i in sorted(unmatched)
        )
        raise ValueError(f"KU regular schedule contains games missing from Media Center: {extras}")


def _game_center_ids(node) -> set[str]:
    ids: set[str] = set()
    for anchor in node.find_all("a", href=True):
        match = GAME_CENTER_RE.search(anchor.get("href", ""))
        if match:
            ids.add(match.group(1))
    return ids


def _ancestor_game_node(anchor):
    """Return the largest ancestor that still belongs to exactly one game."""
    href = anchor.get("href", "")
    match = GAME_CENTER_RE.search(href)
    if not match:
        return None
    target_id = match.group(1)

    node = anchor
    candidate = None
    for _ in range(16):
        node = node.parent
        if node is None:
            break
        ids = _game_center_ids(node)
        if target_id not in ids:
            continue
        if len(ids) == 1:
            candidate = node
            continue
        break
    return candidate


def _ancestor_text(anchor) -> str:
    node = _ancestor_game_node(anchor)
    return normalize_space(node.get_text(" ", strip=True)) if node is not None else ""


def attach_game_center_links(games: list[Game], schedule_html: str, base_url: str) -> None:
    """Attach stable KU Game Center IDs/URLs without reading TV logos."""
    soup = BeautifulSoup(schedule_html, "html.parser")
    by_id: dict[str, tuple[str, str]] = {}
    for anchor in soup.select('a[href*="/game-center/"]'):
        href = anchor.get("href", "")
        match = GAME_CENTER_RE.search(href)
        if not match:
            continue
        gcid = match.group(1)
        context = _ancestor_text(anchor)
        url = urljoin(base_url, href)
        old = by_id.get(gcid)
        if old is None or (context and (not old[1] or len(context) < len(old[1]))):
            by_id[gcid] = (url, context)

    candidates = [(gcid, url, context) for gcid, (url, context) in by_id.items()]
    edges: list[tuple[int, int, int, str, str]] = []

    for game_index, game in enumerate(games):
        opponent = normalize_name(game.opponent)
        month = game.date.strftime("%b").lower()
        day = str(game.date.day)
        location = normalize_name(game.location)

        for gcid, url, context in candidates:
            normalized_context = normalize_name(context)
            low = context.lower()
            date_match = month in low and bool(re.search(rf"\b0?{re.escape(day)}\b", low))
            opponent_match = bool(opponent and opponent in normalized_context)
            if not date_match and not opponent_match:
                continue

            score = 0
            if date_match:
                score += 20
            if opponent_match:
                score += 10
            if location and location in normalized_context:
                score += 1
            edges.append((score, -len(context), game_index, gcid, url))

    assigned_games: set[int] = set()
    assigned_ids: set[str] = set()
    for _, _, game_index, gcid, url in sorted(edges, reverse=True):
        if game_index in assigned_games or gcid in assigned_ids:
            continue
        game = games[game_index]
        game.game_center_id = gcid
        game.game_center_url = url
        assigned_games.add(game_index)
        assigned_ids.add(gcid)

    ids = [game.game_center_id for game in games if game.game_center_id]
    if len(ids) != len(set(ids)):
        raise ValueError("KU schedule mapped multiple games to the same Game Center ID")


class KuSidearmScheduleSource:
    def __init__(self, config: dict, session=None):
        self.config = config
        self.session = session or build_session()

    def fetch(self) -> list[Game]:
        media_center_url = self.config.get("media_center_url")
        if not media_center_url:
            raise ValueError("football config is missing media_center_url")

        # Football source priority:
        #   1. Media Center: opponent/date/time/TV/streaming
        #   2. Text schedule: site/location/tournament/result cross-check
        #   3. Full schedule: stable Game Center IDs/URLs only
        media_html = get_text(self.session, media_center_url)
        text_html = get_text(self.session, self.config["schedule_text_url"])
        schedule_html = get_text(self.session, self.config["schedule_url"])

        games = parse_media_center_schedule(
            media_html,
            sport_name=self.config["sport_name"],
            season=int(self.config["season"]),
            source_timezone=self.config.get("source_timezone", "America/Chicago"),
            season_start_month=int(self.config.get("season_start_month", 1)),
        )
        metadata_games = parse_text_schedule(
            text_html,
            sport_name=self.config["sport_name"],
            season=int(self.config["season"]),
            source_timezone=self.config.get("source_timezone", "America/Chicago"),
            season_start_month=int(self.config.get("season_start_month", 1)),
        )

        merge_schedule_metadata(games, metadata_games)
        attach_game_center_links(games, schedule_html, self.config["schedule_url"])

        minimum = int(self.config.get("minimum_expected_games", 1))
        if len(games) < minimum:
            raise RuntimeError(f"Parsed only {len(games)} games; refusing to publish (minimum {minimum})")

        if self.config.get("require_game_center_ids", False):
            missing = [f"{game.date.isoformat()} {game.opponent}" for game in games if not game.game_center_id]
            if missing:
                raise RuntimeError("Missing stable KU Game Center IDs: " + "; ".join(missing))

        for game in games:
            override = self.config.get("venue_overrides", {}).get(game.game_center_id)
            if override and normalize_space(game.location) == normalize_space(override.get("expected_location", "")):
                game.venue = override.get("venue", "")

        return games


# Backward-compatible alias for the first sport implementation.
KuSidearmFootballSource = KuSidearmScheduleSource
