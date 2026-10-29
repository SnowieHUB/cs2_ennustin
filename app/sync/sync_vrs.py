"""
Valven rankingin (VRS) synkronointi: joukkueet, pisteet, kokoonpanot ja otteluhistoria.

Rankingjulkaisut käydään läpi vanhimmasta uusimpaan. Jokaisen julkaisun
kokoonpanoja verrataan edelliseen, joten siirrot tallentuvat historiaan
(päivämäärä on sen julkaisun päivä, jossa muutos näkyi ensimmäisen kerran).
"""

from app.matches import repository as matches_repo
from app.roster.service import RosterChange
from app.sync.sources import vrs_source
from app.sync.sync_rosters import sync_from_source
from app.teams import repository as teams_repo
from app.teams.names import name_key


def sync_vrs(conn, months: int = 1, top_n: int = 100) -> list[RosterChange]:
    """Päivittää kokoonpanot ja pisteet viimeisimmistä `months` julkaisusta.

    months=6 käy läpi puolen vuoden historian (init-komento), ja months=1
    riittää päivittäiseen synkronointiin.
    """
    files = vrs_source.list_global_standings()
    if not files:
        raise RuntimeError("VRS-tiedostoja ei löytynyt. Aja ensin vrs_source.update_repo().")

    # Jos tietokannassa on jo uudempi julkaisu, vanhempia ei käsitellä uudelleen.
    latest_in_db = conn.execute("SELECT MAX(vrs_date) FROM teams").fetchone()[0]

    all_changes = []
    for standings_date, path in files[-months:]:
        if latest_in_db and standings_date < latest_in_db:
            continue
        print(f"VRS {standings_date}")
        all_teams = vrs_source.parse_standings(path.read_text(encoding="utf-8"))

        # 1. Kokoonpanot vain top_n joukkueelle (sama koodi kuin muillakin lähteillä).
        top_teams = [t for t in all_teams if t["vrs_rank"] <= top_n]
        all_changes.extend(sync_from_source(conn, _StaticSource(top_teams), standings_date))

        # 2. Sijoitukset ja pisteet KAIKILLE listan joukkueille, koska ennustemalli
        #    tarvitsee pisteet myös heikommille joukkueille.
        teams_repo.clear_vrs(conn)
        for team in all_teams:
            team_id = teams_repo.get_or_create_team(conn, team["name"])
            teams_repo.update_vrs(conn, team_id, team["vrs_rank"], team["vrs_points"], standings_date)
        conn.commit()
    return all_changes


def sync_vrs_matches(conn) -> int:
    """Tuo ladattujen joukkuetiedostojen ottelut tietokantaan. Palauttaa uusien määrän.

    Sama ottelu on kahdessa tiedostossa (molempien joukkueiden), ja usein myös
    useassa julkaisussa, koska 6 kk:n ikkunat menevät päällekkäin. Siksi ottelut
    kerätään ensin sanakirjaan, jonka avain on (päivä, joukkue A, joukkue B).
    """
    collected: dict[tuple, dict] = {}
    for path in vrs_source.iter_detail_files():
        team, matches = vrs_source.parse_details(path.read_text(encoding="utf-8"))
        for m in matches:
            # Järjestetään joukkueet aakkosjärjestykseen, jotta A–B ja B–A ovat sama avain.
            a, b = sorted([team, m["opponent"]], key=name_key)
            key = (m["date"], name_key(a), name_key(b))
            winner = team if m["won"] else m["opponent"]
            collected[key] = {"date": m["date"], "team1": a, "team2": b, "winner": winner}

    added = 0
    for m in collected.values():
        team1_id = teams_repo.get_or_create_team(conn, m["team1"])
        team2_id = teams_repo.get_or_create_team(conn, m["team2"])
        winner_id = team1_id if name_key(m["winner"]) == name_key(m["team1"]) else team2_id
        if matches_repo.save_match(
            conn, m["date"], None, None, "completed", team1_id, team2_id,
            winner_id=winner_id, source="vrs",
        ):
            added += 1
    conn.commit()
    return added


class _StaticSource:
    """Pieni apuluokka: valmiiksi luettu lista käyttäytyy datalähteenä."""

    def __init__(self, teams: list[dict]):
        self.teams = teams

    def fetch_rosters(self) -> list[dict]:
        return self.teams
