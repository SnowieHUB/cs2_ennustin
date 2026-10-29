"""
Ennustemalli: yhdistää kolme tietoa yhdeksi voittotodennäköisyydeksi.

Piirteet (features) lasketaan aina kahden joukkueen EROTUKSENA:
  elo_diff = oma Elo-luku A  - oma Elo-luku B      (otteluhistoriasta)
  vrs_diff = VRS-pisteet A    - VRS-pisteet B       (Valven ranking)
  exp_diff = log(1 + ottelut A) - log(1 + ottelut B)  (kokemus)

Logistinen regressio laskee painotetun summan ja muuttaa sen todennäköisyydeksi:
  z = w_elo * elo_diff + w_vrs * vrs_diff + w_exp * exp_diff
  P(A voittaa) = 1 / (1 + e^-z)          (sigmoid-funktio)

Painot (w) opetetaan historiasta: python manage.py train.
Ne tallennetaan tiedostoon data/model.json.

Koska vakiotermiä ei ole, z jakautuu joukkuekohtaisiin osiin:
  z = vahvuus(A) - vahvuus(B), missä vahvuus(X) = w_elo*Elo + w_vrs*VRS + w_exp*log(1+ottelut)
Siksi jokaiselle joukkueelle voidaan laskea yksi "vahvuus"-luku rankingia varten.
"""

import json
import math
from dataclasses import asdict, dataclass, field

from app import config
from app.predictions.elo import EloParams

MODEL_PATH = config.DATA_DIR / "model.json"


@dataclass
class Model:
    elo: EloParams = field(default_factory=EloParams)
    # Oletuspainot = pelkkä Elo (sama tulos kuin elo.expected_score), jos mallia ei ole opetettu.
    w_elo: float = math.log(10) / 400
    w_vrs: float = 0.0
    w_exp: float = 0.0
    metrics: dict = field(default_factory=dict)  # harjoittelun tulokset sivulla näyttämistä varten

    def strength(self, elo_rating: float, vrs_points: float, matches_played: int) -> float:
        """Joukkueen vahvuus mallin asteikolla (katso tiedoston alun selitys)."""
        return self.w_elo * elo_rating + self.w_vrs * vrs_points + self.w_exp * math.log1p(matches_played)

    def win_probability(self, strength_a: float, strength_b: float) -> float:
        """P(A voittaa B:n) kahden vahvuusluvun perusteella."""
        return 1.0 / (1.0 + math.exp(-(strength_a - strength_b)))

    @staticmethod
    def display_points(strength: float) -> float:
        """Muuttaa vahvuuden tutummalle Elo-asteikolle sivulla näyttämistä varten.

        Kerroin 400 / ln(10) valitaan niin, että 400 pisteen ero = 91 %,
        kuten tavallisessa Elossa.
        """
        return strength * 400 / math.log(10)

    def save(self, path=MODEL_PATH) -> None:
        # asdict muuttaa dataclassin (myös sisäkkäisen EloParamsin) sanakirjaksi.
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path=MODEL_PATH) -> "Model":
        """Lataa opetetun mallin. Jos tiedostoa ei ole, palautetaan oletusmalli."""
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        data["elo"] = EloParams(**data["elo"])
        return cls(**data)
