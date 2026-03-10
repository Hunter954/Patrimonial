import os
from pathlib import Path

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from sqlalchemy import inspect, text


db = SQLAlchemy()


def _normalize_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        if os.getenv("PORT") or os.getenv("RAILWAY_ENVIRONMENT"):
            database_url = "sqlite:////tmp/app.db"
        else:
            database_url = "sqlite:///instance/app.db"

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    return database_url


def _resolve_upload_root(app: Flask) -> Path:
    base_upload_dir = os.getenv("UPLOAD_DIR")
    if base_upload_dir:
        return Path(base_upload_dir)

    railway_default = Path("/data/uploads")
    if railway_default.parent.exists():
        return railway_default

    return Path(app.root_path) / "static" / "uploads"


def _ensure_upload_folders(app: Flask):
    upload_root = _resolve_upload_root(app)

    item_dir = upload_root / "items"
    logo_dir = upload_root / "logos"
    item_dir.mkdir(parents=True, exist_ok=True)
    logo_dir.mkdir(parents=True, exist_ok=True)

    app.config["UPLOAD_ROOT"] = str(upload_root)
    app.config["ITEM_UPLOAD_DIR"] = str(item_dir)
    app.config["LOGO_UPLOAD_DIR"] = str(logo_dir)



def _ensure_schema(app: Flask):
    db.create_all()
    inspector = inspect(db.engine)

    if "assets" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("assets")}
        statements = []
        if "church_key" not in columns:
            statements.append("ALTER TABLE assets ADD COLUMN church_key VARCHAR(30) NOT NULL DEFAULT 'foz'")
        if "is_donation" not in columns:
            statements.append("ALTER TABLE assets ADD COLUMN is_donation BOOLEAN NOT NULL DEFAULT FALSE")
        if "image_path" not in columns:
            statements.append("ALTER TABLE assets ADD COLUMN image_path VARCHAR(255)")
        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()

    if "app_settings" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("app_settings")}
        if "church_name" not in columns:
            db.session.execute(text("ALTER TABLE app_settings ADD COLUMN church_name VARCHAR(120) NOT NULL DEFAULT 'Igreja'"))
            db.session.commit()
        if "logo_path" not in columns:
            db.session.execute(text("ALTER TABLE app_settings ADD COLUMN logo_path VARCHAR(255)"))
            db.session.commit()
        if "updated_at" not in columns:
            db.session.execute(text("ALTER TABLE app_settings ADD COLUMN updated_at TIMESTAMP"))
            db.session.commit()

    if "users" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("users")}
        if "role" not in columns:
            db.session.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'viewer'"))
            db.session.commit()
        if "is_active" not in columns:
            db.session.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"))
            db.session.commit()
        if "created_at" not in columns:
            db.session.execute(text("ALTER TABLE users ADD COLUMN created_at TIMESTAMP"))
            db.session.commit()
        if "updated_at" not in columns:
            db.session.execute(text("ALTER TABLE users ADD COLUMN updated_at TIMESTAMP"))
            db.session.commit()


def create_app():
    load_dotenv()

    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = _normalize_database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH", 5 * 1024 * 1024))

    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///"):
        try:
            os.makedirs(os.path.join(app.root_path, "..", "instance"), exist_ok=True)
        except Exception:
            pass

    _ensure_upload_folders(app)
    db.init_app(app)

    from .routes import bp
    app.register_blueprint(bp)

    with app.app_context():
        from . import models  # noqa: F401
        _ensure_schema(app)
        from .seed import seed_if_empty
        seed_if_empty()

    return app
