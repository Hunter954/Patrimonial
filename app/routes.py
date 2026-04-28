from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import io
import re
from functools import wraps
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from . import db
from .barcodes import generate_barcode_png
from .models import AppSetting, Asset, Movement, User
from .utils import currency_br, depreciation_linear

bp = Blueprint("main", __name__)

CHURCHES = {
    "foz": {"name": "Igreja de Foz do Iguaçu", "city": "Foz do Iguaçu"},
    "paraguai": {"name": "Igreja do Paraguai", "city": "Paraguai"},
}
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_decimal(value: str, default: str = "0") -> Decimal:
    raw = (value or default).strip()
    raw = raw.replace("R$", "").replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(raw or default)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def parse_int(value: str, default: int = 5) -> int:
    raw = (value or "").strip()
    if not raw:
        return default
    if not raw.isdigit():
        raise ValueError("Informe apenas números inteiros.")
    return max(int(raw), 1)


def validate_numeric_fields(form) -> list[str]:
    errors = []
    integer_fields = {
        "useful_life_years": "Vida útil",
    }
    for field_name, label in integer_fields.items():
        raw = (form.get(field_name) or "").strip()
        if raw and not raw.isdigit():
            errors.append(f"{label} permite apenas números. Não escreva textos como 'anos' ou '5 à 8 anos'.")
    return errors

def next_internal_code(church_key: str):
    prefix = "FOZ" if church_key == "foz" else "PY"
    last = Asset.query.filter_by(church_key=church_key).order_by(Asset.id.desc()).first()
    if not last or prefix not in (last.internal_code or ""):
        return f"PAT-{prefix}-0001"
    try:
        n = int((last.internal_code or "").split("-")[-1])
    except Exception:
        n = last.id
    return f"PAT-{prefix}-{n+1:04d}"


def add_movement(asset_id: int, action: str, details: str = "", user_name: str = "Sistema"):
    db.session.add(Movement(asset_id=asset_id, action=action, details=details, user_name=user_name))
    db.session.commit()


def get_current_user() -> User | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.filter_by(id=user_id, is_active=True).first()


def get_current_church_key():
    church_key = session.get("church_key")
    return church_key if church_key in CHURCHES else None


def get_current_church():
    church_key = get_current_church_key()
    if not church_key:
        return None
    church = dict(CHURCHES[church_key])
    church["key"] = church_key
    return church


def church_query():
    church_key = get_current_church_key()
    if not church_key:
        return Asset.query.filter(db.text("1=0"))
    return Asset.query.filter_by(church_key=church_key)


def ensure_default_settings():
    changed = False
    for key, cfg in CHURCHES.items():
        exists = AppSetting.query.filter_by(church_key=key).first()
        if not exists:
            db.session.add(AppSetting(church_key=key, church_name=cfg["name"]))
            changed = True
    if changed:
        db.session.commit()


def get_church_settings(church_key: str | None = None):
    ensure_default_settings()
    ck = church_key or get_current_church_key()
    if not ck:
        return None
    return AppSetting.query.filter_by(church_key=ck).first()


def get_login_logo_settings():
    ensure_default_settings()
    preferred_keys = ["foz", "paraguai"]
    for key in preferred_keys:
        settings = AppSetting.query.filter_by(church_key=key).first()
        if settings and settings.logo_path:
            return settings
    return AppSetting.query.order_by(AppSetting.id.asc()).first()


