"""
Pelaajien sivut:
  /players/            kaikki pelaajat (haku: /players/?q=nimi)
  /players/<id>        yhden pelaajan tiedot ja urahistoria
"""

from flask import Blueprint, abort, render_template, request

from app.database.db import get_db
from app.players import repository as players_repo

bp = Blueprint("players", __name__, url_prefix="/players")


@bp.route("/")
def player_list():
    # request.args sisältää osoitteen ?-merkin jälkeiset parametrit.
    # .get("q", "") palauttaa tyhjän, jos hakua ei ole annettu.
    search = request.args.get("q", "").strip()
    players = players_repo.get_all_players(get_db(), search)
    return render_template("players/list.html", players=players, search=search)


@bp.route("/<int:player_id>")
def player_detail(player_id: int):
    conn = get_db()
    player = players_repo.get_player(conn, player_id)
    if player is None:
        abort(404)
    history = players_repo.get_player_history(conn, player_id)
    return render_template("players/detail.html", player=player, history=history)
