"""
Datalähde: tulevat ottelut ja tuoreet tulokset Liquipediasta.

Liquipedian sivu "Liquipedia:Matches" listaa noin 50 tulevaa ja 50 viimeksi
pelattua CS2-ottelua. Haetaan sivu Liquipedian MediaWiki-API:n kautta
(action=parse), joka palauttaa sivun HTML:n JSONin sisällä.

LIQUIPEDIAN SÄÄNNÖT (https://liquipedia.net/api-terms-of-use):
  - parse-pyyntöjä saa tehdä enintään 1 per 30 sekuntia
  - User-Agent pitää asettaa, ja gzip-pakkaus on pakollinen (katso sync/http.py)
  - Data on CC-BY-SA 3.0 -lisenssillä, joten lähde mainitaan sivuston alalaidassa
"""

import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.sync.http import get_text

API_URL = (
    "https://liquipedia.net/counterstrike/api.php"
    "?action=parse&page=Liquipedia:Matches&format=json&prop=text"
)

MIN_SECONDS_BETWEEN_REQUESTS = 30
# Tiedosto, johon tallennetaan edellisen haun aika (rajoituksen valvontaa varten).
_LAST_FETCH_FILE = config.DATA_DIR / ".liquipedia_last_fetch"


def fetch_matches_html() -> str:
    """Hakee otteluiden HTML:n ja odottaa ensin tarvittaessa, ettei rajaa ylitetä."""
    data = json.loads(get_slow(API_URL))
    return data["parse"]["text"]["*"]


def get_slow(url: str) -> str:
    """Raskas Liquipedia-pyyntö (parse tai expandtemplates): enintään 1 / 30 s.

    Edellisen haun aika on tiedostossa, joten raja pätee myös eri komentojen välillä
    (esim. cron ajaa ottelu- ja karttahaun eri aikaan).
    """
    _wait_for_rate_limit(_LAST_FETCH_FILE)
    try:
        return get_text(url)
    finally:
        _LAST_FETCH_FILE.write_text(str(time.time()))


def _wait_for_rate_limit(path: Path) -> None:
    """Jos edellisestä hausta on alle 30 s, odotetaan loppuaika."""
    try:
        elapsed = time.time() - float(path.read_text())
    except (OSError, ValueError):
        return  # tiedostoa ei ole, eli ei aiempaa hakua
    if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
        wait = MIN_SECONDS_BETWEEN_REQUESTS - elapsed
        print(f"Odotetaan {wait:.0f} s (Liquipedian pyyntöraja)...")
        time.sleep(wait)


# --- HTML:n jäsentäminen -------------------------------------------------
#
# Jokainen ottelu on HTML:ssä <div class="match-info"> -lohko. Lohkon sisältä
# poimitaan säännöllisillä lausekkeilla (regex) tarvittavat tiedot:
#   data-timestamp="1793268900"     -> aloitusaika (Unix-aikaleima)
#   <span class="name"><a title="Team Vitality">Vitality</a>  -> joukkue (pitkä ja lyhyt nimi)
#   match-info-header-scoreholder-score">2<   -> tulos (vain pelatuissa)
#   (Bo3)                           -> kuinka monen kartan ottelu
#   match-info-tournament-name ... <span>PGL Masters</span>  -> turnaus

_BLOCK_START = '<div class="match-info">'
_RE_TIMESTAMP = re.compile(r'data-timestamp="(\d+)"')
_RE_TEAM = re.compile(r'<span class="name"[^>]*>(?:<a [^>]*title="([^"]*)"[^>]*>)?([^<]*)')
_RE_SCORE = re.compile(r'scoreholder-score[^"]*">(\d+)<')
_RE_BEST_OF = re.compile(r"\(Bo(\d+)\)")
_RE_EVENT = re.compile(r'match-info-tournament-name">.*?<span>([^<]*)</span>', re.S)
_RE_EVENT_LINK = re.compile(r'match-info-tournament-name"><a href="(/counterstrike/[^"]+)"')
_RE_STREAM = re.compile(r'href="(/counterstrike/Special:Stream/[^"]+)"')
LIQUIPEDIA_URL = "https://liquipedia.net"


