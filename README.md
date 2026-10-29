# CS2 Ennustin

Python-sovellus, joka seuraa oikeiden CS2-joukkueiden kokoonpanoja ja pelaajasiirtoja,
näyttää tulevat ja käynnissä olevat ottelut ja ennustaa niiden voittajat historialla
opetetulla mallilla.

## Sisällys

- [Ominaisuudet](#ominaisuudet)
- [Käytetyt tekniikat ja palvelut](#käytetyt-tekniikat-ja-palvelut)
- [Mistä data tulee](#mistä-data-tulee)
- [Ennustemalli](#ennustemalli)
- [Kansiorakenne](#kansiorakenne)
- [Käyttö omalla koneella](#käyttö-omalla-koneella)
- [Julkaisu omalle palvelimelle](#julkaisu-omalle-palvelimelle)
- [Kehityshistoria](#kehityshistoria)
- [Tunnetut rajoitukset ja jatkoideat](#tunnetut-rajoitukset-ja-jatkoideat)

## Ominaisuudet

| Sivu | Mitä näyttää |
|---|---|
| **Etusivu** `/` | *Menossa nyt* (käynnissä olevat tier 1 -ottelut), *Tulossa* ennusteineen, viimeisimmät tulokset, vahvuusranking ja viimeisimmät kokoonpanomuutokset |
| **Ottelut** `/matches/` | Käynnissä olevat, tulevat ja pelatut ottelut. Valinta tier 1 / kaikki |
| **Joukkueet** `/teams/` | VRS-listan joukkueet mallin vahvuuden mukaan järjestettynä |
| **Joukkueen sivu** `/teams/<id>` | Kokoonpano (nimi, lippu, IGL-rooli, liittymispäivä), valmentaja, entiset pelaajat, tulevat ottelut ja tulokset |
| **Pelaajat** `/players/` | Kaikki pelaajat ja haku. Pelaajan sivulla urahistoria joukkueittain |
| **Ennusta** `/predict` | Kahden joukkueen ennuste (Bo3) ja mallin tarkkuustaulukko |
| **Sarjaennuste** `/series` | Sama ottelu Bo1-, Bo3- ja Bo5-formaatissa sekä tulevat ottelut kaikissa formaateissa |

Muuta:
- **Siirtojen seuranta:** kun pelaaja vaihtaa joukkuetta, vanha jakso suljetaan ja uusi avataan, joten historia säilyy.
- **Joukkuehaku:** ennustesivuilla on hakukenttä, joka suodattaa nimiä kirjoittaessa. Haku hyväksyy myös lyhenteet (esim. NAVI).
- **Ajat Suomen ajassa**, ja ennusteet automaattisesti ottelun omalle formaatille (Bo1/Bo3/Bo5).

## Käytetyt tekniikat ja palvelut

### Ohjelmointi

| Tekniikka | Mihin |
|---|---|
| **Python 3** | Koko sovellus |
| **Flask** | Nettisivun palvelin ja reitit (osoitteet) |
| **Jinja2** | HTML-pohjat (tulee Flaskin mukana) |
| **SQLite** | Tietokanta: yksi tiedosto `data/cs2.db`, tulee Pythonin mukana |
| **scikit-learn ja numpy** | Ennustemallin opetus (logistinen regressio) ja tarkkuuden mittaus |
| **pytest** | Automaattiset testit (`tests/`) |
| **HTML ja CSS** | Ulkoasu. Ei JavaScriptiä: hakukenttä toimii HTML:n `datalist`-elementillä |

Python-kirjastot ovat tiedostossa `requirements.txt`. Muut osat (verkkopyynnöt, JSON, ajat, regex)
hoituvat Pythonin vakiokirjastolla.

### Julkaisu ja ylläpito

| Työkalu / palvelu | Mihin |
|---|---|
| **Git ja GitHub** | Versionhallinta. Koodi on repossa [SnowieHUB/cs2_ennustin](https://github.com/SnowieHUB/cs2_ennustin) |
| **GitHub CLI (`gh`)** | Repon luonti ja kirjautuminen GitHubiin komentoriviltä |
| **Linux-palvelin (Ubuntu)** | Palvelin, jolla sivu pyörii |
| **gunicorn** | Tuotantokäyttöön sopiva palvelin Flaskin kehityspalvelimen tilalle |
| **tmux** | Pitää gunicornin käynnissä taustalla, kun SSH-yhteys suljetaan |
| **cron** | Ajastaa datan päivitykset ja mallin uudelleenopetuksen |
| **Cloudflare** | Verkkotunnus, HTTPS ja suojaus |
| **Cloudflare Tunnel (`cloudflared`)** | Yhdistää palvelimen internetiin ilman reitittimen porttiohjauksia. Palvelimen IP-osoite pysyy piilossa |

## Mistä data tulee

| Lähde | Mitä | Päivittyy |
|---|---|---|
| [Valve Regional Standings](https://github.com/ValveSoftware/counter-strike_regional_standings) | Ranking, pisteet, kokoonpanot ja noin 2 vuoden otteluhistoria (noin 30 000 ottelua) | Noin kerran kuussa |
| [Liquipedia: Matches](https://liquipedia.net/counterstrike/Liquipedia:Matches) | Noin 50 tulevaa tai käynnissä olevaa ottelua ja 50 tuoretta tulosta | Jatkuvasti |
| Liquipedia: joukkuesivut | Pelaajien oikeat nimet, maat, IGL-rooli, liittymispäivät ja valmentaja | Jatkuvasti |

- **Valven repo** kloonataan gitillä kansioon `data/vrs_repo`. Vain tarvittavat tiedostot ladataan
  ("sparse checkout", noin 30 Mt). Gitillä ei ole GitHubin API:n 60 pyynnön tuntirajaa.
- **Liquipedian säännöt:** otteluhaku enintään 1 / 30 s ja sivuhaku 1 / 2 s. Koodi odottaa automaattisesti.
  Data on CC-BY-SA 3.0 -lisenssillä, joten lähde mainitaan jokaisen sivun alalaidassa.
- **Tier 1** = ainakin toinen joukkue on VRS:n top 30:ssä (`app/config.py`: `TIER1_MAX_RANK`).
  Liquipedian ottelulistassa ei ole turnauksen tasoa, joten taso päätellään joukkueista.
- **Nimien yhdistäminen:** sama joukkue on eri lähteissä eri nimellä ("Team Vitality" / "Vitality").
  `app/teams/names.py` muuttaa nimet vertailuavaimiksi, jotka täsmäävät.

### Ottelun tila

| Tila | Milloin |
|---|---|
| `upcoming` (tulossa) | Liquipedian tulevien listalla, tuloksen paikalla lukee "vs" |
| `live` (menossa) | Tulevien listalla, mutta tulos näkyy jo (esim. 1 : 1). Myös ottelu, jonka aloitusaika on mennyt, näytetään menossa olevana |
| `completed` (pelattu) | Liquipedian pelattujen listalla tai Valven historiassa |

### Roolit

Valven datassa on pelkät nimimerkit. Liquipedia merkitsee pelinjohtajan (IGL) ja valmentajan,
mutta **ei AWP-pelaajaa tai muita pelirooleja**, joten muiden pelaajien rooli jää tyhjäksi.
Noin 3/4 top 100 -joukkueista löytyy Liquipediasta automaattisesti.

## Ennustemalli

Malli yhdistää kolme piirrettä (`app/predictions/model.py`):

1. **Oma Elo-luku** koko otteluhistoriasta (`app/predictions/elo.py`). Uusien joukkueiden luku
   muuttuu nopeammin, ja pitkän tauon jälkeen lukua vedetään kohti keskiarvoa.
2. **VRS-pisteet** ottelua edeltäneestä julkaisusta.
3. **Kokemus:** pelattujen otteluiden määrä.

Piirteet yhdistetään **logistisella regressiolla**, joka muuttaa painotetun summan todennäköisyydeksi.

### Opetus (`app/training/train.py`)

- Data jaetaan **ajan mukaan**: viimeiset 6 kk ovat testijakso ja sitä vanhempi data opetusjakso.
  Malli ei näe testijaksoa opetuksessa, joten testitulos kertoo, miten se toimii uusilla otteluilla.
- Piirteet lasketaan vain ottelua edeltäneestä tiedosta, jotta malli ei "huijaa" tulevaisuuden tiedolla.
- Elo-parametrit haetaan kokeilemalla 60 yhdistelmää (grid search).
- Lopuksi malli opetetaan koko datalla ja tallennetaan tiedostoon `data/model.json`.

Testijakson tulokset (lokakuu 2026, näkyvät myös sivulla /predict):

| Malli | Osumat | Tier 1 osumat | Log loss |
|---|---|---|---|
| Pelkkä VRS (Valven kaava, sovelluksen ensimmäinen versio) | 60,0 % | 62,0 % | 0,869 |
| Pelkkä Elo (viritetty) | 63,9 % | 62,6 % | 0,626 |
| **Malli: Elo + VRS + kokemus** | **64,2 %** | **64,0 %** | **0,621** |

- **Log loss** mittaa todennäköisyyksien laatua: kolikonheitto = 0,693, ja pienempi on parempi.
  Ensimmäinen versio oli niin ylivarma, että se oli tällä mittarilla huonompi kuin kolikonheitto.
- **Noin 64 %:n osumatarkkuus** on CS2:ssa hyvä taso, koska lajissa on paljon satunnaisuutta.
- **Kokeiltu, mutta ei otettu käyttöön:**
  - tason laskeminen kokoonpanomuutoksen jälkeen: ei parantanut tulosta
  - gradient boosting: vain marginaalisesti parempi, mutta paljon vaikeampi ymmärtää ja selittää

### Bo1, Bo3 ja Bo5 (`app/predictions/series.py`)

Malli on opetettu pääosin Bo3-sarjoilla, joten sen luku tulkitaan Bo3-todennäköisyydeksi.
Siitä lasketaan puolitushaulla yhden kartan todennäköisyys p ja edelleen muut formaatit:

| Formaatti | Kaava |
|---|---|
| Bo1 | p |
| Bo3 | p² · (3 − 2p) |
| Bo5 | p³ · (10 − 15p + 6p²) |

Oletus: kartat ovat toisistaan riippumattomia. Karttapickien vaikutus vaatisi karttadataa.

## Kansiorakenne

```
cs2_ennustin/
├── manage.py                  Komentorivikomennot (init, sync, train, matches, run)
├── requirements.txt           Python-kirjastot
├── pyproject.toml             pytestin asetukset
├── data/                      Tietokanta, ladattu VRS-data ja opetettu malli (eivät ole gitissä)
├── tests/                     Automaattiset testit
└── app/
    ├── __init__.py            create_app(): kokoaa Flask-sovelluksen
    ├── config.py              Asetukset (polut, tier 1 -raja, aikavyöhyke)
    ├── filters.py             HTML-pohjien apufunktiot (Suomen aika, prosentit, liput)
    ├── database/              Taulujen rakenne (schema.sql) ja tietokantayhteys
    ├── teams/                 JOUKKUEET
    │   ├── names.py             Nimien yhdistäminen lähteiden välillä, ALIASES ja SHORT_NAMES
    │   ├── repository.py        SQL-kyselyt
    │   └── routes.py            Sivut /teams/...
    ├── players/               PELAAJAT (repository + routes /players/...)
    ├── matches/               OTTELUT
    │   ├── repository.py        Tulevat, käynnissä olevat ja pelatut ottelut
    │   └── routes.py            Sivu /matches/
    ├── roster/                KOKOONPANOT JA SIIRROT
    │   ├── repository.py        Jaksojen avaus ja sulkeminen
    │   └── service.py           Tunnistaa liittymiset, lähdöt ja siirrot
    ├── predictions/           ENNUSTUKSET
    │   ├── elo.py               Elo-moottori (ei tietokantakoodia)
    │   ├── model.py             Opetettu malli: painot ja todennäköisyyden kaava
    │   ├── series.py            Bo1/Bo3/Bo5-laskenta (ei tietokantakoodia)
    │   ├── service.py           Yhdistää datan ja mallin
    │   └── routes.py            Sivut /predict ja /series sekä joukkuehaku
    ├── training/              MALLIN OPETUS
    │   ├── dataset.py           Harjoitusrivit historiasta (ilman tulevaisuuden tietoa)
    │   └── train.py             Parametrien haku, opetus, testaus ja tallennus
    ├── sync/                  DATAN TUONTI
    │   ├── http.py              Yhteinen verkkopyyntö
    │   ├── sync_vrs.py          Ranking, kokoonpanot ja otteluhistoria
    │   ├── sync_matches.py      Tulevat, käynnissä olevat ja pelatut ottelut
    │   ├── sync_team_info.py    Pelaajien roolit, nimet ja maat
    │   ├── sync_rosters.py      Yleinen kokoonpanojen synkronointi
    │   └── sources/             Datalähteet (VRS, Liquipedia, joukkuesivut, JSON, PandaScore)
    ├── main/routes.py         Etusivu
    ├── templates/             HTML-pohjat osa-alueittain (_macros.html = yhteiset palat)
    └── static/css/style.css   Tyylit
```

Jokaisessa osa-alueessa toistuu sama jako:

| Tiedosto | Tehtävä | Esimerkki |
|---|---|---|
| `repository.py` | Vain SQL-kyselyt | "hae joukkueen nykyiset pelaajat" |
| `service.py` | Sovelluksen logiikka | "vertaa kokoonpanoja ja kirjaa siirrot" |
| `routes.py` | Nettisivun osoitteet | "/teams/3 näyttää joukkueen 3" |

## Käyttö omalla koneella

```bash
python3 -m venv .venv                # luo virtuaaliympäristö (kerran)
source .venv/bin/activate            # ota se käyttöön (joka kerta uudessa terminaalissa)
pip install -r requirements.txt      # asenna kirjastot (kerran)

python manage.py init                # lataa datan ja opettaa mallin (noin 1 min)
python manage.py run                 # kehityspalvelin: http://127.0.0.1:5000
```

| Komento | Mitä tekee |
|---|---|
| `python manage.py init` | Luo tietokannan, lataa kaiken datan ja opettaa mallin |
| `python manage.py init --reset` | Sama, mutta poistaa ensin vanhan tietokannan (tarvitaan, jos taulujen rakenne muuttuu) |
| `python manage.py sync` | Päivittää kaiken: ranking, otteluhistoria, ottelut ja pelaajatiedot |
| `python manage.py sync --only matches` | Päivittää vain tulevat, käynnissä olevat ja pelatut ottelut |
| `python manage.py sync --only teams` | Päivittää vain pelaajatiedot Liquipediasta |
| `python manage.py train` | Opettaa ennustemallin uudelleen |
| `python manage.py run` | Käynnistää kehityspalvelimen (debug-tila, **ei** internetiin) |
| `pytest` | Ajaa testit |

## Julkaisu omalle palvelimelle

Sivu voidaan julkaista omalta Linux-palvelimelta ilman, että reitittimeen avataan portteja:

```
Kävijä ──HTTPS──> Cloudflare (oma verkkotunnus) ══salattu tunneli══> cloudflared ──HTTP──> gunicorn
                                                                       └──────── palvelin ────────┘
```

### 1. Asennus

```bash
git clone https://github.com/SnowieHUB/cs2_ennustin.git
cd cs2_ennustin
sudo apt update && sudo apt install -y python3-venv
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt gunicorn
.venv/bin/python manage.py init
```

### 2. Sivu käyntiin

```bash
.venv/bin/gunicorn -w 2 -b 127.0.0.1:8000 "app:create_app()"
```

- Gunicornin voi pitää taustalla esimerkiksi **tmuxilla** tai **systemd-palveluna**.
- `127.0.0.1` tarkoittaa, että gunicorniin pääsee vain palvelimelta itseltään. Ulkopuolelta tullaan tunnelin kautta.
- Flaskin kehityspalvelinta (`manage.py run`, `debug=True`) ei saa koskaan avata internetiin.

### 3. Cloudflare Tunnel

1. Cloudflaressa: **Zero Trust → Networks → Tunnels → Create a tunnel → Cloudflared**.
2. Palvelimella: ajetaan Cloudflaren antamat asennuskomennot. Viimeinen niistä on
   `sudo cloudflared service install <avain>`. **Avain on salainen.**
3. Cloudflaressa: tunnelin **Routes → Add route → Published application**:
   oma aliverkkotunnus ja service `http://localhost:8000`.
4. Suositus: **Cloudflare Access** (Zero Trust → Access → Applications), jos sivu on tarkoitettu vain tietyille käyttäjille.

Palvelun osoitteena on `http` eikä `https`, koska liikenne kulkee saman koneen sisällä ja
Cloudflare hoitaa HTTPS:n kävijöille.

### 4. Automaattiset päivitykset (cron)

`crontab -e` ja tiedoston loppuun (vaihda polku omaksesi):

```
*/30 * * * *  cd /polku/cs2_ennustin && .venv/bin/python manage.py sync --only matches >> data/sync.log 2>&1
30 5 * * *    cd /polku/cs2_ennustin && .venv/bin/python manage.py sync >> data/sync.log 2>&1
0 7 8 * *     cd /polku/cs2_ennustin && .venv/bin/python manage.py train >> data/sync.log 2>&1
```

| Ajastus | Mitä |
|---|---|
| `*/30 * * * *` | Ottelut 30 minuutin välein, jolloin päättyneet ottelut siirtyvät tuloksiin |
| `30 5 * * *` | Kaikki data joka päivä klo 5.30 |
| `0 7 8 * *` | Mallin uudelleenopetus joka kuun 8. päivä (Valve julkaisee rankingin kuun alussa) |

Kentät ovat järjestyksessä minuutti, tunti, päivä, kuukausi ja viikonpäivä.
Sivu näyttää uuden datan heti. Gunicornia ei tarvitse käynnistää uudelleen datan päivityksen jälkeen.

### 5. Koodimuutosten vienti

1. Kehityskoneella: `git push`
2. Palvelimella: `git pull` ja gunicornin uudelleenkäynnistys
3. Jos `schema.sql` (taulujen rakenne) muuttui: `.venv/bin/python manage.py init --reset`

## Kehityshistoria

Projekti rakennettiin vaiheittain:

1. **Perusrunko:** Flask-sovellus, SQLite-tietokanta ja osa-alueittain jaettu kansiorakenne.
   Kokoonpanohistoria tallennetaan jaksoina, joten siirrot säilyvät. Ensimmäinen versio käytti keksittyä esimerkkidataa.
2. **Oikea data:** keksitty data korvattiin Valven VRS-rankingilla (joukkueet ja kokoonpanot)
   ja Liquipedian otteluilla. Tulevat tier 1 -ottelut tulivat etusivulle automaattisesti ennusteineen.
3. **Opetettu malli:** Valven julkaisuista koottiin noin 30 000 ottelun historia, ja sillä opetettiin
   ennustemalli (Elo + VRS + kokemus). Tarkkuus nousi 60 %:sta 64 %:iin, ja ylivarmuus korjaantui.
4. **Roolit ja pelaajatiedot:** Liquipedian joukkuesivuilta haetaan oikeat nimet, maat, IGL-rooli,
   liittymispäivät ja valmentajat.
5. **Bo1/Bo3/Bo5:** sarjaennuste omalle sivulleen, ja tulevien otteluiden ennuste oikealle formaatille.
6. **Julkaisu:** koodi GitHubiin, oma Linux-palvelin, gunicorn, Cloudflare Tunnel ja cron-ajastukset.
7. **Käynnissä olevat ottelut:** omat osiot *Menossa nyt*, *Tulossa* ja *Viimeisimmät tulokset*.
8. **Käytettävyys:** hakukenttä ja aakkosjärjestys ennustesivuille, lyhenteet (NAVI, NiP...)
   ja navigaatio vasemmalle.

## Tunnetut rajoitukset ja jatkoideat

### Rajoitukset

- **Kokoonpanot päivittyvät kuukauden välein**, koska ne tulevat VRS-julkaisuista. Liquipediasta tuodaan
  vain lisätietoja pelaajista, jotka ovat jo kokoonpanossa.
- **VRS-historiassa ei ole karttatuloksia eikä formaattia**, vain voittaja (näkyy sivulla muodossa V–H).
- **Nimet eri lähteissä:** jos sama joukkue näkyy kahdesti tai ilman VRS-sijoitusta, lisää nimipari
  `app/teams/names.py`:n `ALIASES`-sanakirjaan ja aja `python manage.py init --reset`.
- **Sama nimimerkki kahdessa joukkueessa:** pelaaja pidetään paremmin rankatussa joukkueessa
  (synkronointi tulostaa varoituksen).
- **Liittymispäivä** tulee Liquipediasta. Jos sitä ei löydy, käytetään vanhimman VRS-julkaisun päivää.

### Jatkoideat

- **Karttadata:** joukkueiden parhaat kartat, vetoennuste ja karttapohjainen sarjaennuste.
  Karttapoolin vaihdokset tallennettaisiin jaksoina samaan tapaan kuin kokoonpanot.
- **Kokoonpanot päivittäin Liquipediasta** kuukausittaisen VRS:n lisäksi.
