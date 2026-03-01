from datetime import date, datetime, timedelta
from decimal import Decimal
import io

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from sqlalchemy import func

from . import db
from .models import Asset, Movement
from .utils import currency_br, depreciation_linear
from .barcodes import generate_barcode_png

bp = Blueprint("main", __name__)

def next_internal_code():
    last = Asset.query.order_by(Asset.id.desc()).first()
    if not last or not (last.internal_code or "").startswith("PAT-"):
        return "PAT-0001"
    try:
        n = int(last.internal_code.split("-")[1])
    except Exception:
        n = last.id
    return f"PAT-{n+1:04d}"

def add_movement(asset_id: int, action: str, details: str = "", user_name: str = "Sistema"):
    db.session.add(Movement(asset_id=asset_id, action=action, details=details, user_name=user_name))
    db.session.commit()

@bp.app_context_processor
def inject_helpers():
    return {"currency_br": currency_br}

@bp.get("/")
def root():
    return redirect(url_for("main.dashboard"))

@bp.get("/dashboard")
def dashboard():
    total_assets = Asset.query.count()
    total_value = db.session.query(func.coalesce(func.sum(Asset.purchase_value), 0)).scalar() or 0

    assets = Asset.query.all()
    total_depreciated = 0.0
    status_counts = {"ativo": 0, "manutencao": 0, "baixado": 0}
    by_cost_center = {}
    for a in assets:
        acc, cur, *_ = depreciation_linear(a.purchase_value, a.purchase_date, a.useful_life_years, date.today())
        total_depreciated += acc
        status_counts[(a.status or "ativo")] = status_counts.get(a.status or "ativo", 0) + 1
        cc = a.cost_center or "Sem centro"
        by_cost_center[cc] = by_cost_center.get(cc, 0) + 1

    maintenance_count = status_counts.get("manutencao", 0)
    recent_moves = Movement.query.order_by(Movement.created_at.desc()).limit(5).all()

    alerts = []
    for a in assets:
        _, _, _, pct = depreciation_linear(a.purchase_value, a.purchase_date, a.useful_life_years, date.today())
        if pct >= 90 and a.status != "baixado":
            alerts.append(("warning", f"{a.internal_code} próximo do fim da vida útil"))

    missing_resp = Asset.query.filter((Asset.responsible == None) | (Asset.responsible == "")).count()  # noqa
    if missing_resp:
        alerts.append(("warning", f"{missing_resp} itens sem responsável definido"))

    cutoff = date.today() - timedelta(days=180)
    stale_inv = Asset.query.filter((Asset.last_inventory_date == None) | (Asset.last_inventory_date < cutoff)).count()  # noqa
    if stale_inv:
        alerts.append(("warning", f"{stale_inv} bens sem inventário recente"))

    cost_labels = list(by_cost_center.keys())
    cost_values = [by_cost_center[k] for k in cost_labels]
    donut = {
        "labels": ["Ativos", "Em Manutenção", "Baixados"],
        "values": [status_counts.get("ativo", 0), status_counts.get("manutencao", 0), status_counts.get("baixado", 0)],
    }

    return render_template(
        "dashboard.html",
        total_assets=total_assets,
        total_value=Decimal(total_value),
        total_depreciated=Decimal(str(total_depreciated)),
        maintenance_count=maintenance_count,
        recent_moves=recent_moves,
        alerts=alerts[:6],
        cost_labels=cost_labels,
        cost_values=cost_values,
        donut=donut,
    )

@bp.get("/patrimonio")
def patrimonio_list():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    location = (request.args.get("location") or "").strip()

    query = Asset.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Asset.internal_code.ilike(like)) |
            (Asset.barcode.ilike(like)) |
            (Asset.description.ilike(like)) |
            (Asset.serial_number.ilike(like))
        )
    if status:
        query = query.filter(Asset.status == status)
    if location:
        query = query.filter(Asset.location == location)

    assets = query.order_by(Asset.id.desc()).all()
    locations = [r[0] for r in db.session.query(Asset.location).distinct().order_by(Asset.location).all() if r[0]]

    return render_template("patrimonio_list.html", assets=assets, q=q, status=status, location=location, locations=locations)

