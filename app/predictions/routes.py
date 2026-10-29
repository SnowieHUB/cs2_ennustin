"""
Ennustesivut:
  /predict   kahden joukkueen ennuste (Bo3) ja mallin tarkkuus
  /series    sarjaennuste: sama ottelu Bo1-, Bo3- ja Bo5-formaatissa

Sivuilla valitaan kaksi joukkuetta. Kun lomake lähetetään, valinnat tulevat
osoitteeseen parametreina (esim. /predict?team_a=1&team_b=2), ja sivu
näyttää ennusteen.
"""

from flask import Blueprint, render_template, request

from app import config
from app.database.db import get_db
from app.matches import repository as matches_repo
from app.predictions.series import FORMATS
from app.predictions.service import add_predictions, get_model_metrics, predict_match, predict_series
from app.teams import repository as teams_repo

bp = Blueprint("predictions", __name__)


def _ranked_teams(conn):
    """Valikon joukkueet: vain VRS-listan joukkueet (historiassa on noin 2 000, mikä olisi liikaa)."""
    return [t for t in teams_repo.get_all_teams(conn) if t["vrs_rank"] is not None]


def _selected_teams():
    """Lukee valitut joukkueet osoitteesta. Palauttaa (a, b, virheilmoitus tai None).

    type=int muuttaa arvon numeroksi. Jos arvo puuttuu tai on virheellinen, tulos on None.
    """
    team_a_id = request.args.get("team_a", type=int)
    team_b_id = request.args.get("team_b", type=int)
    error = "Valitse kaksi eri joukkuetta." if team_a_id and team_a_id == team_b_id else None
    return team_a_id, team_b_id, error


@bp.route("/predict")
def predict():
    conn = get_db()
    teams = _ranked_teams(conn)
    team_a_id, team_b_id, error = _selected_teams()

    result = None
    if team_a_id and team_b_id and not error:
        result = predict_match(conn, team_a_id, team_b_id)
        result["team_a"] = teams_repo.get_team(conn, team_a_id)
        result["team_b"] = teams_repo.get_team(conn, team_b_id)

    return render_template(
        "predictions/predict.html",
        teams=teams,
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        result=result,
        error=error,
        metrics=get_model_metrics(),
    )


@bp.route("/series")
def series():
    conn = get_db()
    teams = _ranked_teams(conn)
    team_a_id, team_b_id, error = _selected_teams()

    result = None
    if team_a_id and team_b_id and not error:
        result = predict_series(conn, team_a_id, team_b_id)
        result["team_a"] = teams_repo.get_team(conn, team_a_id)
        result["team_b"] = teams_repo.get_team(conn, team_b_id)

    # Tulevat tier 1 -ottelut kaikissa formaateissa.
    upcoming = add_predictions(conn, matches_repo.get_upcoming(conn, max_rank=config.TIER1_MAX_RANK, limit=20))

    return render_template(
        "predictions/series.html",
        teams=teams,
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        result=result,
        error=error,
        upcoming=upcoming,
        formats=FORMATS,
    )
