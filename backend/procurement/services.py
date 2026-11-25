"""Procurement agent: master list × unit size → checked carts and an order document."""
from collections import OrderedDict, defaultdict
from decimal import Decimal
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from onboarding.engine import complete_by_title
from onboarding.models import PropertyStep
from properties.services import log

from .models import MasterItem, Order, OrderLine
from .pricing import flag_for, get_checker

AGENT = "Procurement agent"
SUPPLIES_STEP, FURNITURE_STEP = 6, 5


# ---------- quantity engine (pure) ----------

def quantities(items, bedrooms: int, bathrooms: int, beds: int):
    """[(item, qty)] for every item with qty > 0."""
    out = []
    for it in items:
        q = it.quantity_for(bedrooms, bathrooms, beds)
        if q > 0:
            out.append((it, q))
    return out


def _step_open(prop, number):
    return PropertyStep.objects.filter(property=prop, template__number=number).exclude(status=PropertyStep.Status.LOCKED).exists()


def _tick(prop, step, titles, user=None):
    if _step_open(prop, step):
        complete_by_title(prop, step, titles, actor=AGENT, user=user)


# ---------- order lifecycle ----------

@transaction.atomic
def create_order(prop, bedrooms=None, bathrooms=None, beds=None, user=None) -> Order:
    if not _step_open(prop, SUPPLIES_STEP):
        raise ValidationError("Step 6 is locked. Finish step 1 (agreement signed) first.")
    order = Order.objects.create(
        property=prop,
        bedrooms=prop.bedrooms if bedrooms is None else bedrooms,
        bathrooms=prop.bathrooms if bathrooms is None else bathrooms,
        beds=prop.beds if beds is None else beds,
    )
    items = MasterItem.objects.filter(is_active=True).select_related("store")
    OrderLine.objects.bulk_create([
        OrderLine(order=order, master_item=it, category=it.category, name=it.name, item_type=it.item_type,
                  store=it.store, product_url=it.product_url, quantity=q, typical_price=it.typical_price)
        for it, q in quantities(items, order.bedrooms, order.bathrooms, order.beds)
    ])
    log(prop, f"Calculated quantities for {order.bedrooms} bd / {order.bathrooms} ba / {order.beds} beds ({order.lines.count()} lines)", actor=AGENT, user=user)
    _tick(prop, SUPPLIES_STEP, ["Quantities calculated"], user)
    if order.lines.filter(category=MasterItem.Category.FURNITURE).exists():
        _tick(prop, FURNITURE_STEP, ["Standard furniture list generated"], user)
    return order


def _guard_editable(order):
    if order.status == Order.Status.APPROVED:
        raise ValidationError("This order is already approved. Start a new order to change it.")


@transaction.atomic
def run_check(order: Order, user=None) -> Order:
    _guard_editable(order)
    checker = get_checker()
    for line in order.lines.select_related("store"):
        res = checker.check(name=line.name, item_type=line.item_type, store_code=line.store.code,
                            typical_price=line.typical_price, product_url=line.product_url)
        line.current_price, line.in_stock, line.check_note = res.price, res.in_stock, res.note
        line.flag = flag_for(res, line.typical_price)
        if line.flag:
            line.resolution = ""  # a new flag always needs a fresh decision
        line.save()
    order.status, order.checked_at = Order.Status.CHECKED, timezone.now()
    order.save(update_fields=["status", "checked_at"])
    flagged = order.lines.exclude(flag="").count()
    unchecked = order.lines.exclude(check_note="").count()
    log(order.property, f"Checked price and stock: {flagged} item(s) flagged"
        + (f", {unchecked} couldn't be checked automatically" if unchecked else ""), actor=AGENT, user=user)
    _tick(order.property, SUPPLIES_STEP, ["Price and stock checked"], user)
    return order


@transaction.atomic
def resolve_line(line: OrderLine, resolution: str, user=None) -> OrderLine:
    _guard_editable(line.order)
    R = OrderLine.Resolution
    if resolution not in (R.REPLACE, R.KEEP, R.REMOVE):
        raise ValidationError("Choose replace, keep or remove.")
    if resolution == R.KEEP and line.in_stock is False:
        raise ValidationError("Can't keep an out-of-stock item. Replace or remove it.")
    if resolution == R.REPLACE:
        alt = line.master_item.alternatives.select_related("store").first() if line.master_item else None
        if not alt:
            raise ValidationError("No approved replacement for this item. Add one in the master list, or remove the line.")
        res = get_checker().check(name=alt.name, item_type=line.item_type, store_code=alt.store.code,
                                  typical_price=alt.typical_price, product_url=alt.product_url)
        line.replaced_from = line.name
        line.name, line.store, line.product_url = alt.name, alt.store, alt.product_url
        line.current_price, line.in_stock, line.check_note = res.price, res.in_stock, res.note
    line.resolution = resolution
    line.order.status = Order.Status.CHECKED  # any change un-stages carts
    line.order.save(update_fields=["status"])
    line.save()
    log(line.order.property, f"{line.get_resolution_display()}: {line.replaced_from or line.name}", actor=user.get_username() if user else "Team", user=user)
    return line


