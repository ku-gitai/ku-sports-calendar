from __future__ import annotations

import hashlib
import re

from .models import Game


def _slug(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "game"


def stable_uid(game: Game, sport_key: str, uid_domain: str) -> str:
    """Return an identifier that does not depend on mutable date/time/location data.

    SIDEARM Game Center IDs are preferred because they are source-native game identities.
    The fallback uses season/opponent/site plus a short digest; it is only used if KU omits
    a Game Center link.
    """
    if game.game_center_id:
        token = game.game_center_id
    else:
        identity = f"{game.season}|{game.opponent}|{game.site}".lower()
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
        token = f"{_slug(game.opponent)}-{digest}"
    return f"ku-{sport_key}-{game.season}-{token}@{uid_domain}"
