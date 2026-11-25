"""Visits (inspection, setup day, photo shoot), inspection reports, costs and timeline reports, and the daily digest."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from statistics import mean

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from onboarding.engine import complete_by_title
from onboarding.models import PropertyStep, StepTemplate
from properties.services import log

from .models import Expense, Inspection, InspectionItem, Notification, RoomMeasurement, Visit

INSPECTION_STEP, SETUP_STEP, PHOTO_STEP = 4, 7, 8

SETUP_CHECKLIST = [
    "All deliveries received",
    "Assembly done",
    "Beds made",
    "Staging done",
    "Smoke/CO alarm tested",
    "Lockbox installed and tested",
    "Wi-Fi tested",
    "Packaging and boxes removed",
    "Final clean",
]
# setup-day checklist labels that tick a step 7 task of the same name
SETUP_TASKS = {"All deliveries received", "Assembly done", "Beds made", "Staging done"}

COMMON_ITEMS = {
    "Entry": ["Door and lock", "Buzzer / intercom", "Closet", "Walls and floor"],
    "Kitchen": ["Fridge", "Stove and oven", "Dishwasher", "Microwave", "Range hood", "Sink and faucet", "Cabinets and counters", "Walls and floor"],
    "Living": ["Walls and paint", "Floor", "Windows and blinds", "Lights and switches", "Outlets", "Balcony"],
    "Laundry": ["Washer", "Dryer"],
    "Safety": ["Smoke alarm", "CO alarm", "Fire extinguisher", "Electrical panel"],
}
BEDROOM_ITEMS = ["Walls and paint", "Floor", "Windows and blinds", "Closet", "Lights and outlets"]
BATHROOM_ITEMS = ["Toilet", "Sink and vanity", "Shower / tub", "Exhaust fan", "Caulking and grout", "Water pressure / hot water"]


def _who(user):
    return (user.get_full_name() or user.get_username()) if user and user.is_authenticated else "Team"


def _step_open(prop, number):
    return PropertyStep.objects.filter(property=prop, template__number=number).exclude(status=PropertyStep.Status.LOCKED).exists()


def _tick(prop, step, titles, user=None, note=""):
    if _step_open(prop, step):
        complete_by_title(prop, step, titles, actor=_who(user) if user else "Operations", user=user, proof_note=note)


def rooms_for(prop):
    rooms = [r.name for r in prop.bedrooms_detail.filter(is_bedroom=True)]
    if not rooms:
        rooms = [f"Bedroom {i}" for i in range(1, prop.bedrooms + 1)]
    return rooms


def default_checklist(prop):
    areas = [("Entry", COMMON_ITEMS["Entry"]), ("Kitchen", COMMON_ITEMS["Kitchen"]), ("Living", COMMON_ITEMS["Living"])]
    areas += [(room, BEDROOM_ITEMS) for room in rooms_for(prop)]
    baths = max(1, prop.bathrooms)
    areas += [("Bathroom" if baths == 1 else f"Bathroom {i}", BATHROOM_ITEMS) for i in range(1, baths + 1)]
    areas += [("Laundry", COMMON_ITEMS["Laundry"]), ("Safety", COMMON_ITEMS["Safety"])]
    return [(area, item) for area, items in areas for item in items]


# ---------- visits ----------

VISIT_FIELDS = ["date", "time", "assigned_to", "contact_email", "contact_phone", "cost", "drive_link", "notes", "status"]


@transaction.atomic
def book_visit(prop, data, user=None) -> Visit:
    kind = data.get("kind")
    if kind not in Visit.Kind.values:
        raise ValidationError("Choose what kind of visit this is.")
    if not data.get("date"):
        raise ValidationError("Pick a date.")
    v = Visit(property=prop, kind=kind)
    for f in VISIT_FIELDS:
        if f in data and f != "status":
            setattr(v, f, None if f == "cost" and data[f] in ("", None) else data[f])
    if kind == Visit.Kind.SETUP_DAY:
        v.checklist = [{"label": label, "done": False} for label in SETUP_CHECKLIST]
    v.save()
    _sync_expense(v, user)
    log(prop, f"{v.get_kind_display()} booked for {v.date}" + (f" with {v.assigned_to}" if v.assigned_to else ""), actor=_who(user), user=user)
    if kind == Visit.Kind.INSPECTION:
        _tick(prop, INSPECTION_STEP, ["Inspection booked"], user)
    elif kind == Visit.Kind.PHOTO_SHOOT:
        _tick(prop, PHOTO_STEP, ["Shoot booked"], user)
    if v.contact_email and data.get("draft_email", True):
        booking_email(v)
    return v


@transaction.atomic
def update_visit(v: Visit, data, user=None) -> Visit:
    old_status = v.status
    for f in VISIT_FIELDS:
        if f in data:
            setattr(v, f, None if f == "cost" and data[f] in ("", None) else data[f])
    if "checklist" in data and isinstance(data["checklist"], list):
        v.checklist = [{"label": str(i.get("label", ""))[:120], "done": bool(i.get("done"))} for i in data["checklist"] if i.get("label")]
    if v.status not in Visit.Status.values:
        raise ValidationError("Unknown status.")
    if v.status == Visit.Status.DONE and old_status != Visit.Status.DONE:
        v.completed_at = timezone.now()
    v.save()
    _sync_expense(v, user)
    if old_status != v.status:
        log(v.property, f"{v.get_kind_display()} {v.get_status_display().lower()}", actor=_who(user), user=user)
    _after_visit(v, user)
    return v


def _after_visit(v, user=None):
    prop = v.property
    if v.kind == Visit.Kind.SETUP_DAY:
        done = [i["label"] for i in v.checklist if i.get("done") and i["label"] in SETUP_TASKS]
        if done:
            _tick(prop, SETUP_STEP, done, user)
    if v.kind == Visit.Kind.PHOTO_SHOOT and v.drive_link:
        if v.status != Visit.Status.DONE:
            v.status, v.completed_at = Visit.Status.DONE, v.completed_at or timezone.now()
            v.save(update_fields=["status", "completed_at"])
        _tick(prop, PHOTO_STEP, ["Photos received (Drive link)"], user, note=v.drive_link)
        if not prop.drive_folder_url:
            pass  # photos live in their own folder; the listing tab imports from this link
    if v.kind == Visit.Kind.INSPECTION and v.drive_link:
        _tick(prop, INSPECTION_STEP, ["Photos saved to Drive"], user, note=v.drive_link)


def _sync_expense(v: Visit, user=None):
    """A visit with a cost is also an expense, so the cost report sees it."""
    category = {"inspection": "inspection", "photo_shoot": "photography", "setup_day": "labour",
                "repair": "repair", "delivery": "delivery"}.get(v.kind, "other")
    exp = Expense.objects.filter(visit=v).first()
    if v.cost in (None, "") or v.status == Visit.Status.CANCELLED:
        if exp:
            exp.delete()
        return
    if not exp:
        exp = Expense(property=v.property, visit=v, created_by=user if user and user.is_authenticated else None)
    exp.category, exp.amount, exp.date = category, v.cost, v.date
    exp.description = f"{v.get_kind_display()}" + (f" – {v.assigned_to}" if v.assigned_to else "")
    exp.paid_by = exp.paid_by or ""
    exp.save()


def booking_email(v: Visit):
    from agents.emails import fmt
    from agents.models import EmailDraft
    prop = v.property
    what = {"photo_shoot": "the listing photo shoot", "inspection": "the property inspection",
            "setup_day": "setup day", "repair": "the repair visit", "delivery": "the delivery"}.get(v.kind, "the visit")
    access = []
    acc = getattr(prop, "access", None)
    if acc and acc.parking_spot:
        access.append(f"Parking: spot {acc.parking_spot}")
    body = f"""Hello{f' {v.assigned_to}' if v.assigned_to else ''},