def save_upload(file_storage, target_dir: str, prefix: str) -> str | None:
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None
    if not allowed_file(file_storage.filename):
        return None

    original_name = secure_filename(file_storage.filename)
    ext = Path(original_name).suffix.lower()
    filename = f"{prefix}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secure_filename(Path(original_name).stem)[:20]}{ext}"
    target_path = Path(target_dir)
    target_path.mkdir(parents=True, exist_ok=True)
    destination = target_path / filename
    file_storage.save(destination)

    upload_root = Path(current_app.config["UPLOAD_ROOT"]).resolve()
    relative = destination.resolve().relative_to(upload_root).as_posix()
    return relative


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.current_user:
            flash("Faça login para acessar o sistema.", "warning")
            return redirect(url_for("main.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.current_user:
            flash("Faça login para acessar o sistema.", "warning")
            return redirect(url_for("main.login", next=request.path))
        if g.current_user.role != "admin":
            flash("Apenas administrador pode fazer essa ação.", "danger")
            return redirect(url_for("main.dashboard"))
        return view(*args, **kwargs)

    return wrapped


@bp.before_app_request
def load_request_context():
    g.current_user = get_current_user()


@bp.before_app_request
def enforce_access_rules():
    public_endpoints = {
        "main.root",
        "main.login",
        "main.logout",
        "main.uploaded_file",
        "static",
    }
    if request.endpoint in public_endpoints or request.endpoint is None:
        return None
    if not g.current_user:
        return redirect(url_for("main.login", next=request.path))
    allowed_without_church = {"main.select_church", "main.change_church"}
    if request.endpoint in allowed_without_church:
        return None
    if get_current_church_key():
        return None
    return redirect(url_for("main.root"))


@bp.app_context_processor
def inject_helpers():
    church = get_current_church()
    settings = get_church_settings(church["key"]) if church else None
    return {
        "currency_br": currency_br,
        "current_church": church,
        "churches": CHURCHES,
        "church_settings": settings,
        "current_user": g.get("current_user"),
        "is_admin": bool(g.get("current_user") and g.current_user.role == "admin"),
        "can_edit": bool(g.get("current_user") and g.current_user.role == "admin"),
    }


@bp.get("/")
def root():
    if not g.current_user:
        return redirect(url_for("main.login"))
    if get_current_church_key():
        return redirect(url_for("main.dashboard"))
    ensure_default_settings()
    cards = []
    for key, cfg in CHURCHES.items():
        settings = get_church_settings(key)
        cards.append({"key": key, "name": cfg["name"], "city": cfg["city"], "logo_path": settings.logo_path if settings else None})
    return render_template("church_select.html", cards=cards, title="Selecionar patrimônio")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.current_user:
        return redirect(url_for("main.dashboard") if get_current_church_key() else url_for("main.root"))

    login_logo = get_login_logo_settings()
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter(func.lower(User.username) == username.lower()).first()

        if not user or not user.is_active or not check_password_hash(user.password_hash, password):
            flash("Usuário ou senha inválidos.", "danger")
            return render_template("login.html", login_logo=login_logo, title="Login • Sistema Patrimonial")

        session["user_id"] = user.id
        next_url = request.args.get("next") or url_for("main.root")
        flash(f"Bem-vindo, {user.username}.", "success")
        return redirect(next_url)

    return render_template("login.html", login_logo=login_logo, title="Login • Sistema Patrimonial")


@bp.get("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("church_key", None)
    flash("Você saiu do sistema.", "info")
    return redirect(url_for("main.login"))


@bp.post("/selecionar-igreja")
@login_required
def select_church():
    church_key = (request.form.get("church_key") or "").strip()
    if church_key not in CHURCHES:
        flash("Selecione uma igreja válida.", "danger")
        return redirect(url_for("main.root"))
    session["church_key"] = church_key
    flash(f"Você entrou em {CHURCHES[church_key]['name']}.", "success")
    return redirect(url_for("main.dashboard"))


@bp.get("/trocar-igreja")
@login_required
def change_church():
    session.pop("church_key", None)
    flash("Escolha qual patrimônio deseja acessar.", "info")
    return redirect(url_for("main.root"))


@bp.get("/dashboard")
@login_required
def dashboard():
    total_assets = church_query().count()
    total_value = db.session.query(func.coalesce(func.sum(Asset.purchase_value), 0)).filter(Asset.church_key == get_current_church_key()).scalar() or 0

    assets = church_query().all()
    total_depreciated = 0.0
    status_counts = {"ativo": 0, "manutencao": 0, "baixado": 0}
    by_cost_center = {}
    donation_count = 0

    for a in assets:
        acc, cur, *_ = depreciation_linear(a.purchase_value, a.purchase_date, a.useful_life_years, date.today())
        total_depreciated += acc
        status_counts[(a.status or "ativo")] = status_counts.get(a.status or "ativo", 0) + 1
        cc = a.cost_center or "Sem centro"
        by_cost_center[cc] = by_cost_center.get(cc, 0) + 1
        if a.is_donation:
            donation_count += 1

    maintenance_count = status_counts.get("manutencao", 0)
    recent_moves = (
        Movement.query.join(Asset, Asset.id == Movement.asset_id)
        .filter(Asset.church_key == get_current_church_key())
        .order_by(Movement.created_at.desc())
        .limit(5)
        .all()
    )

    alerts = []
    for a in assets:
        _, _, _, pct = depreciation_linear(a.purchase_value, a.purchase_date, a.useful_life_years, date.today())
        if pct >= 90 and a.status != "baixado":
            alerts.append(("warning", f"{a.internal_code} próximo do fim da vida útil"))

    missing_resp = church_query().filter((Asset.responsible == None) | (Asset.responsible == "")).count()  # noqa: E711
    if missing_resp:
        alerts.append(("warning", f"{missing_resp} itens sem responsável definido"))

    cutoff = date.today() - timedelta(days=180)
    stale_inv = church_query().filter((Asset.last_inventory_date == None) | (Asset.last_inventory_date < cutoff)).count()  # noqa: E711
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
        donation_count=donation_count,
        recent_moves=recent_moves,
        alerts=alerts[:6],
        cost_labels=cost_labels,
        cost_values=cost_values,
        donut=donut,
    )


@bp.get("/patrimonio")
@login_required
def patrimonio_list():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    location = (request.args.get("location") or "").strip()
    donation = (request.args.get("donation") or "").strip()

    query = church_query()
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Asset.internal_code.ilike(like))
            | (Asset.barcode.ilike(like))
            | (Asset.description.ilike(like))
            | (Asset.serial_number.ilike(like))
        )
    if status:
        query = query.filter(Asset.status == status)
    if location:
        query = query.filter(Asset.location == location)
    if donation == "1":
        query = query.filter(Asset.is_donation.is_(True))
    elif donation == "0":
        query = query.filter(Asset.is_donation.is_(False))

    assets = query.order_by(Asset.id.desc()).all()
    locations = [r[0] for r in church_query().with_entities(Asset.location).distinct().order_by(Asset.location).all() if r[0]]

    return render_template(
        "patrimonio_list.html",
        assets=assets,
        q=q,
        status=status,
        location=location,
        donation=donation,
        locations=locations,
    )


