"""
Testit sarjaformaattien laskennalle (app/predictions/series.py).
"""

from app.predictions.series import all_formats, map_probability, series_probability


def test_bo1_is_one_map():
    assert series_probability(0.63, 1) == 0.63


def test_bo3_and_bo5_formulas():
    p = 0.6
    assert abs(series_probability(p, 3) - p**2 * (3 - 2 * p)) < 1e-12
    assert abs(series_probability(p, 5) - p**3 * (10 - 15 * p + 6 * p**2)) < 1e-12


def test_even_match_stays_even():
    assert all(abs(v - 0.5) < 1e-9 for v in all_formats(0.5).values())


def test_longer_series_favours_favourite():
    formats = all_formats(0.69)
    assert formats[1] < formats[3] < formats[5]
    assert abs(formats[3] - 0.69) < 1e-9  # mallin oma formaatti säilyy samana


def test_map_probability_is_inverse():
    for p in (0.1, 0.35, 0.5, 0.8, 0.97):
        assert abs(map_probability(series_probability(p, 3)) - p) < 1e-9
