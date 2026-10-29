"""
Täydentää pelaajien tiedot (rooli, nimi, maa, liittymispäivä) ja valmentajan
Liquipedian joukkuesivuilta.

Kokoonpanot (keitä joukkueessa on) tulevat edelleen Valven VRS-datasta, ja
Liquipediasta tuodaan vain lisätietoja niistä pelaajista, jotka ovat jo
joukkueen kokoonpanossa. Näin kaksi lähdettä ei "riitele" siitä, kuka
joukkueessa pelaa.
"""

from app.sync.sources import liquipedia_teams
from app.teams import repository as teams_repo


def _candidate_titles(team) -> list[str]:
    """Mahdolliset Liquipedia-sivujen nimet joukkueelle, todennäköisin ensin."""
    name = team["name"]
    titles = [team["liquipedia_page"]] if team["liquipedia_page"] else []
    titles += [name, f"Team {name}", f"{name} Esports", f"{name} Gaming"]
    return list(dict.fromkeys(titles))  # tuplat pois


def sync_team_info(conn, top_n: int = 100) -> tuple[int, int]:
    """Hakee tiedot VRS:n top_n joukkueelle. Palauttaa (löydetyt joukkueet, päivitetyt pelaajat)."""
    teams = conn.execute(
        "SELECT * FROM teams WHERE vrs_rank <= ? ORDER BY vrs_rank", (top_n,)
    ).fetchall()

    # Kierros 1: jokaisen joukkueen todennäköisin sivu. Kierros 2: muut vaihtoehdot
    # niille, joiden sivua ei löytynyt. Näin pyyntöjä tarvitaan mahdollisimman vähän.
    found: dict[int, str] = {}  # joukkue_id -> wikiteksti
    for round_index in range(2):
        wanted = {}
        for team in teams:
            if team["id"] in found:
                continue
            candidates = _candidate_titles(team)
            for title in candidates[:1] if round_index == 0 else candidates[1:]:
                wanted.setdefault(title, team["id"])
        pages = liquipedia_teams.fetch_pages(list(wanted))
        for title, text in pages.items():
            team_id = wanted[title]
            if team_id not in found and liquipedia_teams.is_team_page(text):
                found[team_id] = text
                teams_repo.set_liquipedia_page(conn, team_id, title)

    updated = 0
    for team_id, text in found.items():
        squad = liquipedia_teams.parse_active_squad(text)
        coaches = [p for p in squad if p["role"] and "coach" in p["role"].lower()]
        teams_repo.set_coach(conn, team_id, coaches[0]["nickname"] if coaches else None)
        updated += _apply_player_info(conn, team_id, [p for p in squad if p not in coaches])
    conn.commit()
    return len(found), updated


def _apply_player_info(conn, team_id: int, squad: list[dict]) -> int:
    """Päivittää Liquipedian tiedot joukkueen nykyisille pelaajille. Palauttaa päivitettyjen määrän."""
    by_nick = {p["nickname"].lower(): p for p in squad}
    updated = 0
    for member in teams_repo.get_current_roster(conn, team_id):
        info = by_nick.get(member["nickname"].lower())
        if not info:
            continue  # pelaaja ei ole Liquipedian kokoonpanossa (esim. tuoreempi siirto)

        conn.execute(
            "UPDATE players SET real_name = COALESCE(?, real_name), country = COALESCE(?, country) WHERE id = ?",
            (info["real_name"], info["flag"], member["id"]),
        )
        # Rooliksi merkitään IGL (pelinjohtaja). Muuten rooli jätetään tyhjäksi,
        # koska Liquipedia ei kerro, kuka on AWP-pelaaja.
        conn.execute(
            "UPDATE roster_history SET role = ? WHERE id = ?",
            ("IGL" if info["igl"] else None, member["membership_id"]),
        )
        # Oikea liittymispäivä: VRS-historia alkaa vain 6 kk taaksepäin, joten pidempään
        # joukkueessa olleen pelaajan päivä korjataan Liquipedian tiedolla. Tämä tehdään
        # vain, jos pelaajalla ei ole aiempaa jaksoa samassa joukkueessa (muuten jaksot
        # menisivät päällekkäin).
        if info["joined"] and info["joined"] < member["start_date"]:
            earlier = conn.execute(
                "SELECT 1 FROM roster_history WHERE player_id = ? AND team_id = ? AND id != ?",
                (member["id"], team_id, member["membership_id"]),
            ).fetchone()
            if not earlier:
                conn.execute(
                    "UPDATE roster_history SET start_date = ? WHERE id = ?",
                    (info["joined"], member["membership_id"]),
                )
        updated += 1
    return updated
