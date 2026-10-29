"""
Joukkueiden tietokantahaut.

"Repository" tarkoittaa tiedostoa, jossa on VAIN SQL-kyselyt yhdelle
asialle. Muu koodi (sivut, ennustukset) kutsuu näitä funktioita eikä
kirjoita SQL:ää itse. Näin kyselyt löytyvät aina samasta paikasta.
"""

import sqlite3

from app.teams.names import name_key


def get_all_teams(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Kaikki joukkueet ja niiden nykyinen pelaajamäärä."""
    # LEFT JOIN ottaa mukaan myös joukkueet, joilla ei ole yhtään pelaajaa.
    # Ehto "end_date IS NULL" laskee vain nykyiset pelaajat.
    return conn.execute(
        """
        SELECT t.*, COUNT(r.id) AS player_count
        FROM teams t
        LEFT JOIN roster_history r
               ON r.team_id = t.id AND r.end_date IS NULL
        GROUP BY t.id
        -- Rankatut joukkueet ensin sijoituksen mukaan, sitten muut aakkosjärjestyksessä.
        ORDER BY t.vrs_rank IS NULL, t.vrs_rank, t.name COLLATE NOCASE
        """
    ).fetchall()


def get_team(conn: sqlite3.Connection, team_id: int) -> sqlite3.Row | None:
    """Yksi joukkue id:n perusteella, tai None jos sitä ei ole."""
    return conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()


def find_team(conn, *names: str) -> sqlite3.Row | None:
    """Etsii joukkueen yhdellä tai useammalla nimellä (esim. pitkä ja lyhyt nimi).

    Palauttaa ensimmäisen osuman tai None, jos mikään nimistä ei löydy.
    """
    for name in names:
        if not name:
            continue
        row = conn.execute("SELECT * FROM teams WHERE name_key = ?", (name_key(name),)).fetchone()
        if row:
            return row
    return None


def get_or_create_team(conn, name: str, region=None, country=None) -> int:
    """Palauttaa joukkueen id:n ja luo joukkueen, jos sitä ei vielä ole.

    Joukkue tunnistetaan nimiavaimella (katso names.py), joten "Team Vitality"
    ja "Vitality" ovat sama joukkue. Olemassa olevan joukkueen puuttuvat tiedot
    (alue, maa) täydennetään, mutta olemassa olevia ei ylikirjoiteta tyhjällä.
    """
    row = find_team(conn, name)
    if row:
        # COALESCE(a, b) palauttaa ensimmäisen arvon, joka ei ole NULL.
        conn.execute(
            """
            UPDATE teams
            SET region = COALESCE(?, region), country = COALESCE(?, country)
            WHERE id = ?
            """,
            (region, country, row["id"]),
        )
        return row["id"]

    cursor = conn.execute(
        "INSERT INTO teams (name, name_key, region, country) VALUES (?, ?, ?, ?)",
        (name, name_key(name), region, country),
    )
    return cursor.lastrowid


def clear_vrs(conn) -> None:
    """Tyhjentää kaikkien joukkueiden VRS-tiedot ennen uuden listan tallentamista.

    Näin joukkue, joka putoaa listalta, ei jää näyttämään vanhaa sijoitusta.
    """
    conn.execute("UPDATE teams SET vrs_rank = NULL, vrs_points = NULL, vrs_date = NULL")


def update_vrs(conn, team_id: int, rank: int, points: float, date: str) -> None:
    """Tallentaa joukkueelle Valven rankingin sijoituksen ja pisteet."""
    conn.execute(
        "UPDATE teams SET vrs_rank = ?, vrs_points = ?, vrs_date = ? WHERE id = ?",
        (rank, points, date, team_id),
    )


def set_liquipedia_page(conn, team_id: int, page: str) -> None:
    """Tallentaa joukkueen Liquipedia-sivun nimen (esim. "Team Vitality")."""
    conn.execute("UPDATE teams SET liquipedia_page = ? WHERE id = ?", (page, team_id))


def set_coach(conn, team_id: int, coach: str | None) -> None:
    conn.execute("UPDATE teams SET coach = ? WHERE id = ?", (coach, team_id))


def get_current_roster(conn, team_id: int) -> list[sqlite3.Row]:
    """Joukkueen nykyiset pelaajat (jaksot, joilla ei ole loppupäivää)."""
    return conn.execute(
        """
        SELECT p.*, r.id AS membership_id, r.role, r.start_date
        FROM roster_history r
        JOIN players p ON p.id = r.player_id
        WHERE r.team_id = ? AND r.end_date IS NULL
        ORDER BY p.nickname COLLATE NOCASE
        """,
        (team_id,),
    ).fetchall()


def get_former_players(conn, team_id: int) -> list[sqlite3.Row]:
    """Pelaajat, jotka ovat joskus pelanneet joukkueessa, mutta lähteneet."""
    return conn.execute(
        """
        SELECT p.*, r.role, r.start_date, r.end_date
        FROM roster_history r
        JOIN players p ON p.id = r.player_id
        WHERE r.team_id = ? AND r.end_date IS NOT NULL
        ORDER BY r.end_date DESC
        """,
        (team_id,),
    ).fetchall()


def get_player_ids_on_date(conn, team_id: int, date: str) -> frozenset[int]:
    """Keitä joukkueessa pelasi tiettynä päivänä (esim. ottelupäivänä).

    Palauttaa joukon (frozenset) pelaajien id:itä. Joukoilla on helppo laskea
    eroja: {1,2,3} - {1,2,4} = {3}.
    """
    rows = conn.execute(
        """
        SELECT player_id FROM roster_history
        WHERE team_id = ?
          AND start_date <= ?
          AND (end_date IS NULL OR end_date > ?)
        """,
        (team_id, date, date),
    ).fetchall()
    return frozenset(row["player_id"] for row in rows)


def get_team_matches(conn, team_id: int, limit: int = 10) -> list[sqlite3.Row]:
    """Joukkueen viimeisimmät pelatut ottelut uusimmasta vanhimpaan."""
    # Tauluun teams liitytään kahdesti (t1 ja t2), koska ottelussa on kaksi joukkuetta.
    return conn.execute(
        """
        SELECT m.*, t1.name AS team1_name, t2.name AS team2_name
        FROM matches m
        JOIN teams t1 ON t1.id = m.team1_id
        JOIN teams t2 ON t2.id = m.team2_id
        WHERE (m.team1_id = ? OR m.team2_id = ?) AND m.status = 'completed'
        ORDER BY m.played_at DESC
        LIMIT ?
        """,
        (team_id, team_id, limit),
    ).fetchall()