def _clean(name: str) -> str:
    """Siistii nimen: HTML-merkinnät (esim. &amp; -> &) ja Liquipedian lisäteksti pois."""
    return html.unescape(name).replace("(page does not exist)", "").strip()


def parse_matches(page_html: str) -> list[dict]:
    """Jäsentää sivun HTML:n listaksi otteluita.

    Sivulla on kaksi osaa: ensin tulevat ottelut ja sitten pelatut
    ("type=recent"). Ottelun tila päätellään näin:
      - pelattujen osassa                    -> "completed" (tulos)
      - tulevien osassa ja tulos näkyy       -> "live" (käynnissä, esim. 1 : 1)
      - tulevien osassa ja tuloksen tilalla "vs" -> "upcoming"
    Ottelut, joissa toinen joukkue on vielä TBD (ei tiedossa), ohitetaan.
    """
    recent_start = page_html.find("type=recent")
    matches = []

    # Kohdat, joista jokainen otteluohko alkaa.
    starts = [m.start() for m in re.finditer(re.escape(_BLOCK_START), page_html)]
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(page_html)
        block = page_html[start:end]
        is_completed = recent_start != -1 and start > recent_start

        match = _parse_block(block, is_completed)
        if match:
            matches.append(match)
    return matches


def _parse_block(block: str, is_completed: bool) -> dict | None:
    """Poimii yhden ottelun tiedot. Palauttaa None, jos tiedot ovat puutteelliset."""
    timestamp = _RE_TIMESTAMP.search(block)
    teams = _RE_TEAM.findall(block)  # lista pareja (pitkä nimi, lyhyt nimi)
    if not timestamp or len(teams) < 2:
        return None

    (title1, short1), (title2, short2) = teams[0], teams[1]
    # Linkin title on joukkueen Liquipedia-sivun nimi, jos sivu on olemassa.
    page1 = None if "(page does not exist)" in title1 else _clean(title1)
    page2 = None if "(page does not exist)" in title2 else _clean(title2)
    # html.unescape muuttaa HTML-merkinnät takaisin merkeiksi, esim. &amp; -> &
    title1, short1, title2, short2 = (_clean(x) for x in (title1, short1, title2, short2))
    # Ilman linkkiä oleva nimi (esim. "TBD" tai "Group A 1st Place") = ei vielä tiedossa.
    if not title1 or not title2:
        return None

    # Unix-aikaleima -> UTC-aika muodossa "2026-10-29 10:15"
    played_at = datetime.fromtimestamp(int(timestamp.group(1)), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

    scores = _RE_SCORE.findall(block)
    best_of = _RE_BEST_OF.search(block)
    event = _RE_EVENT.search(block)
    # Linkit ovat sivulla suhteellisia (/counterstrike/...), joten eteen lisätään osoite.
    event_link = _RE_EVENT_LINK.search(block)
    stream = _RE_STREAM.search(block)

    result = {
        "played_at": played_at,
        "team1": title1, "team1_short": short1, "team1_page": page1,
        "team2": title2, "team2_short": short2, "team2_page": page2,
        "best_of": int(best_of.group(1)) if best_of else None,
        "event": html.unescape(event.group(1)).strip() if event else None,
        "status": "upcoming",
        "score1": None, "score2": None,
        "event_url": LIQUIPEDIA_URL + html.unescape(event_link.group(1)) if event_link else None,
        "stream_url": LIQUIPEDIA_URL + html.unescape(stream.group(1)) if stream else None,
    }
    if is_completed and len(scores) >= 2:
        result.update(status="completed", score1=int(scores[0]), score2=int(scores[1]))
    elif is_completed:
        return None  # pelattu, mutta tulos puuttuu: ohitetaan
    elif len(scores) >= 2:
        # Tulevien listalla, mutta tulos näkyy jo: ottelu on käynnissä.
        result.update(status="live", score1=int(scores[0]), score2=int(scores[1]))
    return result
