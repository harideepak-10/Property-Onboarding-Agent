from datetime import timedelta
from functools import wraps

from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from properties.models import Licence, Property
from properties.services import create_property, log

from . import engine
from .models import PropertyStep, PropertyTask
from .serializers import (
    LicenceSerializer, PropertyCreateSerializer, PropertyDetailSerializer, PropertyListSerializer,
)


def actor_name(user):
    return (user.get_full_name() or user.get_username()) if user and user.is_authenticated else "Team"


def domain_errors(fn):
    """Turn business-rule errors from the services into 400 responses."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except DjangoValidationError as e:
            return Response({"detail": " ".join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)
    return wrapper


# ---------- auth ----------

@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    user = authenticate(username=request.data.get("username", ""), password=request.data.get("password", ""))
    if not user:
        return Response({"detail": "Wrong username or password."}, status=400)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user": _me(user)})


def _me(user):
    from properties.permissions import permissions_for, role_of
    return {"username": user.username, "name": actor_name(user), "role": role_of(user), "permissions": permissions_for(user)}


@api_view(["GET"])
def me(request):
    return Response(_me(request.user))


# ---------- properties ----------

class PropertyViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                      mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Property.objects.select_related("licence")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PropertyDetailSerializer
        if self.action in ("create", "update", "partial_update"):
            return PropertyCreateSerializer
        return PropertyListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            from django.db.models import Q
            qs = qs.filter(Q(nickname__icontains=q) | Q(street_name__icontains=q) | Q(owner_name__icontains=q))
        return qs

    def create(self, request, *args, **kwargs):
        ser = PropertyCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        prop = create_property(dict(ser.validated_data), user=request.user)
        return Response(PropertyDetailSerializer(prop).data, status=201)

    def update(self, request, *args, **kwargs):
        before = self.get_object()
        old = {"nickname": before.nickname, "unit_email": before.unit_email}
        super().update(request, *args, **kwargs)
        prop = self.get_object()
        if prop.nickname != old["nickname"]:
            log(prop, f"Nickname changed from {old['nickname']} to {prop.nickname}", actor=actor_name(request.user), user=request.user)
        if prop.unit_email != old["unit_email"]:
            log(prop, f"Unit email set to {prop.unit_email or '(none)'}", actor=actor_name(request.user), user=request.user)
            if prop.unit_email:
                from agents.compliance import ensure_packet, tick
                ensure_packet(prop)
                tick(prop, 3, ["Unique unit email created"], request.user, prop.unit_email)
        return Response(PropertyDetailSerializer(prop).data)

    @action(detail=True, methods=["get", "patch"])
    def licence(self, request, pk=None):
        lic = get_object_or_404(Licence, property_id=pk)
        if request.method == "PATCH":
            ser = LicenceSerializer(lic, data=request.data, partial=True)
            ser.is_valid(raise_exception=True)
            ser.save()
            log(lic.property, f"Licence updated: {lic.get_status_display()}", actor=actor_name(request.user), user=request.user)
        return Response(LicenceSerializer(lic).data)


@api_view(["POST"])
@domain_errors
def set_task(request, pk):
    task = get_object_or_404(PropertyTask.objects.select_related("step__property", "template"), pk=pk)
    unlocked = engine.set_task(
        task, bool(request.data.get("done", True)), actor=actor_name(request.user), user=request.user,
        proof_url=request.data.get("proof_url", ""), proof_note=request.data.get("proof_note", ""),
    )
    prop = task.step.property
    return Response({"unlocked": unlocked, "property": PropertyDetailSerializer(prop).data})


@api_view(["POST"])
@domain_errors
def block_step(request, pk):
    step = get_object_or_404(PropertyStep, pk=pk)
    engine.set_blocked(step, request.data.get("reason", ""), actor=actor_name(request.user), user=request.user)
    return Response(PropertyDetailSerializer(step.property).data)


@api_view(["POST"])
@domain_errors
def wait_step(request, pk):
    step = get_object_or_404(PropertyStep, pk=pk)
    engine.set_waiting(step, request.data.get("note", ""), actor=actor_name(request.user), user=request.user)
    return Response(PropertyDetailSerializer(step.property).data)


# ---------- dashboard ----------

@api_view(["GET"])
def dashboard(request):
    props = list(Property.objects.select_related("licence"))
    rows = PropertyListSerializer(props, many=True).data
    today = timezone.localdate()
    soon = today + timedelta(days=60)

    attention = []
    for r in rows:
        if r["state"] == "blocked":
            attention.append({"kind": "blocked", "property": r["id"], "nickname": r["nickname"], "text": r["needs"]})
    for p in props:
        lic = getattr(p, "licence", None)
        if lic and lic.expires_on and lic.expires_on <= soon:
            days = (lic.expires_on - today).days
            attention.append({"kind": "licence", "property": p.id, "nickname": p.nickname, "days": days,
                              "text": f"STR licence expires {lic.expires_on} ({days} days). Start renewal."})
    for r in rows:
        if r["state"] == "waiting":
            attention.append({"kind": "waiting", "property": r["id"], "nickname": r["nickname"], "text": r["needs"]})

    def stage(r):
        if r["state"] == "live":
            return "Live"
        n = (r["current_step"] or {}).get("number", 1)
        return "Admin and licence" if n <= 3 else "Inspection and setup" if n <= 7 else "Photos and listing" if n <= 10 else "Go-live prep"

    stages = ["Admin and licence", "Inspection and setup", "Photos and listing", "Go-live prep", "Live"]
    pipeline = [{"stage": s, "count": sum(1 for r in rows if stage(r) == s)} for s in stages]
    return Response({
        "kpis": {
            "onboarding": sum(1 for r in rows if r["state"] != "live"),
            "blocked": sum(1 for r in rows if r["state"] == "blocked"),
            "waiting": sum(1 for r in rows if r["state"] == "waiting"),
            "licences_expiring": sum(1 for a in attention if a["kind"] == "licence"),
            "live": sum(1 for r in rows if r["state"] == "live"),
        },
        "attention": attention,
        "pipeline": pipeline,
        "properties": rows,
        **_dashboard_extras(today),
    })


def _dashboard_extras(today):
    """Recent activity, the week's visits and purchasing totals for the dashboard."""
    from operations.models import Visit
    from procurement.models import OrderLine
    from properties.models import ActivityLog
    activity = [{"id": a.id, "property": a.property_id, "nickname": a.property.nickname, "actor": a.actor,
                 "message": a.message, "created_at": a.created_at}
                for a in ActivityLog.objects.select_related("property").exclude(actor="System")[:10]]
    visits = [{"id": v.id, "property": v.property_id, "nickname": v.property.nickname, "kind": v.kind,
               "kind_label": v.get_kind_display(), "date": v.date, "time": v.time, "assigned_to": v.assigned_to}
              for v in Visit.objects.filter(date__gte=today, date__lte=today + timedelta(days=7), status="booked")
              .select_related("property").order_by("date")[:6]]
    lines = [l for l in OrderLine.objects.filter(order__status="approved").exclude(resolution="remove") if l.quantity]
    spend = {"planned": str(sum((l.line_total for l in lines), 0)),
             "delivered": sum(1 for l in lines if l.purchase_status == "delivered"),
             "lines": len(lines), "late": sum(1 for l in lines if l.is_late)}
    return {"activity": activity, "visits": visits, "spend": spend}
