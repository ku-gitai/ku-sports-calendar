from __future__ import annotations

from datetime import date
from pathlib import Path

from .config import load_config
from .ics import generate_calendar, write_calendar
from .sources import build_source
from .validate import validate_ics_text


def preserve_past_media(games, previous_text: str, today: date) -> None:
    """Keep past-game TV labels when KU Game Center stops displaying them after final.

    Future games are never preserved this way: if KU removes a future TV assignment,
    the feed follows KU and removes it too.
    """
    from .ics import parse_existing_metadata
    from .identity import stable_uid

    prev = parse_existing_metadata(previous_text)
    for game in games:
        if game.date >= today or game.network:
            continue
        # We need config for UID, so this function is only called through update_calendar and
        # game carries temporary attributes set there. Kept internal to avoid widening model.
        cfg = getattr(game, "_calendar_cfg")
        uid = stable_uid(game, cfg["key"], cfg.get("uid_domain", "ku-sports-calendar.local"))
        old = prev.get(uid, {})
        if old.get("X-KU-NETWORK"):
            game.network = old["X-KU-NETWORK"].replace("\\,", ",").replace("\\;", ";")
        if old.get("X-KU-STREAMING"):
            game.streaming_service = old["X-KU-STREAMING"].replace("\\,", ",").replace("\\;", ";")


def update_calendar(config_path: str | Path, *, source=None, today: date | None = None) -> tuple[bool, int]:
    cfg = load_config(config_path)
    output = Path(cfg["output_path"])
    if output.exists():
        with output.open("r", encoding="utf-8", newline="") as f:
            previous_text = f.read()
    else:
        previous_text = ""
    source = source or build_source(cfg)
    games = source.fetch()
    for game in games:
        setattr(game, "_calendar_cfg", cfg)
    preserve_past_media(games, previous_text, today or date.today())
    new_text = generate_calendar(games, cfg, previous_text=previous_text)
    result = validate_ics_text(new_text)
    changed = new_text != previous_text
    if changed:
        write_calendar(output, new_text)
    return changed, result.event_count
