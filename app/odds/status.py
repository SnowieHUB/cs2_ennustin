"""
Kertoimien haun tila nettisivua varten: onko kuukauden kiintiö täynnä?
"""

import json
from datetime import date

from app import config


def quota_full() -> bool:
    """True, jos kertoimia ei voi tässä kuussa enää hakea.

    Tila on tallennettu viimeisimmän haun yhteydessä (sync_odds.py). Jos se on
    tallennettu edellisenä kuukautena, kiintiö on jo nollautunut, joten
    ilmoitusta ei näytetä.
    """
    try:
        status = json.loads(config.ODDS_STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False  # tiedostoa ei ole tai se on rikki: ei ilmoitusta
    return status.get("quota_full", False) and status.get("month") == date.today().strftime("%Y-%m")


def next_reset() -> str:
    """Seuraavan kuun 1. päivä muodossa "1.12."."""
    today = date.today()
    return f"1.{today.month % 12 + 1}."
