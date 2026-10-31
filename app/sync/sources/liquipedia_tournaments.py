"""
Datalähde: turnaussivujen ottelut kartta- ja kierrostuloksineen Liquipediasta.

Turnaussivun wikitekstissä jokainen ottelu on {{Match ...}}-lohko:

  {{Match
    |opponent1={{TeamOpponent|vit}}|opponent2={{TeamOpponent|nemiga}}
    |date=October 30, 2026 - 14:00 {{Abbr/EET}} |finished=
    |map1={{Map|map=Cache|finished=true
        |t1firstside=ct|t1t=3|t1ct=5|t2t=7|t2ct=6}}
    |map2={{Map|map=Dust II|finished=
        |t1firstside=t|t1t=8|t1ct=|t2t=|t2ct=4}}
    |hltv=2399756
  }}

  - opponent: joukkueen lyhenne ("vit"). Oikea nimi selvitetään erikseen (resolve_team_pages).
  - t1t / t1ct = joukkueen 1 kierrokset T- ja CT-puolella. Jatkoerät: o1t1t, o1t1ct jne.
  - finished=true = kartta pelattu, skip = jäi pelaamatta, tyhjä = käynnissä tai tulossa.
  - hltv = ottelun tunnus HLTV:ssä, josta saadaan suora linkki ottelusivulle.

Vapaaehtoiset päivittävät turnaussivua ottelun aikana, joten käynnissä olevan
kartan kierrostilanne näkyy täällä nopeammin kuin Liquipedia:Matches-listassa.

Pyynnöt:
  - Turnauslista ja lyhenteiden selvitys: expandtemplates, raskas -> 1 / 30 s (get_slow)
  - Sivujen wikiteksti: query, 50 sivua kerralla, 1 / 2 s (liquipedia_teams.fetch_pages)
"""

import html
import json
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

from app.sync.sources.liquipedia_source import get_slow
from app.sync.sources.liquipedia_teams import fetch_pages

API_URL = "https://liquipedia.net/counterstrike/api.php"

# Liquipedian turnaustasot: 1 = S-Tier, 2 = A-Tier, 3 = B-Tier.
TIERS = (1, 2, 3)

# Aikavyöhykkeiden lyhenteet ja niiden ero UTC-aikaan tunteina.
TIMEZONES = {
    "UTC": 0, "GMT": 0, "WET": 0, "WEST": 1, "BST": 1, "CET": 1, "CEST": 2,
    "EET": 2, "EEST": 3, "MSK": 3, "GST": 4, "IST": 5.5, "ICT": 7, "SGT": 8,
    "CST": 8, "KST": 9, "JST": 9, "AEST": 10, "AEDT": 11, "BRT": -3,
    "EST": -5, "EDT": -4, "CDT": -5, "MST": -7, "PST": -8, "PDT": -7,
}
# Huom. CST on sekä Kiinan (UTC+8) että USA:n (UTC-6) aika. CS-turnauksissa
# Kiinan aika on yleisempi, joten käytetään sitä.

_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}


# --- Turnauslista ---------------------------------------------------------

def _expand(text: str) -> str:
    """Laajentaa wikitekstin mallineet (esim. turnauslistan) valmiiksi tekstiksi."""
    query = urllib.parse.urlencode({"action": "expandtemplates", "text": text, "prop": "wikitext", "format": "json"})
    return json.loads(get_slow(f"{API_URL}?{query}"))["expandtemplates"]["wikitext"]


def list_tournaments(since: str, until: str) -> list[str]:
    """Turnaussivujen nimet, joiden pelit osuvat aikavälille (S-, A- ja B-Tier)."""
    titles = []
    for tier in TIERS:
        listing = _expand(f"{{{{TournamentsList|tier={tier}|tiertype=none|sdate={since}|edate={until}}}}}")
        titles += parse_tournament_list(listing)
    return list(dict.fromkeys(titles))  # tuplat pois, järjestys säilyy


def parse_tournament_list(listing: str) -> list[str]:
    """Poimii listan jokaiselta riviltä turnaussivun nimen.

    Rivillä on ensin kuvia ([[File:...]]) ja sitten linkki turnaukseen ([[PGL/2026/Masters|...]]).
    Ensimmäinen linkki, joka ei ole kuva, on turnaus.
    """
    titles = []
    for row in listing.split('<tr class="table2__row--body"')[1:]:
        for link in re.findall(r"\[\[([^\]|#]+)", row):
            if not link.startswith("File:"):
                titles.append(link.replace("_", " ").strip())
                break
    return titles


