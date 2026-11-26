"""Downloadable reports: portfolio summary, one property's onboarding, spending, and licences.

Every report is built as plain data (title, KPIs, sections of tables) and then rendered
on screen (JSON), as a PDF (reportlab), an Excel workbook (openpyxl) or CSV.
"""
import calendar
import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

REPORTS = {
    "portfolio": ("Portfolio summary", "Every property, where it is, how long it took and what it cost."),
    "property": ("Property onboarding report", "One property from signed agreement to live: journey, costs, inspection, purchases."),
    "spending": ("Spending report", "What was spent, by property, store and category."),
    "licences": ("Licence status", "Every STR licence, its status and upcoming renewals."),
}
PERIODS = [("this_month", "This month"), ("last_month", "Last month"), ("last_30", "Last 30 days"),
           ("this_quarter", "This quarter"), ("ytd", "Year to date"), ("all", "All time"), ("custom", "Custom")]
STATE_LABEL = {"live": "Live", "blocked": "Blocked", "waiting": "Waiting", "on_track": "On track"}
D0 = Decimal("0")


# ---------- helpers ----------

def period_from(params):
    """(start, end, label) as dates; end is inclusive. 'all' gives (None, None)."""
    today = timezone.localdate()
    key = params.get("period") or "this_month"
    if key == "custom":
        try:
            start = date.fromisoformat(params.get("from"))
            end = date.fromisoformat(params.get("to"))
        except (TypeError, ValueError):
            raise ValidationError("Pick a start and end date for a custom period.")
        if end < start:
            raise ValidationError("The end date is before the start date.")
        return start, end, f"{fmt_d(start)} – {fmt_d(end)}"
    if key == "all":
        return None, None, "All time"
    if key == "last_month":
        last = today.replace(day=1) - timedelta(days=1)
        start, end = last.replace(day=1), last
    elif key == "last_30":
        start, end = today - timedelta(days=29), today
    elif key == "this_quarter":
        q = (today.month - 1) // 3
        start = date(today.year, q * 3 + 1, 1)
        end_month = q * 3 + 3
        end = date(today.year, end_month, calendar.monthrange(today.year, end_month)[1])
    elif key == "ytd":
        start, end = date(today.year, 1, 1), today
    else:
        start = today.replace(day=1)
        end = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    label = dict(PERIODS).get(key, "") + f" ({fmt_d(start)} – {fmt_d(end)})"
    return start, end, label


def in_period(d, start, end):
    if d is None:
        return False
    if isinstance(d, datetime):
        d = timezone.localtime(d).date()
    return (start is None or d >= start) and (end is None or d <= end)


def fmt_d(d):
    if not d:
        return ""
    if isinstance(d, datetime):
        d = timezone.localtime(d).date()
    return f"{d:%b} {d.day}, {d.year}"


def money(v):
    return Decimal(v or 0).quantize(Decimal("0.01"))


def col(key, label, kind="text"):
    return {"key": key, "label": label, "type": kind}


def section(title, columns, rows, total=None, note=""):
    return {"title": title, "note": note, "columns": columns, "rows": rows, "total": total}


def kpi(label, value, detail="", kind="text"):
    return {"label": label, "value": value, "detail": detail, "type": kind}


def property_cost(prop):
    from .services import cost_report
    return Decimal(cost_report(prop)["total"])


# ---------- reports ----------

