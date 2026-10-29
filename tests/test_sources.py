"""
Testit datalähteiden jäsentimille. Testit käyttävät pieniä itse kirjoitettuja
esimerkkejä, joten verkkoyhteyttä ei tarvita.
"""

from app.sync.sources.liquipedia_source import parse_matches
from app.sync.sources.vrs_source import parse_standings
from app.sync.sync_rosters import remove_duplicate_players
from app.teams.names import name_key

VRS_SAMPLE = """\
### Standings as of 2026_10_05<br />

| Standing | Points | Team Name | Roster | |
| :- | -: | :- | :- | :- |
| 3        |   1911 | Vitality  | apEX, flameZ, mezii, ropz, ZywOo | [details](x.md) |
| 34       |   1427 | Natus Vincere | Aleksib, b1t, iM, makazze, w0nderful | [details](y.md) |
"""


def _team_html(title, short):
    """Rakentaa yhden joukkueen HTML:n samassa muodossa kuin Liquipediassa."""
    return f'<span class="name" style="x"><a href="/counterstrike/{short}" title="{title}">{short}</a></span>'


def _match_html(timestamp, team1, team2, scores=None):
    score_html = (
        f'<span class="match-info-header-scoreholder-score">{scores[0]}</span>:'
        f'<span class="match-info-header-scoreholder-score">{scores[1]}</span>'
        if scores else "vs"
    )
    return (
        f'<div class="match-info"><span data-timestamp="{timestamp}"></span>'
        f"{_team_html(*team1)}{score_html}(Bo3){_team_html(*team2)}"
        '<span class="match-info-tournament-name"><a href="/x"><span>PGL Masters</span></a></span></div>'
    )


LIQUIPEDIA_SAMPLE = (
    'type=upcoming'
    + _match_html(1793268900, ("Team Vitality", "Vitality"), ("Natus Vincere", "NAVI"))
    + '<div class="match-info"><span data-timestamp="1793268900"></span><span class="name">TBD</span><span class="name">TBD</span></div>'
    + 'type=recent'
    + _match_html(1793100000, ("Team Spirit", "Spirit"), ("Natus Vincere", "NAVI"), scores=(1, 2))
)


def test_parse_standings():
    teams = parse_standings(VRS_SAMPLE)
    assert [t["name"] for t in teams] == ["Vitality", "Natus Vincere"]
    assert teams[0]["vrs_rank"] == 3 and teams[0]["vrs_points"] == 1911
    assert [p["nickname"] for p in teams[0]["players"]][-1] == "ZywOo"


def test_parse_matches_upcoming_and_completed():
    matches = parse_matches(LIQUIPEDIA_SAMPLE)
    assert len(matches) == 2  # TBD-ottelu ohitetaan

    upcoming, completed = matches
    assert upcoming["status"] == "upcoming"
    assert upcoming["team1"] == "Team Vitality" and upcoming["team2_short"] == "NAVI"
    assert upcoming["played_at"] == "2026-10-29 10:15"  # UTC
    assert upcoming["best_of"] == 3 and upcoming["event"] == "PGL Masters"

    assert completed["status"] == "completed"
    assert (completed["score1"], completed["score2"]) == (1, 2)


def test_name_key_matches_names_between_sources():
    assert name_key("Team Vitality") == name_key("Vitality")
    assert name_key("G2 Esports") == name_key("G2")
    assert name_key("BetBoom Team") == name_key("BETBOOM")
    assert name_key("Natus Vincere") != name_key("NAVI Junior")


def test_duplicate_player_kept_in_first_team():
    teams = [
        {"name": "A", "players": [{"nickname": "p1"}, {"nickname": "p2"}]},
        {"name": "B", "players": [{"nickname": "P1"}, {"nickname": "p3"}]},
    ]
    warnings = remove_duplicate_players(teams)
    assert len(warnings) == 1
    assert [p["nickname"] for p in teams[1]["players"]] == ["p3"]


DETAILS_SAMPLE = """\
### Roster Details<br />
Team Name: Vitality<br />
| Match Played | Match ID | Date       | Opponent | W/L | Age Weight | Event Weight | Bounty Collected | Opponent Network | LAN Wins | H2H Adj. | Roster |
| -: | -: | :- | :- | :- | :- | :- | :- | :- | :- | -: | :- |
|           37 |      710 | 2026-09-20 | Aurora   | W   | 1.000 | 0.769 | 0.586 (0.451) | 0.382 (0.294) | 1 (1.000) | 8.19 | apEX, flameZ, mezii, ropz, ZywOo |
|           35 |      738 | 2026-09-19 | Aurora   | L   | 1.000 | - | - | - | - | -23.41 | apEX, flameZ, mezii, ropz, ZywOo |
"""

WIKITEXT_SAMPLE = """\
{{Infobox team|name=Team Vitality}}
===Active===
{{Squad|status=active
|{{Person|flag=fr|id=apEX|igl=y|name=Dan Madesclaire|joindate={{abbr|2018-10-08|inactive}} <ref name="x"/>}}
|{{Person|flag=fr|id=ZywOo|name=Mathieu Herbaut|joindate=2018-10-08 <ref name="y"/>}}
|{{Person|flag=fr|id=XTQZZZ|name=Rémy Quoniam|role=Coach|joindate=2023-10-13}}
}}
===Former===
{{Squad|status=former
|{{Person|flag=il|id=Spinx|name=Lotan Giladi|joindate=2022-08-15}}
}}
"""


def test_parse_details():
    from app.sync.sources.vrs_source import parse_details

    team, matches = parse_details(DETAILS_SAMPLE)
    assert team == "Vitality"
    assert matches == [
        {"date": "2026-09-20", "opponent": "Aurora", "won": True},
        {"date": "2026-09-19", "opponent": "Aurora", "won": False},
    ]


def test_parse_active_squad():
    from app.sync.sources.liquipedia_teams import is_team_page, parse_active_squad

    assert is_team_page(WIKITEXT_SAMPLE)
    squad = parse_active_squad(WIKITEXT_SAMPLE)
    assert [p["nickname"] for p in squad] == ["apEX", "ZywOo", "XTQZZZ"]  # Spinx on entinen
    apex = squad[0]
    assert apex["igl"] and apex["real_name"] == "Dan Madesclaire" and apex["flag"] == "fr"
    assert apex["joined"] == "2018-10-08"
    assert squad[2]["role"] == "Coach"


def test_flag_filter():
    from app.filters import flag

    assert flag("fi") == "🇫🇮"
    assert flag("uk") == "🇬🇧"
    assert flag(None) == ""