def title_from_url(url: str) -> str | None:
    """Turnaussivun osoitteesta sivun nimi: .../counterstrike/PGL/2026/Masters#Playoffs -> PGL/2026/Masters"""
    if not url or "/counterstrike/" not in url:
        return None
    path = url.split("/counterstrike/", 1)[1].split("#")[0]
    return urllib.parse.unquote(path).replace("_", " ")


# --- Sivujen haku ----------------------------------------------------------

def fetch_tournament_pages(titles: list[str]) -> dict[str, str]:
    """Hakee turnaussivut ja niiden alasivut (esim. PGL/2026/Masters/Playoffs).

    Isot turnaukset on jaettu alasivuihin, ja ottelut ovat niillä. Alasivut
    löytyvät pääsivun välilehdistä (link1=...) ja sisällytyksistä ({{:Sivu/Alasivu}}).
    """
    pages = fetch_pages(titles)
    subpages = []
    for title, text in pages.items():
        for link in re.findall(r"(?:\|link\d+=|\{\{:)([^|}\n]+)", text):
            link = link.replace("_", " ").strip()
            if link.startswith(title + "/") and link not in pages:
                subpages.append(link)
    if subpages:
        pages.update(fetch_pages(subpages))
    return pages


def resolve_team_pages(templates: list[str]) -> dict[str, str]:
    """Muuttaa joukkueiden lyhenteet sivujen nimiksi: {"vit": "Team Vitality", ...}

    Liquipedian malline {{TeamPage|vit}} tuottaa joukkueen sivun nimen. Laajennetaan
    monta kerralla, esim. "vit=[[{{TeamPage|vit}}]]" -> "vit=[[Team Vitality]]".
    """
    result: dict[str, str] = {}
    for i in range(0, len(templates), 100):
        batch = templates[i : i + 100]
        text = "\n".join(f"{t}=[[{{{{TeamPage|{t}}}}}]]" for t in batch)
        for line in _expand(text).splitlines():
            found = re.match(r"(.+?)=\[\[([^\]|]+)", line)
            # Tuntematon lyhenne palauttaa tyhjän tai virheilmoituksen: ohitetaan.
            if found and found.group(1) in batch and found.group(2).strip():
                result[found.group(1)] = html.unescape(found.group(2)).strip()
    return result


# --- Wikitekstin jäsentäminen -------------------------------------------

def tournament_name(pages: dict[str, str], title: str) -> str | None:
    """Turnauksen nimi tietolaatikosta ({{Infobox league|name=PGL Masters Bucharest 2026}}).

    Alasivulla (PGL/2026/Masters/Playoffs) ei ole tietolaatikkoa, joten nimi
    haetaan ylemmältä sivulta.
    """
    while title:
        found = re.search(r"\{\{Infobox league.*?\|name=([^|\n}]+)", pages.get(title, ""), re.S)
        if found:
            return found.group(1).strip()
        title = title.rpartition("/")[0] if "/" in title else ""
    return None


def page_url(title: str) -> str:
    """Sivun nimestä osoite: "PGL/2026/Masters" -> https://liquipedia.net/counterstrike/PGL/2026/Masters"""
    return "https://liquipedia.net/counterstrike/" + urllib.parse.quote(title.replace(" ", "_"))


def _block_end(text: str, start: int) -> int:
    """Etsii kohdasta start alkavan {{...}}-lohkon lopun laskemalla sulkeita.

    Lohkojen sisällä on toisia lohkoja ({{Map ...}}), joten ensimmäinen }} ei riitä.
    """
    depth = 0
    i = start
    while i < len(text) - 1:
        pair = text[i : i + 2]
        if pair == "{{":
            depth += 1
            i += 2
        elif pair == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return i
        else:
            i += 1
    return len(text)


def parse_date(value: str) -> str | None:
    """Liquipedian päivämäärä UTC-ajaksi muotoon "2026-10-30 12:00".

    Muodot: "October 30, 2026 - 14:00 {{Abbr/EET}}" tai "2026-10-30".
    Jos kellonaikaa ei ole, käytetään keskipäivää.
    """
    value = value.strip()
    zone = re.search(r"\{\{Abbr/(\w+)\}\}", value)
    offset = TIMEZONES.get(zone.group(1), 0) if zone else 0
    clock = re.search(r"(\d{1,2}):(\d{2})", value)
    hour, minute = (int(clock.group(1)), int(clock.group(2))) if clock else (12, 0)

    named = re.match(r"([A-Za-z]+) (\d{1,2}), (\d{4})", value)
    iso = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if named and named.group(1) in _MONTHS:
        year, month, day = int(named.group(3)), _MONTHS[named.group(1)], int(named.group(2))
    elif iso:
        year, month, day = (int(x) for x in iso.groups())
    else:
        return None
    if not clock:
        offset = 0  # pelkkä päivä: ei siirretä aikavyöhykkeellä
    try:
        local = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    except ValueError:
        return None
    return (local - timedelta(hours=offset)).strftime("%Y-%m-%d %H:%M")