def portfolio(params):
    from onboarding import engine
    from properties.models import Property

    from .services import timeline_report
    start, end, label = period_from(params)
    tl = timeline_report()
    days_to_live = {r["property"]: r["days_to_live"] for r in tl["properties"]}
    rows, attention = [], []
    started = went_live = 0
    for p in Property.objects.select_related("licence").prefetch_related("steps__template").order_by("nickname"):
        state = engine.overall_state(p)
        cur = engine.current_step(p)
        live_step = next((s for s in p.steps.all() if s.template.number == 12 and s.completed_at), None)
        live_on = live_step.completed_at if state == "live" and live_step else None
        started += in_period(p.created_at, start, end)
        went_live += in_period(live_on, start, end)
        rows.append({"nickname": p.nickname, "address": p.address, "status": STATE_LABEL[state],
                     "step": f"{cur.template.number}. {cur.template.name}" if cur else "Done",
                     "progress": engine.progress(p) / 100, "started": p.created_at.date(), "live": live_on.date() if live_on else None,
                     "days": days_to_live.get(p.id) or (timezone.now() - p.created_at).days, "cost": property_cost(p)})
        if state in ("blocked", "waiting") and cur:
            note = cur.blocked_reason if state == "blocked" else cur.waiting_note
            attention.append({"nickname": p.nickname, "status": STATE_LABEL[state], "step": cur.template.name, "note": note or ""})
    total_cost = sum((r["cost"] for r in rows), D0)
    live_days = [d for d in days_to_live.values() if d is not None]
    spend = spending_totals(start, end)
    k = [
        kpi("Properties", len(rows), f"{sum(1 for r in rows if r['status'] != 'Live')} in onboarding", "int"),
        kpi("Started", started, label.split(" (")[0].lower(), "int"),
        kpi("Went live", went_live, label.split(" (")[0].lower(), "int"),
        kpi("Agreement → live", f"{round(sum(live_days) / len(live_days))} days" if live_days else "—", "Average for live properties"),
        kpi("Spend in period", spend["total"], f"{spend['properties']} properties", "money"),
        kpi("Blocked", sum(1 for r in rows if r["status"] == "Blocked"), "Need a decision or document", "int"),
    ]
    sections = [
        section("Properties", [col("nickname", "Property"), col("address", "Address"), col("status", "Status"), col("step", "Current step"),
                               col("progress", "Progress", "pct"), col("started", "Started", "date"), col("live", "Live since", "date"),
                               col("days", "Days", "int"), col("cost", "Onboarding cost", "money")],
                rows, total={"nickname": "Total", "cost": total_cost}),
        section("Time per step", [col("step", "Step"), col("owner", "Owner"), col("avg", "Average days", "num"), col("samples", "Properties", "int")],
                [{"step": f"{s['number']}. {s['name']}", "owner": s["owner"], "avg": s["avg_step_days"], "samples": s["samples"]} for s in tl["steps"]],
                note="Days each step takes, counted from when the steps it depends on finished."),
    ]
    if attention:
        sections.append(section("Needs attention", [col("nickname", "Property"), col("status", "Status"), col("step", "Step"), col("note", "Why")], attention))
    return build("portfolio", label, k, sections)


