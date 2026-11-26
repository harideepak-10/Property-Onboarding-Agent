import csv
import io
from datetime import date

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from onboarding.views import domain_errors
from procurement import services as proc
from procurement.models import Order, OrderLine, PurchaseStatus
from properties import unit
from properties.models import Property, UserProfile
from properties.permissions import ROLES, can

from . import services
from .models import Expense, Inspection, Notification, Vendor, Visit
from .serializers import (
    AccessSerializer, BedroomSerializer, ExpenseSerializer, InspectionSerializer, NotificationSerializer,
    UtilitySerializer, VendorSerializer, VisitSerializer,
)


# ---------- unit details (step 2) ----------

def _unit_payload(prop):
    from properties.models import UtilityAccount
    utils = {u.kind: u for u in prop.utilities.all()}
    rows = []
    for kind, label in UtilityAccount.Kind.choices:
        if kind in utils:
            rows.append(UtilitySerializer(utils[kind]).data)
        else:
            rows.append({"id": None, "kind": kind, "kind_label": label, "provider": "", "account_number": "",
                         "status": "not_started", "status_label": "Not started", "active_from": None, "monthly_cost": None, "notes": ""})
    from django.conf import settings
    return {
        "layout": prop.layout(), "sofa_beds": prop.sofa_beds, "sleeps_override": prop.sleeps_override,
        "bedrooms": BedroomSerializer(prop.bedrooms_detail.all(), many=True).data,
        "access": AccessSerializer(unit.access_for(prop)).data,
        "utilities": rows, "required_utilities": settings.UNIT["REQUIRED_UTILITIES"],
        "readiness": unit.admin_readiness(prop),
    }


