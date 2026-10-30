"""
Turnaussivujen otteluiden (sarjojen) ja karttojen tallennus ja haku.
"""

# Sama aikaikkuna kuin kertoimissa: 12 tuntia (0.5 päivää).
MAX_TIME_DIFF_DAYS = 0.5


def get_template_pages(conn) -> dict[str, str]:
    """Kaikki tunnetut joukkuelyhenteet: {"vit": "Team Vitality", ...}"""
    return {row["template"]: row["page"] for row in conn.execute("SELECT template, page FROM team_templates")}


def save_template_page(conn, template: str, page: str) -> None:
    conn.execute("INSERT OR REPLACE INTO team_templates (template, page) VALUES (?, ?)", (template, page))


def save_series(conn, event_page, match, team1_id, team2_id) -> int:
    """Tallentaa tai päivittää sarjan ja sen kartat. Palauttaa sarjan id:n.

    match on liquipedia_tournaments.parse_tournament_matches()-funktion sanakirja.
    ON CONFLICT päivittää olemassa olevan rivin (esim. käynnissä olevan ottelun tilanne).
    """
    conn.execute(
        """
        INSERT INTO series (event_page, played_at, team1_id, team2_id, best_of, score1, score2, finished, hltv_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (event_page, played_at, team1_id, team2_id) DO UPDATE SET
            best_of = excluded.best_of, score1 = excluded.score1, score2 = excluded.score2,
            finished = excluded.finished, hltv_id = excluded.hltv_id
        """,
        (event_page, match["played_at"], team1_id, team2_id, match["best_of"],
         match["score1"], match["score2"], int(match["finished"]), match["hltv_id"]),
    )
    series_id = conn.execute(
        "SELECT id FROM series WHERE event_page = ? AND played_at = ? AND team1_id = ? AND team2_id = ?",
        (event_page, match["played_at"], team1_id, team2_id),
    ).fetchone()["id"]

    # Kartat kirjoitetaan aina kokonaan uudelleen: vanhat pois, uudet tilalle.
    conn.execute("DELETE FROM series_maps WHERE series_id = ?", (series_id,))
    conn.executemany(
        "INSERT INTO series_maps (series_id, map_number, map_name, rounds1, rounds2, finished) VALUES (?, ?, ?, ?, ?, ?)",
        [(series_id, m["number"], m["name"], m["rounds1"], m["rounds2"], int(m["finished"])) for m in match["maps"]],
    )
    return series_id


def find_series(conn, team1_id: int, team2_id: int, played_at: str) -> dict | None:
    """Etsii ottelun sarjan ja kartat. Tulokset käännetään ottelun järjestykseen (team1 ensin)."""
    row = conn.execute(
        """
        SELECT * FROM series
        WHERE ((team1_id = ? AND team2_id = ?) OR (team1_id = ? AND team2_id = ?))
          AND abs(julianday(played_at) - julianday(?)) < ?
        ORDER BY abs(julianday(played_at) - julianday(?))
        LIMIT 1
        """,
        (team1_id, team2_id, team2_id, team1_id, played_at, MAX_TIME_DIFF_DAYS, played_at),
    ).fetchone()
    if row is None:
        return None

    swap = row["team1_id"] != team1_id  # joukkueet toisin päin kuin ottelussa
    maps = []
    for m in conn.execute("SELECT * FROM series_maps WHERE series_id = ? ORDER BY map_number", (row["id"],)):
        r1, r2 = (m["rounds2"], m["rounds1"]) if swap else (m["rounds1"], m["rounds2"])
        maps.append({"name": m["map_name"], "rounds1": r1, "rounds2": r2, "finished": bool(m["finished"])})
    score1, score2 = (row["score2"], row["score1"]) if swap else (row["score1"], row["score2"])
    return {
        "score1": score1, "score2": score2, "finished": bool(row["finished"]),
        "hltv_id": row["hltv_id"], "best_of": row["best_of"], "maps": maps,
    }


def earliest_series_date(conn) -> str | None:
    """Vanhimman tallennetun sarjan päivä. None, jos sarjoja ei vielä ole."""
    return conn.execute("SELECT MIN(played_at) FROM series").fetchone()[0]


# Mukaan vain kartat, joiden tulos on varmasti tiedossa (kierrokset kirjattu, ei tasan).
_VALID_MAP = "m.finished = 1 AND m.rounds1 IS NOT NULL AND m.rounds2 IS NOT NULL AND m.rounds1 <> m.rounds2"


def get_team_map_rows(conn, team_id: int, since: str) -> list:
    """Joukkueen tulokset kartoittain annetusta päivästä alkaen.

    CASE WHEN valitsee joukkueen näkökulman: jos joukkue on sarjassa joukkue 2,
    sen kierrokset ovat rounds2-sarakkeessa.
    """
    return conn.execute(
        f"""
        SELECT m.map_name AS name,
               COUNT(*) AS played,
               SUM(CASE WHEN (s.team1_id = :team AND m.rounds1 > m.rounds2)
                          OR (s.team2_id = :team AND m.rounds2 > m.rounds1) THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN s.team1_id = :team THEN m.rounds1 - m.rounds2
                        ELSE m.rounds2 - m.rounds1 END) AS round_diff
        FROM series s JOIN series_maps m ON m.series_id = s.id
        WHERE (s.team1_id = :team OR s.team2_id = :team) AND s.played_at >= :since AND {_VALID_MAP}
        GROUP BY m.map_name
        """,
        {"team": team_id, "since": since},
    ).fetchall()


def get_map_counts(conn, since: str) -> dict[str, int]:
    """Kaikkien pelattujen karttojen määrät annetusta päivästä alkaen: {"Mirage": 120, ...}"""
    rows = conn.execute(
        f"""SELECT m.map_name, COUNT(*) FROM series s JOIN series_maps m ON m.series_id = s.id
            WHERE s.played_at >= ? AND {_VALID_MAP} GROUP BY m.map_name""",
        (since,),
    ).fetchall()
    return {name: count for name, count in rows}
