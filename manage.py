"""
Komentorivityökalu: kaikki sovelluksen komennot yhdessä paikassa.

Käyttö:
  python manage.py init                    luo tietokannan, lataa datan ja opettaa mallin (noin 2 min)
  python manage.py init --reset            poistaa vanhan tietokannan ensin
  python manage.py sync                    päivittää rankingin, kokoonpanot, pelaajatiedot ja ottelut
  python manage.py sync --only matches     päivittää vain ottelut (nopea, aja vaikka tunnin välein)
  python manage.py sync --only odds        päivittää kertoimet (OddsPapi, 1 pyyntö / ajo)
  python manage.py train                   opettaa ennustemallin uudelleen (esim. kerran kuussa)
  python manage.py sync --file POLKU       päivittää kokoonpanot omasta JSON-tiedostosta
  python manage.py sync --pandascore       päivittää kokoonpanot PandaScoresta
  python manage.py matches --file POLKU    lataa ottelutuloksia omasta JSON-tiedostosta
  python manage.py run                     käynnistää nettisivun (http://127.0.0.1:5000)
"""

import argparse
import os
import sys
from datetime import date

from app import config, create_app
from app.database.db import connect, init_schema
from app.sync.sources import vrs_source
from app.sync.sources.json_source import JsonFileSource
from app.sync.sync_matches import load_matches_from_json, sync_liquipedia_matches
from app.sync.sync_rosters import sync_from_source
from app.sync.sync_team_info import sync_team_info
from app.sync.sync_vrs import sync_vrs, sync_vrs_matches


def print_changes(changes) -> None:
    """Tulostaa kokoonpanomuutokset (enintään 40, ettei ruutu täyty)."""
    # Ensimmäisellä latauksella jokainen pelaaja "liittyy", joten näytetään vain siirrot ja lähdöt.
    interesting = [c for c in changes if c.kind != "liittyi"]
    joined = len(changes) - len(interesting)
    for change in interesting[:40]:
        print(" ", change)  # käyttää RosterChange-luokan __str__-metodia
    if len(interesting) > 40:
        print(f"  ... ja {len(interesting) - 40} muuta")
    print(f"  Yhteensä: {joined} liittymistä, {len(interesting)} muuta muutosta.")


def cmd_init(args) -> None:
    """Luo tietokannan ja lataa datan."""
    if args.reset and config.DATABASE_PATH.exists():
        config.DATABASE_PATH.unlink()  # poistaa tiedoston
        print("Vanha tietokanta poistettu.")

    conn = connect(config.DATABASE_PATH)
    init_schema(conn)

    print("1/5 Valven VRS-data (GitHub)")
    vrs_source.update_repo()
    # Kuuden kuukauden rankinghistoria, jotta siirrot näkyvät historiassa.
    print_changes(sync_vrs(conn, months=args.months, top_n=config.VRS_TOP_N))

    print("2/5 Otteluhistoria (noin 2 vuotta)")
    print(f"  {sync_vrs_matches(conn)} ottelua")

    print("3/5 Tulevat ottelut ja tuoreet tulokset (Liquipedia)")
    upcoming, results = sync_liquipedia_matches(conn)
    print(f"  {upcoming} tulevaa, {results} tulosta")

    print("4/5 Pelaajien roolit ja tiedot (Liquipedia)")
    teams_found, players = sync_team_info(conn, top_n=config.VRS_TOP_N)
    print(f"  {teams_found} joukkuetta, {players} pelaajaa päivitetty")

    print("5/5 Ennustemallin opetus")
    from app.training.train import train  # tuodaan vasta tässä: scikit-learn on iso kirjasto
    train(conn)
    conn.close()
    print(f"\nValmis: {config.DATABASE_PATH}")