@bp.route("/patrimonio/novo", methods=["GET", "POST"])
@admin_required
def patrimonio_new():
    if request.method == "POST":
        church_key = get_current_church_key()
        internal_code = next_internal_code(church_key)
        barcode = (request.form.get("barcode") or "").strip()
        if not barcode:
            flash("Código de barras é obrigatório.", "danger")
            return redirect(url_for("main.patrimonio_new"))

        if Asset.query.filter_by(barcode=barcode).first():
            flash("Já existe um item com esse código de barras.", "danger")
            return redirect(url_for("main.patrimonio_new", barcode=barcode))

        numeric_errors = validate_numeric_fields(request.form)
        if numeric_errors:
            for message in numeric_errors:
                flash(message, "danger")
            return redirect(url_for("main.patrimonio_new", barcode=barcode))

        item_image = request.files.get("item_image")
        image_path = None
        if item_image and item_image.filename:
            image_path = save_upload(item_image, current_app.config["ITEM_UPLOAD_DIR"], f"item_{church_key}")
            if not image_path:
                flash("A imagem do item deve ser PNG, JPG, JPEG ou WEBP.", "danger")
                return redirect(url_for("main.patrimonio_new", barcode=barcode))

        asset = Asset(
            internal_code=internal_code,
            barcode=barcode,
            church_key=church_key,
            is_donation=request.form.get("is_donation") == "1",
            image_path=image_path,
            description=(request.form.get("description") or "").strip() or "Sem descrição",
            brand=(request.form.get("brand") or "").strip() or None,
            model=(request.form.get("model") or "").strip() or None,
            serial_number=(request.form.get("serial_number") or "").strip() or None,
            purchase_value=parse_decimal(request.form.get("purchase_value"), "0"),
            purchase_date=datetime.strptime(request.form.get("purchase_date"), "%Y-%m-%d").date() if request.form.get("purchase_date") else date.today(),
            cost_center=(request.form.get("cost_center") or "").strip() or None,
            location=(request.form.get("location") or "").strip() or None,
            responsible=(request.form.get("responsible") or "").strip() or None,
            useful_life_years=parse_int(request.form.get("useful_life_years"), 5),
            depreciation_rate=parse_decimal(request.form.get("depreciation_rate"), "20"),
            status=(request.form.get("status") or "ativo"),
        )
        db.session.add(asset)
        db.session.commit()
        add_movement(asset.id, "Novo Cadastro", "Cadastro inicial do bem", g.current_user.username)
        flash("Bem cadastrado com sucesso.", "success")
        return redirect(url_for("main.patrimonio_edit", asset_id=asset.id))

    preset_barcode = (request.args.get("barcode") or "").strip()
    return render_template("patrimonio_form.html", asset=None, preset_barcode=preset_barcode, read_only=False)