def property_report(params):
    from onboarding import engine
    from properties.models import Property

    from .models import Inspection
    from .services import cost_report
    try:
        prop = Property.objects.select_related("licence", "building").get(pk=params.get("property"))
    except (Property.DoesNotExist, ValueError, TypeError):
        raise ValidationError("Choose a property for this report.")
    state = engine.overall_state(prop)
    lic = getattr(prop, "licence", None)
    lay = prop.layout()
    c = cost_report(prop)
    k = [
        kpi("Progress", engine.progress(prop) / 100, STATE_LABEL[state], "pct"),
        kpi("Days in onboarding", (timezone.now() - prop.created_at).days, f"Started {fmt_d(prop.created_at)}", "int"),
        kpi("Onboarding cost", Decimal(c["total"]), f"${money(c['purchase_total']):,.2f} in purchases", "money"),
        kpi("Licence", lic.get_status_display() if lic else "—", f"Expires {fmt_d(lic.expires_on)}" if lic and lic.expires_on else ""),
    ]
    details = [
        ("Address", f"{prop.address}, {prop.city} {prop.postal_code}".strip()),
        ("Owner", f"{prop.owner_name} ({prop.get_owner_type_display().lower()})"),
        ("Lease", f"{fmt_d(prop.lease_start)} – {fmt_d(prop.lease_end)}" if prop.lease_start else ""),
        ("Layout", f"{lay['bedrooms']} bedroom(s), {prop.bathrooms} bathroom(s), {lay['beds']} bed(s)"
                   + (f" + {lay['sofa_beds']} sofa bed(s)" if lay["sofa_beds"] else "") + f", sleeps {lay['sleeps']}"),
        ("Building", prop.building.name if prop.building else ""),
        ("Unit email", prop.unit_email),
        ("Licence number", lic.number if lic else ""),
        ("Guesty listing", prop.guesty_listing_id),
    ]
    journey = []
    for s in prop.steps.select_related("template").order_by("template__number"):
        journey.append({"step": f"{s.template.number}. {s.template.name}", "owner": s.template.owner, "status": s.get_status_display(),
                        "done": s.completed_at.date() if s.completed_at else None,
                        "day": (s.completed_at - prop.created_at).days if s.completed_at else None,
                        "note": s.blocked_reason or s.waiting_note})
    pu = c["purchases"]
    costs = [{"item": "Furniture and supplies (cart price)", "amount": Decimal(pu["planned"])},
             {"item": "Decor", "amount": Decimal(pu["decor"])}]
    costs += [{"item": k2, "amount": Decimal(v)} for k2, v in c["expenses"].items()]
    sections = [
        section("Details", [col("label", ""), col("value", "")], [{"label": a, "value": b or "—"} for a, b in details]),
        section("Journey", [col("step", "Step"), col("owner", "Owner"), col("status", "Status"), col("done", "Completed", "date"),
                            col("day", "Day", "int"), col("note", "Note")], journey,
                note="Day = days after the property was created."),
        section("Costs", [col("item", "Item"), col("amount", "Amount", "money")], costs,
                total={"item": "Total onboarding cost", "amount": Decimal(c["total"])},
                note=f"Monthly utilities (running cost, not included): ${money(c['monthly_utilities'])}"),
    ]
    stores = purchases_by_store(order__property=prop)
    if stores:
        sections.append(section("Purchases by store", STORE_COLS, stores,
                                total={"store": "Total", "lines": sum(r["lines"] for r in stores), "delivered": sum(r["delivered"] for r in stores),
                                       "cart": sum((r["cart"] for r in stores), D0), "paid": sum((r["paid"] for r in stores), D0)}))
    insp = Inspection.objects.filter(property=prop).prefetch_related("items").first()
    if insp:
        issues = [{"area": i.area, "item": i.item, "condition": i.get_condition_display(), "action": i.get_action_display() if i.action else "",
                   "cost": i.est_cost, "notes": i.notes}
                  for i in insp.items.all() if i.condition in ("fair", "poor", "missing") or i.action not in ("", "none")]
        t = insp.totals()
        sections.append(section(f"Inspection ({fmt_d(insp.inspected_on)}{', ' + insp.inspector if insp.inspector else ''})",
                                [col("area", "Area"), col("item", "Item"), col("condition", "Condition"), col("action", "Action"),
                                 col("cost", "Est. cost", "money"), col("notes", "Notes")],
                                issues or [{"area": "—", "item": "No issues found"}],
                                total={"area": "Estimated repairs", "cost": t["est_cost"]} if issues else None,
                                note=f"{t['checked']} of {t['items']} items checked. {insp.summary}".strip()))
    visits = [{"date": v.date, "kind": v.get_kind_display(), "who": v.assigned_to, "status": v.get_status_display(), "cost": v.cost}
              for v in prop.visits.all()]
    if visits:
        sections.append(section("Visits", [col("date", "Date", "date"), col("kind", "Visit"), col("who", "Who"), col("status", "Status"),
                                           col("cost", "Cost", "money")], visits))
    activity = [{"when": a.created_at, "who": a.actor, "what": a.message} for a in prop.activity.all()[:15]]
    sections.append(section("Recent activity", [col("when", "When", "date"), col("who", "By"), col("what", "What")], activity))
    rep = build("property", f"{prop.nickname} · {prop.address}", k, sections)
    rep["title"] = f"{prop.listing.effective_title() if hasattr(prop, 'listing') else prop.address}"
    rep["eyebrow"] = f"Property onboarding report · {prop.nickname}"
    return rep


