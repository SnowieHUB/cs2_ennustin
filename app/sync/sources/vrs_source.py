"""
Datalähde: Valven virallinen CS2-ranking (Valve Regional Standings, VRS).

Valve julkaisee rankingin noin kerran kuukaudessa GitHubissa:
  https://github.com/ValveSoftware/counter-strike_regional_standings

Repo kloonataan kansioon data/vrs_repo gitillä. Ladataan vain tarvittavat
tiedostot ("sparse checkout"), joten kopio on noin 30 Mt eikä useita satoja.
Gitillä ei myöskään ole GitHubin API:n 60 pyynnön tuntirajaa.

Repossa on kahdenlaisia tiedostoja:

1. Rankinglista  live/2026/standings_global_2026_10_05.md
     | Standing | Points | Team Name | Roster                           | details |
     | 3        |   1911 | Vitality  | apEX, flameZ, mezii, ropz, ZywOo | [...]   |

2. Joukkueen tiedot  live/2026/details/2026_10_05/0003--vitality--....md
   Sisältää kaikki joukkueen ottelut edeltäneiltä 6 kuukaudelta:
     | Match Played | Match ID | Date | Opponent | W/L | ... | Roster |
   Näistä kootaan ennustemallin harjoitusdata.
"""

import re
import subprocess
from datetime import date, timedelta
from pathlib import Path

from app import config
from app.sync.sources.base import RosterSource

REPO_URL = "https://github.com/ValveSoftware/counter-strike_regional_standings.git"
REPO_DIR = config.DATA_DIR / "vrs_repo"