@bp.route("/patrimonio/<int:asset_id>/editar", methods=["GET", "POST"])
@login_required
def patrimonio_edit(asset_id):
    asset = church_query().filter_by(id=asset_id).first_or_404()

    if request.method == "POST":
        if g.current_user.role != "admin":
            flash("Seu usuário é somente visualizador.", "danger")
            return redirect(url_for("main.patrimonio_edit", asset_id=asset.id))

        old_location = asset.location
        old_status = asset.status
        old_donation = asset.is_donation
        old_barcode = asset.barcode

        new_barcode = (request.form.get("barcode") or "").strip()
        if not new_barcode:
            flash("Código de barras é obrigatório.", "danger")
            return redirect(url_for("main.patrimonio_edit", asset_id=asset.id))

        existing_barcode = Asset.query.filter(Asset.barcode == new_barcode, Asset.id != asset.id).first()
        if existing_barcode:
            flash("Já existe outro item com esse código de barras.", "danger")
            return redirect(url_for("main.patrimonio_edit", asset_id=asset.id))

        asset.barcode = new_barcode
        asset.description = (request.form.get("description") or "").strip() or asset.description
        asset.brand = (request.form.get("brand") or "").strip() or None
        asset.model = (request.form.get("model") or "").strip() or None
        asset.serial_number = (request.form.get("serial_number") or "").strip() or None
        asset.purchase_value = parse_decimal(request.form.get("purchase_value"), "0")
        asset.purchase_date = datetime.strptime(request.form.get("purchase_date"), "%Y-%m-%d").date() if request.form.get("purchase_date") else asset.purchase_date
        asset.cost_center = (request.form.get("cost_center") or "").strip() or None
        asset.location = (request.form.get("location") or "").strip() or None
        asset.responsible = (request.form.get("responsible") or "").strip() or None
        asset.is_donation = request.form.get("is_donation") == "1"

        item_image = request.files.get("item_image")
        if item_image and item_image.filename:
            image_path = save_upload(item_image, current_app.config["ITEM_UPLOAD_DIR"], f"item_{asset.church_key}")
            if not image_path:
                flash("A imagem do item deve ser PNG, JPG, JPEG ou WEBP.", "danger")
                return redirect(url_for("main.patrimonio_edit", asset_id=asset.id))
            asset.image_path = image_path

        numeric_errors = validate_numeric_fields(request.form)
        if numeric_errors:
            for message in numeric_errors:
                flash(message, "danger")
            return redirect(url_for("main.patrimonio_edit", asset_id=asset.id))

        asset.useful_life_years = parse_int(request.form.get("useful_life_years"), asset.useful_life_years)
        asset.depreciation_rate = parse_decimal(request.form.get("depreciation_rate"), "20")
        asset.status = (request.form.get("status") or asset.status)

        if request.form.get("mark_inventoried") == "1":
            asset.last_inventory_date = date.today()

        db.session.commit()

        if asset.location != old_location:
            add_movement(asset.id, "Alteração Localização", f"{old_location or '-'} -> {asset.location or '-'}", g.current_user.username)
        if asset.status != old_status:
            add_movement(asset.id, "Alteração Status", f"{old_status} -> {asset.status}", g.current_user.username)
        if asset.is_donation != old_donation:
            add_movement(asset.id, "Alteração Categoria", f"Doação: {'Sim' if old_donation else 'Não'} -> {'Sim' if asset.is_donation else 'Não'}", g.current_user.username)
        if asset.barcode != old_barcode:
            add_movement(asset.id, "Alteração Código de Barras", f"{old_barcode} -> {asset.barcode}", g.current_user.username)

        flash("Item atualizado.", "success")
        return redirect(url_for("main.patrimonio_edit", asset_id=asset.id))

    acc, cur, years, pct = depreciation_linear(asset.purchase_value, asset.purchase_date, asset.useful_life_years, date.today())
    dep = {"accumulated": acc, "current": cur, "years": years, "percent": pct}
    moves = Movement.query.filter_by(asset_id=asset.id).order_by(Movement.created_at.desc()).limit(10).all()
    return render_template("patrimonio_form.html", asset=asset, dep=dep, moves=moves, preset_barcode=None, read_only=g.current_user.role != "admin")