@bp.route("/patrimonio/novo", methods=["GET", "POST"])
def patrimonio_new():
    if request.method == "POST":
        internal_code = next_internal_code()
        barcode = (request.form.get("barcode") or "").strip()
        if not barcode:
            flash("Código de barras é obrigatório.", "danger")
            return redirect(url_for("main.patrimonio_new"))

        if Asset.query.filter_by(barcode=barcode).first():
            flash("Já existe um item com esse código de barras.", "danger")
            return redirect(url_for("main.patrimonio_new", barcode=barcode))

        asset = Asset(
            internal_code=internal_code,
            barcode=barcode,
            description=(request.form.get("description") or "").strip() or "Sem descrição",
            brand=(request.form.get("brand") or "").strip() or None,
            model=(request.form.get("model") or "").strip() or None,
            serial_number=(request.form.get("serial_number") or "").strip() or None,
            purchase_value=Decimal((request.form.get("purchase_value") or "0").replace(".", "").replace(",", ".")),
            purchase_date=datetime.strptime(request.form.get("purchase_date"), "%Y-%m-%d").date() if request.form.get("purchase_date") else date.today(),
            cost_center=(request.form.get("cost_center") or "").strip() or None,
            location=(request.form.get("location") or "").strip() or None,
            responsible=(request.form.get("responsible") or "").strip() or None,
            useful_life_years=int(request.form.get("useful_life_years") or 5),
            depreciation_rate=Decimal((request.form.get("depreciation_rate") or "20").replace(",", ".")),
            status=(request.form.get("status") or "ativo"),
        )
        db.session.add(asset)
        db.session.commit()
        add_movement(asset.id, "Novo Cadastro", "Cadastro inicial do bem")
        flash("Bem cadastrado com sucesso.", "success")
        return redirect(url_for("main.patrimonio_edit", asset_id=asset.id))

    preset_barcode = (request.args.get("barcode") or "").strip()
    return render_template("patrimonio_form.html", asset=None, preset_barcode=preset_barcode)

@bp.route("/patrimonio/<int:asset_id>/editar", methods=["GET", "POST"])
def patrimonio_edit(asset_id):
    asset = Asset.query.get_or_404(asset_id)

    if request.method == "POST":
        old_location = asset.location
        old_status = asset.status

        asset.description = (request.form.get("description") or "").strip() or asset.description
        asset.brand = (request.form.get("brand") or "").strip() or None
        asset.model = (request.form.get("model") or "").strip() or None
        asset.serial_number = (request.form.get("serial_number") or "").strip() or None

        asset.purchase_value = Decimal((request.form.get("purchase_value") or "0").replace(".", "").replace(",", "."))
        asset.purchase_date = datetime.strptime(request.form.get("purchase_date"), "%Y-%m-%d").date() if request.form.get("purchase_date") else asset.purchase_date

        asset.cost_center = (request.form.get("cost_center") or "").strip() or None
        asset.location = (request.form.get("location") or "").strip() or None
        asset.responsible = (request.form.get("responsible") or "").strip() or None

        asset.useful_life_years = int(request.form.get("useful_life_years") or asset.useful_life_years)
        asset.depreciation_rate = Decimal((request.form.get("depreciation_rate") or "20").replace(",", "."))
        asset.status = (request.form.get("status") or asset.status)

        if request.form.get("mark_inventoried") == "1":
            asset.last_inventory_date = date.today()

        db.session.commit()

        if asset.location != old_location:
            add_movement(asset.id, "Alteração Localização", f"{old_location or '-'} -> {asset.location or '-'}")
        if asset.status != old_status:
            add_movement(asset.id, "Alteração Status", f"{old_status} -> {asset.status}")

        flash("Item atualizado.", "success")
        return redirect(url_for("main.patrimonio_edit", asset_id=asset.id))

    acc, cur, years, pct = depreciation_linear(asset.purchase_value, asset.purchase_date, asset.useful_life_years, date.today())
    dep = {"accumulated": acc, "current": cur, "years": years, "percent": pct}
    moves = Movement.query.filter_by(asset_id=asset.id).order_by(Movement.created_at.desc()).limit(10).all()
    return render_template("patrimonio_form.html", asset=asset, dep=dep, moves=moves, preset_barcode=None)

