"""
Tietokantayhteyden hallinta.

Kaikki muu koodi saa tietokantayhteyden tämän tiedoston kautta, joten
jos tietokanta joskus vaihdetaan (esim. PostgreSQL:ään), muutokset
keskittyvät pääosin tänne.
"""

import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(database_path) -> sqlite3.Connection:
    """Avaa uuden yhteyden tietokantaan.

    Tätä käytetään suoraan komentoriviskripteissä ja testeissä.
    Nettisivun puolella käytetään get_db()-funktiota.
    """
    conn = sqlite3.connect(database_path)

    # Row-tehdas saa rivit käyttäytymään sanakirjan tapaan:
    # voidaan kirjoittaa row["name"] eikä row[1].
    conn.row_factory = sqlite3.Row

    # SQLite ei oletuksena valvo viittauksia tauluihin (REFERENCES).
    # Tämä asetus kytkee valvonnan päälle.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Sarakkeet, jotka on lisätty tauluihin myöhemmin: (taulu, sarake, tyyppi).
# CREATE TABLE IF NOT EXISTS ei muuta jo olemassa olevaa taulua, joten
# vanhaan tietokantaan uudet sarakkeet lisätään erikseen ALTER TABLE -komennolla.
_ADDED_COLUMNS = [
    ("matches", "event_url", "TEXT"),
    ("matches", "stream_url", "TEXT"),
]


def init_schema(conn: sqlite3.Connection) -> None:
    """Luo taulut ajamalla schema.sql-tiedoston ja lisää puuttuvat sarakkeet."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    for table, column, column_type in _ADDED_COLUMNS:
        # PRAGMA table_info palauttaa taulun sarakkeet, row["name"] on sarakkeen nimi.
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
    conn.commit()


def get_db() -> sqlite3.Connection:
    """Palauttaa nykyisen sivupyynnön tietokantayhteyden.

    Flaskin `g` on pyyntökohtainen säilö. Ensimmäisellä kutsulla avataan
    yhteys ja tallennetaan se g:hen, ja saman pyynnön myöhemmät kutsut
    käyttävät samaa yhteyttä.
    """
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(exception=None) -> None:
    """Sulkee yhteyden. Flask kutsuu tätä automaattisesti pyynnön lopuksi."""
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