@transaction.atomic
def add_manual_line(order: Order, *, name, item_type, store, price, quantity=1, category="living", product_url="", user=None):
    _guard_editable(order)
    line = OrderLine.objects.create(order=order, source=OrderLine.Source.MANUAL, category=category, name=name,
                                    item_type=item_type.strip().lower(), store=store, product_url=product_url,
                                    quantity=quantity, typical_price=price, current_price=price, in_stock=True)
    if order.status == Order.Status.CARTS_BUILT:
        order.status = Order.Status.CHECKED
        order.save(update_fields=["status"])
    return line


def required_types(order: Order):
    items = MasterItem.objects.filter(is_active=True)
    return sorted({it.item_type for it, _ in quantities(items, order.bedrooms, order.bathrooms, order.beds)})


def cross_check(order: Order) -> dict:
    """Compare included lines with the checklist by item type, not brand."""
    included = [l for l in order.lines.all() if l.included]
    by_type = defaultdict(list)
    for l in included:
        by_type[l.item_type].append(l)
    req = required_types(order)
    missing = [t for t in req if t not in by_type]
    duplicates = {t: [l.id for l in ls] for t, ls in by_type.items() if len(ls) > 1}
    return {"required": len(req), "missing": missing, "duplicates": duplicates, "ok": not missing and not duplicates}


@transaction.atomic
def build_carts(order: Order, user=None) -> Order:
    _guard_editable(order)
    if order.status == Order.Status.DRAFT:
        raise ValidationError("Run the price and stock check first.")
    pending = order.lines.exclude(flag="").filter(resolution="").count()
    if pending:
        raise ValidationError(f"Resolve {pending} flagged item(s) before building carts.")
    order.status = Order.Status.CARTS_BUILT
    order.save(update_fields=["status"])
    log(order.property, f"Built carts at {len(carts(order))} store(s) and staged them for review", actor=AGENT, user=user)
    return order


def carts(order: Order):
    groups = OrderedDict()
    for l in order.lines.select_related("store", "master_item").order_by("store__name", "category", "id"):
        if l.included:
            groups.setdefault(l.store, []).append(l)
    out = []
    for store, lines in groups.items():
        total = sum((l.line_total for l in lines), Decimal("0"))
        out.append({"store": store, "lines": lines, "total": total, "cart_url": cart_url(store, lines)})
    return out


def cart_url(store, lines):
    """One-click cart where the store supports it and every line has a product ID."""
    if store.code == "amazon":
        skus = [(l.master_item.store_sku if l.master_item else "", l.quantity) for l in lines]
        if skus and all(s for s, _ in skus):
            params = {}
            for i, (sku, q) in enumerate(skus, start=1):
                params[f"ASIN.{i}"], params[f"Quantity.{i}"] = sku, q
            return "https://www.amazon.ca/gp/aws/cart/add.html?" + urlencode(params)
    return ""


@transaction.atomic
def approve(order: Order, user=None) -> Order:
    if order.status != Order.Status.CARTS_BUILT:
        raise ValidationError("Build and review the carts before approving.")
    cc = cross_check(order)
    if not cc["ok"]:
        raise ValidationError("Fix the cross-check first: " + ", ".join(
            [f"missing {t}" for t in cc["missing"]] + [f"duplicate {t}" for t in cc["duplicates"]]))
    order.status, order.approved_at, order.approved_by = Order.Status.APPROVED, timezone.now(), user
    order.save(update_fields=["status", "approved_at", "approved_by"])
    prop = order.property
    log(prop, f"Order approved: {summary(order)['lines']} lines, ${summary(order)['total']:.2f}", actor=user.get_username() if user else "Client", user=user)
    _tick(prop, SUPPLIES_STEP, ["Carts cross-checked against checklist", "Order approved and placed", "Order document saved"], user)
    if order.lines.filter(category=MasterItem.Category.FURNITURE).exists():
        _tick(prop, FURNITURE_STEP, ["Furniture ordered"], user)
    return order


def summary(order: Order) -> dict:
    lines = [l for l in order.lines.all() if l.included]
    furniture = sum((l.line_total for l in lines if l.category == MasterItem.Category.FURNITURE), Decimal("0"))
    total = sum((l.line_total for l in lines), Decimal("0"))
    decor = sum((d.price * d.quantity for d in order.decor.all()), Decimal("0"))
    return {
        "lines": len(lines),
        "units": sum(l.quantity for l in lines),
        "furniture": furniture,
        "supplies": total - furniture,
        "decor": decor,
        "total": total,
        "flags_open": sum(1 for l in order.lines.all() if l.needs_decision),
        "unchecked": sum(1 for l in order.lines.all() if l.included and l.check_note),
    }


def order_document_rows(order: Order):
    rows = [["Item", "Type", "Qty", "Store", "Unit price", "Line total", "Link"]]
    for l in order.lines.select_related("store").order_by("category", "id"):
        if l.included:
            rows.append([l.name, l.item_type, l.quantity, l.store.name, f"{l.unit_price:.2f}", f"{l.line_total:.2f}", l.link])
    s = summary(order)
    rows.append(["Total (CAD, before tax)", "", s["units"], "", "", f"{s['total']:.2f}", ""])
    for d in order.decor.all():
        rows.append([f"Decor: {d.name}", "decor", d.quantity, d.where, f"{d.price:.2f}", f"{d.price * d.quantity:.2f}", ""])
    return rows
