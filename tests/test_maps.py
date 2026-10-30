"""
Testit karttadatalle: turnaussivun jäsennys, tallennus ja karttatilastot.
"""

from datetime import date, timedelta

import pytest

from app.database.db import connect, init_schema
from app.maps import repository as maps_repo
from app.maps.service import team_map_stats
from app.sync.sources.liquipedia_tournaments import (
    parse_date, parse_tournament_list, parse_tournament_matches, title_from_url,
)
from app.teams import repository as teams_repo

WIKITEXT = """
{{Matchlist|id=abc|title=Group A
|{{Match
	|opponent1={{TeamOpponent|vit}}|opponent2={{TeamOpponent|nemiga}}
	|date=October 30, 2026 - 14:00 {{Abbr/EET}} |finished=
	|map1={{Map|map=Cache|finished=true
		|t1firstside=ct|t1t=3|t1ct=5|t2t=7|t2ct=6}}
	|map2={{Map|map=Dust II|finished=
		|t1firstside=t|t1t=8|t1ct=|t2t=|t2ct=4}}
	|map3={{Map|map=Mirage|finished=
		|t1firstside=|t1t=|t1ct=|t2t=|t2ct=}}
	|hltv=2399756
	}}
|{{Match
	|opponent1={{TeamOpponent|}}|opponent2={{TeamOpponent|}}
	|date=October 31, 2026 - 13:00 {{Abbr/EET}} |finished=
	}}
}}
"""


@pytest.fixture
def conn():
    connection = connect(":memory:")
    init_schema(connection)
    yield connection
    connection.close()


def test_parse_live_match():
    [match] = parse_tournament_matches(WIKITEXT)  # TBD-ottelu ohitetaan
    assert (match["team1"], match["team2"]) == ("vit", "nemiga")
    assert match["played_at"] == "2026-10-30 12:00"  # EET = UTC+2
    assert (match["score1"], match["score2"], match["finished"]) == (0, 1, False)
    assert match["hltv_id"] == 2399756
    cache, dust, mirage = match["maps"]
    assert (cache["rounds1"], cache["rounds2"], cache["finished"]) == (8, 13, True)
    assert (dust["rounds1"], dust["rounds2"], dust["finished"]) == (8, 4, False)
    assert mirage["rounds1"] is None


def test_overtime_rounds_are_counted():
    text = WIKITEXT.replace("|t1t=3|t1ct=5|t2t=7|t2ct=6", "|t1t=6|t1ct=6|t2t=6|t2ct=6|o1t1t=3|o1t1ct=1|o1t2t=1|o1t2ct=1")
    cache = parse_tournament_matches(text)[0]["maps"][0]
    assert (cache["rounds1"], cache["rounds2"]) == (16, 14)


def test_parse_date_formats():
    assert parse_date("2026-02-24") == "2026-02-24 12:00"
    assert parse_date("March 3, 2026 - 18:30 {{Abbr/CET}}") == "2026-03-03 17:30"
    assert parse_date("TBA") is None


def test_tournament_list_and_url():
    listing = ('<tr class="table2__row--body"><td>[[File:icon.png|x]]</td><td>[[PGL/2026/Masters|PGL Masters]]</td></tr>'
               '<tr class="table2__row--body"><td>[[File:a.png]]</td><td>[[ESL/Pro_League/Season_24]]</td></tr>')
    assert parse_tournament_list(listing) == ["PGL/2026/Masters", "ESL/Pro League/Season 24"]
    assert title_from_url("https://liquipedia.net/counterstrike/PGL/2026/Masters#Playoffs") == "PGL/2026/Masters"


def test_find_series_in_match_order(conn):
    vit = teams_repo.get_or_create_team(conn, "Vitality")
    nemiga = teams_repo.get_or_create_team(conn, "Nemiga")
    [match] = parse_tournament_matches(WIKITEXT)
    maps_repo.save_series(conn, "PGL/2026/Masters", match, vit, nemiga)

    # Sivulla Nemiga on ensin: tulokset käännetään sen näkökulmaan.
    series = maps_repo.find_series(conn, nemiga, vit, "2026-10-30 12:00")
    assert (series["score1"], series["score2"]) == (1, 0)
    assert (series["maps"][0]["rounds1"], series["maps"][0]["rounds2"]) == (13, 8)


def test_team_map_stats_best_and_ban(conn):
    team = teams_repo.get_or_create_team(conn, "A")
    rival = teams_repo.get_or_create_team(conn, "B")
    pool = ["Ancient", "Dust II", "Mirage"]
    # 10 Dust II -voittoa, 10 Mirage-tappiota, Ancientia ei koskaan -> bänni.
    for i, (name, r1, r2) in enumerate([("Dust II", 13, 5)] * 10 + [("Mirage", 5, 13)] * 10):
        # Päivät suhteessa tähän päivään, jotta testi toimii myös tulevaisuudessa.
        played_at = (date.today() - timedelta(days=i + 1)).isoformat() + " 12:00"
        match = {"played_at": played_at, "best_of": 1, "score1": int(r1 > r2),
                 "score2": int(r2 > r1), "finished": True, "hltv_id": None,
                 "maps": [{"number": 1, "name": name, "rounds1": r1, "rounds2": r2, "finished": True}]}
        maps_repo.save_series(conn, "Testi", match, team, rival)

    stats = team_map_stats(conn, team, pool)
    assert stats["best"] == "Dust II"
    assert stats["ban"] == "Ancient"
    assert stats["maps"]["Mirage"]["rate"] == 0
    assert stats["maps"]["Dust II"]["round_diff"] == 80
