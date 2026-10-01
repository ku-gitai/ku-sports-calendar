from __future__ import annotations

import re
from datetime import date, datetime, time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..http import build_session, get_text
from ..models import Game

NETWORK_RE = re.compile(
    r"(?<!\w)(Big 12 Now(?: on ESPN\+)?|ESPN\+|ESPNU|ESPN2|ESPNEWS|ESPN|ABC|CBS|FOX|NBC|FS1|FS2|CBSSN|BTN|TNT|TBS|truTV|The CW|Peacock)(?!\w)",
    re.IGNORECASE,
)
GAME_CENTER_RE = re.compile(r"/game-center/(\d+)")
TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\s*(?:CT|CST|CDT)?$", re.IGNORECASE)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_name(value: str) -> str:
    value = normalize_space(value).lower()
    value = value.replace("university", "").replace("state university", "state")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def parse_time(value: str) -> time | None:
    value = normalize_space(value)
    if not value or value.upper() in {"TBA", "TBD"}:
        return None
    value = value.replace("p.m.", "pm").replace("a.m.", "am").replace("p.m", "pm").replace("a.m", "am")
    value = value.replace(" p.m.", " pm").replace(" a.m.", " am")
    m = TIME_RE.match(value)
    if not m:
        # tolerate "7 pm CT" after punctuation normalization
        m2 = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*([ap])m\s*(?:CT|CST|CDT)?$", value, re.I)
        if not m2:
            raise ValueError(f"Unrecognized KU kickoff time: {value!r}")
        m = m2
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = m.group(3).lower()
    if hour == 12:
        hour = 0
    if ampm == "p":
        hour += 12
    return time(hour, minute)

def _canonical_network(value: str) -> str:
    canonical = {
        "fox": "FOX",
        "fs1": "FS1",
        "fs2": "FS2",
        "espnu": "ESPNU",
        "espn": "ESPN",
        "espn2": "ESPN2",
        "espnews": "ESPNEWS",
        "espn+": "ESPN+",
        "cbs": "CBS",
        "nbc": "NBC",
        "abc": "ABC",
        "cbssn": "CBSSN",
        "btn": "BTN",
        "tnt": "TNT",
        "tbs": "TBS",
        "trutv": "truTV",
        "peacock": "Peacock",
        "the cw": "The CW",
        "big 12 now": "Big 12 Now",
        "big 12 now on espn+": "Big 12 Now on ESPN+",
    }
    return canonical.get(value.lower(), value) if value else ""


def _header_map(table) -> dict[str, int]:
    headers = [normalize_space(th.get_text(" ", strip=True)).lower() for th in table.find_all("th")]
    return {name: i for i, name in enumerate(headers)}


def parse_text_schedule(html: str, *, sport_name: str, season: int, source_timezone: str, season_start_month: int = 1) -> list[Game]:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    target = None
    header = {}
    for table in tables:
        hm = _header_map(table)
        if all(k in hm for k in ("date", "time", "at", "opponent", "location")):
            target = table
            header = hm
            break
    if target is None:
        raise ValueError("KU text schedule table with expected headers was not found")

    games: list[Game] = []
    for row in target.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells or cells[0].name == "th":
            continue
        values = [normalize_space(c.get_text(" ", strip=True)) for c in cells]
        if len(values) <= max(header.values()):
            continue
        opponent = values[header["opponent"]]
        if not opponent or opponent.upper() == "BYE":
            continue
        date_text = values[header["date"]]
        m = re.match(r"([A-Za-z]{3,9})\s+(\d{1,2})", date_text)
        if not m:
            raise ValueError(f"Unrecognized KU date: {date_text!r}")
        month = datetime.strptime(m.group(1)[:3], "%b").month
        year = season + (1 if month < season_start_month else 0)
        game_date = date(year, month, int(m.group(2)))
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
        raise ValueError("KU schedule parsed zero games")
    return games


def _game_center_ids(node) -> set[str]:
    """Return unique KU Game Center IDs contained inside *node*."""
    ids: set[str] = set()
    for a in node.find_all("a", href=True):
        m = GAME_CENTER_RE.search(a.get("href", ""))
        if m:
            ids.add(m.group(1))
    return ids


def _ancestor_game_node(anchor):
    """Return the largest ancestor that still belongs to exactly one game.

    SIDEARM can wrap a game in several nested ``div`` elements and can duplicate
    links for responsive layouts.  CSS class names are not stable enough to be
    the only boundary.  A stronger boundary is the Game Center ID itself: climb
    upward while every Game Center link in the ancestor points to the *same*
    game, and stop before the ancestor starts containing another game's ID.

    This prevents TV-logo metadata from one schedule card leaking into every
    other game when SIDEARM changes its wrapper markup.
    """
    href = anchor.get("href", "")
    m = GAME_CENTER_RE.search(href)
    if not m:
        return None
    target_id = m.group(1)

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
        # This ancestor contains at least one other scheduled game's Game Center
        # link, so the previous candidate is the outer boundary of this game card.
        break
    return candidate


