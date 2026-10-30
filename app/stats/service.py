"""
Mallin tilasto: kuinka hyvin ennusteet ovat osuneet pelatuissa otteluissa.

Jokaiselle pelatulle ottelulle on ennuste, joka laskettiin ENNEN ottelua
(katso predictions/service.py: pre_match). Tässä ne verrataan toteutuneisiin
tuloksiin, ja jos ottelulle on kertoimet, myös Pinnaclen ennusteeseen.
"""

from datetime import date, timedelta

from app.matches import repository as matches_repo
from app.predictions.model import Model
from app.predictions.service import add_result_predictions

# Luotettavuustaulukon välit suosikin todennäköisyydelle: (alaraja, yläraja).
CALIBRATION_BINS = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)]


def _hit_rate(hits: int, total: int) -> dict:
    """Osumat sanakirjana pohjaa varten. rate on None, jos otteluita ei ole."""
    return {"hits": hits, "total": total, "rate": hits / total if total else None}


def _favourite_won(prob1: float, match) -> bool:
    """Voittiko suosikki? Suosikki = joukkue, jonka todennäköisyys on yli 50 %."""
    return (prob1 > 0.5) == (match["winner_id"] == match["team1_id"])


def get_model_stats(conn, days: int | None, max_rank: int | None) -> dict:
    """Laskee tilastot. days=None = kaikki ottelut, max_rank=None = kaikki tasot."""
    since = (date.today() - timedelta(days=days)).isoformat() if days else None
    matches = add_result_predictions(conn, matches_repo.get_results_since(conn, since, max_rank))
    # Mukaan vain ottelut, joilla on ennuste ja voittaja (tasapelit ja ilman ennustetta jäävät pois).
    matches = [m for m in matches if m["correct"] is not None]

    model_hits = sum(m["correct"] for m in matches)

    # Malli vs Pinnacle samoissa otteluissa, jotta vertailu on reilu.
    with_odds = [m for m in matches if m["odds"]]
    for m in with_odds:
        m["odds_correct"] = _favourite_won(m["odds"]["fair1"], m)

    # Opetuksen jälkeen pelatut: näitä malli ei ole nähnyt, joten ne ovat rehellisin mittari.
    trained_on = Model.load().metrics.get("trained_on")
    after_training = [m for m in matches if trained_on and m["played_at"][:10] > trained_on]

    # Luotettavuus: kun malli antoi suosikille 60-70 %, voittiko suosikki noin 65 % kerroista?
    calibration = []
    for low, high in CALIBRATION_BINS:
        in_bin = [m for m in matches if low <= max(m["prob1"], m["prob2"]) < high]
        expected = sum(max(m["prob1"], m["prob2"]) for m in in_bin) / len(in_bin) if in_bin else None
        calibration.append({
            "label": f"{low * 100:.0f}–{min(high, 1) * 100:.0f} %",
            "expected": expected,
            **_hit_rate(sum(m["correct"] for m in in_bin), len(in_bin)),
        })

    return {
        "model": _hit_rate(model_hits, len(matches)),
        "model_on_odds": _hit_rate(sum(m["correct"] for m in with_odds), len(with_odds)),
        "odds": _hit_rate(sum(m["odds_correct"] for m in with_odds), len(with_odds)),
        "after_training": _hit_rate(sum(m["correct"] for m in after_training), len(after_training)),
        "trained_on": trained_on,
        "calibration": calibration,
        "odds_matches": with_odds[:30],
    }
