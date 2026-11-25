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

from .models import MasterItem, Order, OrderLine, PurchaseStatus, simple_layout
from .pricing import flag_for, get_checker

AGENT = "Procurement agent"
SUPPLIES_STEP, FURNITURE_STEP = 6, 5


# ---------- quantity engine (pure) ----------

def quantities(items, bedrooms, bathrooms=None, beds=None):
    """[(item, qty)] for every item with qty > 0. Pass a layout dict or plain counts."""
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

def order_layout(prop, bedrooms=None, bathrooms=None, beds=None):
    """The unit's layout, with any counts the team overrode for this order."""
    lay = prop.layout()
    if bedrooms is not None:
        lay["bedrooms"] = bedrooms
    if bathrooms is not None:
        lay["bathrooms"] = bathrooms
    if beds is not None and beds != lay["beds"]:
        lay = {**simple_layout(lay["bedrooms"], lay["bathrooms"], beds, lay["sofa_beds"])}
    return lay


@transaction.atomic
def create_order(prop, bedrooms=None, bathrooms=None, beds=None, user=None, kind=Order.Kind.FULL, budget=None) -> Order:
    if not _step_open(prop, SUPPLIES_STEP):
        raise ValidationError("Step 6 is locked. Finish step 1 (agreement signed) first.")
    lay = order_layout(prop, bedrooms, bathrooms, beds)
    order = Order.objects.create(property=prop, kind=kind, layout=lay, budget=budget,
                                 bedrooms=lay["bedrooms"], bathrooms=lay["bathrooms"], beds=lay["beds"])
    if kind == Order.Kind.TOP_UP:
        n = _copy_problem_lines(order)
        log(prop, f"Started a top-up order ({n} missing/damaged item(s) carried over)", actor=AGENT, user=user)
        return order
    items = MasterItem.objects.filter(is_active=True).select_related("store")
    OrderLine.objects.bulk_create([
        OrderLine(order=order, master_item=it, category=it.category, name=it.name, item_type=it.item_type,
                  store=it.store, product_url=it.product_url, quantity=q, typical_price=it.typical_price)
        for it, q in quantities(items, lay)
    ])
    sofa = f" + {lay['sofa_beds']} sofa bed(s)" if lay["sofa_beds"] else ""
    log(prop, f"Calculated quantities for {order.bedrooms} bd / {order.bathrooms} ba / {order.beds} beds{sofa}, sleeps {lay['sleeps']} ({order.lines.count()} lines)", actor=AGENT, user=user)
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


def _layout_of(order):
    return order.layout or simple_layout(order.bedrooms, order.bathrooms, order.beds)


def required_types(order: Order):
    items = MasterItem.objects.filter(is_active=True)
    return sorted({it.item_type for it, _ in quantities(items, _layout_of(order))})


def cross_check(order: Order) -> dict:
    """Compare included lines with the checklist by item type, not brand."""
    if order.kind == Order.Kind.TOP_UP:
        return {"required": 0, "missing": [], "duplicates": {}, "ok": True, "skipped": "Top-up orders aren't cross-checked."}
    included = [l for l in order.lines.all() if l.included]
    by_type = defaultdict(list)
    for l in included:
        by_type[l.item_type].append(l)
    req = required_types(order)
    missing = [t for t in req if t not in by_type]
    duplicates = {t: [l.id for l in ls] for t, ls in by_type.items() if len(ls) > 1}
    return {"required": len(req), "missing": missing, "duplicates": duplicates, "ok": not missing and not duplicates,
            "uncovered": uncovered_sizes(_layout_of(order))}


def uncovered_sizes(lay):
    """Bed sizes in the unit that a size-specific master-list item has no version for (e.g. king sheets)."""
    from django.conf import settings
    sizes = {s for s, n in lay.get("beds_by_size", {}).items() if n}
    sofa = settings.UNIT["SOFA_BED_SIZE"] if lay.get("sofa_beds") else None
    by_base = defaultdict(set)
    sofa_bases = set()
    for it in MasterItem.objects.filter(is_active=True, rule=MasterItem.Rule.PER_BED).exclude(bed_size=""):
        base = it.item_type.rsplit(" (", 1)[0]
        by_base[base].add(it.bed_size)
        if it.include_sofa_beds:
            sofa_bases.add(base)
    out = []
    for base, have in sorted(by_base.items()):
        for s in sorted(sizes - have):
            out.append(f"No {s} {base} on the master list")
        if sofa and base in sofa_bases and sofa not in have:
            out.append(f"No {sofa} {base} for sofa beds")
    return out


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
    if order.kind == Order.Kind.FULL:
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


# ---------- purchase tracking (after approval) ----------

PROBLEM = (PurchaseStatus.MISSING, PurchaseStatus.DAMAGED, PurchaseStatus.RETURNED)
TRACK_FIELDS = ["purchase_status", "store_order_number", "actual_unit_price", "quantity_received", "ordered_at",
                "expected_delivery", "delivered_at", "purchase_notes"]
SETUP_STEP = 7


def _copy_problem_lines(order):
    """A top-up starts with every missing, damaged or returned line from earlier approved orders."""
    src = OrderLine.objects.filter(order__property=order.property, order__status=Order.Status.APPROVED,
                                   purchase_status__in=PROBLEM, carried_over=False).exclude(order=order).select_related("store")
    n = 0
    for l in src:
        qty = l.quantity - (l.quantity_received or 0) if l.purchase_status == PurchaseStatus.MISSING and l.quantity_received else l.quantity
        OrderLine.objects.create(order=order, master_item=l.master_item, source=OrderLine.Source.MANUAL, category=l.category,
                                 name=l.name, item_type=l.item_type, store=l.store, product_url=l.product_url,
                                 quantity=max(1, qty), typical_price=l.typical_price, current_price=l.unit_price, in_stock=True,
                                 purchase_notes=f"Replaces {l.get_purchase_status_display().lower()} line from order {l.order_id}")
        l.carried_over = True
        l.save(update_fields=["carried_over"])
        n += 1
    return n