def _rounds(block: str, team: int) -> int | None:
    """Joukkueen kierrokset kartalla: T + CT + mahdolliset jatkoerät. None, jos tyhjä."""
    values = re.findall(rf"\|(?:o\d+)?t{team}(?:t|ct)=(\d+)", block)
    if not values:
        score = re.search(rf"\|score{team}=(\d+)", block)  # vanhempi muoto: score1=13
        return int(score.group(1)) if score else None
    return sum(int(v) for v in values)


def _parse_map(number: int, block: str) -> dict | None:
    """Yksi {{Map ...}}-lohko. None, jos kartta jäi pelaamatta tai sitä ei ole vielä valittu."""
    name = re.search(r"\|map=([^|}\n]*)", block)
    finished = re.search(r"\|finished=([^|}\n]*)", block)
    name = name.group(1).strip() if name else ""
    finished = finished.group(1).strip().lower() if finished else ""
    if not name or finished == "skip":
        return None
    rounds1, rounds2 = _rounds(block, 1), _rounds(block, 2)
    return {
        "number": number,
        "name": name,
        "rounds1": rounds1,
        "rounds2": rounds2,
        "finished": finished == "true",
    }


def _opponent(block: str, number: int) -> str | None:
    """Joukkueen lyhenne: {{TeamOpponent|vit}} tai {{TeamOpponent|template=vit}} -> "vit"."""
    found = re.search(rf"\|opponent{number}=\{{\{{TeamOpponent\|(?:template=)?([^|}}]*)", block)
    name = found.group(1).strip().lower() if found else ""
    return name or None


def parse_tournament_matches(wikitext: str) -> list[dict]:
    """Kaikki sivun ottelut, joiden molemmat joukkueet ja päivä tiedetään."""
    matches = []
    # (?![a-zA-Z]) estää osumat muihin mallineisiin, kuten {{Matchlist tai {{MatchSection.
    for start in (m.start() for m in re.finditer(r"\{\{Match(?![a-zA-Z])", wikitext)):
        block = wikitext[start : _block_end(wikitext, start)]
        team1, team2 = _opponent(block, 1), _opponent(block, 2)
        date = re.search(r"\|date=([^|]*)", block)
        played_at = parse_date(date.group(1)) if date else None
        if not team1 or not team2 or not played_at:
            continue

        maps = []
        for found in re.finditer(r"\|map(\d+)=\{\{Map\b", block):
            map_start = found.start() + len(found.group(0)) - len("{{Map")
            parsed = _parse_map(int(found.group(1)), block[map_start : _block_end(block, map_start)])
            if parsed:
                maps.append(parsed)

        # Ottelun oma finished-kenttä on ennen ensimmäistä karttaa (kartoilla on omansa).
        head = block.split("|map1=")[0]
        finished = re.search(r"\|finished=([^|}\n]*)", head)
        hltv = re.search(r"\|hltv=(\d+)", block)
        wins1 = sum(1 for m in maps if m["finished"] and (m["rounds1"] or 0) > (m["rounds2"] or 0))
        wins2 = sum(1 for m in maps if m["finished"] and (m["rounds2"] or 0) > (m["rounds1"] or 0))
        # Karttapaikkojen määrä = formaatti (Bo3 -> map1..map3). Ottelu on ohi, jos se on
        # merkitty päättyneeksi tai toinen joukkue on voittanut yli puolet kartoista
        # (merkintä unohtuu joskus).
        best_of = len(re.findall(r"\|map\d+=", block))
        is_finished = bool(finished and finished.group(1).strip().lower() == "true")
        is_finished = is_finished or (best_of > 0 and max(wins1, wins2) > best_of // 2)
        matches.append({
            "team1": team1,
            "team2": team2,
            "played_at": played_at,
            "best_of": best_of or None,
            "finished": is_finished,
            "hltv_id": int(hltv.group(1)) if hltv else None,
            "score1": wins1,
            "score2": wins2,
            "maps": maps,
        })
    return matches
