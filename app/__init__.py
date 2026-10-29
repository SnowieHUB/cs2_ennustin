"""
Sovelluksen käynnistyspiste: create_app() rakentaa Flask-sovelluksen.

Tätä tapaa kutsutaan "application factoryksi". Sovellusta ei luoda heti
tiedostoa ladattaessa, vaan funktiokutsulla. Hyöty: testeissä voidaan
luoda oma sovellus, joka käyttää eri tietokantaa kuin oikea sovellus.
"""

from flask import Flask

from app import config, filters
from app.database import db


def create_app(database_path=None) -> Flask:
    """Luo ja palauttaa valmiin Flask-sovelluksen."""
    flask_app = Flask(__name__)

    # Jos tietokannan polkua ei anneta, käytetään oletusta asetuksista.
    flask_app.config["DATABASE_PATH"] = database_path or config.DATABASE_PATH

    # Suljetaan tietokantayhteys automaattisesti jokaisen sivupyynnön lopuksi.
    flask_app.teardown_appcontext(db.close_db)

    # Omat suodattimet HTML-pohjiin, esim. {{ aika | local_time }}
    flask_app.add_template_filter(filters.local_time)
    flask_app.add_template_filter(filters.percent)
    flask_app.add_template_filter(filters.flag)

    # Blueprint = yhden osa-alueen reitit (sivut) omana kokonaisuutenaan.
    # Tuodaan ne vasta tässä, jotta jokainen osa pysyy omassa kansiossaan.
    from app.main.routes import bp as main_bp
    from app.teams.routes import bp as teams_bp
    from app.players.routes import bp as players_bp
    from app.predictions.routes import bp as predictions_bp
    from app.matches.routes import bp as matches_bp

    flask_app.register_blueprint(main_bp)
    flask_app.register_blueprint(teams_bp)
    flask_app.register_blueprint(players_bp)
    flask_app.register_blueprint(predictions_bp)
    flask_app.register_blueprint(matches_bp)

    return flask_app
