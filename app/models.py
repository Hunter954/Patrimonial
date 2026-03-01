from datetime import date, datetime
from . import db

class Asset(db.Model):
    __tablename__ = "assets"

    id = db.Column(db.Integer, primary_key=True)
    internal_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    barcode = db.Column(db.String(64), unique=True, nullable=False, index=True)

    description = db.Column(db.String(160), nullable=False)
    brand = db.Column(db.String(80), nullable=True)
    model = db.Column(db.String(80), nullable=True)
    serial_number = db.Column(db.String(80), nullable=True)

    purchase_value = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    purchase_date = db.Column(db.Date, nullable=False, default=date.today)

    cost_center = db.Column(db.String(80), nullable=True)
    location = db.Column(db.String(120), nullable=True)
    responsible = db.Column(db.String(120), nullable=True)

    useful_life_years = db.Column(db.Integer, nullable=False, default=5)
    depreciation_rate = db.Column(db.Numeric(6, 2), nullable=False, default=20.00)

    status = db.Column(db.String(20), nullable=False, default="ativo")  # ativo, baixado, manutencao

    last_inventory_date = db.Column(db.Date, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    movements = db.relationship("Movement", backref="asset", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Asset {self.internal_code} {self.description}>"

class Movement(db.Model):
    __tablename__ = "movements"

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id"), nullable=False)

    action = db.Column(db.String(80), nullable=False)
    details = db.Column(db.String(220), nullable=True)

    user_name = db.Column(db.String(80), nullable=True, default="Sistema")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<Movement {self.action} {self.created_at}>"
