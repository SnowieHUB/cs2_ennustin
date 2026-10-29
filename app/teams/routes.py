"""
Joukkueiden sivut:
  /teams/        VRS-listan joukkueet vahvuusjärjestyksessä
  /teams/<id>    yhden joukkueen kokoonpano, entiset pelaajat ja ottelut
"""

from flask import Blueprint, abort, render_template

from app.database.db import get_db
from app.matches import repository as matches_repo
from app.predictions.service import add_predictions, get_rankings, team_rating
from app.teams import repository as teams_repo

# url_prefix: kaikki tämän tiedoston osoitteet alkavat /teams
bp = Blueprint("teams", __name__, url_prefix="/teams")


@bp.route("/")
def team_list():
    return render_template("teams/list.html", rankings=get_rankings(get_db()))


# <int:team_id> poimii osoitteesta numeron, esim. /teams/3 -> team_id = 3
@bp.route("/<int:team_id>")
def team_detail(team_id: int):
    conn = get_db()
    team = teams_repo.get_team(conn, team_id)
    if team is None:
        abort(404)  # palauttaa "sivua ei löydy" -virheen

    return render_template(
        "teams/detail.html",
        team=team,
        rating=team_rating(conn, team_id),
        roster=teams_repo.get_current_roster(conn, team_id),
        former=teams_repo.get_former_players(conn, team_id),
        matches=teams_repo.get_team_matches(conn, team_id),
        live=add_predictions(conn, matches_repo.get_live(conn, team_id=team_id)),
        upcoming=add_predictions(conn, matches_repo.get_upcoming(conn, team_id=team_id)),
    )