STORE_COLS = [col("store", "Store"), col("lines", "Lines", "int"), col("delivered", "Delivered", "int"),
              col("cart", "Cart total", "money"), col("paid", "Paid so far", "money")]


def _lines(**filters):
    from procurement.models import OrderLine
    return [l for l in OrderLine.objects.filter(order__status="approved", **filters)
            .select_related("store", "order__property").exclude(resolution="remove") if l.quantity]


def purchases_by_store(**filters):
    by = defaultdict(lambda: {"lines": 0, "delivered": 0, "cart": D0, "paid": D0})
    for l in _lines(**filters):
        r = by[l.store.name]
        r["lines"] += 1
        r["delivered"] += l.purchase_status == "delivered"
        r["cart"] += l.line_total
        if l.purchase_status != "to_buy":
            r["paid"] += l.actual_total
    return [{"store": k, **v} for k, v in sorted(by.items())]


def _period_filters(start, end):
    f = {}
    if start:
        f["order__approved_at__date__gte"] = start
    if end:
        f["order__approved_at__date__lte"] = end
    return f


def _expenses(start, end, prop=None):
    from .models import Expense
    qs = Expense.objects.select_related("property")
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    if prop:
        qs = qs.filter(property_id=prop)
    return list(qs.order_by("date"))


def spending_totals(start, end):
    lines = _lines(**_period_filters(start, end))
    ex = _expenses(start, end)
    total = sum((l.line_total for l in lines), D0) + sum((e.amount for e in ex), D0)
    return {"total": total, "properties": len({l.order.property_id for l in lines} | {e.property_id for e in ex})}


def spending(params):
    from procurement.models import MasterItem
    start, end, label = period_from(params)
    f = _period_filters(start, end)
    prop = params.get("property") or None
    if prop:
        f["order__property_id"] = prop
    lines = _lines(**f)
    ex = _expenses(start, end, prop)
    by_prop = defaultdict(lambda: {"purchases": D0, "expenses": D0})
    for l in lines:
        by_prop[l.order.property.nickname]["purchases"] += l.line_total
    for e in ex:
        by_prop[e.property.nickname]["expenses"] += e.amount
    prop_rows = [{"nickname": k, **v, "total": v["purchases"] + v["expenses"]} for k, v in sorted(by_prop.items())]
    cats = dict(MasterItem.Category.choices)
    by_cat = defaultdict(lambda: D0)
    for l in lines:
        by_cat[("Purchases", cats.get(l.category, l.category))] += l.line_total
    for e in ex:
        by_cat[("Expenses", e.get_category_display())] += e.amount
    purchases = sum((l.line_total for l in lines), D0)
    expenses = sum((e.amount for e in ex), D0)
    paid = sum((l.actual_total for l in lines if l.purchase_status != "to_buy"), D0)
    stores = purchases_by_store(**f)
    k = [
        kpi("Total spend", purchases + expenses, label.split(" (")[0], "money"),
        kpi("Store purchases", purchases, f"{len(lines)} order lines", "money"),
        kpi("Other expenses", expenses, f"{len(ex)} expenses", "money"),
        kpi("Average per property", (purchases + expenses) / len(prop_rows) if prop_rows else D0, f"{len(prop_rows)} properties", "money"),
        kpi("Paid so far", paid, "Lines ordered or delivered", "money"),
        kpi("Late deliveries", sum(1 for l in lines if l.is_late), "Past the expected date", "int"),
    ]
    sections = [
        section("By property", [col("nickname", "Property"), col("purchases", "Purchases", "money"), col("expenses", "Expenses", "money"),
                                col("total", "Total", "money")], prop_rows,
                total={"nickname": "Total", "purchases": purchases, "expenses": expenses, "total": purchases + expenses}),
        section("By store", STORE_COLS, stores,
                total={"store": "Total", "lines": sum(r["lines"] for r in stores), "delivered": sum(r["delivered"] for r in stores),
                       "cart": sum((r["cart"] for r in stores), D0), "paid": sum((r["paid"] for r in stores), D0)} if stores else None),
        section("By category", [col("kind", "Type"), col("category", "Category"), col("amount", "Amount", "money")],
                [{"kind": a, "category": b, "amount": v} for (a, b), v in sorted(by_cat.items())],
                total={"kind": "Total", "amount": purchases + expenses}),
        section("Expenses", [col("date", "Date", "date"), col("nickname", "Property"), col("category", "Category"),
                             col("description", "Description"), col("paid_by", "Paid by"), col("amount", "Amount", "money")],
                [{"date": e.date, "nickname": e.property.nickname, "category": e.get_category_display(), "description": e.description,
                  "paid_by": e.paid_by, "amount": e.amount} for e in ex],
                total={"date": "Total", "amount": expenses} if ex else None),
    ]
    rep = build("spending", label, k, sections)
    rep["note"] = "Store purchases count approved orders by approval date, at the paid price where entered, otherwise the cart price. CAD, before tax."
    return rep


