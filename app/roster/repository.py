"""
Kokoonpanojaksojen tietokantaoperaatiot: jakson avaaminen, sulkeminen
ja viimeisimpien siirtojen haku.
"""

import sqlite3


def open_membership(conn, player_id: int, team_id: int, role, start_date: str) -> None:
    """Aloittaa uuden jakson: pelaaja liittyy joukkueeseen."""
    conn.execute(
        """
        INSERT INTO roster_history (player_id, team_id, role, start_date)
        VALUES (?, ?, ?, ?)
        """,
        (player_id, team_id, role, start_date),
    )


def close_membership(conn, membership_id: int, end_date: str) -> None:
    """Päättää jakson: pelaaja lähtee joukkueesta.

    Riviä EI poisteta, vaan siihen merkitään loppupäivä. Näin historia säilyy.
    """
    conn.execute(
        "UPDATE roster_history SET end_date = ? WHERE id = ?",
        (end_date, membership_id),
    )


def update_role(conn, membership_id: int, role: str) -> None:
    """Päivittää pelaajan roolin nykyisessä joukkueessa (esim. Rifler -> IGL)."""
    conn.execute(
        "UPDATE roster_history SET role = ? WHERE id = ?", (role, membership_id)
    )


def get_recent_changes(conn, limit: int = 10) -> list[sqlite3.Row]:
    """Viimeisimmät liittymiset ja lähdöt yhdessä listassa.

    UNION ALL yhdistää kahden kyselyn tulokset peräkkäin:
      1. kysely: jokainen jakson alku = "liittyi"
      2. kysely: jokainen jakson loppu = "lähti"
    Lopuksi koko lista järjestetään päivämäärän mukaan.
    """
    return conn.execute(
        """
        SELECT r.start_date AS date, 'liittyi' AS kind,
               p.id AS player_id, p.nickname, t.id AS team_id, t.name AS team_name
        FROM roster_history r
        JOIN players p ON p.id = r.player_id
        JOIN teams t ON t.id = r.team_id

        UNION ALL

        SELECT r.end_date AS date, 'lähti' AS kind,
               p.id, p.nickname, t.id, t.name
        FROM roster_history r
        JOIN players p ON p.id = r.player_id
        JOIN teams t ON t.id = r.team_id
        WHERE r.end_date IS NOT NULL

        ORDER BY date DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
