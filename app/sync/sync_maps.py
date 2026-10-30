"""
Turnaussivujen synkronointi: kartat, kierrokset, HLTV-tunnukset ja käynnissä
olevien otteluiden tilanne.

Kaksi tapaa:
  sync_maps(conn)  turnaukset aikaväliltä (ensimmäisellä kerralla 6 kk, sen jälkeen 2 viikkoa)
  sync_live(conn)  vain käynnissä olevien otteluiden turnaussivut (nopea, 5 min välein)
"""

from datetime import date, timedelta

from app.maps import repository as maps_repo
from app.matches import repository as matches_repo
from app.sync.sources import liquipedia_tournaments as source
from app.teams import repository as teams_repo

FIRST_RUN_DAYS = 182  # ensimmäinen haku: puoli vuotta karttatilastoja varten
UPDATE_DAYS = 14      # myöhemmät haut: viimeiset kaksi viikkoa riittävät


def _team_id(conn, page: str) -> int:
    """Liquipedian sivun nimestä joukkueen id. Luo joukkueen, jos sitä ei ole."""
    row = conn.execute("SELECT id FROM teams WHERE liquipedia_page = ?", (page,)).fetchone()
    if row:
        return row["id"]
    team = teams_repo.find_team(conn, page)
    team_id = team["id"] if team else teams_repo.get_or_create_team(conn, page)
    teams_repo.set_liquipedia_page(conn, team_id, page)
    return team_id


def _save_pages(conn, pages: dict[str, str], save_results: bool) -> tuple[int, int]:
    """Jäsentää sivut ja tallentaa ottelut. Palauttaa (sarjoja, karttoja).

    save_results=True: päättyneet ottelut tallennetaan myös tuloksiksi (matches-tauluun).
    Näin ottelu siirtyy tuloksiin, vaikka Liquipedia:Matches-lista olisi jäänyt jälkeen.
    """
    parsed = {title: source.parse_tournament_matches(text) for title, text in pages.items()}

    # Selvitetään uudet joukkuelyhenteet kerralla (yksi raskas pyyntö / 100 lyhennettä).
    known = maps_repo.get_template_pages(conn)
    needed = sorted({t for matches in parsed.values() for m in matches for t in (m["team1"], m["team2"])} - set(known))
    for template, page in source.resolve_team_pages(needed).items():
        maps_repo.save_template_page(conn, template, page)
        known[template] = page

    series_count = map_count = 0
    for title, matches in parsed.items():
        for m in matches:
            if m["team1"] not in known or m["team2"] not in known:
                continue  # lyhennettä ei tunnistettu
            team1_id, team2_id = _team_id(conn, known[m["team1"]]), _team_id(conn, known[m["team2"]])
            maps_repo.save_series(conn, title, m, team1_id, team2_id)
            series_count += 1
            map_count += len(m["maps"])
            if save_results and m["finished"] and m["score1"] != m["score2"]:
                matches_repo.save_match(
                    conn, m["played_at"], None, m["best_of"], "completed",
                    team1_id, team2_id, m["score1"], m["score2"], source="liquipedia",
                )
    conn.commit()
    return series_count, map_count


def sync_maps(conn, days: int | None = None) -> str:
    """Hakee turnausten ottelut ja kartat. Palauttaa tekstin lokiin."""
    if days is None:
        # Jos vanhin tallennettu ottelu on alle 5 kk vanha, historiaa ei ole vielä haettu
        # (esim. vain live-haku on ajettu). Silloin haetaan koko puoli vuotta.
        earliest = maps_repo.earliest_series_date(conn)
        history_start = (date.today() - timedelta(days=FIRST_RUN_DAYS - 30)).isoformat()
        days = UPDATE_DAYS if earliest and earliest[:10] <= history_start else FIRST_RUN_DAYS
    since = (date.today() - timedelta(days=days)).isoformat()
    until = (date.today() + timedelta(days=7)).isoformat()

    titles = source.list_tournaments(since, until)
    pages = source.fetch_tournament_pages(titles)
    series_count, map_count = _save_pages(conn, pages, save_results=False)
    return f"Kartat: {len(titles)} turnausta ({days} pv), {series_count} ottelua, {map_count} karttaa."


def sync_live(conn) -> str:
    """Päivittää käynnissä olevien otteluiden tilanteen niiden turnaussivuilta."""
    live = matches_repo.get_live(conn)
    titles = sorted({t for t in (source.title_from_url(m["event_url"]) for m in live) if t})
    if not titles:
        return "Live: ei käynnissä olevia otteluita."
    pages = source.fetch_tournament_pages(titles)
    series_count, _ = _save_pages(conn, pages, save_results=True)
    return f"Live: {len(live)} käynnissä, {len(titles)} turnaussivua, {series_count} ottelua päivitetty."