Confirming {what} at {prop.street_number} {prop.street_name}, unit {prop.unit} on {fmt(v.date)}{f' ({v.time})' if v.time else ''}.

Property reference: {prop.nickname}
{chr(10).join(access) + chr(10) if access else ''}{('Notes: ' + v.notes + chr(10)) if v.notes else ''}
{"Please share the edited photos as a Google Drive link when they're ready." if v.kind == 'photo_shoot' else "Please reply to confirm."}

Thank you,
Operations team
{settings.AGENTS['OPS_EMAIL']}
"""
    return EmailDraft.objects.create(property=prop, kind=EmailDraft.Kind.VENDOR_BOOKING, to=v.contact_email,
                                     subject=f"Booking confirmed: {what} – {prop.nickname} on {fmt(v.date)}",
                                     body=body, created_by_agent="Operations")


# ---------- inspection ----------

@transaction.atomic
def start_inspection(prop, visit=None, inspector="", inspected_on=None, user=None) -> Inspection:
    if not _step_open(prop, INSPECTION_STEP):
        raise ValidationError("Step 4 is locked. Finish admin setup (step 2) first.")
    insp = Inspection.objects.create(property=prop, visit=visit, inspector=inspector or (visit.assigned_to if visit else ""),
                                     inspected_on=inspected_on or (visit.date if visit else timezone.localdate()))
    InspectionItem.objects.bulk_create([InspectionItem(inspection=insp, area=a, item=i, order=n)
                                        for n, (a, i) in enumerate(default_checklist(prop))])
    RoomMeasurement.objects.bulk_create([RoomMeasurement(inspection=insp, room=r) for r in ["Living"] + rooms_for(prop)])
    log(prop, f"Inspection started ({insp.items.count()} items to check)", actor=_who(user), user=user)
    return insp


ITEM_FIELDS = ["condition", "action", "est_cost", "notes"]
ROOM_FIELDS = ["room", "length_ft", "width_ft", "windows", "window_width_in", "window_height_in", "notes"]


def _guard(insp):
    if insp.status == Inspection.Status.DONE:
        raise ValidationError("This report is final. Start a new inspection to change it.")


@transaction.atomic
def save_inspection(insp: Inspection, data, user=None) -> Inspection:
    _guard(insp)
    for f in ["inspector", "inspected_on", "summary", "photos_link"]:
        if f in data:
            setattr(insp, f, data[f] or (None if f == "inspected_on" else ""))
    insp.save()
    items = {i.id: i for i in insp.items.all()}
    for row in data.get("items", []):
        if row.get("id") in items:
            it = items[row["id"]]
        elif row.get("area") and row.get("item"):
            it = InspectionItem(inspection=insp, area=row["area"][:60], item=row["item"][:120], order=len(items) + 1)
        else:
            continue
        for f in ITEM_FIELDS:
            if f in row:
                setattr(it, f, None if f == "est_cost" and row[f] in ("", None) else row[f])
        it.save()
    rooms = {r.id: r for r in insp.rooms.all()}
    for row in data.get("rooms", []):
        r = rooms.get(row.get("id")) or RoomMeasurement(inspection=insp, room=(row.get("room") or "Room")[:60])
        if row.get("delete") and r.pk:
            r.delete()
            continue
        for f in ROOM_FIELDS:
            if f in row:
                setattr(r, f, (0 if f == "windows" else None) if row[f] in ("", None) and f not in ("room", "notes") else row[f])
        r.save()
    if insp.photos_link:
        _tick(insp.property, INSPECTION_STEP, ["Photos saved to Drive"], user, note=insp.photos_link)
    _tick_measured(insp, user)
    return insp


def _tick_measured(insp, user=None):
    rooms = list(insp.rooms.all())
    if rooms and all(r.length_ft and r.width_ft for r in rooms):
        _tick(insp.property, INSPECTION_STEP, ["Unit measured"], user)


@transaction.atomic
def complete_inspection(insp: Inspection, user=None, base_url="") -> Inspection:
    _guard(insp)
    unchecked = insp.items.filter(condition="").count()
    if unchecked:
        raise ValidationError(f"{unchecked} item(s) still need a condition. Mark them N/A if they don't apply.")
    insp.status, insp.completed_at = Inspection.Status.DONE, timezone.now()
    insp.save(update_fields=["status", "completed_at"])
    t = insp.totals()
    prop = insp.property
    link = f"{base_url}/api/inspections/{insp.pk}/report/"
    log(prop, f"Condition report generated: {t['issues']} issue(s), {t['actions']} action(s), est. ${t['est_cost']:.2f}", actor=_who(user), user=user)
    _tick(prop, INSPECTION_STEP, ["Condition report generated"], user, note=f"Condition report #{insp.pk}: {link}")
    _tick_measured(insp, user)
    if insp.visit and insp.visit.status == Visit.Status.BOOKED:
        insp.visit.status, insp.visit.completed_at = Visit.Status.DONE, timezone.now()
        insp.visit.save(update_fields=["status", "completed_at"])
    return insp


# ---------- costs ----------

def cost_report(prop) -> dict:
    from procurement.models import Order
    from procurement.services import summary, tracking_summary
    orders = Order.objects.filter(property=prop, status=Order.Status.APPROVED).prefetch_related("lines__store", "decor")
    purchases = {"planned": Decimal("0"), "spent": Decimal("0"), "decor": Decimal("0"), "budget": Decimal("0")}
    by_store = defaultdict(lambda: Decimal("0"))
    for o in orders:
        ts, s = tracking_summary(o), summary(o)
        purchases["planned"] += ts["planned"]
        purchases["spent"] += ts["spent"]
        purchases["decor"] += s["decor"]
        purchases["budget"] += o.budget or 0
        for l in o.lines.all():
            if l.included:
                by_store[l.store.name] += l.actual_total
    expenses = defaultdict(lambda: Decimal("0"))
    for e in prop.expenses.all():
        expenses[e.get_category_display()] += e.amount
    lic = getattr(prop, "licence", None)
    licence_fee = lic.fee if lic and lic.fee else Decimal("0")
    if licence_fee and not prop.expenses.filter(category=Expense.Category.LICENCE).exists():
        expenses["Licence / permits"] += licence_fee
    monthly = sum((u.monthly_cost or 0 for u in prop.utilities.all()), Decimal("0"))
    purchase_total = purchases["planned"] + purchases["decor"]
    expense_total = sum(expenses.values(), Decimal("0"))
    return {
        "purchases": {k: str(v) for k, v in purchases.items()},
        "by_store": {k: str(v) for k, v in sorted(by_store.items())},
        "expenses": {k: str(v) for k, v in sorted(expenses.items())},
        "purchase_total": str(purchase_total),
        "expense_total": str(expense_total),
        "total": str(purchase_total + expense_total),
        "monthly_utilities": str(monthly),
        "orders": orders.count(),
    }


def portfolio_costs():
    from properties.models import Property
    rows = []
    for p in Property.objects.all().select_related("licence").prefetch_related("expenses", "utilities"):
        c = cost_report(p)
        rows.append({"property": p.id, "nickname": p.nickname, "purchases": c["purchase_total"],
                     "expenses": c["expense_total"], "total": c["total"], "budget": c["purchases"]["budget"]})
    totals = [Decimal(r["total"]) for r in rows if Decimal(r["total"]) > 0]
    return {"rows": rows, "average": str((sum(totals) / len(totals)).quantize(Decimal("0.01")) if totals else Decimal("0"))}


# ---------- timeline ----------

def timeline_report():
    """How long each step takes (from when its prerequisite steps finished), and where each property is now."""
    from onboarding.engine import current_step, progress
    from properties.models import Property
    deps = {t.number: [d.number for d in t.depends_on.all()] for t in StepTemplate.objects.prefetch_related("depends_on")}
    durations, from_start = defaultdict(list), defaultdict(list)
    props = []
    for p in Property.objects.prefetch_related("steps__template"):
        start = p.created_at
        done = {s.template.number: s.completed_at for s in p.steps.all() if s.completed_at}
        row = {"property": p.id, "nickname": p.nickname, "progress": progress(p), "steps": {}}
        for n, at in done.items():
            prior = [done[d] for d in deps.get(n, []) if d in done]
            began = max(prior) if prior else start
            durations[n].append(max(0, (at - began).total_seconds() / 86400))
            from_start[n].append(max(0, (at - start).days))
            row["steps"][n] = max(0, (at - start).days)
        cur = current_step(p)
        row["current"] = cur.template.name if cur else "Done"
        row["days_open"] = (timezone.now() - start).days
        row["days_to_live"] = max(row["steps"].values()) if row["progress"] == 100 and row["steps"] else None
        props.append(row)
    steps = [{"number": t.number, "name": t.name, "owner": t.owner, "samples": len(durations[t.number]),
              "avg_step_days": round(mean(durations[t.number]), 1) if durations[t.number] else None,
              "avg_days": round(mean(from_start[t.number]), 1) if from_start[t.number] else None}
             for t in StepTemplate.objects.order_by("number")]
    live = [r["days_to_live"] for r in props if r["days_to_live"] is not None]
    return {"steps": steps, "properties": props, "avg_total_days": round(mean(live), 1) if live else None}


# ---------- sweeps and digest ----------

def photo_followups(now=None):
    """Draft a follow-up when the photographer hasn't sent the Drive link a few days after the shoot."""
    from agents.models import EmailDraft
    now = now or timezone.now()
    cutoff = now.date() - timedelta(days=settings.OPERATIONS["PHOTO_FOLLOWUP_DAYS"])
    out = []
    for v in Visit.objects.filter(kind=Visit.Kind.PHOTO_SHOOT, drive_link="", date__lte=cutoff, followup_sent_at__isnull=True)\
            .exclude(status=Visit.Status.CANCELLED).select_related("property"):
        if not v.contact_email:
            continue
        prop = v.property
        d = EmailDraft.objects.create(
            property=prop, kind=EmailDraft.Kind.VENDOR_FOLLOWUP, to=v.contact_email, created_by_agent="Operations",
            subject=f"Photos for {prop.nickname} ({prop.street_number} {prop.street_name} #{prop.unit})",
            body=f"""Hello{f' {v.assigned_to}' if v.assigned_to else ''},

Following up on the photo shoot on {v.date:%B} {v.date.day} at {prop.street_number} {prop.street_name}, unit {prop.unit}. Could you share the Google Drive link to the edited photos when they're ready?

Thank you,
Operations team
{settings.AGENTS['OPS_EMAIL']}
""")
        v.followup_sent_at = now
        v.save(update_fields=["followup_sent_at"])
        log(prop, "Drafted a follow-up to the photographer", actor="Operations")
        out.append(d)
    return out


