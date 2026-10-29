"""
Testit kokoonpanojen synkronoinnille: huomataanko siirrot oikein?

Jokainen testi käyttää omaa tyhjää muistissa olevaa tietokantaa (":memory:"),
joten testit eivät koske oikeaan dataan.
"""

import pytest

from app.database.db import connect, init_schema
from app.players import repository as players_repo
from app.roster.service import sync_team_roster
from app.teams import repository as teams_repo


# fixture = testien yhteinen valmistelu. Jokainen testi, jolla on parametri
# "conn", saa uuden tyhjän tietokannan.
@pytest.fixture
def conn():
    connection = connect(":memory:")
    init_schema(connection)
    yield connection
    connection.close()


def team(name, *nicknames):
    """Apufunktio: luo joukkueen datan lyhyesti."""
    return {"name": name, "players": [{"nickname": n} for n in nicknames]}


def test_new_team_players_are_added(conn):
    changes = sync_team_roster(conn, team("A", "p1", "p2"), "2026-01-01")
    assert [c.kind for c in changes] == ["liittyi", "liittyi"]


def test_player_leaving_closes_membership(conn):
    sync_team_roster(conn, team("A", "p1", "p2"), "2026-01-01")
    changes = sync_team_roster(conn, team("A", "p1"), "2026-02-01")

    assert len(changes) == 1 and changes[0].kind == "lähti"
    team_id = teams_repo.get_or_create_team(conn, "A")
    former = teams_repo.get_former_players(conn, team_id)
    assert former[0]["nickname"] == "p2"
    assert former[0]["end_date"] == "2026-02-01"


def test_transfer_between_teams_is_detected(conn):
    sync_team_roster(conn, team("A", "p1"), "2026-01-01")
    sync_team_roster(conn, team("B", "p2"), "2026-01-01")

    # p1 siirtyy A:sta B:hen. Ensin päivitetään B, joka "vie" pelaajan.
    changes = sync_team_roster(conn, team("B", "p2", "p1"), "2026-03-01")
    assert changes[0].kind == "siirto"
    assert changes[0].from_team == "A"

    # Historiaan jää kaksi jaksoa: A (päättynyt) ja B (käynnissä).
    player_id = players_repo.get_or_create_player(conn, "p1")
    history = players_repo.get_player_history(conn, player_id)
    assert [(h["team_name"], h["end_date"]) for h in history] == [("B", None), ("A", "2026-03-01")]


def test_transfer_detected_when_old_team_synced_first(conn):
    sync_team_roster(conn, team("A", "p1"), "2026-01-01")
    sync_team_roster(conn, team("B", "p2"), "2026-01-01")

    sync_team_roster(conn, team("A"), "2026-03-01")  # A päivitetään ensin: p1 lähti
    changes = sync_team_roster(conn, team("B", "p2", "p1"), "2026-03-01")
    assert changes[0].kind == "siirto"
    assert changes[0].from_team == "A"


def test_roster_on_date_respects_history(conn):
    sync_team_roster(conn, team("A", "p1", "p2"), "2026-01-01")
    sync_team_roster(conn, team("A", "p1", "p3"), "2026-06-01")
    team_id = teams_repo.get_or_create_team(conn, "A")

    ids = lambda *names: frozenset(players_repo.get_or_create_player(conn, n) for n in names)
    assert teams_repo.get_player_ids_on_date(conn, team_id, "2026-03-01") == ids("p1", "p2")
    assert teams_repo.get_player_ids_on_date(conn, team_id, "2026-07-01") == ids("p1", "p3")


def test_same_match_from_two_sources_saved_once(conn):
    from app.matches import repository as matches_repo

    a = teams_repo.get_or_create_team(conn, "A")
    b = teams_repo.get_or_create_team(conn, "B")
    # Valvelta pelkkä päivä, Liquipediasta kellonaika ja joukkueet eri järjestyksessä.
    assert matches_repo.save_match(conn, "2026-10-27", None, None, "completed", a, b, winner_id=a, source="vrs")
    assert not matches_repo.save_match(conn, "2026-10-27 17:50", "X", 3, "completed", b, a, 0, 2, source="liquipedia")
    assert len(matches_repo.get_all_completed(conn)) == 1


def test_started_match_moves_from_upcoming_to_live(conn):
    from datetime import datetime, timedelta, timezone

    from app.matches import repository as matches_repo

    a = teams_repo.get_or_create_team(conn, "A")
    b = teams_repo.get_or_create_team(conn, "B")
    fmt = "%Y-%m-%d %H:%M"
    now = datetime.now(timezone.utc)
    started = (now - timedelta(minutes=30)).strftime(fmt)
    later = (now + timedelta(hours=5)).strftime(fmt)
    matches_repo.save_match(conn, started, None, 3, "upcoming", a, b)
    matches_repo.save_match(conn, later, None, 3, "upcoming", b, a)

    # Alkanut ottelu on "menossa", vaikka Liquipedia ei olisi vielä merkinnyt sitä.
    assert [m["played_at"] for m in matches_repo.get_live(conn)] == [started]
    assert [m["played_at"] for m in matches_repo.get_upcoming(conn)] == [later]
