"""
Sovelluksen asetukset yhdessä paikassa.

Kun polut ja säädettävät arvot ovat täällä, niitä ei tarvitse etsiä
ympäri koodia. Jos haluat esimerkiksi vaihtaa tietokannan sijaintia,
muutat vain tätä tiedostoa.
"""

from pathlib import Path

# Projektin juurikansio. __file__ on tämän tiedoston polku (app/config.py),
# joten .parent.parent nousee kaksi tasoa ylös: app/ -> cs2_ennustin/
BASE_DIR = Path(__file__).resolve().parent.parent

# Kansio, jossa data (tietokanta ja esimerkkitiedostot) sijaitsee.
DATA_DIR = BASE_DIR / "data"

# SQLite-tietokanta on yksi tavallinen tiedosto levyllä.
DATABASE_PATH = DATA_DIR / "cs2.db"

# "Tier 1" = joukkue on Valven rankingissa tällä sijalla tai paremmin.
# Liquipedian ottelulistassa ei ole turnauksen tasoa, joten taso päätellään joukkueista.
TIER1_MAX_RANK = 30

# Kuinka monta parasta joukkuetta VRS-listalta tallennetaan kokoonpanoineen.
VRS_TOP_N = 100

# Aikavyöhyke, jossa ottelujen ajat näytetään sivulla.
TIMEZONE = "Europe/Helsinki"

# OddsPapin API-avain kertoimia varten. Avain luetaan tiedostosta (ei GitHubiin,
# katso .gitignore) tai ympäristömuuttujasta ODDSPAPI_KEY.
ODDSPAPI_KEY_PATH = DATA_DIR / "oddspapi_key.txt"
# Kertoimien haun tila (montako pyyntöä jäljellä). Sivu näyttää tästä ilmoituksen,
# jos kuukauden kiintiö on käytetty.
ODDS_STATUS_PATH = DATA_DIR / "odds_status.json"
