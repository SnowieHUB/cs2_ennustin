"""
Testit ennustesivun joukkuehaulle (app/predictions/routes.py: _find_team_id).
"""

from app.predictions.routes import _find_team_id
from app.teams.names import name_key

TEAMS = [
    {"id": 3, "name": "Vitality", "name_key": name_key("Vitality")},
    {"id": 34, "name": "Natus Vincere", "name_key": name_key("Natus Vincere")},
]


def test_name_is_case_insensitive():
    assert _find_team_id("vitality", TEAMS) == 3
    assert _find_team_id("Team Vitality", TEAMS) == 3  # lisäsana "Team" ei haittaa


def test_short_name():
    assert _find_team_id("NAVI", TEAMS) == 34
    assert _find_team_id("navi", TEAMS) == 34


def test_number_from_old_links():
    assert _find_team_id("34", TEAMS) == 34


def test_unknown_or_empty():
    assert _find_team_id("Vitalityy", TEAMS) is None
    assert _find_team_id("", TEAMS) is None
    assert _find_team_id(None, TEAMS) is None
