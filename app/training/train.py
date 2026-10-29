"""
Ennustemallin opetus ja testaus.

Vaiheet:
  1. Data jaetaan AJAN mukaan: viimeiset 6 kk = testijakso, sitä vanhempi = opetusjakso.
     (Satunnainen jako olisi virhe: malli näkisi "tulevaisuutta" opetuksessa.)
  2. Elo-parametrit haetaan kokeilemalla (grid search) opetusjaksolla.
  3. Logistinen regressio opetetaan opetusjaksolla.
  4. Tarkkuus mitataan testijaksolla, jota malli ei ole nähnyt, ja sitä
     verrataan yksinkertaisempiin malleihin (pelkkä VRS, pelkkä Elo).
  5. Lopuksi malli opetetaan uudelleen KOKO datalla ja tallennetaan.
     Testijakson tulos kertoo, kuinka hyvin tämä menetelmä toimii uusilla otteluilla.

Mittarit:
  - log loss: rankaisee varmoista vääristä ennusteista. Pienempi on parempi.
    Kolikonheitto (aina 50 %) = 0.693.
  - Brier score: todennäköisyyden ja tuloksen erotuksen neliö. Pienempi on parempi.
  - osumatarkkuus: kuinka usein suosikki (yli 50 %) voitti.
"""

import itertools
import math
from datetime import date, timedelta

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss

from app.predictions.elo import EloParams
from app.predictions.model import Model
from app.training.dataset import build_rows, load_vrs_history

FEATURES = ["elo_diff", "vrs_diff", "exp_diff"]
TEST_DAYS = 182  # viimeiset noin 6 kk testijaksoksi
WARMUP_DAYS = 90  # ensimmäiset 3 kk vain Elo-lukujen "lämmittelyä", ei mitata

# Kokeiltavat Elo-parametrit. Kaikki yhdistelmät käydään läpi (4 * 5 * 3 = 60 kpl).
GRID = {
    "k": [24, 32, 40, 48],
    "new_team_boost": [0, 2, 3, 4, 6],
    "inactivity_decay": [0, 0.05, 0.1],
}


