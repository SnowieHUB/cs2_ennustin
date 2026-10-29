"""
Datalähteiden yhteinen "sopimus" (rajapinta).

Kaikki datalähteet (JSON-tiedosto, PandaScore, tulevaisuudessa ehkä
Liquipedia) palauttavat datan SAMASSA muodossa. Synkronointikoodin ei siis
tarvitse tietää, mistä data tulee. Uuden lähteen lisääminen tarkoittaa
vain uutta luokkaa, joka perii RosterSourcen.

Palautettava muoto (lista joukkueita):
[
    {
        "name": "Nordic Wolves",
        "region": "Europe",            # vapaaehtoinen
        "country": "Finland",          # vapaaehtoinen
        "players": [
            {
                "nickname": "frostbyte",
                "real_name": "Eino Esimerkki",   # vapaaehtoinen
                "country": "Finland",            # vapaaehtoinen
                "role": "AWP",                   # vapaaehtoinen
                "joined": "2025-02-01"           # vapaaehtoinen liittymispäivä
            },
            ...
        ]
    },
    ...
]

TÄRKEÄÄ: players-listan on oltava joukkueen KOKO nykyinen kokoonpano.
Jos pelaaja puuttuu listasta, hänet merkitään lähteneeksi.
"""

from abc import ABC, abstractmethod


class RosterSource(ABC):
    """Kantaluokka. ABC = Abstract Base Class: tästä ei voi luoda oliota suoraan,
    vaan se pitää periä ja toteuttaa fetch_rosters()."""

    @abstractmethod
    def fetch_rosters(self) -> list[dict]:
        """Hakee joukkueet ja niiden nykyiset kokoonpanot yllä kuvatussa muodossa."""
        raise NotImplementedError
