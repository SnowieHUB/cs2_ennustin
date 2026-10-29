"""
Harjoitusdatan kokoaminen.

Jokaisesta historian ottelusta tehdään yksi rivi, jossa on:
  - piirteet (elo_diff, vrs_diff, exp_diff) sellaisina kuin ne olivat ENNEN ottelua
  - tulos y (1 = joukkue 1 voitti, 0 = hävisi)

TÄRKEÄÄ: piirteet saavat käyttää vain tietoa, joka oli saatavilla ennen ottelua.
Muuten malli "huijaa" (data leakage) ja näyttää testissä paremmalta kuin on.
Siksi:
  - Elo-luvut otetaan ennen kuin ottelu päivittää niitä.
  - VRS-pisteet otetaan viimeisimmästä julkaisusta, joka on ENNEN ottelupäivää.
"""

import bisect
import math

from app.matches import repository as matches_repo
from app.predictions.elo import EloEngine, EloParams, match_score
from app.sync.sources import vrs_source
from app.teams.names import name_key


def load_vrs_history(conn) -> tuple[list[str], list[dict[int, tuple[float, int]]]]:
    """Lataa kaikki VRS-julkaisut. Palauttaa (päivämäärät, [{joukkue_id: (pisteet, sija)}]).

    Kaksi rinnakkaista listaa, jotta päivämäärästä voidaan etsiä julkaisu
    nopeasti bisect-moduulilla (puolitushaku).
    """
    ids_by_key = {row["name_key"]: row["id"] for row in conn.execute("SELECT id, name_key FROM teams")}
    dates, tables = [], []
    for release_date, path in vrs_source.list_global_standings():
        table = {}
        for team in vrs_source.parse_standings(path.read_text(encoding="utf-8")):
            team_id = ids_by_key.get(name_key(team["name"]))
            if team_id is not None:
                table[team_id] = (team["vrs_points"], team["vrs_rank"])
        dates.append(release_date)
        tables.append(table)
    return dates, tables


def build_rows(conn, params: EloParams, vrs_history) -> list[dict]:
    """Käy historian läpi ja palauttaa harjoitusrivit (yksi per ottelu)."""
    vrs_dates, vrs_tables = vrs_history
    engine = EloEngine(params)
    rows = []

    for m in matches_repo.get_all_completed(conn):
        t1, t2, day = m["team1_id"], m["team2_id"], m["played_at"][:10]
        score1 = match_score(t1, m["winner_id"])

        # Viimeisin VRS-julkaisu ennen ottelupäivää. bisect_left antaa ensimmäisen
        # julkaisun, joka on >= day, joten sitä edellinen on viimeisin ennen.
        i = bisect.bisect_left(vrs_dates, day) - 1
        table = vrs_tables[i] if i >= 0 else {}
        lowest = min((points for points, _ in table.values()), default=0.0)
        vrs1, rank1 = table.get(t1, (lowest, None))
        vrs2, rank2 = table.get(t2, (lowest, None))

        elo1 = engine.rating_at(t1, m["played_at"])
        elo2 = engine.rating_at(t2, m["played_at"])
        n1, n2 = engine.matches_played[t1], engine.matches_played[t2]

        # process() päivittää luvut ja palauttaa Elon oman ennusteen ennen ottelua.
        p_elo = engine.process(t1, t2, score1, m["played_at"])

        if score1 == 0.5:
            continue  # tasapelit ovat harvinaisia; ei käytetä niitä opetuksessa
        rows.append(
            {
                "date": day,
                "y": score1,
                "elo_diff": elo1 - elo2,
                "vrs_diff": vrs1 - vrs2,
                "exp_diff": math.log1p(n1) - math.log1p(n2),
                "p_elo": p_elo,
                "has_vrs": i >= 0,
                # Tier 1 -ottelu: molemmat VRS:n top 30:ssä ottelun aikaan.
                "tier1": rank1 is not None and rank2 is not None and rank1 <= 30 and rank2 <= 30,
            }
        )
    return rows