@api_view(["GET", "PUT"])
@domain_errors
def unit_details(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    if request.method == "PUT":
        d = request.data
        if "bedrooms" in d:
            unit.save_bedrooms(prop, d["bedrooms"], sofa_beds=d.get("sofa_beds"),
                               sleeps_override=d.get("sleeps_override", "keep"), user=request.user)
        if "access" in d:
            unit.save_access(prop, d["access"], user=request.user)
        for row in d.get("utilities", []):
            unit.save_utility(prop, row.get("kind"), row, user=request.user)
        unit.sync_admin_tasks(prop, request.user)
        prop.refresh_from_db()
    return Response(_unit_payload(prop))


# ---------- visits ----------

class VisitViewSet(viewsets.ModelViewSet):
    serializer_class = VisitSerializer

    def get_queryset(self):
        qs = Visit.objects.select_related("property", "inspection")
        p = self.request.query_params
        if p.get("property"):
            qs = qs.filter(property_id=p["property"])
        if p.get("kind"):
            qs = qs.filter(kind=p["kind"])
        if p.get("upcoming"):
            qs = qs.filter(date__gte=date.today()).exclude(status="cancelled")
        return qs

    @domain_errors
    def create(self, request):
        prop = get_object_or_404(Property, pk=request.data.get("property"))
        v = services.book_visit(prop, request.data, user=request.user)
        return Response(VisitSerializer(v).data, status=201)

    @domain_errors
    def update(self, request, pk=None, partial=False):
        v = services.update_visit(self.get_object(), request.data, user=request.user)
        return Response(VisitSerializer(v).data)

    def partial_update(self, request, pk=None):
        return self.update(request, pk, partial=True)


# ---------- inspections ----------

class InspectionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = InspectionSerializer

    def get_queryset(self):
        qs = Inspection.objects.select_related("property").prefetch_related("items", "rooms")
        prop = self.request.query_params.get("property")
        return qs.filter(property_id=prop) if prop else qs

    @domain_errors
    def create(self, request):
        prop = get_object_or_404(Property, pk=request.data.get("property"))
        visit = Visit.objects.filter(pk=request.data.get("visit"), property=prop).first() if request.data.get("visit") else None
        insp = services.start_inspection(prop, visit=visit, inspector=request.data.get("inspector", ""), user=request.user)
        return Response(InspectionSerializer(insp).data, status=201)

    @domain_errors
    def partial_update(self, request, pk=None):
        insp = services.save_inspection(self.get_object(), request.data, user=request.user)
        return Response(InspectionSerializer(self.get_queryset().get(pk=insp.pk)).data)


InspectionViewSet.http_method_names = ["get", "post", "patch", "head", "options"]


@api_view(["POST"])
@domain_errors
def complete_inspection(request, pk):
    insp = get_object_or_404(Inspection, pk=pk)
    services.complete_inspection(insp, user=request.user, base_url=request.build_absolute_uri("/").rstrip("/"))
    return Response(InspectionSerializer(Inspection.objects.prefetch_related("items", "rooms").get(pk=pk)).data)


@api_view(["POST"])
def inspection_item_photo(request, pk, item_id):
    insp = get_object_or_404(Inspection, pk=pk)
    item = get_object_or_404(insp.items, pk=item_id)
    f = request.FILES.get("photo")
    if not f:
        return Response({"detail": "Attach a photo."}, status=400)
    item.photo.save(f.name, f, save=True)
    return Response({"photo_url": item.photo.url})


@api_view(["GET"])
def inspection_report(request, pk):
    """Printable condition report (open in a browser and print to PDF)."""
    insp = get_object_or_404(Inspection.objects.select_related("property"), pk=pk)
    areas = {}
    for it in insp.items.all():
        areas.setdefault(it.area, []).append(it)
    html = render_to_string("operations/condition_report.html", {
        "insp": insp, "prop": insp.property, "areas": areas, "rooms": insp.rooms.all(), "totals": insp.totals(),
        "issues": [i for i in insp.items.all() if i.condition in ("fair", "poor", "missing") or i.action not in ("", "none")],
    })
    return HttpResponse(html)


# ---------- expenses ----------

class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        qs = Expense.objects.select_related("property")
        prop = self.request.query_params.get("property")
        return qs.filter(property_id=prop) if prop else qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


# ---------- purchasing tracker ----------

@api_view(["PATCH"])
@domain_errors
def track_line(request, pk):
    line = get_object_or_404(OrderLine.objects.select_related("order__property", "store"), pk=pk)
    data = {k: request.data[k] for k in proc.TRACK_FIELDS if k in request.data}
    proc.update_purchase(line, data, user=request.user)
    if request.FILES.get("receipt"):
        line.receipt.save(request.FILES["receipt"].name, request.FILES["receipt"], save=True)
    return Response(proc.purchasing_rows([line])[0])


@api_view(["POST"])
@domain_errors
def mark_store(request, pk):
    order = get_object_or_404(Order, pk=pk)
    proc.mark_store(order, request.data.get("store_code", ""), request.data.get("status", ""),
                    store_order_number=request.data.get("store_order_number", ""),
                    expected_delivery=request.data.get("expected_delivery") or None, user=request.user)
    return Response({"ok": True})


def _purchasing_qs(params):
    qs = OrderLine.objects.filter(order__status=Order.Status.APPROVED).exclude(resolution="remove").exclude(quantity=0)\
        .select_related("order__property", "store").order_by("order__property__nickname", "store__name", "category", "id")
    if params.get("property"):
        qs = qs.filter(order__property_id=params["property"])
    if params.get("store"):
        qs = qs.filter(store__code=params["store"])
    if params.get("status"):
        qs = qs.filter(purchase_status__in=params["status"].split(","))
    if params.get("category"):
        qs = qs.filter(category=params["category"])
    if params.get("q"):
        qs = qs.filter(name__icontains=params["q"])
    return qs


@api_view(["GET"])
def purchasing(request):
    rows = proc.purchasing_rows(_purchasing_qs(request.query_params))
    if request.query_params.get("late"):
        rows = [r for r in rows if r["late"]]
    if request.query_params.get("export") == "csv":
        buf = io.StringIO()
        cols = ["nickname", "name", "item_type", "store_name", "quantity", "quantity_received", "unit_price", "actual_unit_price",
                "line_total", "actual_total", "purchase_status_label", "store_order_number", "ordered_at", "expected_delivery",
                "delivered_at", "notes", "link"]
        w = csv.writer(buf)
        w.writerow(["Property", "Item", "Type", "Store", "Qty", "Received", "Cart price", "Paid price", "Cart total", "Paid total",
                    "Status", "Store order #", "Ordered", "Expected", "Delivered", "Notes", "Link"])
        for r in rows:
            w.writerow([r[c] if r[c] is not None else "" for c in cols])
        resp = HttpResponse(buf.getvalue(), content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="purchasing.csv"'
        return resp
    from collections import defaultdict
    from decimal import Decimal
    by_prop = defaultdict(lambda: {"lines": 0, "planned": Decimal("0"), "spent": Decimal("0"), "delivered": 0, "late": 0, "problems": 0})
    by_store = defaultdict(lambda: {"lines": 0, "planned": Decimal("0"), "open": 0})
    counts = {s: 0 for s in PurchaseStatus.values}
    for r in rows:
        p = by_prop[r["nickname"]]
        p["property"] = r["property"]
        p["lines"] += 1
        p["planned"] += Decimal(r["line_total"])
        if r["purchase_status"] != "to_buy":
            p["spent"] += Decimal(r["actual_total"])
        p["delivered"] += r["purchase_status"] == "delivered"
        p["late"] += r["late"]
        p["problems"] += r["purchase_status"] in ("missing", "damaged", "returned")
        s = by_store[r["store_name"]]
        s["lines"] += 1
        s["planned"] += Decimal(r["line_total"])
        s["open"] += r["purchase_status"] in ("to_buy", "ordered", "shipped")
        counts[r["purchase_status"]] += 1
    fmt = lambda d: {k: (str(v) if isinstance(v, Decimal) else v) for k, v in d.items()}  # noqa: E731
    return Response({
        "rows": rows, "counts": counts, "late": sum(1 for r in rows if r["late"]),
        "by_property": [{"nickname": k, **fmt(v)} for k, v in sorted(by_prop.items())],
        "by_store": [{"store": k, **fmt(v)} for k, v in sorted(by_store.items())],
        "statuses": [{"value": v, "label": l} for v, l in PurchaseStatus.choices],
    })


# ---------- reports ----------

@api_view(["GET"])
def property_costs(request, pk):
    return Response(services.cost_report(get_object_or_404(Property, pk=pk)))


@api_view(["GET"])
def reports(request):
    from . import reports as rp
    return Response({"costs": services.portfolio_costs(), "timeline": services.timeline_report(),
                     "catalog": [{"key": k, "title": t, "about": a} for k, (t, a) in rp.REPORTS.items()],
                     "periods": [{"value": v, "label": l} for v, l in rp.PERIODS]})


@api_view(["GET"])
@domain_errors
def report(request, key):
    """One report, on screen (JSON) or downloaded with ?export=pdf|xlsx|csv."""
    from . import reports as rp
    rep = rp.make(key, request.query_params)
    kind = request.query_params.get("export")
    if kind == "pdf":
        resp = HttpResponse(rp.to_pdf(rep), content_type="application/pdf")
    elif kind == "xlsx":
        resp = HttpResponse(rp.to_xlsx(rep), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    elif kind == "csv":
        resp = HttpResponse(rp.to_csv(rep), content_type="text/csv")
    else:
        return Response(rp.to_json(rep))
    resp["Content-Disposition"] = f'attachment; filename="{rp.filename(rep, kind)}"'
    return resp


@api_view(["GET", "POST"])
def digest(request):
    if request.method == "POST":
        if not can(request.user, "send_emails"):
            return Response({"detail": "Your role doesn't allow sending the digest."}, status=403)
        sent = services.send_digest()
        return Response(NotificationSerializer(sent, many=True).data, status=201)
    return Response({"preview": services.digest_text(services.digest_data()),
                     "recent": NotificationSerializer(Notification.objects.all()[:10], many=True).data})


# ---------- users ----------

def _user_row(u):
    from properties.permissions import role_of
    return {"id": u.id, "username": u.username, "name": u.get_full_name(), "email": u.email, "role": role_of(u),
            "is_active": u.is_active, "last_login": u.last_login}


@api_view(["GET", "POST"])
def users(request):
    User = get_user_model()
    if not can(request.user, "manage_users"):
        return Response({"detail": "Only admins can manage users."}, status=403)
    if request.method == "GET":
        return Response({"users": [_user_row(u) for u in User.objects.order_by("username")], "roles": ROLES})
    d = request.data
    if not d.get("username") or not d.get("password"):
        return Response({"detail": "Username and a temporary password are required."}, status=400)
    if len(d["password"]) < 8:
        return Response({"detail": "Use at least 8 characters for the password."}, status=400)
    if User.objects.filter(username=d["username"]).exists():
        return Response({"detail": "That username is taken."}, status=400)
    role = d.get("role") if d.get("role") in ROLES else "coordinator"
    u = User.objects.create_user(username=d["username"], password=d["password"], email=d.get("email", ""),
                                 first_name=d.get("first_name", ""), last_name=d.get("last_name", ""))
    UserProfile.objects.create(user=u, role=role)
    return Response(_user_row(u), status=201)


@api_view(["PATCH"])
def user_detail(request, pk):
    User = get_user_model()
    u = get_object_or_404(User, pk=pk)
    d = request.data
    if "role" in d:
        if d["role"] not in ROLES:
            return Response({"detail": "Unknown role."}, status=400)
        if u == request.user and d["role"] != "admin":
            return Response({"detail": "You can't remove your own admin role."}, status=400)
        UserProfile.objects.update_or_create(user=u, defaults={"role": d["role"]})
    if "is_active" in d:
        if u == request.user and not d["is_active"]:
            return Response({"detail": "You can't deactivate yourself."}, status=400)
        u.is_active = bool(d["is_active"])
    if d.get("password"):
        if len(d["password"]) < 8:
            return Response({"detail": "Use at least 8 characters for the password."}, status=400)
        u.set_password(d["password"])
    for f in ["email", "first_name", "last_name"]:
        if f in d:
            setattr(u, f, d[f])
    u.save()
    u = User.objects.select_related("profile").get(pk=u.pk)
    return Response(_user_row(u))


# ---------- contacts: vendors and CSV imports ----------

class VendorViewSet(viewsets.ModelViewSet):
    serializer_class = VendorSerializer

    def get_queryset(self):
        qs = Vendor.objects.all()
        if self.request.query_params.get("kind"):
            qs = qs.filter(kind=self.request.query_params["kind"])
        if self.request.query_params.get("active"):
            qs = qs.filter(is_active=True)
        return qs


@api_view(["POST"])
def import_contacts(request, kind):
    from . import contacts
    f = request.FILES.get("file")
    if not f:
        return Response({"detail": "Attach a CSV file."}, status=400)
    fn = {"buildings": contacts.import_buildings, "vendors": contacts.import_vendors}.get(kind)
    if not fn:
        return Response({"detail": "Unknown import."}, status=404)
    result = fn(io.TextIOWrapper(f.file, encoding="utf-8-sig"))
    return Response(result, status=400 if result["errors"] else 200)
