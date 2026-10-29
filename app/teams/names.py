"""
Joukkueiden nimien yhdistäminen eri datalähteiden välillä.

Ongelma: sama joukkue on eri lähteissä eri nimellä.
  Valve VRS:       "Vitality",       "G2",         "BETBOOM"
  Liquipedia:      "Team Vitality",  "G2 Esports", "BetBoom Team"

Ratkaisu: muutetaan jokainen nimi "avaimeksi", josta on poistettu
yleiset lisäsanat, isot kirjaimet ja erikoismerkit. Kaikki yllä olevat
parit saavat saman avaimen, ja niitä voidaan verrata.
"""

import re

# Käsin lisättävät poikkeukset: nimi, joka ei muuten täsmää -> nimi, jolla
# joukkue on VRS-listalla. Lisää tähän pareja, jos huomaat saman joukkueen
# näkyvän sivulla kahdesti. Avaimet kirjoitetaan pienillä kirjaimilla.
# Esimerkki:  "joku pitkä nimi esports": "Lyhyt Nimi",
ALIASES: dict[str, str] = {}

# Yleiset lyhenteet hakukenttää varten: lyhenne -> nimi VRS-listalla.
# Esim. Valvella NAVI on "Natus Vincere", joten ilman tätä haku "NAVI" ei löytäisi mitään.
# Lisää tähän omia suosikkejasi. Oikean puolen nimen pitää olla täsmälleen sama kuin VRS-listalla.
SHORT_NAMES: dict[str, str] = {
    "NAVI": "Natus Vincere",
    "NiP": "Ninjas in Pyjamas",
    "GL": "GamerLegion",
    "EF": "Eternal Fire",
    "VP": "Virtus.pro",
    "TL": "Liquid",
}

# Sanat, jotka poistetaan nimestä, koska ne eivät erottele joukkueita toisistaan.
FILLER_WORDS = {"team", "esports", "esport", "gaming", "club", "the"}


def name_key(name: str) -> str:
    """Muuttaa joukkueen nimen vertailuavaimeksi.

    >>> name_key("Team Vitality")
    'vitality'
    >>> name_key("G2 Esports")
    'g2'
    """
    name = ALIASES.get(name.lower().strip(), name)
    # \w+ poimii sanat. Ne muutetaan pieniksi kirjaimiksi ja täytesanat jätetään pois.
    words = [w for w in re.findall(r"\w+", name.lower()) if w not in FILLER_WORDS]
    key = "".join(words)
    # Jos nimi koostui pelkistä täytesanoista (esim. "Team"), käytetään koko nimeä.
    return key or re.sub(r"\W+", "", name.lower())
