from datetime import date, datetime, time, timezone

from ku_sports_calendar.ics import generate_calendar, parse_existing_metadata
from ku_sports_calendar.identity import stable_uid
from ku_sports_calendar.models import Game
from ku_sports_calendar.validate import validate_ics_text

CFG = {
    "key": "football",
    "team_name": "Kansas",
    "uid_domain": "ku-sports-calendar.local",
    "default_duration_minutes": 240,
    "include_network_in_title": False,
}


def game(**kw):
    base = dict(
        sport="Football", season=2026, opponent="Missouri", date=date(2026, 9, 11), site="Home",
        location="Lawrence, Kan.", venue="David Booth Kansas Memorial Stadium", start_time=time(19, 0),
        source_timezone="America/Chicago", network="FOX", game_center_id="20530",
        game_center_url="https://kuathletics.com/game-center/20530",
    )
    base.update(kw)
    return Game(**base)


def test_uid_does_not_change_with_mutable_schedule_data():
    a = game()
    b = game(date=date(2026, 9, 12), start_time=time(20, 0), network="FS1", location="Kansas City, Kan.")
    assert stable_uid(a, "football", "ku-sports-calendar.local") == stable_uid(b, "football", "ku-sports-calendar.local")


def test_known_time_is_converted_from_central_to_utc():
    text = generate_calendar([game()], CFG, now=datetime(2026, 9, 7, 16, 52, tzinfo=timezone.utc))
    assert "DTSTART:20260912T000000Z" in text  # 7 p.m. CDT = midnight UTC
    assert "DTEND:20260912T040000Z" in text
    assert "SUMMARY:Kansas vs. Missouri" in text
    assert "X-KU-NETWORK:FOX" in text
    validate_ics_text(text)


def test_away_or_neutral_uses_ku_central_source_time_not_venue_timezone():
    london = game(opponent="Arizona State", date=date(2026, 9, 19), site="Neutral", location="London, England",
                  venue="Wembley Stadium", start_time=time(11, 0), network="FS1", game_center_id="20529",
                  game_center_url="https://kuathletics.com/game-center/20529")
    text = generate_calendar([london], CFG, now=datetime(2026, 9, 7, 16, 52, tzinfo=timezone.utc))
    assert "DTSTART:20260919T160000Z" in text  # KU lists all times Central


def test_tba_is_all_day_and_converts_to_timed_with_same_uid_and_incremented_sequence():
    tba = game(opponent="Middle Tennessee", date=date(2026, 10, 3), start_time=None, network="", game_center_id="20531",
               game_center_url="https://kuathletics.com/game-center/20531")
    first = generate_calendar([tba], CFG, now=datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert "DTSTART;VALUE=DATE:20261003" in first
    uid = stable_uid(tba, "football", "ku-sports-calendar.local")
    meta1 = parse_existing_metadata(first)[uid]
    assert meta1["SEQUENCE"] == "0"

    timed = game(opponent="Middle Tennessee", date=date(2026, 10, 3), start_time=time(14, 30), network="ESPN2",
                 game_center_id="20531", game_center_url="https://kuathletics.com/game-center/20531")
    second = generate_calendar([timed], CFG, previous_text=first, now=datetime(2026, 9, 20, tzinfo=timezone.utc))
    meta2 = parse_existing_metadata(second)[uid]
    assert meta2["SEQUENCE"] == "1"
    assert "DTSTART:20261003T193000Z" in second
    assert first != second


def test_unchanged_regeneration_is_byte_stable():
    first = generate_calendar([game()], CFG, now=datetime(2026, 9, 7, tzinfo=timezone.utc))
    second = generate_calendar([game()], CFG, previous_text=first, now=datetime(2026, 9, 8, tzinfo=timezone.utc))
    assert second == first


def test_duplicate_uid_validation_fails():
    a = generate_calendar([game()], CFG, now=datetime(2026, 9, 7, tzinfo=timezone.utc))
    event = a.split("BEGIN:VEVENT", 1)[1].split("END:VEVENT", 1)[0]
    duplicate = a.replace("END:VCALENDAR\r\n", f"BEGIN:VEVENT{event}END:VEVENT\r\nEND:VCALENDAR\r\n")
    try:
        validate_ics_text(duplicate)
    except ValueError as exc:
        assert "Duplicate" in str(exc)
    else:
        raise AssertionError("duplicate UID should fail validation")
