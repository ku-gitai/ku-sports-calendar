from pathlib import Path

from ku_sports_calendar.validate import validate_file


def test_checked_in_initial_calendar_is_valid():
    path = Path(__file__).parents[1] / "docs" / "ku-football.ics"
    result = validate_file(path)
    assert result.event_count == 12
    assert len(result.uids) == 12
