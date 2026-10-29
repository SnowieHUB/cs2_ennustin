"""
Omat Jinja-suodattimet (filters) HTML-pohjia varten.

Suodatinta käytetään pohjassa pystyviivalla:  {{ match.played_at | local_time }}
Ne rekisteröidään sovellukseen tiedostossa app/__init__.py.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app import config

_LOCAL_TZ = ZoneInfo(config.TIMEZONE)
_WEEKDAYS = ["ma", "ti", "ke", "to", "pe", "la", "su"]


def local_time(utc_text: str) -> str:
    """Muuttaa UTC-ajan "2026-10-29 10:15" Suomen ajaksi muotoon "to 29.10. klo 12.15"."""
    try:
        moment = datetime.strptime(utc_text, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return utc_text or ""  # pelkkä päivämäärä tai tuntematon muoto: näytetään sellaisenaan
    local = moment.astimezone(_LOCAL_TZ)
    return f"{_WEEKDAYS[local.weekday()]} {local.day}.{local.month}. klo {local.hour}.{local.minute:02d}"


def flag(code: str | None) -> str:
    """Muuttaa maakoodin lippu-emojiksi: "fi" -> 🇫🇮

    Lippu-emoji koostuu kahdesta erikoismerkistä ("regional indicator"), yksi
    kummallekin kirjaimelle. Kirjain A on merkki U+1F1E6, B on U+1F1E7 jne.
    Liquipedia käyttää Isosta-Britanniasta koodia "uk", mutta lipussa se on "GB".
    """
    if not code:
        return ""
    code = {"uk": "gb"}.get(code.lower(), code.lower())
    if len(code) != 2 or not code.isalpha():
        return code.upper()  # esim. "eu" tai "world": näytetään tekstinä
    return "".join(chr(0x1F1E6 + ord(c) - ord("a")) for c in code)


def percent(value: float) -> str:
    """0.6234 -> "62 %" """
    return f"{value * 100:.0f} %"
