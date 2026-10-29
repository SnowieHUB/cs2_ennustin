"""
Elo-rating: matemaattinen malli, jolla arvioidaan joukkueiden tasoa otteluhistoriasta.

Idea lyhyesti:
  - Jokainen joukkue aloittaa samasta luvusta (start_rating).
  - Voittaja saa pisteitä ja häviäjä menettää niitä.
  - Yllätysvoitosta (heikko voittaa vahvan) saa paljon pisteitä,
    odotetusta voitosta vain vähän.
  - Kahden joukkueen lukujen erotuksesta saadaan voittotodennäköisyys.

Kaksi lisäystä tavalliseen Eloon (molemmat paransivat tarkkuutta harjoitusdatalla):
  1. Uusien joukkueiden luku muuttuu nopeammin (new_team_boost), koska niiden
     tasosta tiedetään vähän. Kokemuksen kertyessä muutokset pienenevät.
  2. Pitkän tauon jälkeen lukua vedetään kohti keskiarvoa (inactivity_decay),
     koska taukoa pitäneen joukkueen tasosta ollaan epävarmempia.

Parametrien arvot haetaan harjoittelussa (app/training/train.py) kokeilemalla,
mikä yhdistelmä olisi ennustanut historian otteluita parhaiten.

Tässä tiedostossa ei ole tietokantakoodia, vaan pelkkää laskentaa.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date

START_RATING = 1500.0


@dataclass
class EloParams:
    """Elo-mallin säädettävät arvot."""

    k: float = 32.0  # perus-K: kuinka paljon yksi ottelu muuttaa lukua
    new_team_boost: float = 3.0  # uuden joukkueen K on (1 + boost) kertaa suurempi
    inactivity_decay: float = 0.05  # tauon vaikutus kuukautta kohden (yli 30 pv tauot)
    start_rating: float = START_RATING


def expected_score(rating_a: float, rating_b: float) -> float:
    """Todennäköisyys (0–1), että A voittaa B:n.

    Elon vakiokaava: 400 pisteen ero = vahvempi on 10 kertaa
    todennäköisempi voittaja (noin 91 %).
    """
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def _days_between(earlier: str, later: str) -> int:
    """Päivien määrä kahden päivämäärän välillä. Kellonaika (jos on) ohitetaan."""
    return (date.fromisoformat(later[:10]) - date.fromisoformat(earlier[:10])).days


class EloEngine:
    """Käy ottelut läpi yksi kerrallaan ja pitää kirjaa joukkueiden luvuista.

    Käyttö:
        engine = EloEngine(EloParams())
        for match in ottelut_aikajärjestyksessä:
            engine.process(match_team1, match_team2, score1, match_date)
        engine.rating_at(joukkue, "2026-11-01")   # luku tiettynä päivänä
    """

    def __init__(self, params: EloParams):
        self.params = params
        self.ratings: dict[int, float] = {}
        self.matches_played: Counter = Counter()  # Counter = sanakirja, jonka oletusarvo on 0
        self.last_played: dict[int, str] = {}

    def rating_at(self, team_id: int, on_date: str) -> float:
        """Joukkueen luku tiettynä päivänä (tauon vaikutus huomioituna).

        Ei muuta tallennettua lukua, joten tällä voi ennustaa tulevia otteluita.
        """
        p = self.params
        rating = self.ratings.get(team_id, p.start_rating)
        last = self.last_played.get(team_id)
        if last and p.inactivity_decay:
            gap = _days_between(last, on_date)
            if gap > 30:
                # Esim. 90 pv tauko ja decay 0.05 -> lukua siirretään 10 % kohti keskiarvoa.
                factor = min(1.0, p.inactivity_decay * (gap - 30) / 30)
                rating += (p.start_rating - rating) * factor
        return rating

    def k_for(self, team_id: int) -> float:
        """Joukkueen K-kerroin: suuri uusilla joukkueilla, pienenee kokemuksen myötä."""
        played = self.matches_played[team_id]
        return self.params.k * (1 + self.params.new_team_boost / (1 + played / 10))

    def process(self, team1_id: int, team2_id: int, score1: float, on_date: str) -> float:
        """Päivittää luvut yhden ottelun perusteella.

        score1: 1.0 = joukkue 1 voitti, 0.0 = hävisi, 0.5 = tasapeli.
        Palauttaa todennäköisyyden, jonka malli antoi joukkueen 1 voitolle
        ENNEN ottelua (harjoittelu käyttää tätä tarkkuuden mittaamiseen).
        """
        rating1 = self.rating_at(team1_id, on_date)
        rating2 = self.rating_at(team2_id, on_date)
        expected1 = expected_score(rating1, rating2)

        # Muutos = K * (toteutunut - odotettu). Jos joukkueen 1 odotettiin voittavan
        # 90 %:n varmuudella ja se voitti, muutos on vain K * 0.1.
        surprise = score1 - expected1
        self.ratings[team1_id] = rating1 + self.k_for(team1_id) * surprise
        self.ratings[team2_id] = rating2 - self.k_for(team2_id) * surprise

        for team_id in (team1_id, team2_id):
            self.matches_played[team_id] += 1
            self.last_played[team_id] = on_date
        return expected1


def match_score(team1_id: int, winner_id: int | None) -> float:
    """Ottelun tulos joukkueen 1 näkökulmasta: 1.0 voitto, 0.0 häviö, 0.5 tasapeli."""
    if winner_id is None:
        return 0.5
    return 1.0 if winner_id == team1_id else 0.0