def _ancestor_text(anchor) -> str:
    """Return visible text from the bounded schedule card for one game."""
    node = _ancestor_game_node(anchor)
    return normalize_space(node.get_text(" ", strip=True)) if node is not None else ""


def _network_from_metadata(value: str) -> str:
    """Extract a canonical TV network from an HTML attribute/asset reference."""
    value = normalize_space(value)
    if not value:
        return ""

    low = value.lower()
    compact = re.sub(r"[^a-z0-9+]+", "", low)

    # Specific aliases first so e.g. ``espn-u.svg`` is not reduced to ESPN.
    aliases = (
        ("big12nowonespn+", "Big 12 Now on ESPN+"),
        ("big12nowonespnplus", "Big 12 Now on ESPN+"),
        ("big12now", "Big 12 Now"),
        ("espnplus", "ESPN+"),
        ("espn+", "ESPN+"),
        ("espnews", "ESPNEWS"),
        ("espnu", "ESPNU"),
        ("espn2", "ESPN2"),
        ("cbssn", "CBSSN"),
        ("peacock", "Peacock"),
        ("thecw", "The CW"),
        ("trutv", "truTV"),
        ("fs1", "FS1"),
        ("fs2", "FS2"),
    )
    for token, network in aliases:
        if token in compact:
            return network

    match = NETWORK_RE.search(value)
    return _canonical_network(match.group(1)) if match else ""


def _attrs_text(tag) -> str:
    """Flatten relevant HTML attributes into searchable text."""
    pieces: list[str] = []
    for key, value in getattr(tag, "attrs", {}).items():
        if isinstance(value, (list, tuple)):
            value = " ".join(str(v) for v in value)
        pieces.append(f"{key}={value}")
    return " ".join(pieces)


def _network_from_schedule_card(anchor) -> str:
    """Read a TV-logo network from the official KU schedule card without OCR.

    Only media-like elements inside the *single-game* boundary are inspected.
    We intentionally do not serialize/search the whole card or its visible text;
    doing that can pick up unrelated global ESPN references when SIDEARM changes
    wrapper structure.
    """
    node = _ancestor_game_node(anchor)
    if node is None:
        return ""

    # The KU schedule currently renders TV as a graphic.  Its filename/source or
    # accessibility metadata is enough to identify the network.
    for tag in node.find_all(["img", "source", "svg", "use"]):
        network = _network_from_metadata(_attrs_text(tag))
        if network:
            return network

    # Some SIDEARM themes put the TV asset in a CSS background or data attribute
    # on a media/network wrapper rather than an <img>.  Inspect only elements whose
    # own metadata says they are TV/broadcast/media related.
    for tag in node.find_all(True):
        marker = " ".join(
            [
                str(tag.get("id", "")),
                " ".join(tag.get("class", []) if isinstance(tag.get("class", []), list) else [str(tag.get("class", ""))]),
                str(tag.get("aria-label", "")),
                str(tag.get("title", "")),
            ]
        ).lower()
        if not re.search(r"\b(tv|television|network|broadcast|media)\b", marker):
            continue
        network = _network_from_metadata(_attrs_text(tag))
        if network:
            return network

    return ""