def _guard_tracking(order):
    if order.status != Order.Status.APPROVED:
        raise ValidationError("Track purchases after the order is approved.")


@transaction.atomic
def update_purchase(line: OrderLine, data: dict, user=None) -> OrderLine:
    _guard_tracking(line.order)
    old = line.purchase_status
    for f in TRACK_FIELDS:
        if f in data:
            v = data[f]
            setattr(line, f, None if v == "" and f not in ("store_order_number", "purchase_notes", "purchase_status") else v)
    if line.purchase_status not in PurchaseStatus.values:
        raise ValidationError("Unknown purchase status.")
    today = timezone.localdate()
    if line.purchase_status == PurchaseStatus.ORDERED and not line.ordered_at:
        line.ordered_at = today
    if line.purchase_status == PurchaseStatus.DELIVERED:
        line.delivered_at = line.delivered_at or today
        if line.quantity_received is None:
            line.quantity_received = line.quantity
    line.save()
    if old != line.purchase_status:
        log(line.order.property, f"{line.name}: {line.get_purchase_status_display().lower()}", actor=_who(user), user=user)
    after_tracking(line.order, user)
    return line


@transaction.atomic
def mark_store(order: Order, store_code: str, status: str, store_order_number="", expected_delivery=None, user=None):
    """Bulk update every line of one store cart, e.g. after checking out the Amazon cart."""
    _guard_tracking(order)
    if status not in PurchaseStatus.values:
        raise ValidationError("Unknown purchase status.")
    lines = [l for l in order.lines.select_related("store") if l.included and l.store.code == store_code]
    if not lines:
        raise ValidationError("No lines for that store in this order.")
    for l in lines:
        data = {"purchase_status": status}
        if store_order_number:
            data["store_order_number"] = store_order_number
        if expected_delivery:
            data["expected_delivery"] = expected_delivery
        for f, v in data.items():
            setattr(l, f, v)
        if status == PurchaseStatus.ORDERED and not l.ordered_at:
            l.ordered_at = timezone.localdate()
        if status == PurchaseStatus.DELIVERED:
            l.delivered_at = l.delivered_at or timezone.localdate()
            l.quantity_received = l.quantity if l.quantity_received is None else l.quantity_received
        l.save()
    log(order.property, f"{lines[0].store.name} cart marked {PurchaseStatus(status).label.lower()} ({len(lines)} lines"
        + (f", order #{store_order_number}" if store_order_number else "") + ")", actor=_who(user), user=user)
    after_tracking(order, user)
    return order


def _who(user):
    return (user.get_full_name() or user.get_username()) if user and user.is_authenticated else "Team"


def tracking_summary(order: Order) -> dict:
    lines = [l for l in order.lines.all() if l.included]
    counts = {s: 0 for s in PurchaseStatus.values}
    for l in lines:
        counts[l.purchase_status] += 1
    planned = sum((l.line_total for l in lines), Decimal("0"))
    actual = sum((l.actual_total for l in lines if l.purchase_status != PurchaseStatus.TO_BUY), Decimal("0"))
    return {"counts": counts, "lines": len(lines), "planned": planned, "spent": actual,
            "late": sum(1 for l in lines if l.is_late),
            "all_delivered": bool(lines) and all(l.purchase_status == PurchaseStatus.DELIVERED for l in lines)}


def after_tracking(order: Order, user=None):
    """When every line of every approved order is delivered, tick step 5/7 delivery tasks."""
    prop = order.property
    approved = Order.objects.filter(property=prop, status=Order.Status.APPROVED)
    lines = [l for o in approved for l in o.lines.all() if l.included and not l.carried_over]
    if not lines:
        return
    furniture = [l for l in lines if l.category == MasterItem.Category.FURNITURE]
    if furniture and all(l.purchase_status == PurchaseStatus.DELIVERED for l in furniture):
        _tick(prop, FURNITURE_STEP, ["Delivery confirmed"], user)
    if all(l.purchase_status == PurchaseStatus.DELIVERED for l in lines):
        _tick(prop, SETUP_STEP, ["All deliveries received"], user)


def purchasing_rows(qs):
    """Flat rows for the cross-property purchasing tracker and its CSV export."""
    rows = []
    for l in qs:
        rows.append({
            "id": l.id, "order": l.order_id, "order_kind": l.order.kind, "property": l.order.property_id,
            "nickname": l.order.property.nickname, "name": l.name, "item_type": l.item_type, "category": l.category,
            "store_code": l.store.code, "store_name": l.store.name, "link": l.link, "quantity": l.quantity,
            "quantity_received": l.quantity_received, "unit_price": str(l.unit_price),
            "actual_unit_price": None if l.actual_unit_price is None else str(l.actual_unit_price),
            "line_total": str(l.line_total), "actual_total": str(l.actual_total),
            "purchase_status": l.purchase_status, "purchase_status_label": l.get_purchase_status_display(),
            "store_order_number": l.store_order_number, "ordered_at": l.ordered_at, "expected_delivery": l.expected_delivery,
            "delivered_at": l.delivered_at, "late": l.is_late, "receipt_url": l.receipt.url if l.receipt else "",
            "notes": l.purchase_notes,
        })
    return rows