@bp.post("/patrimonio/<int:asset_id>/baixar")
@admin_required
def patrimonio_deactivate(asset_id):
    asset = church_query().filter_by(id=asset_id).first_or_404()
    asset.status = "baixado"
    db.session.commit()
    add_movement(asset.id, "Baixado", "Bem baixado no sistema", g.current_user.username)
    flash("Bem baixado.", "info")
    return redirect(url_for("main.patrimonio_edit", asset_id=asset.id))


@bp.post("/patrimonio/<int:asset_id>/excluir")
@admin_required
def patrimonio_delete(asset_id):
    asset = church_query().filter_by(id=asset_id).first_or_404()
    code = asset.internal_code
    desc = asset.description
    db.session.delete(asset)
    db.session.commit()
    flash(f"Bem {code} - {desc} excluído com sucesso.", "success")
    return redirect(request.referrer or url_for("main.patrimonio_list"))


@bp.get("/leitor")
@login_required
def leitor():
    return render_template("leitor.html")


@bp.post("/leitor/processar")
@login_required
def leitor_processar():
    code = (request.form.get("code") or "").strip()
    if not code:
        flash("Leia/insira um código de barras.", "danger")
        return redirect(url_for("main.leitor"))

    asset = church_query().filter_by(barcode=code).first()
    if asset:
        flash(f"Item encontrado: {asset.internal_code}", "success")
        return redirect(url_for("main.patrimonio_edit", asset_id=asset.id))
    if g.current_user.role != "admin":
        flash("Item não cadastrado e seu usuário é somente visualizador.", "warning")
        return redirect(url_for("main.leitor"))
    flash("Item não cadastrado nesta igreja. Abrindo tela para cadastro.", "warning")
    return redirect(url_for("main.patrimonio_new", barcode=code))


@bp.get("/etiqueta/<int:asset_id>.png")
@login_required
def etiqueta_png(asset_id):
    asset = church_query().filter_by(id=asset_id).first_or_404()
    png = generate_barcode_png(asset.barcode)
    return send_file(io.BytesIO(png), mimetype="image/png", download_name=f"{asset.internal_code}.png")


@bp.get("/uploads/<path:relative_path>")
def uploaded_file(relative_path):
    upload_root = Path(current_app.config["UPLOAD_ROOT"]).resolve()
    full_path = (upload_root / relative_path).resolve()

    try:
        full_path.relative_to(upload_root)
    except ValueError:
        return "", 404

    if not full_path.is_file():
        return "", 404

    parent = str(full_path.parent)
    filename = full_path.name
    response = send_from_directory(parent, filename, conditional=True)
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


@bp.get("/inventario")
@login_required
def inventario():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    query = church_query()
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Asset.internal_code.ilike(like))
            | (Asset.barcode.ilike(like))
            | (Asset.description.ilike(like))
            | (Asset.location.ilike(like))
            | (Asset.responsible.ilike(like))
        )
    if status:
        query = query.filter(Asset.status == status)

    assets = query.order_by(Asset.location.asc().nullslast(), Asset.id.desc()).all()
    return render_template("inventario.html", assets=assets, q=q, status=status)


@bp.get("/inventario/exportar.csv")
@login_required
def inventario_exportar():
    import csv
    import io as _io

    si = _io.StringIO()
    cw = csv.writer(si)
    cw.writerow([
        "Igreja", "Código", "Código de Barras", "Descrição", "Doação", "Marca", "Modelo", "Série", "Valor",
        "Data compra", "Centro custo", "Localização", "Responsável", "Vida útil", "Status", "Últ. inventário"
    ])
    for a in church_query().order_by(Asset.id.asc()).all():
        cw.writerow([
            CHURCHES.get(a.church_key, {}).get("name", a.church_key), a.internal_code, a.barcode, a.description,
            "Sim" if a.is_donation else "Não", a.brand or "", a.model or "", a.serial_number or "",
            str(a.purchase_value), a.purchase_date.isoformat() if a.purchase_date else "",
            a.cost_center or "", a.location or "", a.responsible or "", a.useful_life_years,
            a.status, a.last_inventory_date.isoformat() if a.last_inventory_date else ""
        ])
    out = _io.BytesIO(si.getvalue().encode("utf-8-sig"))
    return send_file(out, mimetype="text/csv", download_name="inventario.csv", as_attachment=True)


