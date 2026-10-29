"""
Datalähde, joka hakee oikeat CS2-joukkueet PandaScoren API:sta.

KÄYTTÖ:
  1. Rekisteröidy osoitteessa https://pandascore.co (ilmainen taso riittää alkuun).
  2. Laita API-avain ympäristömuuttujaan:  export PANDASCORE_TOKEN=avaimesi
  3. Aja:  python manage.py sync --pandascore

HUOM: Tätä tiedostoa ei ole testattu oikeaa API:a vasten. Kenttien nimet
(name, location, players, first_name...) perustuvat PandaScoren
dokumentaatioon. Jos jokin ei toimi, tulosta yksi vastaus
(print(teams[0])) ja korjaa _convert_team()-funktion kenttien nimet.
"""

import json
import urllib.request

from app.sync.sources.base import RosterSource

API_URL = "https://api.pandascore.co/csgo/teams"  # PandaScore käyttää CS2:lle polkua "csgo"


class PandaScoreSource(RosterSource):
    def __init__(self, token: str, max_pages: int = 2, page_size: int = 50):
        self.token = token
        self.max_pages = max_pages  # rajoitetaan sivujen määrää, koska ilmaisen tason kutsuja on rajallisesti
        self.page_size = page_size

    def fetch_rosters(self) -> list[dict]:
        teams = []
        for page in range(1, self.max_pages + 1):
            batch = self._get(f"{API_URL}?page[number]={page}&page[size]={self.page_size}")
            if not batch:
                break  # tyhjä sivu = kaikki on haettu
            teams.extend(self._convert_team(team) for team in batch)
        return teams

    def _get(self, url: str) -> list[dict]:
        """Tekee HTTP GET -pyynnön ja palauttaa vastauksen JSONina."""
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _convert_team(team: dict) -> dict:
        """Muuntaa PandaScoren muodon sovelluksen omaan muotoon (katso base.py)."""
        players = []
        for p in team.get("players") or []:
            # Yhdistetään etu- ja sukunimi ja jätetään tyhjät pois.
            full_name = " ".join(part for part in (p.get("first_name"), p.get("last_name")) if part)
            players.append(
                {
                    "nickname": p["name"],
                    "real_name": full_name or None,
                    "country": p.get("nationality"),
                    "role": p.get("role"),
                }
            )
        return {
            "name": team["name"],
            "country": team.get("location"),
            "players": players,
        }
