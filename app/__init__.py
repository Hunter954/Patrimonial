import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

db = SQLAlchemy()

def create_app():
    load_dotenv()

    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-change-me")
    database_url = os.getenv("DATABASE_URL", "sqlite:///instance/app.db")

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if database_url.startswith("sqlite:///"):
        try:
            os.makedirs(os.path.join(app.root_path, "..", "instance"), exist_ok=True)
        except Exception:
            pass

    db.init_app(app)

    from .routes import bp
    app.register_blueprint(bp)

    with app.app_context():
        from . import models  # noqa
        db.create_all()
        from .seed import seed_if_empty
        seed_if_empty()

    return app
