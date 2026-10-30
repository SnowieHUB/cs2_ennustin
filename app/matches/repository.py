"""
Otteluiden tietokantahaut: tulevat ottelut, pelatut tulokset ja tallennus.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

# Yhteinen SELECT-alku, jota käytetään useassa kyselyssä. Joukkueiden tiedot
# liitetään kahdesti (t1 ja t2), koska ottelussa on kaksi joukkuetta.
_MATCH_SELECT = """
    SELECT m.*,
           t1.name AS team1_name, t1.vrs_rank AS team1_rank,
           t2.name AS team2_name, t2.vrs_rank AS team2_rank
    FROM matches m
    JOIN teams t1 ON t1.id = m.team1_id
    JOIN teams t2 ON t2.id = m.team2_id
"""


# Kuinka kauan ottelu voi enintään olla käynnissä. Bo3 kestää yleensä 2-4 tuntia.
# Joskus Liquipedia jättää ottelun "käynnissä olevaksi" vielä päiviä sen jälkeen,
# kun se on loppunut. Tätä vanhempia otteluita ei siksi näytetä käynnissä olevina.
LIVE_MAX_HOURS = 8


def now_utc(hours_ago: float = 0) -> str:
    """Nykyhetki (tai hours_ago tuntia sitten) samassa muodossa kuin played_at (UTC),
    esim. "2026-10-29 15:05"."""
    moment = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return moment.strftime("%Y-%m-%d %H:%M")


def _filters(max_rank, team_id) -> tuple[list[str], list]:
    """Yhteiset vapaaehtoiset suodattimet: tier 1 -raja ja yksittäinen joukkue.

    Kysely rakennetaan paloista: ehdot lisätään vain, jos suodatin on käytössä.
    """
    conditions: list[str] = []
    params: list = []
    if max_rank is not None:
        conditions.append("(t1.vrs_rank <= ? OR t2.vrs_rank <= ?)")
        params += [max_rank, max_rank]
    if team_id is not None:
        conditions.append("(m.team1_id = ? OR m.team2_id = ?)")
        params += [team_id, team_id]
    return conditions, params


def get_upcoming(conn, max_rank: int | None = None, team_id: int | None = None, limit: int = 50):
    """Tulevat ottelut, joiden aloitusaika on vielä edessä (lähin ensin).

    max_rank: jos annettu, näytetään vain ottelut, joissa ainakin toinen
              joukkue on VRS-rankingissa tällä sijalla tai paremmalla (tier 1 -suodatin).
    team_id:  jos annettu, näytetään vain tämän joukkueen ottelut.
    """
    conditions, params = _filters(max_rank, team_id)
    conditions = ["m.status = 'upcoming'", "m.played_at > ?", *conditions]
    sql = _MATCH_SELECT + " WHERE " + " AND ".join(conditions) + " ORDER BY m.played_at LIMIT ?"
    return conn.execute(sql, (now_utc(), *params, limit)).fetchall()


def get_live(conn, max_rank: int | None = None, team_id: int | None = None):
    """Käynnissä olevat ottelut.

    Mukaan tulevat:
      - ottelut, jotka Liquipedia on merkinnyt käynnissä oleviksi (status 'live')
      - ottelut, joiden aloitusaika on jo mennyt, mutta joista ei vielä ole tulosta.
        Ne ovat todennäköisesti käynnissä, vaikka päivitystä ei ole ajettu.
    Kun tulos tulee seuraavassa päivityksessä, ottelu siirtyy tuloksiin.
    Yli LIVE_MAX_HOURS tuntia sitten alkaneita ei näytetä (unohtuneet merkinnät).
    """
    conditions, params = _filters(max_rank, team_id)
    conditions = [
        "(m.status = 'live' OR (m.status = 'upcoming' AND m.played_at <= ?))",
        "m.played_at > ?",
        *conditions,
    ]
    sql = _MATCH_SELECT + " WHERE " + " AND ".join(conditions) + " ORDER BY m.played_at"
    return conn.execute(sql, (now_utc(), now_utc(LIVE_MAX_HOURS), *params)).fetchall()


def get_recent_results(conn, max_rank: int | None = None, limit: int = 20):
    """Viimeksi pelatut ottelut (uusin ensin)."""
    conditions, params = _filters(max_rank, None)
    conditions = ["m.status = 'completed'", *conditions]
    sql = _MATCH_SELECT + " WHERE " + " AND ".join(conditions) + " ORDER BY m.played_at DESC LIMIT ?"
    return conn.execute(sql, (*params, limit)).fetchall()


def delete_upcoming(conn) -> None:
    """Poistaa kaikki tulevat ja käynnissä olevat ottelut.

    Synkronointi hakee tulevat ottelut joka kerta kokonaan uudelleen, koska
    aikataulut muuttuvat ja TBD-paikat täyttyvät turnauksen edetessä.
    """
    conn.execute("DELETE FROM matches WHERE status IN ('upcoming', 'live')")


def save_match(conn, played_at, event, best_of, status, team1_id, team2_id,
               team1_score=None, team2_score=None, winner_id=None, source=None) -> bool:
    """Tallentaa ottelun. Palauttaa True, jos ottelu oli uusi.

    Pelatuilla otteluilla tarkistetaan ensin, onko samojen joukkueiden ottelu
    jo tallennettu SAMANA PÄIVÄNÄ. Tämä on tarpeen, koska Valvelta tulee pelkkä
    päivä (2026-10-27) ja Liquipediasta kellonaika (2026-10-27 17:50), eikä
    sama ottelu saa tulla kahdesti.

    INSERT OR IGNORE ohittaa rivin hiljaa, jos täsmälleen sama rivi on jo
    olemassa (katso UNIQUE schema.sql:ssä).
    """
    if status == "completed" and _completed_exists_on_day(conn, played_at[:10], team1_id, team2_id):
        return False

    # Voittaja päätellään tuloksesta, jos sitä ei annettu erikseen.
    if winner_id is None and team1_score is not None and team2_score is not None:
        if team1_score > team2_score:
            winner_id = team1_id
        elif team2_score > team1_score:
            winner_id = team2_id

    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO matches
            (played_at, event, best_of, status, team1_id, team2_id,
             team1_score, team2_score, winner_id, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (played_at, event, best_of, status, team1_id, team2_id,
         team1_score, team2_score, winner_id, source),
    )
    return cursor.rowcount == 1


def _completed_exists_on_day(conn, day: str, team1_id: int, team2_id: int) -> bool:
    """Onko näiden joukkueiden välillä jo pelattu ottelu tänä päivänä (kumpi tahansa järjestys)?"""
    row = conn.execute(
        """
        SELECT 1 FROM matches
        WHERE status = 'completed' AND substr(played_at, 1, 10) = ?
          AND ((team1_id = ? AND team2_id = ?) OR (team1_id = ? AND team2_id = ?))
        """,
        (day, team1_id, team2_id, team2_id, team1_id),
    ).fetchone()
    return row is not None


def get_all_completed(conn) -> list[sqlite3.Row]:
    """Kaikki pelatut ottelut aikajärjestyksessä. Ennustemalli käy nämä läpi."""
    return conn.execute(
        "SELECT id, played_at, team1_id, team2_id, winner_id FROM matches "
        "WHERE status = 'completed' ORDER BY played_at, id"
    ).fetchall()
