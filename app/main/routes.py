"""
Etusivun reitti.

Reitti (route) yhdistää URL-osoitteen Python-funktioon. Kun selain avaa
osoitteen "/", Flask kutsuu index()-funktiota, ja se palauttaa HTML-sivun.
"""

from flask import Blueprint, render_template

from app import config
from app.database.db import get_db
from app.matches import repository as matches_repo
from app.predictions.service import add_predictions, get_rankings
from app.roster.repository import get_recent_changes

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    conn = get_db()
    tier1 = config.TIER1_MAX_RANK
    live = matches_repo.get_live(conn, max_rank=tier1)
    upcoming = matches_repo.get_upcoming(conn, max_rank=tier1, limit=8)

    # render_template täyttää HTML-pohjan (templates/index.html) annetuilla tiedoilla.
    return render_template(
        "index.html",
        live=add_predictions(conn, live),
        upcoming=add_predictions(conn, upcoming),
        results=matches_repo.get_recent_results(conn, max_rank=tier1, limit=8),
        rankings=get_rankings(conn)[:20],  # [:20] = vain 20 ensimmäistä
        changes=get_recent_changes(conn, limit=12),
    )
