from datetime import date
from decimal import Decimal

def currency_br(value):
    try:
        v = Decimal(value)
    except Exception:
        v = Decimal("0")
    s = f"{v:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"

def depreciation_linear(purchase_value, purchase_date, useful_life_years, as_of=None):
    if as_of is None:
        as_of = date.today()
    if purchase_date is None:
        purchase_date = as_of

    try:
        pv = float(purchase_value)
    except Exception:
        pv = 0.0

    life = max(int(useful_life_years or 0), 1)
    total_days = life * 365.0
    elapsed_days = max((as_of - purchase_date).days, 0)
    elapsed_days_capped = min(elapsed_days, total_days)

    accumulated = pv * (elapsed_days_capped / total_days)
    current = max(pv - accumulated, 0.0)
    years_elapsed = elapsed_days / 365.0
    percent_elapsed = min((elapsed_days / total_days) * 100.0, 100.0) if total_days > 0 else 0.0
    return accumulated, current, years_elapsed, percent_elapsed