def digest_data(today=None):
    from agents.models import EmailDraft
    from onboarding.engine import overall_state
    from procurement.models import OrderLine, PurchaseStatus
    from properties.models import Licence, Property
    today = today or timezone.localdate()
    props = list(Property.objects.all())
    states = defaultdict(int)
    for p in props:
        states[overall_state(p)] += 1
    blocked = [(s.property.nickname, s.template.name, s.blocked_reason) for s in
               PropertyStep.objects.filter(status=PropertyStep.Status.BLOCKED).select_related("property", "template")]
    late = OrderLine.objects.filter(purchase_status__in=[PurchaseStatus.ORDERED, PurchaseStatus.SHIPPED], expected_delivery__lt=today,
                                    order__status="approved").select_related("order__property", "store")
    visits = Visit.objects.filter(date__gte=today, date__lte=today + timedelta(days=7), status=Visit.Status.BOOKED).select_related("property")
    expiring = Licence.objects.filter(expires_on__gte=today, expires_on__lte=today + timedelta(days=30)).select_related("property")
    drafts = EmailDraft.objects.filter(status=EmailDraft.Status.DRAFT).count()
    return {"today": today, "total": len(props), "states": dict(states), "blocked": blocked,
            "late": _group_late(late),
            "visits": [(v.date, v.property.nickname, v.get_kind_display(), v.assigned_to) for v in visits],
            "expiring": [(l.property.nickname, l.expires_on) for l in expiring], "drafts": drafts}


