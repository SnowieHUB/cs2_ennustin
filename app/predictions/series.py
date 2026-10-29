"""
Sarjaformaatit: Bo1, Bo3 ja Bo5.

Ennustemalli on opetettu otteluilla, joista suurin osa on Bo3-sarjoja
(Valven datassa formaattia ei ole merkitty). Siksi mallin antama
todennäköisyys tulkitaan Bo3-sarjan voittotodennäköisyydeksi.

Siitä lasketaan yhden kartan voittotodennäköisyys p ja edelleen muut formaatit:

  Bo1:  P = p
  Bo3:  P = p² · (3 − 2p)
  Bo5:  P = p³ · (10 − 15p + 6p²)

Mitä pidempi sarja, sitä varmemmin parempi joukkue voittaa, koska yksittäisen
kartan sattuma tasoittuu. Esim. p = 0.60 -> Bo1 60 %, Bo3 65 %, Bo5 68 %.

Oletus: jokainen kartta on toisistaan riippumaton ja yhtä vaikea. Todellisuudessa
karttapickit vaikuttavat (decider-kartta on usein tasaisempi), mutta ilman
karttadataa tämä on paras yksinkertainen arvio.

Tässä tiedostossa ei ole tietokantakoodia, vaan pelkkää matematiikkaa.
"""

from math import comb

FORMATS = (1, 3, 5)
# Formaatti, jonka voittotodennäköisyyttä malli ennustaa (katso yllä).
MODEL_FORMAT = 3


def series_probability(p_map: float, best_of: int) -> float:
    """Todennäköisyys voittaa Bo-n-sarja, kun yhden kartan voittotodennäköisyys on p_map.

    Bo3:ssa tarvitaan 2 voittoa, Bo5:ssä 3. Jos voittoja tarvitaan k, sarjan voi
    voittaa niin, että vastustaja ehtii voittaa j karttaa (j = 0 ... k−1).
    Jokaista j:tä kohden:
      - viimeinen kartta on aina oma voitto
      - sitä ennen on pelattu k−1 omaa voittoa ja j häviötä jossain järjestyksessä,
        ja järjestyksiä on comb(k − 1 + j, j) kappaletta (binomikerroin).
    Esim. Bo3 (k=2): p² · (1 + 2(1−p)) = p² · (3 − 2p)
    """
    wins_needed = (best_of + 1) // 2
    q = 1 - p_map
    return sum(
        comb(wins_needed - 1 + j, j) * p_map**wins_needed * q**j
        for j in range(wins_needed)
    )


def map_probability(series_prob: float, best_of: int = MODEL_FORMAT) -> float:
    """Käänteinen laskenta: sarjan todennäköisyydestä yhden kartan todennäköisyys.

    Kaavaa ei ole helppo kääntää käsin, joten ratkaisu haetaan puolitushaulla
    (bisection): series_probability kasvaa, kun p_map kasvaa, joten voidaan
    arvata väliltä [0, 1] ja puolittaa väliä, kunnes tulos on tarpeeksi tarkka.
    40 kierroksen jälkeen virhe on alle 0.000000000001.
    """
    low, high = 0.0, 1.0
    for _ in range(40):
        middle = (low + high) / 2
        if series_probability(middle, best_of) < series_prob:
            low = middle  # liian pieni arvaus, vastaus on yläpuoliskolla
        else:
            high = middle
    return (low + high) / 2


def all_formats(model_prob: float) -> dict[int, float]:
    """Mallin todennäköisyydestä kaikkien formaattien todennäköisyydet: {1: ..., 3: ..., 5: ...}"""
    p_map = map_probability(model_prob, MODEL_FORMAT)
    return {best_of: series_probability(p_map, best_of) for best_of in FORMATS}
