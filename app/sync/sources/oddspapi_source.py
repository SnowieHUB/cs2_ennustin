"""
Vedonlyöntikertoimet OddsPapista (https://oddspapi.io).

Ilmaisella tilillä on 250 pyyntöä kuukaudessa, joten haku on tehty säästeliääksi:
  - /fixtures   (maksullinen, 1 pyyntö): kaikki tulevat CS2-ottelut, joille on kertoimet
  - /historical-odds (ilmainen): yhden ottelun kertoimien historia, josta otetaan uusin
  - /account    (ilmainen): montako pyyntöä on käytetty tässä kuussa
Yksi päivitys maksaa siis vain yhden pyynnön.

Kertoimet otetaan Pinnaclelta, jonka kertoimia pidetään yleisesti tarkimpina.
"""

import json
import os
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from app import config
from app.sync.http import get_text

API_URL = "https://api.oddspapi.io/v4"
CS2_SPORT_ID = 17
BOOKMAKER = "pinnacle"
# Markkina 171 = ottelun voittaja. Vaihtoehto 171 = joukkue 1, 172 = joukkue 2.
MATCH_WINNER = "171"
OUTCOME_TEAM1, OUTCOME_TEAM2 = "171", "172"
# OddsPapin vaatima tauko historiahakujen välillä (sekunteja).
HISTORY_COOLDOWN = 5


def read_api_key() -> str | None:
    """Lukee API-avaimen ympäristömuuttujasta tai tiedostosta. None, jos avainta ei ole."""
    key = os.environ.get("ODDSPAPI_KEY")
    if not key and config.ODDSPAPI_KEY_PATH.exists():
        key = config.ODDSPAPI_KEY_PATH.read_text(encoding="utf-8")
    return key.strip() if key else None


def _get(path: str, api_key: str, **params) -> dict | list:
    """Tekee GET-pyynnön OddsPapiin ja palauttaa vastauksen JSON-muodossa."""
    query = urllib.parse.urlencode({**params, "apiKey": api_key})
    return json.loads(get_text(f"{API_URL}/{path}?{query}"))


def requests_left(api_key: str) -> int:
    """Montako maksullista pyyntöä tässä kuussa on vielä jäljellä (tämä haku on ilmainen)."""
    subscription = _get("account", api_key)["subscriptions"][0]
    return subscription["request_limit"] - subscription["request_count"]


def fetch_fixtures(api_key: str, hours_back: int = 12, days_ahead: int = 9) -> list[dict]:
    """Ottelut, joille Pinnaclella on kertoimet. Maksaa 1 pyynnön.

    Mukaan otetaan myös hetki sitten alkaneet (hours_back), jotta käynnissä
    olevien otteluiden kertoimet saadaan. OddsPapi sallii alle 10 päivän välin.
    """
    now = datetime.now(timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    fixtures = _get(
        "fixtures", api_key,
        sportId=CS2_SPORT_ID,
        **{"from": (now - timedelta(hours=hours_back)).strftime(fmt)},  # from on Pythonin varattu sana
        to=(now + timedelta(days=days_ahead)).strftime(fmt),
        hasOdds="true",
        bookmakers=BOOKMAKER,
    )
    return [parse_fixture(f) for f in fixtures]


def parse_fixture(fixture: dict) -> dict:
    """Poimii ottelusta tarvittavat kentät. Aika muutetaan muotoon "2026-10-30 15:00" (UTC)."""
    start = datetime.strptime(fixture["startTime"][:16], "%Y-%m-%dT%H:%M")
    return {
        "fixture_id": fixture["fixtureId"],
        "start_time": start.strftime("%Y-%m-%d %H:%M"),
        # Kolme nimimuotoa, koska joku niistä yleensä täsmää omaan tietokantaamme.
        "team1_names": (fixture["participant1Name"], fixture.get("participant1ShortName"), fixture.get("participant1Abbr")),
        "team2_names": (fixture["participant2Name"], fixture.get("participant2ShortName"), fixture.get("participant2Abbr")),
    }


def fetch_latest_odds(api_key: str, fixture_id: str) -> tuple[float, float] | None:
    """Ottelun uusimmat voittajakertoimet (joukkue 1, joukkue 2). Ilmainen haku.

    Odottaa ensin OddsPapin vaatiman tauon. None, jos kertoimia ei löydy.
    """
    time.sleep(HISTORY_COOLDOWN)
    data = _get("historical-odds", api_key, fixtureId=fixture_id, bookmakers=BOOKMAKER)
    return parse_latest_odds(data)


def parse_latest_odds(data: dict) -> tuple[float, float] | None:
    """Etsii historiasta molempien joukkueiden viimeisimmän kertoimen."""
    try:
        outcomes = data["bookmakers"][BOOKMAKER]["markets"][MATCH_WINNER]["outcomes"]
        prices = []
        for outcome_id in (OUTCOME_TEAM1, OUTCOME_TEAM2):
            history = outcomes[outcome_id]["players"]["0"]
            # Historia on lista hetkiä. max() createdAt-ajan mukaan = uusin hetki.
            latest = max(history, key=lambda entry: entry["createdAt"])
            prices.append(float(latest["price"]))
    except (KeyError, TypeError, ValueError):
        return None  # odotettua rakennetta ei löytynyt: ei kertoimia
    return prices[0], prices[1]