def _split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Jakaa rivit opetus- ja testijaksoon ajan perusteella."""
    first, last = date.fromisoformat(rows[0]["date"]), date.fromisoformat(rows[-1]["date"])
    warmup_end = (first + timedelta(days=WARMUP_DAYS)).isoformat()
    test_start = (last - timedelta(days=TEST_DAYS)).isoformat()
    train = [r for r in rows if warmup_end <= r["date"] < test_start and r["has_vrs"]]
    test = [r for r in rows if r["date"] >= test_start]
    return train, test


def _scores(y, p) -> dict:
    """Laskee mittarit todennäköisyyksistä p ja toteutuneista tuloksista y."""
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)  # estää log(0):n
    y = np.asarray(y, dtype=float)
    return {
        "log_loss": round(float(log_loss(y, p, labels=[0, 1])), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "accuracy": round(float(accuracy_score(y, p > 0.5)), 4),
        "n": int(len(y)),
    }


def _evaluate(name: str, rows: list[dict], p) -> dict:
    """Mittarit kaikille testiotteluille ja erikseen tier 1 -otteluille."""
    y = [r["y"] for r in rows]
    tier1 = [i for i, r in enumerate(rows) if r["tier1"]]
    p = np.asarray(p)
    return {
        "name": name,
        "all": _scores(y, p),
        "tier1": _scores([y[i] for i in tier1], p[tier1]) if tier1 else None,
    }


def _matrix(rows: list[dict], flip: bool = False):
    """Muuttaa rivit numpy-taulukoiksi X (piirteet) ja y (tulokset).

    flip=True lisää jokaisen ottelun myös toisin päin (joukkueet vaihdettu,
    piirteet vastaluvuiksi, tulos käännetty). Silloin malli oppii, ettei
    joukkueiden järjestyksellä ole merkitystä.
    """
    X = np.array([[r[f] for f in FEATURES] for r in rows], dtype=float)
    y = np.array([r["y"] for r in rows], dtype=float)
    if flip:
        X, y = np.vstack([X, -X]), np.concatenate([y, 1 - y])
    return X, y


def _fit_logistic(rows: list[dict]) -> np.ndarray:
    """Opettaa logistisen regression ja palauttaa painot alkuperäisellä asteikolla.

    Piirteet ovat hyvin eri kokoisia (Elo-ero satoja, kokemusero alle 5), joten
    ne skaalataan ensin samaan kokoluokkaan (jaetaan keskihajonnalla). Muuten
    regularisointi rankaisisi pieniä piirteitä epäreilusti. Lopuksi painot
    muunnetaan takaisin, jotta niitä voi käyttää suoraan raakapiirteisiin.
    """
    X, y = _matrix(rows, flip=True)
    std = X.std(axis=0)
    std[std == 0] = 1.0
    # fit_intercept=False: ei vakiotermiä, koska kumpikaan joukkue ei ole "kotijoukkue".
    clf = LogisticRegression(fit_intercept=False, C=10.0, max_iter=1000).fit(X / std, y)
    return clf.coef_[0] / std


def _predict(weights: np.ndarray, rows: list[dict]) -> np.ndarray:
    X, _ = _matrix(rows)
    return 1 / (1 + np.exp(-(X @ weights)))


def train(conn, verbose: bool = True) -> Model:
    """Opettaa mallin tietokannan otteluilla ja tallentaa sen. Palauttaa mallin."""
    log = print if verbose else (lambda *a, **k: None)
    vrs_history = load_vrs_history(conn)

    # --- 1. Elo-parametrien haku opetusjaksolla ---
    log(f"Haetaan Elo-parametrit ({math.prod(len(v) for v in GRID.values())} yhdistelmää)...")
    best = None
    for values in itertools.product(*GRID.values()):
        params = EloParams(**dict(zip(GRID.keys(), values)))
        rows = build_rows(conn, params, vrs_history)
        train_rows, _ = _split(rows)
        loss = _scores([r["y"] for r in train_rows], [r["p_elo"] for r in train_rows])["log_loss"]
        if best is None or loss < best[0]:
            best = (loss, params, rows)
    _, params, rows = best
    log(f"  Paras: K={params.k}, uuden joukkueen kerroin={params.new_team_boost}, tauon vaikutus={params.inactivity_decay}")

    # --- 2. ja 3. Logistinen regressio opetusjaksolla, testaus testijaksolla ---
    train_rows, test_rows = _split(rows)
    weights = _fit_logistic(train_rows)

    # Vertailukohta: Valven oma kaava (sama kuin sovelluksen edellisessä versiossa).
    valve_g = 1 / math.sqrt(1 + 3 * (math.log(10) / 400) ** 2 * 75**2 / math.pi**2)
    valve_p = [1 / (1 + 10 ** (-r["vrs_diff"] * valve_g / 400)) for r in test_rows]

    results = [
        _evaluate("Pelkkä VRS (Valven kaava)", test_rows, valve_p),
        _evaluate("Pelkkä Elo (viritetty)", test_rows, [r["p_elo"] for r in test_rows]),
        _evaluate("Malli: Elo + VRS + kokemus", test_rows, _predict(weights, test_rows)),
    ]

    log(f"\nTestijakso {test_rows[0]['date']} – {test_rows[-1]['date']} (malli ei nähnyt näitä opetuksessa)")
    log(f"{'':30s} {'log loss':>9s} {'Brier':>7s} {'osumat':>7s}   {'tier 1 osumat':>14s}")
    for r in results:
        t1 = f"{r['tier1']['accuracy']:.1%} ({r['tier1']['n']})" if r["tier1"] else "–"
        log(f"{r['name']:30s} {r['all']['log_loss']:9.4f} {r['all']['brier']:7.4f} {r['all']['accuracy']:7.1%}   {t1:>14s}")

    # --- 5. Lopullinen malli koko datalla ---
    final_weights = _fit_logistic(train_rows + test_rows)
    model = Model(
        elo=params,
        w_elo=float(final_weights[0]),
        w_vrs=float(final_weights[1]),
        w_exp=float(final_weights[2]),
        metrics={
            "trained_on": date.today().isoformat(),
            "train_period": [train_rows[0]["date"], train_rows[-1]["date"]],
            "test_period": [test_rows[0]["date"], test_rows[-1]["date"]],
            "train_matches": len(train_rows),
            "results": results,
        },
    )
    model.save()
    log(f"\nMalli tallennettu. Painot: Elo {model.w_elo:.5f}, VRS {model.w_vrs:.5f}, kokemus {model.w_exp:.4f}")
    return model
