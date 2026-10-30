"""
Testit Mallin tilasto -sivun laskennalle.
"""

from app.database.db import connect, init_schema
from app.matches import repository as matches_repo
from app.odds import repository as odds_repo
from app.stats.service import get_model_stats
from app.teams import repository as teams_repo


def test_model_and_odds_hit_rates(monkeypatch):
    from app.predictions import service

    conn = connect(":memory:")
    init_schema(conn)
    a = teams_repo.get_or_create_team(conn, "A")
    b = teams_repo.get_or_create_team(conn, "B")
    today = matches_repo.now_utc(hours_ago=24)
    matches_repo.save_match(conn, today, None, 3, "completed", a, b, 2, 0)  # A voitti
    match_id = conn.execute("SELECT id FROM matches").fetchone()[0]
    # Pinnacle piti B:tä suosikkina (A:n kerroin 3.0).
    odds_repo.save_odds(conn, "f1", a, b, today, 3.0, 1.4, "pinnacle", today)

    # Malli antoi ennen ottelua A:lle 70 % (asetetaan suoraan, ettei tarvita opetettua mallia).
    state = service.get_state(conn)
    state.pre_match[match_id] = 0.7
    monkeypatch.setattr(service, "get_state", lambda conn: state)

    stats = get_model_stats(conn, days=7, max_rank=None)
    assert (stats["model"]["hits"], stats["model"]["total"]) == (1, 1)
    assert (stats["odds"]["hits"], stats["odds"]["total"]) == (0, 1)  # Pinnaclen suosikki hävisi
    # 70 %:n ennuste kuuluu luotettavuustaulukon riville 70-80 %.
    assert [row["total"] for row in stats["calibration"]] == [0, 0, 1, 0]
