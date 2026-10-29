"""
Datalähde: pelaajien tarkemmat tiedot Liquipedian joukkuesivuilta.

Valven datassa on pelkät nimimerkit. Liquipedian joukkuesivun
"Player Roster" -osiossa on jokaisesta pelaajasta rivi wikitekstinä:

  {{Person|flag=fr|id=apEX|igl=y|name=Dan Madesclaire|joindate=2018-10-08}}
  {{Person|flag=fr|id=XTQZZZ|name=Rémy Quoniam|role=Coach|joindate=2023-10-13}}

Näistä saadaan: oikea nimi, maa (flag), pelinjohtaja (igl=y), valmentaja
(role=Coach) ja liittymispäivä. AWP- tai muita pelirooleja Liquipedia ei merkitse.

Sivujen raakateksti haetaan API:n query-toiminnolla, jossa yhdellä pyynnöllä
saa jopa 50 sivua. Sääntö: enintään 1 pyyntö / 2 s.
"""

import json
import re
import time
import urllib.parse

from app.sync.http import get_text

API_URL = "https://liquipedia.net/counterstrike/api.php"
MAX_TITLES_PER_REQUEST = 50
SECONDS_BETWEEN_REQUESTS = 2.5  # vähän yli säännön 2 s, varmuuden vuoksi


def fetch_pages(titles: list[str]) -> dict[str, str]:
    """Hakee sivujen wikitekstin. Palauttaa {pyydetty nimi: wikiteksti}.

    Sivut, joita ei ole, jätetään pois tuloksesta. Uudelleenohjaukset
    (esim. "Vitality" -> "Team Vitality") seurataan automaattisesti.
    """
    result: dict[str, str] = {}
    unique = list(dict.fromkeys(titles))  # poistaa tuplat mutta säilyttää järjestyksen
    for i in range(0, len(unique), MAX_TITLES_PER_REQUEST):
        if i > 0:
            time.sleep(SECONDS_BETWEEN_REQUESTS)
        batch = unique[i : i + MAX_TITLES_PER_REQUEST]
        query = urllib.parse.urlencode(
            {
                "action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                "format": "json", "redirects": "1", "titles": "|".join(batch),
            }
        )
        data = json.loads(get_text(f"{API_URL}?{query}"))["query"]

        # API voi muuttaa nimeä kahdesti: normalisointi ("magic" -> "Magic") ja
        # uudelleenohjaus ("Magic" -> "Magic Esports"). Seurataan ketju alusta loppuun.
        renames = {n["from"]: n["to"] for n in data.get("normalized", [])}
        renames.update({r["from"]: r["to"] for r in data.get("redirects", [])})
        contents = {
            page["title"]: page["revisions"][0]["slots"]["main"]["*"]
            for page in data.get("pages", {}).values()
            if "revisions" in page
        }
        for title in batch:
            final = title
            for _ in range(3):  # enintään kolme uudelleennimeämistä peräkkäin
                final = renames.get(final, final)
            if final in contents:
                result[title] = contents[final]
    return result


def is_team_page(wikitext: str) -> bool:
    """Onko sivu joukkueen sivu (eikä esim. täsmennyssivu, joka listaa useita samannimisiä)?"""
    return "{{Infobox team" in wikitext


# Yksittäisen kentän poiminta Person-riviltä, esim. |name=Dan Madesclaire
def _field(line: str, name: str) -> str | None:
    match = re.search(rf"\|{name}=([^|}}<]+)", line)
    return match.group(1).strip() if match else None


def parse_active_squad(wikitext: str) -> list[dict]:
    """Poimii ensimmäisen aktiivisen kokoonpanon (CS2-välilehti on sivulla ensimmäisenä).

    Palauttaa listan: {"nickname", "real_name", "flag", "igl", "role", "joined"}
    """
    start = wikitext.find("{{Squad|status=active")
    if start == -1:
        return []
    # Kokoonpanolohko päättyy riviin, jolla on pelkkä "}}".
    end = wikitext.find("\n}}", start)
    block = wikitext[start : end if end != -1 else len(wikitext)]

    people = []
    for line in block.splitlines():
        if "{{Person" not in line:
            continue
        nickname = _field(line, "id")
        if not nickname:
            continue
        # Liittymispäivä voi olla muodossa joindate=2018-10-08 tai joindate={{abbr|2018-10-08|...}}
        joined = re.search(r"\|joindate=(?:\{\{abbr\|)?(\d{4}-\d{2}-\d{2})", line)
        people.append(
            {
                "nickname": nickname,
                "real_name": _field(line, "name"),
                "flag": _field(line, "flag"),
                "igl": "|igl=y" in line,
                "role": _field(line, "role"),  # yleensä vain "Coach" tai vastaava
                "joined": joined.group(1) if joined else None,
            }
        )
    return people
