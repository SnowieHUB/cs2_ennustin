"""
Ennustesivu:
  /predict   kahden joukkueen ennuste Bo1-, Bo3- ja Bo5-formaatissa ja tulevat ottelut
  /series    vanha sarjaennusteen osoite, ohjaa /predict-sivulle

Sivuilla valitaan kaksi joukkuetta. Kun lomake lähetetään, valinnat tulevat
osoitteeseen parametreina (esim. /predict?team_a=1&team_b=2), ja sivu
näyttää ennusteen.
"""

from flask import Blueprint, redirect, render_template, request, url_for

from app import config
from app.database.db import get_db
from app.matches import repository as matches_repo
from app.maps.service import compare_teams
from app.predictions.series import FORMATS
from app.predictions.service import add_predictions, predict_series
from app.teams import repository as teams_repo
from app.teams.names import SHORT_NAMES, name_key

bp = Blueprint("predictions", __name__)


def _ranked_teams(conn):
    """Valikon joukkueet aakkosjärjestyksessä.

    Vain VRS-listan joukkueet, koska historiassa on noin 2 000 joukkuetta, mikä olisi liikaa.
    casefold() tekee vertailusta kirjainkoosta riippumattoman, joten "fnatic" ja "FURIA"
    menevät oikeisiin kohtiin.
    """
    teams = [t for t in teams_repo.get_all_teams(conn) if t["vrs_rank"] is not None]
    return sorted(teams, key=lambda t: t["name"].casefold())


def _short_names(teams) -> list[tuple[str, str]]:
    """Lyhenteet, joiden joukkue on valikossa: [("NAVI", "Natus Vincere"), ...]"""
    names = {t["name"] for t in teams}
    return [(short, full) for short, full in SHORT_NAMES.items() if full in names]


def _find_team_id(value: str | None, teams) -> int | None:
    """Muuttaa lomakkeen arvon joukkueen id:ksi.

    Kelpaavat:
      - joukkueen nimi, kirjainkoosta riippumatta ("vitality", "Team Vitality")
      - lyhenne SHORT_NAMES-listalta ("NAVI")
      - numero (vanhat linkit, esim. ?team_a=3)
    """
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return int(value)
    # Lyhenne -> koko nimi. Haku ilman kirjainkoon merkitystä.
    shorts = {short.casefold(): full for short, full in SHORT_NAMES.items()}
    value = shorts.get(value.casefold(), value)
    # Verrataan nimiavaimilla (katso teams/names.py), jolloin myös "Team Vitality" löytyy.
    for team in teams:
        if team["name_key"] == name_key(value):
            return team["id"]
    return None


def _selected_teams(teams):
    """Lukee valitut joukkueet osoitteesta. Palauttaa (a, b, virheilmoitus tai None)."""
    raw_a, raw_b = request.args.get("team_a"), request.args.get("team_b")
    team_a_id, team_b_id = _find_team_id(raw_a, teams), _find_team_id(raw_b, teams)

    # Kerätään kaikki nimet, joita ei löytynyt, jotta virheilmoitus kertoo ne kaikki.
    not_found = [raw for raw, team_id in ((raw_a, team_a_id), (raw_b, team_b_id)) if raw and team_id is None]
    if not_found:
        error = "Joukkuetta ei löytynyt: " + ", ".join(not_found) + ". Valitse nimi listalta."
    elif team_a_id and team_a_id == team_b_id:
        error = "Valitse kaksi eri joukkuetta."
    else:
        error = None
    return team_a_id, team_b_id, error


@bp.route("/predict")
def predict():
    """Kahden joukkueen ennuste kaikissa formaateissa sekä tulevat tier 1 -ottelut."""
    conn = get_db()
    teams = _ranked_teams(conn)
    team_a_id, team_b_id, error = _selected_teams(teams)

    result = None
    if team_a_id and team_b_id and not error:
        result = predict_series(conn, team_a_id, team_b_id)
        result["team_a"] = teams_repo.get_team(conn, team_a_id)
        result["team_b"] = teams_repo.get_team(conn, team_b_id)
        result["maps"] = compare_teams(conn, team_a_id, team_b_id)

    # Tulevat tier 1 -ottelut kaikissa formaateissa.
    upcoming = add_predictions(conn, matches_repo.get_upcoming(conn, max_rank=config.TIER1_MAX_RANK, limit=20))

    return render_template(
        "predictions/predict.html",
        teams=teams,
        short_names=_short_names(teams),
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        result=result,
        error=error,
        upcoming=upcoming,
        formats=FORMATS,
    )


@bp.route("/series")
def series():
    """Vanha Sarjaennuste-sivu on yhdistetty Ennusta-sivuun. Vanhat linkit ohjataan sinne.

    request.args sisältää osoitteen parametrit (team_a, team_b), jotka siirretään mukana.
    """
    return redirect(url_for("predictions.predict", **request.args))
