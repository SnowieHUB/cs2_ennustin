"""
Pelaajien tietokantahaut.

Sama periaate kuin teams/repository.py:ssä: kaikki pelaajiin liittyvä
SQL on tässä tiedostossa.
"""

import sqlite3


def get_all_players(conn, search: str = "") -> list[sqlite3.Row]:
    """Kaikki pelaajat ja heidän nykyinen joukkueensa.

    search: vapaaehtoinen hakusana, jolla suodatetaan nimimerkkiä tai
    oikeaa nimeä. Tyhjä hakusana palauttaa kaikki pelaajat.
    """
    # LIKE '%sana%' löytää rivit, joissa "sana" esiintyy missä kohtaa tahansa.
    pattern = f"%{search}%"
    return conn.execute(
        """
        SELECT p.*, t.id AS team_id, t.name AS team_name, r.role
        FROM players p
        LEFT JOIN roster_history r
               ON r.player_id = p.id AND r.end_date IS NULL
        LEFT JOIN teams t ON t.id = r.team_id
        WHERE p.nickname LIKE ? OR COALESCE(p.real_name, '') LIKE ?
        ORDER BY p.nickname COLLATE NOCASE
        """,
        (pattern, pattern),
    ).fetchall()


def get_player(conn, player_id: int) -> sqlite3.Row | None:
    """Yksi pelaaja id:n perusteella."""
    return conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()


def get_or_create_player(conn, nickname: str, real_name=None, country=None) -> int:
    """Palauttaa pelaajan id:n ja luo pelaajan, jos sitä ei vielä ole.

    Olemassa olevan pelaajan puuttuvat tiedot täydennetään.
    """
    row = conn.execute(
        "SELECT id FROM players WHERE nickname = ?", (nickname,)
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE players
            SET real_name = COALESCE(?, real_name), country = COALESCE(?, country)
            WHERE id = ?
            """,
            (real_name, country, row["id"]),
        )
        return row["id"]

    cursor = conn.execute(
        "INSERT INTO players (nickname, real_name, country) VALUES (?, ?, ?)",
        (nickname, real_name, country),
    )
    return cursor.lastrowid


def get_player_history(conn, player_id: int) -> list[sqlite3.Row]:
    """Pelaajan kaikki joukkueet uusimmasta vanhimpaan (ura-historia)."""
    return conn.execute(
        """
        SELECT r.*, t.name AS team_name
        FROM roster_history r
        JOIN teams t ON t.id = r.team_id
        WHERE r.player_id = ?
        ORDER BY r.start_date DESC
        """,
        (player_id,),
    ).fetchall()


def get_latest_membership(conn, player_id: int) -> sqlite3.Row | None:
    """Pelaajan viimeisin joukkuejakso (voi olla käynnissä tai päättynyt).

    Kokoonpanojen synkronointi käyttää tätä tunnistaakseen siirrot:
    jos pelaajan edellinen jakso on yhä käynnissä tai päättyi samana
    päivänä, kun hän liittyy uuteen joukkueeseen, kyse on siirrosta.
    """
    return conn.execute(
        """
        SELECT r.*, t.name AS team_name
        FROM roster_history r
        JOIN teams t ON t.id = r.team_id
        WHERE r.player_id = ?
        ORDER BY (r.end_date IS NULL) DESC, r.end_date DESC, r.start_date DESC
        LIMIT 1
        """,
        (player_id,),
    ).fetchone()