@bp.post("/patrimonio/<int:asset_id>/baixar")
def patrimonio_deactivate(asset_id):
    asset = Asset.query.get_or_404(asset_id)
    asset.status = "baixado"
    db.session.commit()
    add_movement(asset.id, "Baixado", "Bem baixado no sistema")
    flash("Bem baixado.", "info")
    return redirect(url_for("main.patrimonio_edit", asset_id=asset.id))

@bp.get("/leitor")
def leitor():
    return render_template("leitor.html")

@bp.post("/leitor/processar")
def leitor_processar():
    code = (request.form.get("code") or "").strip()
    if not code:
        flash("Leia/insira um código de barras.", "danger")
        return redirect(url_for("main.leitor"))

    asset = Asset.query.filter_by(barcode=code).first()
    if asset:
        flash(f"Item encontrado: {asset.internal_code}", "success")
        return redirect(url_for("main.patrimonio_edit", asset_id=asset.id))
    else:
        flash("Item não cadastrado. Abrindo tela para cadastro.", "warning")
        return redirect(url_for("main.patrimonio_new", barcode=code))

@bp.get("/etiqueta/<int:asset_id>.png")
def etiqueta_png(asset_id):
    asset = Asset.query.get_or_404(asset_id)
    png = generate_barcode_png(asset.barcode)
    return send_file(io.BytesIO(png), mimetype="image/png", download_name=f"{asset.internal_code}.png")

@bp.get("/inventario")
def inventario():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    query = Asset.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Asset.internal_code.ilike(like)) |
            (Asset.barcode.ilike(like)) |
            (Asset.description.ilike(like)) |
            (Asset.location.ilike(like)) |
            (Asset.responsible.ilike(like))
        )
    if status:
        query = query.filter(Asset.status == status)

    assets = query.order_by(Asset.location.asc().nullslast(), Asset.id.desc()).all()
    return render_template("inventario.html", assets=assets, q=q, status=status)

@bp.get("/inventario/exportar.csv")
def inventario_exportar():
    import csv
    import io as _io
    si = _io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["Código", "Código de Barras", "Descrição", "Marca", "Modelo", "Série", "Valor", "Data compra", "Centro custo", "Localização", "Responsável", "Vida útil", "Status", "Últ. inventário"])
    for a in Asset.query.order_by(Asset.id.asc()).all():
        cw.writerow([
            a.internal_code, a.barcode, a.description, a.brand or "", a.model or "", a.serial_number or "",
            str(a.purchase_value), a.purchase_date.isoformat() if a.purchase_date else "",
            a.cost_center or "", a.location or "", a.responsible or "", a.useful_life_years, a.status,
            a.last_inventory_date.isoformat() if a.last_inventory_date else ""
        ])
    out = _io.BytesIO(si.getvalue().encode("utf-8-sig"))
    return send_file(out, mimetype="text/csv", download_name="inventario.csv", as_attachment=True)

@bp.get("/relatorios")
def relatorios():
    assets = Asset.query.all()
    today = date.today()
    by_cc = {}
    maintenance = []
    depreciated = []
    for a in assets:
        acc, cur, *_ = depreciation_linear(a.purchase_value, a.purchase_date, a.useful_life_years, today)
        by_cc[a.cost_center or "Sem centro"] = by_cc.get(a.cost_center or "Sem centro", 0) + 1
        if a.status == "manutencao":
            maintenance.append(a)
        depreciated.append((a, acc, cur))

    depreciated.sort(key=lambda x: x[1], reverse=True)
    top_depreciated = depreciated[:10]
    return render_template("relatorios.html", by_cc=by_cc, maintenance=maintenance, top_depreciated=top_depreciated)
