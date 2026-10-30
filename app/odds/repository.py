"""
Kertoimien tallennus ja haku tietokannasta.
"""

# Kuinka kaukana toisistaan ottelun ja kertoimen aloitusajat saavat olla (päivinä).
# Lähteiden kellonajat eroavat joskus vähän, ja ottelu voi siirtyä. 0.5 = 12 tuntia.
MAX_TIME_DIFF_DAYS = 0.5


def save_odds(conn, fixture_id, team1_id, team2_id, start_time, price1, price2, bookmaker, updated_at) -> None:
    """Tallentaa ottelun kertoimet. Jos ottelulla on jo kertoimet, ne korvataan uusilla."""
    conn.execute(
        """
        INSERT INTO odds (fixture_id, team1_id, team2_id, start_time, price1, price2, bookmaker, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (fixture_id) DO UPDATE SET
            start_time = excluded.start_time, price1 = excluded.price1,
            price2 = excluded.price2, updated_at = excluded.updated_at
        """,
        (fixture_id, team1_id, team2_id, start_time, price1, price2, bookmaker, updated_at),
    )


def find_odds(conn, team1_id: int, team2_id: int, played_at: str) -> dict | None:
    """Etsii ottelun kertoimet joukkueiden ja ajan perusteella.

    Kertoimet palautetaan ottelun omassa järjestyksessä: price1 on aina
    team1_id:n kerroin, vaikka vedonlyöntisivulla joukkueet olisivat toisin päin.
    julianday() muuttaa ajan päiviksi, joten erotus kertoo aikaeron päivinä.
    """
    row = conn.execute(
        """
        SELECT * FROM odds
        WHERE ((team1_id = ? AND team2_id = ?) OR (team1_id = ? AND team2_id = ?))
          AND abs(julianday(start_time) - julianday(?)) < ?
        ORDER BY abs(julianday(start_time) - julianday(?))
        LIMIT 1
        """,
        (team1_id, team2_id, team2_id, team1_id, played_at, MAX_TIME_DIFF_DAYS, played_at),
    ).fetchone()
    if row is None:
        return None
    price1, price2 = row["price1"], row["price2"]
    if row["team1_id"] != team1_id:
        price1, price2 = price2, price1  # joukkueet toisin päin: vaihdetaan kertoimet
    return {"price1": price1, "price2": price2, "bookmaker": row["bookmaker"], "updated_at": row["updated_at"]}