def licences(params):
    from properties.models import Licence
    today = timezone.localdate()
    rows, due = [], []
    counts = defaultdict(int)
    for lic in Licence.objects.select_related("property").order_by("expires_on", "property__nickname"):
        days = (lic.expires_on - today).days if lic.expires_on else None
        counts[lic.status] += 1
        r = {"nickname": lic.property.nickname, "address": lic.property.address, "number": lic.number, "status": lic.get_status_display(),
             "submitted": lic.submitted_on, "approved": lic.approved_on, "expires": lic.expires_on, "days": days, "fee": lic.fee}
        rows.append(r)
        if days is not None and days <= 60:
            due.append(r)
    k = [
        kpi("Approved", counts["approved"], "Valid licences", "int"),
        kpi("With the city", counts["submitted"], "Submitted, waiting", "int"),
        kpi("Returned", counts["returned"], "Need documents", "int"),
        kpi("Not started", counts["not_started"], "", "int"),
        kpi("Renew within 60 days", sum(1 for r in due if r["days"] >= 0), "Reminders at 60, 30, 7 days", "int"),
        kpi("Expired", sum(1 for r in due if r["days"] < 0), "", "int"),
    ]
    cols = [col("nickname", "Property"), col("address", "Address"), col("number", "Licence #"), col("status", "Status"),
            col("submitted", "Submitted", "date"), col("approved", "Approved", "date"), col("expires", "Expires", "date"),
            col("days", "Days left", "int"), col("fee", "Fee", "money")]
    sections = [section("All licences", cols, rows, total={"nickname": "Total fees", "fee": sum((r["fee"] or D0 for r in rows), D0)})]
    if due:
        sections.insert(0, section("Renewals due", cols, due, note="Expired or expiring within 60 days."))
    return build("licences", f"As of {fmt_d(today)}", k, sections)


BUILDERS = {"portfolio": portfolio, "property": property_report, "spending": spending, "licences": licences}


def build(key, subtitle, kpis, sections):
    title, about = REPORTS[key]
    return {"key": key, "title": title, "eyebrow": about, "subtitle": subtitle, "generated": timezone.now(),
            "kpis": kpis, "sections": sections, "note": ""}


def make(key, params):
    if key not in BUILDERS:
        raise ValidationError("Unknown report.")
    return BUILDERS[key](params)