_STANDINGS_PATTERN = re.compile(r"standings_global_(\d{4})_(\d{2})_(\d{2})\.md$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --- Git-kopion hallinta --------------------------------------------------

def _git(*args: str) -> str:
    """Ajaa git-komennon repon kansiossa ja palauttaa tulosteen."""
    result = subprocess.run(["git", "-C", str(REPO_DIR), *args], capture_output=True, text=True, check=True)
    return result.stdout


def update_repo(history_months: int = 27) -> None:
    """Kloonaa repon (ensimmäisellä kerralla) tai päivittää sen uusimpaan versioon.

    history_months: kuinka kauas taaksepäin joukkuetiedostoja ladataan.
    27 kk = kahden vuoden harjoitusdata + 3 kk "lämmittelyä" Elo-luvuille.
    """
    if not (REPO_DIR / ".git").exists():
        print("Kloonataan Valven VRS-repo (ensimmäinen kerta)...")
        # --depth 1 = vain uusin versio, ei koko historiaa
        # --filter=blob:none + --no-checkout = tiedostojen sisältöä ei ladata vielä
        subprocess.run(
            ["git", "clone", "--depth", "1", "--filter=blob:none", "--no-checkout", "-q", REPO_URL, str(REPO_DIR)],
            check=True,
        )
        _git("sparse-checkout", "init", "--no-cone")
    else:
        _git("fetch", "--depth", "1", "-q", "origin", "main")
        _git("reset", "--hard", "-q", "origin/main")

    # Valitaan ladattavat kansiot ja ladataan vain ne.
    patterns = ["live/*/standings_global_*.md"]
    patterns += [f"{release_dir}/*" for release_dir in choose_detail_releases(history_months)]
    _git("sparse-checkout", "set", "--no-cone", *patterns)
    _git("checkout", "-q", "main")


def _all_detail_dirs() -> list[tuple[str, str]]:
    """Kaikki julkaisujen joukkuetiedostokansiot muodossa (päivä, polku), vanhin ensin.

    git ls-tree listaa kansiot ilman, että niiden sisältöä tarvitsee ladata.
    """
    dirs = []
    for line in _git("ls-tree", "-d", "--name-only", "HEAD", "live/").split():
        year_dir = line.strip()
        for sub in _git("ls-tree", "-d", "--name-only", "HEAD", f"{year_dir}/details/").split():
            release = sub.rsplit("/", 1)[-1]  # esim. "2026_10_05"
            dirs.append((release.replace("_", "-"), sub))
    return sorted(dirs)


def choose_detail_releases(history_months: int) -> list[str]:
    """Valitsee julkaisut niin, että niiden 6 kk:n ikkunat kattavat koko jakson.

    Joka julkaisun lataaminen olisi turhaa, koska ikkunat menevät päällekkäin.
    Otetaan julkaisu noin 3 kk:n välein (puolet päällekkäin, jotta joukkueet,
    jotka putoavat listalta välillä, eivät jää pois) ja aina uusin.
    """
    start = (date.today() - timedelta(days=30 * history_months)).isoformat()
    candidates = [(d, path) for d, path in _all_detail_dirs() if d >= start]
    chosen, last = [], None
    for d, path in candidates:
        if last is None or date.fromisoformat(d) - date.fromisoformat(last) >= timedelta(days=85):
            chosen.append(path)
            last = d
    if candidates and candidates[-1][1] not in chosen:
        chosen.append(candidates[-1][1])
    return chosen


# --- Tiedostojen listaus ja jäsentäminen ---------------------------------

def list_global_standings() -> list[tuple[str, Path]]:
    """Kaikki paikalliset rankinglistat muodossa (päivä, polku), vanhin ensin."""
    files = []
    for path in REPO_DIR.glob("live/*/standings_global_*.md"):
        match = _STANDINGS_PATTERN.search(path.name)
        if match:
            files.append(("-".join(match.groups()), path))
    return sorted(files)


def _table_rows(markdown: str):
    """Käy läpi Markdown-taulukon rivit ja palauttaa jokaisen rivin solut listana."""
    for line in markdown.splitlines():
        # "| 3 | 1911 | Vitality | ... |" -> ["3", "1911", "Vitality", ...]
        yield [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_standings(markdown: str) -> list[dict]:
    """Muuttaa rankingtiedoston taulukon listaksi joukkueita."""
    teams = []
    for cells in _table_rows(markdown):
        # Hyväksytään vain rivit, joiden ensimmäinen solu on numero (otsikkorivit hylätään).
        if len(cells) < 4 or not cells[0].isdigit():
            continue
        rank, points, name, roster = cells[0], cells[1], cells[2], cells[3]
        teams.append(
            {
                "name": name,
                "vrs_rank": int(rank),
                "vrs_points": float(points),
                "players": [{"nickname": nick.strip()} for nick in roster.split(",") if nick.strip()],
            }
        )
    return teams


def parse_details(markdown: str) -> tuple[str, list[dict]]:
    """Jäsentää joukkuetiedoston: palauttaa joukkueen nimen ja sen ottelut.

    Jokainen ottelu: {"date": "2026-09-20", "opponent": "Aurora", "won": True}
    """
    name_match = re.search(r"Team Name: (.*?)<br", markdown)
    team = name_match.group(1).strip() if name_match else ""
    matches = []
    for cells in _table_rows(markdown):
        # Ottelurivi: 1. solu numero, 3. solu päivämäärä, 5. solu W tai L.
        if len(cells) >= 5 and cells[0].isdigit() and _DATE_PATTERN.match(cells[2]) and cells[4] in ("W", "L"):
            matches.append({"date": cells[2], "opponent": cells[3], "won": cells[4] == "W"})
    return team, matches


def iter_detail_files():
    """Käy läpi kaikki ladatut joukkuetiedostot."""
    yield from sorted(REPO_DIR.glob("live/*/details/*/*.md"))


class VrsStandingsSource(RosterSource):
    """Yksi rankingjulkaisu kokoonpanojen lähteenä.

    top_n rajaa joukkueiden määrää. Listalla on satoja joukkueita, mutta
    meitä kiinnostavat lähinnä parhaat. Pienempi määrä vähentää myös riskiä,
    että kaksi eri pelaajaa samalla nimimerkillä sekoittuvat.
    """

    def __init__(self, path: Path, top_n: int = 100):
        self.path = path
        self.top_n = top_n

    def fetch_rosters(self) -> list[dict]:
        teams = parse_standings(self.path.read_text(encoding="utf-8"))
        return [team for team in teams if team["vrs_rank"] <= self.top_n]
