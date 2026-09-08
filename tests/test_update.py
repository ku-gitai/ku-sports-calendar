import json
from datetime import date, datetime, time, timezone
from pathlib import Path

import pytest

from ku_sports_calendar.gameday import is_game_day
from ku_sports_calendar.ics import generate_calendar
from ku_sports_calendar.models import Game
from ku_sports_calendar.update import update_calendar


class BrokenSource:
    def fetch(self):
        raise RuntimeError("KU unavailable")


class StaticSource:
    def __init__(self, games):
        self.games = games
    def fetch(self):
        return self.games


def _cfg(tmp_path):
    path = tmp_path / "football.json"
    out = tmp_path / "ku-football.ics"
    data = {
        "key":"football","sport_name":"Football","team_name":"Kansas","season":2026,
        "source_timezone":"America/Chicago","default_duration_minutes":240,
        "schedule_url":"https://kuathletics.com/sports/football/schedule/",
        "schedule_text_url":"https://kuathletics.com/sports/football/schedule/text",
        "output_path":str(out),"uid_domain":"ku-sports-calendar.local","minimum_expected_games":1,
        "venue_overrides":{}
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path, out, data


def _game(network="FOX", start=time(19, 0)):
    return Game(sport="Football", season=2026, opponent="Missouri", date=date(2026,9,11), site="Home",
                location="Lawrence, Kan.", start_time=start, source_timezone="America/Chicago", network=network,
                game_center_id="20530", game_center_url="https://kuathletics.com/game-center/20530")


def test_source_failure_never_overwrites_existing_feed(tmp_path):
    cfg_path, out, _ = _cfg(tmp_path)
    out.write_text("KEEP-ME", encoding="utf-8")
    with pytest.raises(RuntimeError):
        update_calendar(cfg_path, source=BrokenSource())
    assert out.read_text(encoding="utf-8") == "KEEP-ME"


def test_schedule_change_updates_existing_uid_not_duplicate(tmp_path):
    cfg_path, out, cfg = _cfg(tmp_path)
    changed, count = update_calendar(cfg_path, source=StaticSource([_game()]), today=date(2026,9,7))
    assert changed and count == 1
    first = out.read_text(encoding="utf-8")
    changed2, count2 = update_calendar(cfg_path, source=StaticSource([_game(network="FS1", start=time(20,0))]), today=date(2026,9,7))
    second = out.read_text(encoding="utf-8")
    assert changed2 and count2 == 1
    assert second.count("BEGIN:VEVENT") == 1
    assert "SEQUENCE:1" in second
    assert "X-KU-NETWORK:FS1" in second
    assert first != second


def test_gameday_gate_uses_central_calendar_date(tmp_path):
    path = tmp_path / "feed.ics"
    cfg = {"key":"football","team_name":"Kansas","uid_domain":"ku-sports-calendar.local","default_duration_minutes":240}
    path.write_text(generate_calendar([_game()], cfg, now=datetime(2026,9,1,tzinfo=timezone.utc)), encoding="utf-8", newline="")
    assert is_game_day(path, now=datetime(2026,9,11,8,0,tzinfo=timezone.utc).astimezone()) is True


def test_unchanged_update_does_not_rewrite_feed(tmp_path):
    cfg_path, out, _ = _cfg(tmp_path)
    first_changed, _ = update_calendar(cfg_path, source=StaticSource([_game()]), today=date(2026, 9, 7))
    before = out.read_bytes()
    second_changed, _ = update_calendar(cfg_path, source=StaticSource([_game()]), today=date(2026, 9, 7))
    after = out.read_bytes()
    assert first_changed is True
    assert second_changed is False
    assert after == before
