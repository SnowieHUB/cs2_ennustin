# CS2 Ennustin

Python-sovellus, joka seuraa oikeiden CS2-joukkueiden kokoonpanoja ja
pelaajasiirtoja ja näyttää tulevat ottelut voittoennusteineen nettisivulla.

## Käynnistys

```bash
python -m venv .venv                 # luo virtuaaliympäristö (kerran)
source .venv/bin/activate            # ota se käyttöön (joka kerta uudessa terminaalissa)
pip install -r requirements.txt      # asenna kirjastot (kerran)

python manage.py init                # lataa datan ja opettaa mallin (noin 1 min)
python manage.py run                 # avaa selaimessa http://127.0.0.1:5000
```

Datan päivitys:

```bash
python manage.py sync                # kaikki: ranking, otteluhistoria, ottelut, pelaajatiedot
python manage.py sync --only matches # vain tulevat ottelut ja tulokset (aja vaikka muutaman tunnin välein)
python manage.py train               # opeta malli uudelleen (esim. kun uusi VRS-julkaisu on tullut)
```

Testit: `pytest`

## Mistä data tulee

| Lähde | Mitä | Päivittyy |
|---|---|---|
| [Valve Regional Standings](https://github.com/ValveSoftware/counter-strike_regional_standings) | Ranking, pisteet, kokoonpanot ja noin 2 vuoden otteluhistoria (noin 30 000 ottelua) | Noin kerran kuussa |
| [Liquipedia: Matches](https://liquipedia.net/counterstrike/Liquipedia:Matches) | Noin 50 tulevaa ottelua ja 50 tuoretta tulosta | Jatkuvasti |
| Liquipedia: joukkuesivut | Pelaajien oikeat nimet, maat, IGL-rooli, liittymispäivät ja valmentaja | Jatkuvasti |

- Valven repo kloonataan gitillä kansioon `data/vrs_repo` (vain tarvittavat tiedostot, noin 30 Mt).
- Liquipedian säännöt: otteluhaku enintään 1 / 30 s ja sivuhaku 1 / 2 s. Koodi odottaa automaattisesti.
- **Tier 1** = ainakin toinen joukkue on VRS:n top 30:ssä (`app/config.py`: `TIER1_MAX_RANK`).

### Roolit

Valven datassa on pelkät nimimerkit. Liquipedia merkitsee pelinjohtajan (IGL) ja valmentajan,
mutta **ei AWP-pelaajaa tai muita pelirooleja**, joten muiden pelaajien rooli jää tyhjäksi.
Noin 3/4 top 100 -joukkueista löytyy Liquipediasta automaattisesti. Loput voi lisätä
`app/teams/names.py`:n `ALIASES`-listaan.

## Miten ennuste lasketaan ja opetetaan

Malli yhdistää kolme piirrettä (`app/predictions/model.py`):

1. **Oma Elo-luku** koko otteluhistoriasta. Uusien joukkueiden luku muuttuu nopeammin,
   ja pitkän tauon jälkeen lukua vedetään kohti keskiarvoa (`app/predictions/elo.py`).
2. **VRS-pisteet** ottelua edeltäneestä julkaisusta.
3. **Kokemus:** pelattujen otteluiden määrä.

Opetus (`app/training/train.py`):

- Data jaetaan **ajan mukaan**: viimeiset 6 kk ovat testijakso ja sitä vanhempi data opetusjakso.
  Malli ei näe testijaksoa opetuksessa, joten testitulos kertoo, miten se toimii uusilla otteluilla.
- Elo-parametrit haetaan kokeilemalla 60 yhdistelmää, ja logistinen regressio opetetaan
  yhdistämään piirteet.
- Lopuksi malli opetetaan koko datalla ja tallennetaan `data/model.json`-tiedostoon.

Testijakson tulokset (lokakuu 2026, näkyvät myös sivulla /predict):

| Malli | Osumat | Tier 1 osumat | Log loss |
|---|---|---|---|
| Pelkkä VRS (Valven kaava, sovelluksen vanha versio) | 60,0 % | 62,0 % | 0,869 |
| Pelkkä Elo (viritetty) | 63,9 % | 62,6 % | 0,626 |
| **Malli: Elo + VRS + kokemus** | **64,2 %** | **64,0 %** | **0,621** |

Log loss mittaa todennäköisyyksien laatua (kolikonheitto = 0,693, pienempi on parempi).
Vanha versio oli niin ylivarma, että se oli tällä mittarilla huonompi kuin kolikonheitto.
Noin 64 %:n osumatarkkuus on CS2:ssa hyvä taso, koska lajissa on paljon satunnaisuutta.

Kokeilin myös, kannattaako tasoa laskea kokoonpanomuutoksen jälkeen, ja gradient boosting -mallia.
Kokoonpanokorjaus ei parantanut tulosta. Gradient boosting oli vain marginaalisesti parempi,
mutta sitä on paljon vaikeampi ymmärtää ja selittää.

### Bo1, Bo3 ja Bo5 (sivu /series)

Malli on opetettu pääosin Bo3-sarjoilla, joten sen luku tulkitaan Bo3-todennäköisyydeksi.
Siitä lasketaan yhden kartan todennäköisyys p ja muut formaatit (`app/predictions/series.py`):

| Formaatti | Kaava |
|---|---|
| Bo1 | p |
| Bo3 | p² · (3 − 2p) |
| Bo5 | p³ · (10 − 15p + 6p²) |

Tulevien otteluiden ennuste käyttää automaattisesti ottelun omaa formaattia (Liquipediasta).
Oletus: kartat ovat toisistaan riippumattomia. Karttapickien vaikutus vaatisi karttadataa.

## Kansiorakenne

```
cs2_ennustin/
├── manage.py                  Komentorivikomennot (init, sync, matches, run)
├── data/                      Tietokanta (cs2.db)
├── tests/                     Automaattiset testit
└── app/
    ├── __init__.py            create_app(): kokoaa Flask-sovelluksen
    ├── config.py              Asetukset (polut, tier 1 -raja, aikavyöhyke)
    ├── filters.py             HTML-pohjien apufunktiot (Suomen aika, prosentit)
    ├── database/              Taulujen rakenne ja tietokantayhteys
    ├── teams/                 JOUKKUEET
    │   ├── names.py             Nimien yhdistäminen lähteiden välillä (+ ALIASES)
    │   ├── repository.py        SQL-kyselyt
    │   └── routes.py            Sivut /teams/...
    ├── players/               PELAAJAT (repository + routes)
    ├── matches/               OTTELUT (repository + routes /matches/)
    ├── roster/                KOKOONPANOT JA SIIRROT
    │   ├── repository.py        Jaksojen avaus/sulkeminen
    │   └── service.py           Tunnistaa liittymiset, lähdöt ja siirrot
    ├── predictions/           ENNUSTUKSET
    │   ├── elo.py               Elo-moottori (ei tietokantakoodia)
    │   ├── model.py             Opetettu malli: painot ja todennäköisyyden kaava
    │   ├── series.py            Bo1/Bo3/Bo5-laskenta (ei tietokantakoodia)
    │   ├── service.py           Yhdistää datan ja mallin
    │   └── routes.py            Sivut /predict (ennuste + mallin tarkkuus) ja /series (Bo1/Bo3/Bo5)
    ├── training/              MALLIN OPETUS
    │   ├── dataset.py           Harjoitusrivit historiasta (ilman tulevaisuuden tietoa)
    │   └── train.py             Parametrien haku, opetus, testaus ja tallennus
    ├── sync/                  DATAN TUONTI
    │   ├── http.py              Yhteinen verkkopyyntö
    │   ├── sync_vrs.py          Ranking, kokoonpanot ja otteluhistoria
    │   ├── sync_matches.py      Tulevat ottelut ja tuoreet tulokset
    │   ├── sync_team_info.py    Pelaajien roolit, nimet ja maat
    │   ├── sync_rosters.py      Yleinen kokoonpanojen synkronointi
    │   └── sources/             Datalähteet (VRS, Liquipedia, joukkuesivut, JSON, PandaScore)
    ├── main/routes.py         Etusivu
    ├── templates/             HTML-pohjat osa-alueittain (+ matches/_macros.html)
    └── static/css/style.css   Tyylit
```

Jokaisessa osa-alueessa toistuu sama jako:

| Tiedosto | Tehtävä | Esimerkki |
|---|---|---|
| `repository.py` | Vain SQL-kyselyt | "hae joukkueen nykyiset pelaajat" |
| `service.py` | Sovelluksen logiikka | "vertaa kokoonpanoja ja kirjaa siirrot" |
| `routes.py` | Nettisivun osoitteet | "/teams/3 näyttää joukkueen 3" |

## Tunnetut rajoitukset

- **Nimet eri lähteissä:** jos sama joukkue näkyy kahdesti tai ilman VRS-sijoitusta
  (esim. Liquipedian nimi poikkeaa paljon), lisää nimipari `app/teams/names.py`:n `ALIASES`-sanakirjaan
  ja aja `python manage.py init --reset`.
- **Sama nimimerkki kahdessa joukkueessa:** pelaaja pidetään paremmin rankatussa joukkueessa
  (synkronointi tulostaa varoituksen).
- **Kokoonpanot päivittyvät kuukauden välein**, koska ne tulevat VRS-julkaisuista. Liquipediasta tuodaan
  vain lisätietoja pelaajista, jotka ovat jo kokoonpanossa.
- **Liittymispäivä** tulee Liquipediasta. Jos sitä ei löydy, käytetään vanhimman VRS-julkaisun päivää.
- **VRS-historiassa ei ole karttatuloksia**, vain voittaja (näkyy sivulla muodossa V–H).