def cmd_sync(args) -> None:
    """Päivittää datan valitusta lähteestä ja tulostaa muutokset."""
    conn = connect(config.DATABASE_PATH)
    init_schema(conn)  # varmistaa, että taulut ovat olemassa

    if args.file:
        print_changes(sync_from_source(conn, JsonFileSource(args.file), args.date))
    elif args.pandascore:
        # Tuodaan vasta tarvittaessa, jotta tämä ei hidasta muita komentoja.
        from app.sync.sources.pandascore_source import PandaScoreSource

        token = os.environ.get("PANDASCORE_TOKEN")
        if not token:
            sys.exit("Aseta ensin API-avain: export PANDASCORE_TOKEN=avaimesi")
        print_changes(sync_from_source(conn, PandaScoreSource(token), args.date))
    else:
        # Oletus: kaikki lähteet. --only rajaa yhteen.
        if args.only in (None, "vrs"):
            vrs_source.update_repo()
            print_changes(sync_vrs(conn, months=1, top_n=config.VRS_TOP_N))
            print(f"VRS-otteluhistoria: {sync_vrs_matches(conn)} uutta ottelua")
        if args.only in (None, "matches"):
            upcoming, results = sync_liquipedia_matches(conn)
            print(f"Ottelut: {upcoming} tulevaa, {results} uutta tulosta.")
        if args.only in (None, "teams"):
            teams_found, players = sync_team_info(conn, top_n=config.VRS_TOP_N)
            print(f"Pelaajatiedot: {teams_found} joukkuetta, {players} pelaajaa.")
        if args.only == "odds":
            # Ei mukana oletuksena: ilmaisessa tilissä on vain 250 pyyntöä kuukaudessa,
            # joten kertoimille on oma cron-rivi, jonka tahti on laskettu kiintiön mukaan.
            from app.sync.sync_odds import sync_odds
            print(sync_odds(conn))
    conn.close()


def cmd_matches(args) -> None:
    """Lataa ottelutuloksia tiedostosta."""
    conn = connect(config.DATABASE_PATH)
    added = load_matches_from_json(conn, args.file)
    conn.close()
    print(f"{added} uutta ottelua ladattu.")


def cmd_train(args) -> None:
    """Opettaa ennustemallin uudelleen tietokannan otteluilla."""
    from app.training.train import train

    conn = connect(config.DATABASE_PATH)
    train(conn)
    conn.close()


def cmd_run(args) -> None:
    """Käynnistää kehityspalvelimen. debug=True lataa koodin uudelleen, kun tallennat muutoksia."""
    create_app().run(debug=True, port=args.port)


def main() -> None:
    # argparse lukee komentoriviltä annetut argumentit ja tekee --help-ohjeen automaattisesti.
    parser = argparse.ArgumentParser(description="CS2 Ennustin")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="luo tietokanta ja lataa data")
    p_init.add_argument("--reset", action="store_true", help="poista vanha tietokanta ensin")
    p_init.add_argument("--months", type=int, default=6, help="montako kuukautta rankinghistoriaa (oletus 6)")
    p_init.set_defaults(func=cmd_init)

    p_sync = sub.add_parser("sync", help="päivitä data")
    p_sync.add_argument("--only", choices=["vrs", "matches", "teams", "odds"], help="päivitä vain yksi lähde")
    p_sync.add_argument("--file", help="JSON-tiedosto, jossa kokoonpanot")
    p_sync.add_argument("--pandascore", action="store_true", help="hae kokoonpanot PandaScoren API:sta")
    p_sync.add_argument("--date", default=date.today().isoformat(), help="muutosten päivä (oletus: tänään)")
    p_sync.set_defaults(func=cmd_sync)

    p_matches = sub.add_parser("matches", help="lataa ottelutuloksia tiedostosta")
    p_matches.add_argument("--file", required=True)
    p_matches.set_defaults(func=cmd_matches)

    p_train = sub.add_parser("train", help="opeta ennustemalli uudelleen")
    p_train.set_defaults(func=cmd_train)

    p_run = sub.add_parser("run", help="käynnistä nettisivu")
    p_run.add_argument("--port", type=int, default=5000)
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)  # kutsuu valitun komennon funktiota


# Tämä ehto on tosi vain, kun tiedosto ajetaan suoraan (python manage.py),
# ei silloin, kun se tuodaan toisesta tiedostosta importilla.
if __name__ == "__main__":
    main()
