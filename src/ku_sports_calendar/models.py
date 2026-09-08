from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, time
from typing import Literal

Site = Literal["Home", "Away", "Neutral"]


@dataclass
class Game:
    sport: str
    season: int
    opponent: str
    date: date
    site: Site
    location: str = ""
    venue: str = ""
    start_time: time | None = None
    source_timezone: str = "America/Chicago"
    network: str = ""
    streaming_service: str = ""
    streaming_url: str = ""
    tournament: str = ""
    result: str = ""
    game_center_id: str = ""
    game_center_url: str = ""

    @property
    def is_tba(self) -> bool:
        return self.start_time is None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["date"] = self.date.isoformat()
        data["start_time"] = self.start_time.isoformat(timespec="minutes") if self.start_time else None
        return data
