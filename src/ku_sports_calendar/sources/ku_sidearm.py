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


def _ancestor_text(anchor) -> str:
    node = anchor
    best = ""
    for _ in range(8):
        node = node.parent
        if node is None:
            break
        text = normalize_space(node.get_text(" ", strip=True))
        if len(text) > len(best):
            best = text
        if node.name in {"li", "article"}:
            return text
        if len(text) > 1200:
            break
    return best


def attach_game_center_links(games: list[Game], schedule_html: str, base_url: str) -> None:
    soup = BeautifulSoup(schedule_html, "html.parser")
    candidates: list[tuple[str, str, str]] = []
    for a in soup.select('a[href*="/game-center/"]'):
        href = a.get("href", "")
        m = GAME_CENTER_RE.search(href)
        if not m:
            continue
        candidates.append((m.group(1), urljoin(base_url, href), _ancestor_text(a)))

    for game in games:
        opp = normalize_name(game.opponent)
        month = game.date.strftime("%b").lower()
        day = str(game.date.day)
        scored: list[tuple[int, str, str]] = []
        for gcid, url, context in candidates:
            norm_context = normalize_name(context)
            score = 0
            if opp and opp in norm_context:
                score += 10
            low = context.lower()
            if month in low:
                score += 2
            if re.search(rf"\b0?{re.escape(day)}\b", low):
                score += 1
            if score >= 10:
                scored.append((score, gcid, url))
        if scored:
            scored.sort(reverse=True)
            _, game.game_center_id, game.game_center_url = scored[0]


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
    network = match.group(1) if match else ""
    # Preserve KU's display capitalization where useful.
    canonical = {"fox": "FOX", "fs1": "FS1", "fs2": "FS2", "espnu": "ESPNU", "espn": "ESPN", "espn2": "ESPN2", "espn+": "ESPN+", "cbs": "CBS", "nbc": "NBC", "abc": "ABC", "cbssn": "CBSSN", "btn": "BTN", "tnt": "TNT", "tbs": "TBS", "trutv": "truTV", "peacock": "Peacock", "the cw": "The CW"}
    if network:
        network = canonical.get(network.lower(), network)

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
                    game.network = network
                    game.streaming_service = service
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