# ---------- renderers ----------

def cell_text(v, kind):
    if v is None or v == "":
        return ""
    if kind == "money":
        return v if isinstance(v, str) else f"${money(v):,.2f}"
    if kind == "pct":
        return f"{round(float(v) * 100)}%"
    if kind == "date":
        return v if isinstance(v, str) else fmt_d(v)
    if kind == "num":
        return f"{v:g}" if isinstance(v, (int, float)) else str(v)
    return str(v)


def to_json(rep):
    """Numbers stay numbers; dates become ISO strings."""
    def conv(v):
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, datetime):
            return timezone.localtime(v).isoformat()
        if isinstance(v, date):
            return v.isoformat()
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        if isinstance(v, list):
            return [conv(x) for x in v]
        return v
    return conv(rep)


def filename(rep, ext):
    import re
    base = re.sub(r"[^A-Za-z0-9]+", "-", f"{rep['key']}-{rep['subtitle']}").strip("-").lower()[:80]
    return f"{base}-{timezone.localdate():%Y%m%d}.{ext}"


def to_csv(rep):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([rep["title"]])
    w.writerow([rep["subtitle"]])
    w.writerow([])
    for k in rep["kpis"]:
        w.writerow([k["label"], cell_text(k["value"], k["type"]), k["detail"]])
    for s in rep["sections"]:
        w.writerow([])
        w.writerow([s["title"]])
        w.writerow([c["label"] for c in s["columns"]])
        for r in s["rows"] + ([s["total"]] if s["total"] else []):
            w.writerow([raw_value(r.get(c["key"]), c["type"]) for c in s["columns"]])
    return buf.getvalue()


def raw_value(v, kind):
    if v is None:
        return ""
    if kind == "money":
        return v if isinstance(v, str) else f"{money(v)}"
    if kind == "pct":
        return f"{round(float(v) * 100)}%"
    if kind == "date":
        return v.isoformat()[:10] if hasattr(v, "isoformat") else v
    return v


