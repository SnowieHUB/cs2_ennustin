"""
Testit Elo-laskennalle ja ennustemallille. Aja kaikki testit komennolla:  pytest

pytest etsii automaattisesti funktiot, joiden nimi alkaa sanalla test_,
ja assert-rivi kaatuu, jos sen ehto ei ole tosi.
"""

import math

from app.predictions.elo import EloEngine, EloParams, expected_score, match_score
from app.predictions.model import Model


def test_equal_ratings_give_fifty_percent():
    assert expected_score(1500, 1500) == 0.5


def test_400_points_is_ten_to_one():
    assert abs(expected_score(1900, 1500) - 10 / 11) < 1e-9


def test_winner_gains_and_loser_loses():
    engine = EloEngine(EloParams(k=32, new_team_boost=0, inactivity_decay=0))
    p = engine.process(1, 2, 1.0, "2026-01-01")
    assert p == 0.5  # ennuste ennen ottelua
    assert engine.ratings[1] == 1516 and engine.ratings[2] == 1484


def test_new_teams_move_faster():
    engine = EloEngine(EloParams(k=32, new_team_boost=3))
    # Uuden joukkueen K = 32 * (1 + 3) = 128. Kokemuksen kertyessä K pienenee.
    assert engine.k_for(1) == 128
    engine.matches_played[1] = 90
    assert abs(engine.k_for(1) - 32 * (1 + 3 / 10)) < 1e-9  # 41.6


def test_long_break_pulls_toward_mean():
    engine = EloEngine(EloParams(inactivity_decay=0.1))
    engine.ratings[1] = 1800
    engine.last_played[1] = "2026-01-01"
    assert engine.rating_at(1, "2026-01-20") == 1800  # alle 30 pv: ei vaikutusta
    assert 1500 < engine.rating_at(1, "2026-04-01") < 1800  # noin 3 kk: lähempänä 1500:aa


def test_match_score():
    assert match_score(1, 1) == 1.0
    assert match_score(1, 2) == 0.0
    assert match_score(1, None) == 0.5


def test_default_model_equals_plain_elo():
    model = Model()
    s1, s2 = model.strength(1900, 0, 0), model.strength(1500, 0, 0)
    assert abs(model.win_probability(s1, s2) - expected_score(1900, 1500)) < 1e-9


def test_display_points_scale():
    # 400 näyttöpisteen ero vastaa samaa todennäköisyyttä kuin 400 Elo-pisteen ero.
    model = Model()
    strength_diff = 400 * math.log(10) / 400
    assert abs(Model.display_points(strength_diff) - 400) < 1e-9
    assert abs(model.win_probability(strength_diff, 0) - 10 / 11) < 1e-9