@bp.get("/relatorios")
@login_required
def relatorios():
    assets = church_query().all()
    today = date.today()
    by_cc = {}
    maintenance = []
    depreciated = []
    donated_assets = []
    for a in assets:
        acc, cur, *_ = depreciation_linear(a.purchase_value, a.purchase_date, a.useful_life_years, today)
        by_cc[a.cost_center or "Sem centro"] = by_cc.get(a.cost_center or "Sem centro", 0) + 1
        if a.status == "manutencao":
            maintenance.append(a)
        if a.is_donation:
            donated_assets.append(a)
        depreciated.append((a, acc, cur))

    depreciated.sort(key=lambda x: x[1], reverse=True)
    top_depreciated = depreciated[:10]
    return render_template(
        "relatorios.html",
        by_cc=by_cc,
        maintenance=maintenance,
        donated_assets=donated_assets,
        top_depreciated=top_depreciated,
    )


@bp.route("/admin/igreja", methods=["GET", "POST"])
@admin_required
def church_admin():
    church = get_current_church()
    settings = get_church_settings(church["key"])

    if request.method == "POST":
        settings.church_name = (request.form.get("church_name") or "").strip() or church["name"]
        logo = request.files.get("church_logo")
        if logo and logo.filename:
            logo_path = save_upload(logo, current_app.config["LOGO_UPLOAD_DIR"], f"logo_{church['key']}")
            if not logo_path:
                flash("A logo precisa ser PNG, JPG, JPEG ou WEBP.", "danger")
                return redirect(url_for("main.church_admin"))
            settings.logo_path = logo_path
        db.session.commit()
        flash("Configurações da igreja atualizadas.", "success")
        return redirect(url_for("main.church_admin"))

    return render_template("church_admin.html", settings=settings)


@bp.route("/admin/usuarios", methods=["GET", "POST"])
@admin_required
def admin_users():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        role = (request.form.get("role") or "viewer").strip().lower()

        if not username:
            flash("Informe o nome de usuário.", "danger")
            return redirect(url_for("main.admin_users"))
        if len(password) < 4:
            flash("A senha precisa ter pelo menos 4 caracteres.", "danger")
            return redirect(url_for("main.admin_users"))
        if role not in {"admin", "viewer"}:
            flash("Nível de usuário inválido.", "danger")
            return redirect(url_for("main.admin_users"))
        if User.query.filter(func.lower(User.username) == username.lower()).first():
            flash("Já existe um usuário com esse nome.", "danger")
            return redirect(url_for("main.admin_users"))

        db.session.add(User(username=username, password_hash=generate_password_hash(password), role=role, is_active=True))
        db.session.commit()
        flash("Usuário cadastrado com sucesso.", "success")
        return redirect(url_for("main.admin_users"))

    users = User.query.order_by(User.username.asc()).all()
    return render_template("admin_users.html", users=users)


@bp.post("/admin/usuarios/<int:user_id>/toggle")
@admin_required
def admin_users_toggle(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == g.current_user.id:
        flash("Você não pode desativar o próprio usuário logado.", "danger")
        return redirect(url_for("main.admin_users"))
    user.is_active = not user.is_active
    db.session.commit()
    flash("Status do usuário atualizado.", "success")
    return redirect(url_for("main.admin_users"))


@bp.post("/admin/usuarios/<int:user_id>/senha")
@admin_required
def admin_users_password(user_id):
    user = User.query.get_or_404(user_id)
    password = request.form.get("new_password") or ""
    if len(password) < 4:
        flash("A nova senha precisa ter pelo menos 4 caracteres.", "danger")
        return redirect(url_for("main.admin_users"))
    user.password_hash = generate_password_hash(password)
    db.session.commit()
    flash(f"Senha do usuário {user.username} atualizada.", "success")
    return redirect(url_for("main.admin_users"))
