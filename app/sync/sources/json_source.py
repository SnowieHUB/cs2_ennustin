"""
Datalähde, joka lukee kokoonpanot paikallisesta JSON-tiedostosta.

Tätä on hyvä käyttää testaamiseen ja omaan dataan. Voit kirjoittaa
kokoonpanot itse tiedostoon tai muuntaa ne jostain muualta.
"""

import json
from pathlib import Path

from app.sync.sources.base import RosterSource


class JsonFileSource(RosterSource):
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def fetch_rosters(self) -> list[dict]:
        # Tiedoston on oltava muodossa {"teams": [ ...joukkueet... ]}
        with self.path.open(encoding="utf-8") as file:
            data = json.load(file)
        return data["teams"]