def to_xlsx(rep):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    accent, soft, line = "0F6E5F", "E8F3F0", "E9E9E5"
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor=accent)
    total_fill = PatternFill("solid", fgColor=soft)
    border = Border(bottom=Side(style="thin", color=line))
    fmts = {"money": '"$"#,##0.00', "pct": "0%", "date": "mmm d, yyyy", "int": "0", "num": "0.0"}

    def value(v, kind):
        if v is None or v == "":
            return None
        if kind == "money":
            return v if isinstance(v, str) else float(v)
        if kind == "date" and isinstance(v, datetime):
            return timezone.localtime(v).replace(tzinfo=None)
        return v

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = rep["title"]
    ws["A1"].font = Font(size=18, bold=True)
    ws["A2"] = rep["subtitle"]
    ws["A2"].font = Font(color="77776F")
    ws["A3"] = f"Generated {fmt_d(rep['generated'])}"
    ws["A3"].font = Font(color="77776F", size=9)
    ws.append([])
    ws.append(["Measure", "Value", "Detail"])
    for c in ws[5]:
        c.font, c.fill = head_font, head_fill
    for k in rep["kpis"]:
        ws.append([k["label"], value(k["value"], k["type"]), k["detail"]])
        cell = ws.cell(row=ws.max_row, column=2)
        if k["type"] in fmts:
            cell.number_format = fmts[k["type"]]
        cell.font = Font(bold=True)
    if rep.get("note"):
        ws.append([])
        ws.append([rep["note"]])
    for c, w in zip("ABC", (28, 18, 40)):
        ws.column_dimensions[c].width = w

    used = set()
    for s in rep["sections"]:
        name = "".join(ch for ch in s["title"] if ch not in '[]:*?/\\')[:28] or "Sheet"
        while name in used:
            name = name[:26] + "_2"
        used.add(name)
        sh = wb.create_sheet(name)
        sh.append([s["title"]])
        sh["A1"].font = Font(size=14, bold=True)
        if s["note"]:
            sh.append([s["note"]])
            sh.cell(row=2, column=1).font = Font(color="77776F", italic=True)
        sh.append([c["label"] for c in s["columns"]])
        hr = sh.max_row
        for c in sh[hr]:
            c.font, c.fill = head_font, head_fill
            c.alignment = Alignment(vertical="center")
        for r in s["rows"]:
            sh.append([value(r.get(c["key"]), c["type"]) for c in s["columns"]])
        if s["total"]:
            sh.append([value(s["total"].get(c["key"]), c["type"]) for c in s["columns"]])
            for c in sh[sh.max_row]:
                c.font, c.fill = Font(bold=True), total_fill
        for i, c in enumerate(s["columns"], start=1):
            letter = get_column_letter(i)
            width = max([len(str(c["label"]))] + [len(cell_text(r.get(c["key"]), c["type"])) for r in s["rows"]]) + 3
            sh.column_dimensions[letter].width = min(max(width, 10), 60)
            if c["type"] in fmts:
                for row in sh.iter_rows(min_row=hr + 1, min_col=i, max_col=i):
                    row[0].number_format = fmts[c["type"]]
        for row in sh.iter_rows(min_row=hr + 1):
            for c in row:
                c.border = border
        sh.freeze_panes = sh.cell(row=hr + 1, column=1)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def to_pdf(rep):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ink, muted, accent = colors.HexColor("#141413"), colors.HexColor("#77776F"), colors.HexColor("#0F6E5F")
    soft, line, zebra = colors.HexColor("#E8F3F0"), colors.HexColor("#E9E9E5"), colors.HexColor("#FAFAF8")
    wide = max((len(s["columns"]) for s in rep["sections"]), default=0) > 6
    page = landscape(A4) if wide else A4
    margin = 16 * mm
    width = page[0] - 2 * margin

    st = {
        "eyebrow": ParagraphStyle("e", fontName="Helvetica", fontSize=8.5, textColor=muted, leading=11),
        "title": ParagraphStyle("t", fontName="Times-Roman", fontSize=26, leading=30, textColor=ink, spaceBefore=2, spaceAfter=2),
        "sub": ParagraphStyle("s", fontName="Helvetica", fontSize=10, textColor=muted, leading=13),
        "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=11.5, textColor=ink, spaceBefore=14, spaceAfter=5),
        "note": ParagraphStyle("n", fontName="Helvetica-Oblique", fontSize=8, textColor=muted, leading=10, spaceAfter=4),
        "cell": ParagraphStyle("c", fontName="Helvetica", fontSize=8, leading=10, textColor=ink),
        "cellr": ParagraphStyle("cr", fontName="Helvetica", fontSize=8, leading=10, textColor=ink, alignment=TA_RIGHT),
        "head": ParagraphStyle("hd", fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=colors.white),
        "headr": ParagraphStyle("hdr", fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=colors.white, alignment=TA_RIGHT),
        "kl": ParagraphStyle("kl", fontName="Helvetica", fontSize=7.5, textColor=muted, leading=9),
        "kv": ParagraphStyle("kv", fontName="Times-Roman", fontSize=18, leading=21, textColor=ink),
        "kd": ParagraphStyle("kd", fontName="Helvetica", fontSize=7, textColor=muted, leading=9),
    }

    def esc(t):
        return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story = [Paragraph(esc(rep["eyebrow"]), st["eyebrow"]), Paragraph(esc(rep["title"]), st["title"]),
             Paragraph(esc(rep["subtitle"]), st["sub"]), Spacer(1, 10)]
    kp = rep["kpis"]
    if kp:
        per_row = 3 if len(kp) > 4 and not wide else min(len(kp), 6)
        cells = [[Paragraph(esc(k["label"]), st["kl"]), Paragraph(esc(cell_text(k["value"], k["type"]) or "—"), st["kv"]),
                  Paragraph(esc(k["detail"]), st["kd"])] for k in kp]
        rows = [cells[i:i + per_row] for i in range(0, len(cells), per_row)]
        rows[-1] += [""] * (per_row - len(rows[-1]))
        t = Table(rows, colWidths=[width / per_row] * per_row)
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, line), ("INNERGRID", (0, 0), (-1, -1), 0.6, line),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 8),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 9)]))
        story.append(t)
    if rep.get("note"):
        story += [Spacer(1, 4), Paragraph(esc(rep["note"]), st["note"])]

    for s in rep["sections"]:
        cols = s["columns"]
        right = [c["type"] in ("money", "int", "num", "pct") for c in cols]
        is_kv = cols and not any(c["label"] for c in cols)
        data = [] if is_kv else [[Paragraph(esc(c["label"]), st["headr" if r else "head"]) for c, r in zip(cols, right)]]
        for row in s["rows"]:
            data.append([Paragraph(esc(cell_text(row.get(c["key"]), c["type"])), st["cellr" if r else "cell"]) for c, r in zip(cols, right)])
        if s["total"]:
            data.append([Paragraph("<b>" + esc(cell_text(s["total"].get(c["key"]), c["type"])) + "</b>", st["cellr" if r else "cell"])
                         for c, r in zip(cols, right)])
        if not s["rows"]:
            data.append([Paragraph("Nothing in this period.", st["cell"])] + [""] * (len(cols) - 1))
        # widths: numbers and dates get fixed widths; text columns share the rest by how long their content is
        fixed = {"money": 25 * mm, "int": 15 * mm, "num": 18 * mm, "pct": 17 * mm, "date": 25 * mm}
        fixed["int"] = max([15 * mm] + [len(c["label"]) * 1.9 * mm + 6 * mm for c in cols if c["type"] == "int"])
        used = sum(fixed.get(c["type"], 0) for c in cols)
        weights = {i: min(40, max([len(c["label"])] + [len(cell_text(r.get(c["key"]), "text")) for r in s["rows"]] + [6]))
                   for i, c in enumerate(cols) if c["type"] not in fixed}
        total_w = sum(weights.values()) or 1
        widths = [fixed[c["type"]] if c["type"] in fixed else (width - used) * weights[i] / total_w for i, c in enumerate(cols)]
        if is_kv:
            widths = [width * .28, width * .72]
        t = Table(data, colWidths=widths, repeatRows=0 if is_kv else 1)
        style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, line),
                 ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
                 ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
        if not is_kv:
            style += [("BACKGROUND", (0, 0), (-1, 0), accent)]
            style += [("BACKGROUND", (0, i), (-1, i), zebra) for i in range(2, len(data), 2)]
        else:
            style += [("TEXTCOLOR", (0, 0), (0, -1), muted)]
        if s["total"]:
            style += [("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), soft)]
        t.setStyle(TableStyle(style))
        head = [Paragraph(esc(s["title"]), st["h"])] + ([Paragraph(esc(s["note"]), st["note"])] if s["note"] else [])
        story.append(KeepTogether(head + [t]) if len(data) < 18 else KeepTogether(head))
        if len(data) >= 18:
            story.append(t)

    gen = f"Generated {fmt_d(rep['generated'])} · Property onboarding"

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(margin, 9 * mm, gen)
        canvas.drawRightString(page[0] - margin, 9 * mm, f"Page {doc.page}")
        canvas.setStrokeColor(accent)
        canvas.setLineWidth(2)
        canvas.line(margin, page[1] - 9 * mm, margin + 24 * mm, page[1] - 9 * mm)
        canvas.restoreState()

    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=page, leftMargin=margin, rightMargin=margin, topMargin=15 * mm, bottomMargin=16 * mm,
                            title=rep["title"], author="Property onboarding")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