def attach_game_center_links(games: list[Game], schedule_html: str, base_url: str) -> None:
    soup = BeautifulSoup(schedule_html, "html.parser")
    by_id: dict[str, tuple[str, str, str]] = {}
    for a in soup.select('a[href*="/game-center/"]'):
        href = a.get("href", "")
        m = GAME_CENTER_RE.search(href)
        if not m:
            continue
        gcid = m.group(1)
        context = _ancestor_text(a)
        schedule_network = _network_from_schedule_card(a)
        url = urljoin(base_url, href)

        # Duplicate links to the same Game Center can occur in responsive markup.
        # Prefer the more specific (shorter) non-empty context, but preserve network
        # metadata found in either copy of the same game card.
        old = by_id.get(gcid)
        if old is None:
            by_id[gcid] = (url, context, schedule_network)
        else:
            old_url, old_context, old_network = old
            if context and (not old_context or len(context) < len(old_context)):
                old_url, old_context = url, context
            by_id[gcid] = (old_url, old_context, old_network or schedule_network)

    candidates = [
        (gcid, url, context, schedule_network)
        for gcid, (url, context, schedule_network) in by_id.items()
    ]

    # Build all plausible game/link matches, then assign one-to-one.  The one-to-one
    # constraint is fail-safe protection against a site markup change accidentally
    # assigning the same source-native ID to multiple calendar events.
    edges: list[tuple[int, int, int, str, str, str]] = []
    for game_index, game in enumerate(games):
        opp = normalize_name(game.opponent)
        month = game.date.strftime("%b").lower()
        day = str(game.date.day)
        location = normalize_name(game.location)
        for gcid, url, context, schedule_network in candidates:
            norm_context = normalize_name(context)
            if not opp or opp not in norm_context:
                continue
            low = context.lower()
            score = 10
            if month in low:
                score += 2
            if re.search(rf"\b0?{re.escape(day)}\b", low):
                score += 2
            if location and location in norm_context:
                score += 1
            # Higher score wins; for ties, shorter context is more likely to be a
            # single game card rather than a schedule-wide ancestor.
            edges.append((score, -len(context), game_index, gcid, url, schedule_network))

    assigned_games: set[int] = set()
    assigned_ids: set[str] = set()
    for _, _, game_index, gcid, url, schedule_network in sorted(edges, reverse=True):
        if game_index in assigned_games or gcid in assigned_ids:
            continue
        game = games[game_index]
        game.game_center_id = gcid
        game.game_center_url = url
        if schedule_network:
            game.network = schedule_network
        assigned_games.add(game_index)
        assigned_ids.add(gcid)

    ids = [g.game_center_id for g in games if g.game_center_id]
    if len(ids) != len(set(ids)):
        raise ValueError("KU schedule mapped multiple games to the same Game Center ID")


def parse_game_center_media(html: str) -> tuple[str, str, str]:
    soup = BeautifulSoup(html, "html.parser")
    full_text = "\n".join(soup.stripped_strings)
    start = full_text.find("Game Center for")
    if start < 0:
        start = 0
    end_points = [p for p in (full_text.find("Headed to the Game?", start), full_text.find("Game Info", start)) if p >= 0]
    end = min(end_points) if end_points else min(len(full_text), start + 3500)
    hero = full_text[start:end]
    match = NETWORK_RE.search(hero)
    network = _canonical_network(match.group(1) if match else "")

    stream_service = ""
    stream_url = ""
    main = soup.find("main") or soup
    for a in main.find_all("a", href=True):
        label = normalize_space(a.get_text(" ", strip=True))
        if label.lower() in {"watch", "video", "stream", "watch live"}:
            stream_url = a["href"]
            host = urlparse(stream_url).netloc.lower()
            if network == "ESPN+":
                stream_service = "ESPN+"
            elif "espn.com" in host:
                stream_service = "ESPN"
            elif "foxsports.com" in host:
                stream_service = "FOX Sports"
            elif "peacocktv.com" in host or network == "Peacock":
                stream_service = "Peacock"
            else:
                stream_service = label
            break
    return network, stream_service, stream_url


class KuSidearmScheduleSource:
    def __init__(self, config: dict, session=None):
        self.config = config
        self.session = session or build_session()

    def fetch(self) -> list[Game]:
        text_html = get_text(self.session, self.config["schedule_text_url"])
        schedule_html = get_text(self.session, self.config["schedule_url"])
        games = parse_text_schedule(
            text_html,
            sport_name=self.config["sport_name"],
            season=int(self.config["season"]),
            source_timezone=self.config.get("source_timezone", "America/Chicago"),
            season_start_month=int(self.config.get("season_start_month", 1)),
        )
        attach_game_center_links(games, schedule_html, self.config["schedule_url"])

        for game in games:
            if game.game_center_url:
                try:
                    page = get_text(self.session, game.game_center_url)
                    network, service, stream_url = parse_game_center_media(page)
                    # The main schedule card can be updated before Game Center.
                    # Treat it as the primary TV source and use Game Center only to
                    # fill fields the schedule card did not provide.
                    if not game.network and network:
                        game.network = network
                    if service:
                        game.streaming_service = service
                    if stream_url:
                        game.streaming_url = stream_url
                except Exception:
                    # Base schedule is still usable when one Game Center page is unavailable.
                    pass
            override = self.config.get("venue_overrides", {}).get(game.game_center_id)
            if override and normalize_space(game.location) == normalize_space(override.get("expected_location", "")):
                game.venue = override.get("venue", "")

        minimum = int(self.config.get("minimum_expected_games", 1))
        if len(games) < minimum:
            raise RuntimeError(f"Parsed only {len(games)} games; refusing to publish (minimum {minimum})")
        return games


# Backward-compatible alias for the first sport implementation.
KuSidearmFootballSource = KuSidearmScheduleSource
