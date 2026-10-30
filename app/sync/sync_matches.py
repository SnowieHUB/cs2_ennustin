"""
Otteluiden synkronointi Liquipediasta (ja tarvittaessa JSON-tiedostosta).
"""

import json
from pathlib import Path

from app.matches import repository as matches_repo
from app.sync.sources.liquipedia_source import fetch_matches_html, parse_matches
from app.teams import repository as teams_repo


def _resolve_team(conn, full_name: str, short_name: str, page: str | None = None) -> int:
    """Etsii joukkueen pitkällä tai lyhyellä nimellä, tai luo uuden.

    Esim. Liquipedian "Natus Vincere" / "NAVI" löytyy VRS:n nimellä "Natus Vincere".
    Jos joukkuetta ei löydy (ei VRS:n top-listalla), luodaan uusi joukkue pitkällä nimellä.
    """
    team = teams_repo.find_team(conn, full_name, short_name)
    team_id = team["id"] if team else teams_repo.get_or_create_team(conn, full_name)
    if page:
        # Tallennetaan sivun nimi, jotta pelaajien tiedot voidaan hakea sieltä myöhemmin.
        teams_repo.set_liquipedia_page(conn, team_id, page)
    return team_id


def sync_liquipedia_matches(conn) -> tuple[int, int]:
    """Hakee tulevat ottelut ja tuoreet tulokset.

    Palauttaa parin (tulevia otteluita, uusia tuloksia).
    """
    matches = parse_matches(fetch_matches_html())

    upcoming = 0
    new_results = 0
    try:
        # Tulevat ja käynnissä olevat ottelut haetaan joka kerta kokonaan uudelleen.
        # Kun käynnissä oleva ottelu loppuu, se on seuraavalla haulla pelattujen
        # listalla ja tallentuu tulokseksi.
        matches_repo.delete_upcoming(conn)
        for m in matches:
            team1_id = _resolve_team(conn, m["team1"], m["team1_short"], m["team1_page"])
            team2_id = _resolve_team(conn, m["team2"], m["team2_short"], m["team2_page"])
            is_new = matches_repo.save_match(
                conn, m["played_at"], m["event"], m["best_of"], m["status"],
                team1_id, team2_id, m["score1"], m["score2"], source="liquipedia",
                event_url=m["event_url"], stream_url=m["stream_url"],
            )
            if m["status"] in ("upcoming", "live"):
                upcoming += 1
            elif is_new:
                new_results += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return upcoming, new_results


def load_matches_from_json(conn, path: str | Path) -> int:
    """Lataa pelattuja otteluita omasta JSON-tiedostosta. Palauttaa uusien määrän.

    Muoto: {"matches": [{"date": "2026-01-12", "event": "...", "team1": "...",
                         "team2": "...", "score1": 2, "score2": 1, "best_of": 3}]}
    """
    with Path(path).open(encoding="utf-8") as file:
        matches = json.load(file)["matches"]

    added = 0
    for m in matches:
        team1_id = teams_repo.get_or_create_team(conn, m["team1"])
        team2_id = teams_repo.get_or_create_team(conn, m["team2"])
        if matches_repo.save_match(conn, m["date"], m.get("event"), m.get("best_of"), "completed",
                                   team1_id, team2_id, m["score1"], m["score2"], source="json"):
            added += 1
    conn.commit()
    return added
