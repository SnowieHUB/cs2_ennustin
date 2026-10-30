-- Tietokannan rakenne (taulut).
--
-- "IF NOT EXISTS" tarkoittaa, että taulu luodaan vain, jos sitä ei vielä ole.
-- Näin tämän tiedoston voi ajaa uudelleen ilman, että vanha data katoaa.
-- Jos muutat taulujen rakennetta, aja: python manage.py init --reset
--
-- Päivämäärät tallennetaan tekstinä muodossa VVVV-KK-PP tai VVVV-KK-PP TT:MM (UTC).
-- Tässä muodossa aakkosjärjestys on sama kuin aikajärjestys, joten
-- vertailut kuten start_date <= '2026-05-01' toimivat suoraan.

-- Joukkueet
CREATE TABLE IF NOT EXISTS teams (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    -- Normalisoitu nimi, jolla eri lähteiden nimet yhdistetään samaan joukkueeseen.
    -- Esim. Liquipedian "Team Vitality" ja Valven "Vitality" -> "vitality"
    name_key   TEXT NOT NULL UNIQUE,
    region     TEXT,
    country    TEXT,
    -- Valven rankingin (VRS) tiedot. NULL = joukkue ei ole viimeisimmällä listalla.
    vrs_rank   INTEGER,
    vrs_points REAL,
    vrs_date   TEXT,
    -- Liquipedian sivun nimi (esim. "Team Vitality"), josta haetaan pelaajien tiedot.
    liquipedia_page TEXT,
    coach      TEXT
);

-- Pelaajat. Pelaajan joukkue EI ole tässä taulussa, vaan roster_history-taulussa,
-- koska pelaaja voi vaihtaa joukkuetta ja haluamme säilyttää historian.
-- Yksinkertaistus: nimimerkki oletetaan yksilölliseksi.
CREATE TABLE IF NOT EXISTS players (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname  TEXT NOT NULL UNIQUE,
    real_name TEXT,
    country   TEXT
);

-- Kokoonpanohistoria: yksi rivi = yksi jakso, jonka pelaaja on ollut joukkueessa.
--   end_date on tyhjä (NULL), jos pelaaja pelaa joukkueessa edelleen.
--   Pelaaja kuuluu joukkueeseen päivänä P, jos start_date <= P < end_date.
CREATE TABLE IF NOT EXISTS roster_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id  INTEGER NOT NULL REFERENCES players(id),
    team_id    INTEGER NOT NULL REFERENCES teams(id),
    role       TEXT,            -- esim. AWP, IGL, Rifler
    start_date TEXT NOT NULL,
    end_date   TEXT
);

-- Indeksit nopeuttavat yleisimpiä hakuja (vähän kuin kirjan hakemisto).
CREATE INDEX IF NOT EXISTS idx_roster_team   ON roster_history(team_id);
CREATE INDEX IF NOT EXISTS idx_roster_player ON roster_history(player_id);

-- Ottelut: tulevat (status = 'upcoming'), käynnissä olevat ('live') ja pelatut ('completed').
-- Tulevilla otteluilla tulokset ovat NULL. Käynnissä olevilla tulos on senhetkinen karttatilanne.
CREATE TABLE IF NOT EXISTS matches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    played_at   TEXT NOT NULL,      -- UTC-aika, esim. 2026-10-29 10:15
    event       TEXT,               -- turnauksen nimi
    best_of     INTEGER,            -- Bo1, Bo3, Bo5
    status      TEXT NOT NULL DEFAULT 'completed',
    team1_id    INTEGER NOT NULL REFERENCES teams(id),
    team2_id    INTEGER NOT NULL REFERENCES teams(id),
    team1_score INTEGER,            -- voitetut kartat (NULL, jos vain voittaja tiedetään)
    team2_score INTEGER,
    winner_id   INTEGER REFERENCES teams(id),  -- NULL = ei vielä pelattu tai tasapeli
    source      TEXT,               -- mistä ottelu tuli: 'vrs' tai 'liquipedia'
    event_url   TEXT,               -- turnaussivu Liquipediassa (oikeaan vaiheeseen)
    stream_url  TEXT,               -- lähetyksen linkki, jos tiedossa
    -- Sama ottelu ei voi olla kannassa kahdesti.
    UNIQUE (played_at, team1_id, team2_id)
);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status, played_at);
CREATE INDEX IF NOT EXISTS idx_matches_teams  ON matches(team1_id, team2_id);

-- Vedonlyöntikertoimet (OddsPapi / Pinnacle). Omana tauluna, koska tulevat ottelut
-- poistetaan ja haetaan uudelleen joka päivityksessä, mutta kertoimet halutaan säilyttää.
-- Ottelu yhdistetään kertoimiin joukkueiden ja aloitusajan perusteella.
CREATE TABLE IF NOT EXISTS odds (
    fixture_id  TEXT PRIMARY KEY,   -- OddsPapin ottelun tunnus
    team1_id    INTEGER NOT NULL REFERENCES teams(id),
    team2_id    INTEGER NOT NULL REFERENCES teams(id),
    start_time  TEXT NOT NULL,      -- UTC, esim. 2026-10-30 15:00
    price1      REAL NOT NULL,      -- desimaalikerroin joukkueen 1 voitolle, esim. 1.60
    price2      REAL NOT NULL,
    bookmaker   TEXT NOT NULL,
    updated_at  TEXT NOT NULL       -- milloin kertoimet haettiin (UTC)
);
CREATE INDEX IF NOT EXISTS idx_odds_teams ON odds(team1_id, team2_id);
