from pathlib import Path

import pytest

from ku_sports_calendar.sources.ku_sidearm import (
    attach_game_center_links,
    parse_game_center_media,
    parse_text_schedule,
)

FIX = Path(__file__).parent / "fixtures"


def test_parse_current_style_text_schedule():
    html = (FIX / "schedule_text.html").read_text(encoding="utf-8")
    games = parse_text_schedule(html, sport_name="Football", season=2026, source_timezone="America/Chicago")
    assert len(games) == 12
    assert games[0].opponent == "LIU"
    assert games[0].start_time.hour == 19
    assert games[1].tournament == "StorageMart Border Showdown"
    assert games[2].site == "Neutral"
    assert games[3].is_tba
    assert games[4].site == "Away"


def test_attach_game_center_ids():
    text = (FIX / "schedule_text.html").read_text(encoding="utf-8")
    full = (FIX / "schedule_full.html").read_text(encoding="utf-8")
    games = parse_text_schedule(text, sport_name="Football", season=2026, source_timezone="America/Chicago")
    attach_game_center_links(games, full, "https://kuathletics.com/sports/football/schedule/")
    by_opp = {g.opponent: g for g in games}
    assert by_opp["Missouri"].game_center_id == "20530"
    assert by_opp["Oklahoma State"].game_center_url == "https://kuathletics.com/game-center/20539"


def test_parse_network_ignores_footer_espn_link():
    html = (FIX / "game_center_fox.html").read_text(encoding="utf-8")
    network, service, url = parse_game_center_media(html)
    assert network == "FOX"
    assert service == ""
    assert url == ""


def test_parse_streaming_watch_link():
    html = (FIX / "game_center_stream.html").read_text(encoding="utf-8")
    network, service, url = parse_game_center_media(html)
    assert network == "ESPN+"
    assert service == "ESPN+"
    assert url.startswith("https://www.espn.com/watch/")


def test_missing_required_table_field_fails_closed():
    bad = "<table><tr><th>Date</th><th>Opponent</th></tr><tr><td>Sep 1</td><td>X</td></tr></table>"
    with pytest.raises(ValueError):
        parse_text_schedule(bad, sport_name="Football", season=2026, source_timezone="America/Chicago")


def test_season_rollover_supports_future_basketball_shape():
    html = """<table><tr><th>Date</th><th>Time</th><th>At</th><th>Opponent</th><th>Location</th></tr>
    <tr><td>Jan 5</td><td>8 p.m. CT</td><td>Home</td><td>Example</td><td>Lawrence, Kan.</td></tr></table>"""
    games = parse_text_schedule(
        html, sport_name="Basketball", season=2026, source_timezone="America/Chicago", season_start_month=7
    )
    assert games[0].date.isoformat() == "2027-01-05"
