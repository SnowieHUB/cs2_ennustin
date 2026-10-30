"""
Mallin tilasto -sivu:
  /stats/                 tier 1 -ottelut viimeiseltä 30 päivältä
  /stats/?days=7          ajanjakso päivinä (7, 30, 182) tai days=all
  /stats/?all=1           myös muut kuin tier 1 -ottelut
"""

from flask import Blueprint, render_template, request

from app import config
from app.database.db import get_db
from app.predictions.service import get_model_metrics
from app.stats.service import get_model_stats

bp = Blueprint("stats", __name__, url_prefix="/stats")

# Valittavat ajanjaksot: (osoitteen arvo, päiviä, teksti napissa)
PERIODS = [("7", 7, "7 pv"), ("30", 30, "30 pv"), ("182", 182, "6 kk"), ("all", None, "Kaikki")]


@bp.route("/")
def model_stats():
    conn = get_db()
    show_all = request.args.get("all") == "1"
    period = request.args.get("days", "30")
    # Tuntematon arvo -> oletus 30 päivää. next() palauttaa ensimmäisen osuman listasta.
    days = next((d for key, d, _ in PERIODS if key == period), 30)
    if period not in [key for key, _, _ in PERIODS]:
        period = "30"

    return render_template(
        "stats/model.html",
        stats=get_model_stats(conn, days, None if show_all else config.TIER1_MAX_RANK),
        metrics=get_model_metrics(),
        periods=PERIODS,
        period=period,
        show_all=show_all,
        tier1_rank=config.TIER1_MAX_RANK,
    )
