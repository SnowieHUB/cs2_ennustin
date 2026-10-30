"""
Kertoimien päivitys: haetaan OddsPapista ja tallennetaan niille otteluille,
jotka löytyvät myös omasta tietokannasta.
"""

import json
import urllib.error
from datetime import date, datetime, timedelta, timezone

from app import config
from app.matches.repository import now_utc
from app.odds import repository as odds_repo
from app.sync.sources import oddspapi_source as source
from app.teams import repository as teams_repo

# Jätetään kuukauden kiintiöstä pieni varaus, ettei raja ylity vahingossa.
QUOTA_RESERVE = 5
# Jos kertoimet on haettu tätä tuoreemmin, uutta maksullista hakua ei tehdä.
# Cron hakee 4 tunnin välein, joten 3 tuntia ei estä sitä, mutta estää vahingossa
# toistetut käsiajot.
MIN_HOURS_BETWEEN_FETCHES = 3


def _has_match(conn, team1_id: int, team2_id: int, start_time: str) -> bool:
    """Onko tietokannassa näiden joukkueiden ottelu noin samaan aikaan?"""
    row = conn.execute(
        """
        SELECT 1 FROM matches
        WHERE ((team1_id = ? AND team2_id = ?) OR (team1_id = ? AND team2_id = ?))
          AND abs(julianday(played_at) - julianday(?)) < ?
        """,
        (team1_id, team2_id, team2_id, team1_id, start_time, odds_repo.MAX_TIME_DIFF_DAYS),
    ).fetchone()
    return row is not None


def load_status() -> dict:
    """Lukee edellisen haun tilan. Tyhjä sanakirja, jos tiedostoa ei ole."""
    try:
        return json.loads(config.ODDS_STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_status(requests_left: int, quota_full: bool, fetched: bool = False) -> None:
    """Tallentaa haun tilan tiedostoon, josta nettisivu lukee sen (katso app/odds/status.py).

    fetched=True: maksullinen haku tehtiin juuri nyt, joten sen aika tallennetaan.
    Muuten edellisen haun aika säilytetään.
    """
    status = load_status()
    status.update(requests_left=requests_left, quota_full=quota_full,
                  month=date.today().strftime("%Y-%m"), checked_at=now_utc())
    if fetched:
        status["fetched_at"] = now_utc()
    config.ODDS_STATUS_PATH.write_text(json.dumps(status), encoding="utf-8")


def minutes_since_fetch() -> float | None:
    """Montako minuuttia edellisestä maksullisesta hausta. None, jos hakua ei ole tehty."""
    fetched_at = load_status().get("fetched_at")
    if not fetched_at:
        return None
    moment = datetime.strptime(fetched_at, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - moment) / timedelta(minutes=1)


def sync_odds(conn) -> str:
    """Päivittää kertoimet. Palauttaa lyhyen tekstin lokiin.

    Jos kuukauden kiintiö on (lähes) käytetty, haku lopetetaan, ja tila
    tallennetaan, jotta sivun alalaidassa voidaan kertoa siitä.
    Kiintiö nollautuu kuun 1. päivänä, jolloin haku jatkuu itsestään.
    """
    api_key = source.read_api_key()
    if not api_key:
        return "Kertoimet: ei API-avainta (data/oddspapi_key.txt), ohitetaan."

    # Onko kertoimet jo haettu hetki sitten? Silloin ei käytetä pyyntöä turhaan.
    minutes = minutes_since_fetch()
    if minutes is not None and minutes < MIN_HOURS_BETWEEN_FETCHES * 60:
        return f"Kertoimet: haettu {minutes:.0f} min sitten, ohitetaan (ei kuluta pyyntöjä)."

    left = source.requests_left(api_key)  # ilmainen haku
    if left <= QUOTA_RESERVE:
        save_status(left, quota_full=True)
        return f"Kertoimet: kuukauden kiintiö on käytetty ({left} jäljellä), ohitetaan."

    try:
        fixtures = source.fetch_fixtures(api_key)
    except urllib.error.HTTPError as error:
        # 429 = liikaa pyyntöjä. Kiintiö on siis loppunut, vaikka laskuri ei sitä vielä näyttänyt.
        if error.code == 429:
            save_status(0, quota_full=True)
            return "Kertoimet: OddsPapi ilmoitti kiintiön täyttyneen, ohitetaan."
        raise
    save_status(left - 1, quota_full=False, fetched=True)
    saved = 0
    for fixture in fixtures:
        team1 = teams_repo.find_team(conn, *fixture["team1_names"])
        team2 = teams_repo.find_team(conn, *fixture["team2_names"])
        # Haetaan kertoimet vain otteluille, jotka näkyvät sivulla. Ilmainen haku
        # vaatii 5 sekunnin tauon, joten turhia hakuja kannattaa välttää.
        if not team1 or not team2 or not _has_match(conn, team1["id"], team2["id"], fixture["start_time"]):
            continue
        prices = source.fetch_latest_odds(api_key, fixture["fixture_id"])
        if prices:
            odds_repo.save_odds(
                conn, fixture["fixture_id"], team1["id"], team2["id"], fixture["start_time"],
                prices[0], prices[1], source.BOOKMAKER, now_utc(),
            )
            saved += 1
    conn.commit()
    return f"Kertoimet: {len(fixtures)} ottelua OddsPapissa, {saved} tallennettu ({left - 1} pyyntöä jäljellä tässä kuussa)."
