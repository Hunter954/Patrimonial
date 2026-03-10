from datetime import date, timedelta
from decimal import Decimal

from . import db
from .models import Asset, Movement


def seed_if_empty():
    if Asset.query.first():
        return

    today = date.today()
    assets = [
        Asset(
            internal_code="PAT-FOZ-0001",
            barcode="789000000001",
            church_key="foz",
            description="Notebook Dell Latitude 5420",
            brand="Dell",
            model="Latitude 5420",
            serial_number="DL-5420-XY12",
            purchase_value=Decimal("5000.00"),
            purchase_date=today - timedelta(days=550),
            cost_center="TI",
            location="Escritório - 2º andar",
            responsible="João",
            useful_life_years=5,
            depreciation_rate=Decimal("20.00"),
            status="ativo",
            last_inventory_date=today - timedelta(days=30),
        ),
        Asset(
            internal_code="PAT-FOZ-0002",
            barcode="789000000002",
            church_key="foz",
            is_donation=True,
            description="Impressora HP LaserJet Pro",
            brand="HP",
            model="M404dn",
            serial_number="HP-M404-9981",
            purchase_value=Decimal("1800.00"),
            purchase_date=today - timedelta(days=820),
            cost_center="Administração",
            location="Recepção",
            responsible="Maria",
            useful_life_years=4,
            depreciation_rate=Decimal("25.00"),
            status="manutencao",
            last_inventory_date=today - timedelta(days=120),
        ),
        Asset(
            internal_code="PAT-PY-0001",
            barcode="789000000101",
            church_key="paraguai",
            description="Projetor Epson PowerLite",
            brand="Epson",
            model="X41",
            serial_number="EP-X41-3321",
            purchase_value=Decimal("2600.00"),
            purchase_date=today - timedelta(days=1200),
            cost_center="Culto",
            location="Sala Principal",
            responsible="Carlos",
            useful_life_years=5,
            depreciation_rate=Decimal("20.00"),
            status="ativo",
            last_inventory_date=today - timedelta(days=400),
        ),
        Asset(
            internal_code="PAT-PY-0002",
            barcode="789000000102",
            church_key="paraguai",
            is_donation=True,
            description="Desktop Lenovo ThinkCentre",
            brand="Lenovo",
            model="M70s",
            serial_number="LV-M70S-1133",
            purchase_value=Decimal("4200.00"),
            purchase_date=today - timedelta(days=300),
            cost_center="Administração",
            location="Secretaria",
            responsible=None,
            useful_life_years=5,
            depreciation_rate=Decimal("20.00"),
            status="ativo",
            last_inventory_date=None,
        ),
    ]
    db.session.add_all(assets)
    db.session.flush()

    moves = [
        Movement(asset_id=assets[0].id, action="Alteração Localização", details="TI -> Escritório - 2º andar", user_name="João"),
        Movement(asset_id=assets[1].id, action="Enviado para Manutenção", details="Recepção -> Oficina", user_name="Maria"),
        Movement(asset_id=assets[2].id, action="Novo Cadastro", details="Cadastro inicial do bem", user_name="Carlos"),
    ]
    db.session.add_all(moves)
    db.session.commit()