def _group_late(lines):
    groups = defaultdict(int)
    for l in lines:
        groups[(l.order.property.nickname, l.store.name, l.expected_delivery)] += 1
    return [(nick, store, n, exp) for (nick, store, exp), n in sorted(groups.items())]


def digest_text(d):
    lines = [f"Onboarding digest for {d['today']:%A, %B} {d['today'].day}", "",
             f"{d['total']} properties: " + ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in sorted(d["states"].items()))]
    if d["drafts"]:
        lines.append(f"{d['drafts']} email draft(s) waiting for approval.")
    for title, rows, fmt in [
        ("Blocked", d["blocked"], lambda r: f"- {r[0]}: {r[1]} – {r[2]}"),
        ("Late deliveries", d["late"], lambda r: f"- {r[0]}: {r[1]} order, {r[2]} item(s), expected {r[3]}"),
        ("Visits in the next 7 days", d["visits"], lambda r: f"- {r[0]} {r[1]}: {r[2]}" + (f" ({r[3]})" if r[3] else "")),
        ("Licences expiring within 30 days", d["expiring"], lambda r: f"- {r[0]}: {r[1]}"),
    ]:
        if rows:
            lines += ["", f"{title}:"] + [fmt(r) for r in rows]
    if len(lines) <= 4 and not d["drafts"]:
        lines += ["", "Nothing needs attention today."]
    return "\n".join(lines)


def send_digest(google=None, post=None):
    """Email the digest to the ops inbox (dry-run without Google credentials) and post to Slack if configured."""
    from agents.integrations.google_workspace import GoogleWorkspace
    d = digest_data()
    body = digest_text(d)
    subject = body.splitlines()[0]
    to = settings.OPERATIONS["DIGEST_TO"] or settings.AGENTS["OPS_EMAIL"]
    res = (google or GoogleWorkspace()).send_email(to=to, subject=subject, body=body)
    out = [Notification.objects.create(kind="digest", channel="email", subject=subject, body=body, dry_run=res.dry_run)]
    hook = settings.OPERATIONS["SLACK_WEBHOOK_URL"]
    if hook:
        ok = True
        try:
            (post or requests.post)(hook, json={"text": body}, timeout=10).raise_for_status()
        except Exception:  # noqa: BLE001
            ok = False
        out.append(Notification.objects.create(kind="digest", channel="slack", subject=subject, body=body, dry_run=not ok))
    return out
