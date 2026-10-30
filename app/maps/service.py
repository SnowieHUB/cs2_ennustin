"""
Karttatilastot: joukkueen parhaat kartat ja todennäköiset bännit.

Bännejä ei ole saatavilla luotettavasti, joten ne päätellään pelatuista kartoista:
kartta, jota joukkue ei juuri koskaan pelaa, on todennäköisesti sen vakiobänni.
Joukkue nimittäin bännää sen joka ottelussa, joten se ei päädy pelattavaksi.
"""

from datetime import date, timedelta

from app.maps import repository as maps_repo

STATS_DAYS = 182      # tilastojen aikaväli: puoli vuotta
POOL_DAYS = 30        # karttapooli päätellään viimeisen kuukauden peleistä
POOL_MIN_SHARE = 0.03 # kartta kuuluu pooliin, jos sen osuus peleistä on vähintään 3 %
MIN_PLAYED_FOR_BEST = 5  # parhaan kartan pitää olla pelattu vähintään näin monta kertaa
BAN_MAX_SHARE = 0.05     # bänni: kartan osuus joukkueen peleistä enintään 5 %
BAN_MIN_TOTAL = 15       # bänni päätellään vain, jos joukkueella on vähintään näin monta karttaa


def _days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def active_map_pool(conn) -> list[str]:
    """Nykyiset kilpakartat: viimeisen kuukauden aikana riittävän usein pelatut.

    Valve vaihtaa karttapoolia välillä (esim. Overpass pois, Cache tilalle), joten
    vanhoja karttoja ei näytetä.
    """
    counts = maps_repo.get_map_counts(conn, _days_ago(POOL_DAYS))
    total = sum(counts.values())
    return sorted(name for name, count in counts.items() if total and count / total >= POOL_MIN_SHARE)


def team_map_stats(conn, team_id: int, pool: list[str] | None = None) -> dict:
    """Joukkueen karttatilastot nykyisen poolin kartoille.

    Palauttaa {"maps": {kartta: {"played", "wins", "rate", "round_diff"}},
               "best": paras kartta tai None, "ban": todennäköinen bänni tai None,
               "total": pelattuja karttoja yhteensä}
    """
    pool = pool if pool is not None else active_map_pool(conn)
    rows = {row["name"]: row for row in maps_repo.get_team_map_rows(conn, team_id, _days_ago(STATS_DAYS))}

    maps = {}
    for name in pool:
        row = rows.get(name)
        played = row["played"] if row else 0
        maps[name] = {
            "played": played,
            "wins": row["wins"] if row else 0,
            "rate": row["wins"] / played if played else None,
            "round_diff": row["round_diff"] if row else 0,
        }
    total = sum(m["played"] for m in maps.values())

    # Paras kartta: korkein voitto-% riittävällä otosmäärällä.
    candidates = [name for name, m in maps.items() if m["played"] >= MIN_PLAYED_FOR_BEST]
    best = max(candidates, key=lambda name: (maps[name]["rate"], maps[name]["played"]), default=None)
    # Todennäköinen bänni: vähiten pelattu kartta, jos sitä pelataan selvästi harvemmin
    # kuin muita. Vähällä datalla tai tasaisella jakaumalla bänniä ei voi päätellä.
    ban = min(maps, key=lambda name: (maps[name]["played"], maps[name]["rate"] or 0), default=None)
    if total < BAN_MIN_TOTAL or ban is None or maps[ban]["played"] / total > BAN_MAX_SHARE:
        ban = None
    return {"maps": maps, "best": best, "ban": ban, "total": total}


def compare_teams(conn, team_a_id: int, team_b_id: int) -> dict:
    """Kahden joukkueen karttavertailu Ennusta-sivulle."""
    pool = active_map_pool(conn)
    return {"pool": pool, "a": team_map_stats(conn, team_a_id, pool), "b": team_map_stats(conn, team_b_id, pool), "days": STATS_DAYS}
