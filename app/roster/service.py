"""
Kokoonpanojen päivityslogiikka: tämä on se osa, joka huomaa, kun pelaaja
vaihtaa joukkuetta.

Ero repository-tiedostoon: repository tekee yksittäisiä tietokanta-
operaatioita, ja service päättää, MITÄ operaatioita tehdään ja missä
järjestyksessä. Service-tiedostossa on siis sovelluksen "äly".

Toimintaperiaate:
  1. Datalähde kertoo joukkueen TÄMÄNHETKISEN kokoonpanon.
  2. Verrataan sitä tietokannassa olevaan kokoonpanoon.
  3. Lähteneiden pelaajien jakso suljetaan ja uusille avataan jakso.
"""

from dataclasses import dataclass

from app.players import repository as players_repo
from app.roster import repository as roster_repo
from app.teams import repository as teams_repo


@dataclass
class RosterChange:
    """Yksi havaittu muutos. Näitä tulostetaan käyttäjälle synkronoinnin jälkeen.

    @dataclass luo automaattisesti __init__-metodin ja siistin tulostusmuodon,
    joten luokkaan tarvitsee kirjoittaa vain kentät.
    """

    kind: str  # "liittyi", "lähti", "siirto" tai "rooli"
    player: str
    team: str
    date: str
    from_team: str | None = None  # vain siirroissa: mistä joukkueesta pelaaja tuli
    detail: str | None = None  # lisätieto, esim. roolin muutos

    def __str__(self) -> str:
        if self.kind == "siirto":
            return f"{self.date}  SIIRTO   {self.player}: {self.from_team} -> {self.team}"
        if self.kind == "liittyi":
            return f"{self.date}  LIITTYI  {self.player} -> {self.team}"
        if self.kind == "lähti":
            return f"{self.date}  LÄHTI    {self.player} <- {self.team}"
        return f"{self.date}  ROOLI    {self.player} ({self.team}): {self.detail}"


def sync_team_roster(conn, team_data: dict, date: str) -> list[RosterChange]:
    """Päivittää yhden joukkueen kokoonpanon vastaamaan team_dataa.

    team_data on sanakirja, jossa on joukkueen tiedot ja players-lista
    (muoto on kuvattu tiedostossa app/sync/sources/base.py).
    date on päivä, jolloin muutokset kirjataan tapahtuneiksi.

    HUOM: Funktio ei tee commitia. Kutsuja tallentaa kaikki joukkueet
    kerralla, jotta kesken kaatunut päivitys ei jätä tietokantaa puolivalmiiksi.
    """
    team_name = team_data["name"]
    team_id = teams_repo.get_or_create_team(
        conn, team_name, team_data.get("region"), team_data.get("country")
    )

    # Rakennetaan kaksi sanakirjaa, joissa avaimena on nimimerkki:
    #   current  = mitä tietokannassa nyt on
    #   incoming = mitä datalähde sanoo
    current = {row["nickname"]: row for row in teams_repo.get_current_roster(conn, team_id)}
    incoming = {p["nickname"]: p for p in team_data.get("players", [])}

    changes: list[RosterChange] = []

    # --- 1. Lähteneet: tietokannassa, mutta ei enää datalähteessä ---
    # Avainjoukkojen erotus (-) antaa nimet, jotka ovat vain vasemmassa joukossa.
    # sorted() pitää järjestyksen samana joka ajolla.
    for nickname in sorted(current.keys() - incoming.keys()):
        roster_repo.close_membership(conn, current[nickname]["membership_id"], date)
        changes.append(RosterChange("lähti", nickname, team_name, date))

    # --- 2. Uudet: datalähteessä, mutta ei vielä tietokannassa ---
    for nickname in sorted(incoming.keys() - current.keys()):
        player = incoming[nickname]
        player_id = players_repo.get_or_create_player(
            conn, nickname, player.get("real_name"), player.get("country")
        )
        # Jos datalähde kertoo liittymispäivän, käytetään sitä.
        join_date = player.get("joined", date)

        # Tutkitaan, oliko pelaaja juuri jossain toisessa joukkueessa.
        previous = players_repo.get_latest_membership(conn, player_id)
        from_team = None
        if previous and previous["end_date"] is None:
            # Pelaaja on yhä toisen joukkueen kirjoilla: suljetaan se jakso.
            roster_repo.close_membership(conn, previous["id"], join_date)
            from_team = previous["team_name"]
        elif previous and previous["end_date"] == join_date:
            # Vanha joukkue käsiteltiin ensin ja pelaaja merkittiin jo lähteneeksi
            # samana päivänä, joten tämäkin on siirto.
            from_team = previous["team_name"]

        roster_repo.open_membership(conn, player_id, team_id, player.get("role"), join_date)
        kind = "siirto" if from_team else "liittyi"
        changes.append(RosterChange(kind, nickname, team_name, join_date, from_team))

    # --- 3. Jatkavat pelaajat: päivitetään tiedot ja tarkistetaan rooli ---
    # Joukkojen leikkaus (&) antaa nimet, jotka ovat molemmissa.
    for nickname in sorted(incoming.keys() & current.keys()):
        player = incoming[nickname]
        players_repo.get_or_create_player(
            conn, nickname, player.get("real_name"), player.get("country")
        )
        new_role = player.get("role")
        old_role = current[nickname]["role"]
        if new_role and new_role != old_role:
            roster_repo.update_role(conn, current[nickname]["membership_id"], new_role)
            changes.append(
                RosterChange("rooli", nickname, team_name, date, detail=f"{old_role} -> {new_role}")
            )

    return changes
