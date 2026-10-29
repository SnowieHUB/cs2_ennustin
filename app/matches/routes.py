"""
Otteluiden sivu:
  /matches/            käynnissä olevat ja tulevat ottelut ennusteineen sekä viimeisimmät tulokset
  /matches/?all=1      myös muut kuin tier 1 -ottelut
"""

from flask import Blueprint, render_template, request

from app import config
from app.database.db import get_db
from app.matches import repository as matches_repo
from app.predictions.service import add_predictions, add_result_predictions

bp = Blueprint("matches", __name__, url_prefix="/matches")


@bp.route("/")
def match_list():
    conn = get_db()
    show_all = request.args.get("all") == "1"
    # None = ei suodatusta. Muuten näytetään vain tier 1 -ottelut.
    max_rank = None if show_all else config.TIER1_MAX_RANK

    return render_template(
        "matches/list.html",
        live=add_predictions(conn, matches_repo.get_live(conn, max_rank=max_rank)),
        upcoming=add_predictions(conn, matches_repo.get_upcoming(conn, max_rank=max_rank)),
        results=add_result_predictions(conn, matches_repo.get_recent_results(conn, max_rank=max_rank, limit=30)),
        show_all=show_all,
        tier1_rank=config.TIER1_MAX_RANK,
    )
