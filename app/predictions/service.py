"""
Ennustuspalvelu: yhdistää tietokannan datan, Elo-moottorin ja opetetun mallin.

Joukkueen vahvuus lasketaan näin (katso model.py):
  1. Oma Elo-luku: kaikki tietokannan pelatut ottelut käydään läpi aikajärjestyksessä.
  2. VRS-pisteet: Valven viimeisin ranking. Listalta puuttuva joukkue saa listan pienimmät pisteet.
  3. Kokemus: pelattujen otteluiden määrä.
  Nämä yhdistetään opetetuilla painoilla.
"""

from dataclasses import dataclass
from datetime import date

from app.matches import repository as matches_repo
from app.predictions.elo import EloEngine, match_score
from app.predictions.model import MODEL_PATH, Model
from app.predictions.series import MODEL_FORMAT, all_formats, map_probability
from app.teams import repository as teams_repo


@dataclass
class RatingState:
    """Kaikki ennustamiseen tarvittava yhdessä paketissa."""

    model: Model
    engine: EloEngine
    vrs_points: dict[int, float]
    default_vrs: float

    def strength(self, team_id: int, on_date: str) -> float:
        """Joukkueen vahvuus tiettynä päivänä."""
        return self.model.strength(
            self.engine.rating_at(team_id, on_date),
            self.vrs_points.get(team_id, self.default_vrs),
            self.engine.matches_played[team_id],
        )


# Välimuisti: historian läpikäynti kestää hetken, joten tulos säilytetään,
# kunnes tietokantaan tulee uusia otteluita tai malli opetetaan uudelleen.
_cache: dict = {"key": None, "state": None}


def get_state(conn) -> RatingState:
    """Palauttaa ajantasaisen RatingStaten (välimuistista, jos data ei ole muuttunut)."""
    count, max_id = conn.execute(
        "SELECT COUNT(*), MAX(id) FROM matches WHERE status = 'completed'"
    ).fetchone()
    vrs_date = conn.execute("SELECT MAX(vrs_date) FROM teams").fetchone()[0]
    model_time = MODEL_PATH.stat().st_mtime if MODEL_PATH.exists() else 0
    key = (count, max_id, vrs_date, model_time)
    if _cache["key"] == key:
        return _cache["state"]

    model = Model.load()
    engine = EloEngine(model.elo)
    for m in matches_repo.get_all_completed(conn):
        engine.process(m["team1_id"], m["team2_id"], match_score(m["team1_id"], m["winner_id"]), m["played_at"])

    vrs_points = {
        row["id"]: row["vrs_points"]
        for row in conn.execute("SELECT id, vrs_points FROM teams WHERE vrs_points IS NOT NULL")
    }
    state = RatingState(model, engine, vrs_points, min(vrs_points.values(), default=0.0))
    _cache.update(key=key, state=state)
    return state


def get_rankings(conn) -> list[dict]:
    """VRS-listan joukkueet järjestettynä mallin vahvuuden mukaan, paras ensin.

    "rating" näytetään Elo-tyyppisenä lukuna: 1500 = listan keskitaso, ja
    400 pisteen ero tarkoittaa noin 91 %:n voittotodennäköisyyttä.
    """
    state = get_state(conn)
    today = date.today().isoformat()
    ranked = [t for t in teams_repo.get_all_teams(conn) if t["vrs_rank"] is not None]
    strengths = {t["id"]: state.strength(t["id"], today) for t in ranked}
    if not strengths:
        return []
    mean = sum(strengths.values()) / len(strengths)

    rankings = [
        {"team": t, "rating": 1500 + Model.display_points(strengths[t["id"]] - mean)}
        for t in ranked
    ]
    rankings.sort(key=lambda item: item["rating"], reverse=True)
    return rankings


def team_rating(conn, team_id: int) -> float:
    """Yhden joukkueen vahvuus samalla asteikolla kuin get_rankings()."""
    for item in get_rankings(conn):
        if item["team"]["id"] == team_id:
            return item["rating"]
    return 0.0


def add_predictions(conn, matches) -> list[dict]:
    """Lisää jokaiseen otteluun voittotodennäköisyydet.

    Todennäköisyys lasketaan ottelun omalle formaatille (Bo1/Bo3/Bo5).
    Jos formaattia ei tiedetä, oletetaan Bo3.
    Lisäksi mukaan tulevat kaikkien formaattien luvut (item["formats"]).
    """
    state = get_state(conn)
    result = []
    for match in matches:
        item = dict(match)  # sqlite3.Row -> muokattava sanakirja
        s1 = state.strength(match["team1_id"], match["played_at"])
        s2 = state.strength(match["team2_id"], match["played_at"])
        formats = all_formats(state.model.win_probability(s1, s2))
        best_of = match["best_of"] if match["best_of"] in formats else MODEL_FORMAT
        item["formats"] = formats
        item["prob1"] = formats[best_of]
        item["prob2"] = 1.0 - item["prob1"]
        # Jos joukkueella on vähän otteluita historiassa, ennuste on epävarma.
        item["uncertain"] = min(
            state.engine.matches_played[match["team1_id"]],
            state.engine.matches_played[match["team2_id"]],
        ) < 10
        result.append(item)
    return result


def predict_match(conn, team_a_id: int, team_b_id: int) -> dict:
    """Ennustaa, kumpi kahdesta joukkueesta voittaisi tänään."""
    state = get_state(conn)
    today = date.today().isoformat()
    prob_a = state.model.win_probability(state.strength(team_a_id, today), state.strength(team_b_id, today))
    return {
        "rating_a": team_rating(conn, team_a_id),
        "rating_b": team_rating(conn, team_b_id),
        "prob_a": prob_a,
        "prob_b": 1.0 - prob_a,
    }


def predict_series(conn, team_a_id: int, team_b_id: int) -> dict:
    """Ennuste kahdelle joukkueelle kaikissa formaateissa.

    Palauttaa: {"map": kartan todennäköisyys, "formats": {1: ..., 3: ..., 5: ...},
                "rating_a": ..., "rating_b": ...}
    Todennäköisyydet ovat joukkueen A näkökulmasta.
    """
    base = predict_match(conn, team_a_id, team_b_id)
    return {
        "rating_a": base["rating_a"],
        "rating_b": base["rating_b"],
        "map": map_probability(base["prob_a"]),
        "formats": all_formats(base["prob_a"]),
    }


def get_model_metrics() -> dict:
    """Harjoittelun tulokset (tarkkuus ym.) sivulla näyttämistä varten."""
    return Model.load().metrics
