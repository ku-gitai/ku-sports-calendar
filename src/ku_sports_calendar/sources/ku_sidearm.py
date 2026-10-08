

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
