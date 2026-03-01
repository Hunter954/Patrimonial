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
            internal_code="PAT-0001",
            barcode="789000000001",
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
            internal_code="PAT-0002",
            barcode="789000000002",
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
            internal_code="PAT-0003",
            barcode="789000000003",
            description="Projetor Epson PowerLite",
            brand="Epson",
            model="X41",
            serial_number="EP-X41-3321",
            purchase_value=Decimal("2600.00"),
            purchase_date=today - timedelta(days=1200),
            cost_center="Vendas",
            location="Sala de Reunião",
            responsible="Carlos",
            useful_life_years=5,
            depreciation_rate=Decimal("20.00"),
            status="ativo",
            last_inventory_date=today - timedelta(days=400),
        ),
        Asset(
            internal_code="PAT-0004",
            barcode="789000000004",
            description="Desktop Lenovo ThinkCentre",
            brand="Lenovo",
            model="M70s",
            serial_number="LV-M70S-1133",
            purchase_value=Decimal("4200.00"),
            purchase_date=today - timedelta(days=300),
            cost_center="Produção",
            location="Fábrica - Linha 1",
            responsible=None,
            useful_life_years=5,
            depreciation_rate=Decimal("20.00"),
            status="ativo",
            last_inventory_date=None,
        ),
        Asset(
            internal_code="PAT-0005",
            barcode="789000000005",
            description="Tablet Samsung Galaxy Tab",
            brand="Samsung",
            model="Tab A8",
            serial_number="SS-A8-7788",
            purchase_value=Decimal("1400.00"),
            purchase_date=today - timedelta(days=200),
            cost_center="Vendas",
            location="Externo",
            responsible="Ana",
            useful_life_years=3,
            depreciation_rate=Decimal("33.33"),
            status="baixado",
            last_inventory_date=today - timedelta(days=20),
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
