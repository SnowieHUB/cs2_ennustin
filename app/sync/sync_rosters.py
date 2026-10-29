"""
Kokoonpanojen synkronointi: hakee datan lähteestä ja tallentaa sen tietokantaan.

Tämä toimii minkä tahansa RosterSourcen kanssa (VRS, JSON-tiedosto, PandaScore).
"""

from app.roster.service import RosterChange, sync_team_roster
from app.sync.sources.base import RosterSource


def remove_duplicate_players(teams: list[dict]) -> list[str]:
    """Poistaa pelaajan kaikista paitsi ensimmäisestä joukkueesta, jossa hän esiintyy.

    Miksi: jos sama nimimerkki on samassa haussa kahdessa joukkueessa (esim.
    lainapelaaja tai kaksi eri pelaajaa samalla nimellä), synkronointi
    "siirtäisi" hänet edestakaisin. Lista on järjestyksessä parhaasta alkaen,
    joten pelaaja jää paremmin rankattuun joukkueeseen.

    Muokkaa listaa paikallaan ja palauttaa varoitukset tulostettavaksi.
    """
    seen: dict[str, str] = {}  # pienellä kirjoitettu nimimerkki -> joukkue
    warnings = []
    for team in teams:
        kept = []
        for player in team.get("players", []):
            key = player["nickname"].lower()
            if key in seen:
                warnings.append(f"{player['nickname']} on sekä {seen[key]} että {team['name']} -> pidetään {seen[key]}")
                continue
            seen[key] = team["name"]
            kept.append(player)
        team["players"] = kept
    return warnings


def sync_from_source(conn, source: RosterSource, date: str) -> list[RosterChange]:
    """Päivittää kaikkien lähteen joukkueiden kokoonpanot.

    Kaikki muutokset tallennetaan yhtenä transaktiona: joko kaikki
    onnistuu, tai mitään ei tallenneta (rollback).
    """
    teams = source.fetch_rosters()
    for warning in remove_duplicate_players(teams):
        print("  Huom:", warning)

    all_changes: list[RosterChange] = []
    try:
        for team_data in teams:
            all_changes.extend(sync_team_roster(conn, team_data, date))
        conn.commit()  # tallennetaan kaikki kerralla
    except Exception:
        conn.rollback()  # perutaan keskeneräiset muutokset
        raise  # heitetään virhe eteenpäin, jotta käyttäjä näkee sen
    return all_changes
