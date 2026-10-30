"""
Testit kertoimille: OddsPapin vastauksen jäsennys ja kertoimien yhdistäminen otteluun.
"""

import pytest

from app.database.db import connect, init_schema
from app.odds import repository as odds_repo
from app.sync.sources.oddspapi_source import parse_fixture, parse_latest_odds
from app.teams import repository as teams_repo


@pytest.fixture
def conn():
    connection = connect(":memory:")
    init_schema(connection)
    yield connection
    connection.close()


def test_parse_latest_odds_takes_newest_price():
    def entry(created, price):
        return {"createdAt": created, "price": price, "active": True}

    data = {"bookmakers": {"pinnacle": {"markets": {"171": {"outcomes": {
        "171": {"players": {"0": [entry("2026-10-30T10:00:00Z", 1.60), entry("2026-10-29T19:00:00Z", 1.70)]}},
        "172": {"players": {"0": [entry("2026-10-30T10:00:00Z", 2.41), entry("2026-10-29T19:00:00Z", 2.20)]}},
    }}}}}}
    assert parse_latest_odds(data) == (1.60, 2.41)


def test_parse_latest_odds_without_market_returns_none():
    assert parse_latest_odds({"bookmakers": {"pinnacle": {"markets": {}}}}) is None


def test_parse_fixture():
    fixture = parse_fixture({
        "fixtureId": "id1", "startTime": "2026-10-30T15:00:00.000Z",
        "participant1Name": "MOUZ", "participant1ShortName": "MOUZ", "participant1Abbr": "MOU",
        "participant2Name": "Furia",  # lyhyet nimet voivat puuttua
    })
    assert fixture["start_time"] == "2026-10-30 15:00"
    assert fixture["team2_names"] == ("Furia", None, None)


def test_find_odds_swaps_prices_when_teams_reversed(conn):
    mouz = teams_repo.get_or_create_team(conn, "MOUZ")
    furia = teams_repo.get_or_create_team(conn, "FURIA")
    odds_repo.save_odds(conn, "id1", mouz, furia, "2026-10-30 15:00", 1.60, 2.41, "pinnacle", "2026-10-30 12:00")

    # Sivulla FURIA on joukkue 1 ja kellonaika on vähän eri.
    odds = odds_repo.find_odds(conn, furia, mouz, "2026-10-30 15:30")
    assert (odds["price1"], odds["price2"]) == (2.41, 1.60)
    # Eri päivän ottelu ei saa näitä kertoimia.
    assert odds_repo.find_odds(conn, furia, mouz, "2026-11-05 15:00") is None


def test_sync_stops_when_quota_used_and_footer_shows_notice(conn, tmp_path, monkeypatch):
    from app import config, create_app
    from app.sync import sync_odds as sync_module

    monkeypatch.setattr(config, "ODDS_STATUS_PATH", tmp_path / "odds_status.json")
    monkeypatch.setattr(sync_module.source, "read_api_key", lambda: "testiavain")
    monkeypatch.setattr(sync_module.source, "requests_left", lambda key: 3)

    def fail(*args, **kwargs):
        raise AssertionError("maksullista hakua ei saa tehdä, kun kiintiö on käytetty")

    monkeypatch.setattr(sync_module.source, "fetch_fixtures", fail)

    assert "kiintiö" in sync_module.sync_odds(conn)

    # Sivun alalaidassa näkyy ilmoitus.
    app = create_app(database_path=tmp_path / "test.db")
    with app.app_context():
        init_schema(connect(app.config["DATABASE_PATH"]))
    html = app.test_client().get("/").get_data(as_text=True)
    assert "kuukausikiintiö on käytetty" in html


def test_notice_hidden_after_month_changes(tmp_path, monkeypatch):
    import json

    from app import config
    from app.odds import status

    path = tmp_path / "odds_status.json"
    monkeypatch.setattr(config, "ODDS_STATUS_PATH", path)
    path.write_text(json.dumps({"quota_full": True, "month": "2000-01"}))
    assert status.quota_full() is False  # vanha kuukausi: kiintiö on jo nollautunut


def test_recent_fetch_is_not_repeated(conn, tmp_path, monkeypatch):
    from app import config
    from app.sync import sync_odds as sync_module

    monkeypatch.setattr(config, "ODDS_STATUS_PATH", tmp_path / "odds_status.json")
    monkeypatch.setattr(sync_module.source, "read_api_key", lambda: "testiavain")
    monkeypatch.setattr(sync_module.source, "requests_left", lambda key: 100)
    calls = []
    monkeypatch.setattr(sync_module.source, "fetch_fixtures", lambda key: calls.append(1) or [])

    sync_module.sync_odds(conn)              # ensimmäinen haku tehdään
    message = sync_module.sync_odds(conn)    # heti perään: ohitetaan
    assert len(calls) == 1
    assert "ohitetaan" in message
