from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from onboarding.serializers import LicenceSerializer, PropertyDetailSerializer
from onboarding.views import actor_name, domain_errors
from properties.models import Licence, Property
from properties.services import log

from . import compliance, emails, intake
from .integrations.google_workspace import GoogleWorkspace, anthropic_status
from .models import AgentRun, AgreementDocument, Building, ComplianceItem, EmailDraft
from .serializers import (
    AgentRunSerializer, AgreementSerializer, BuildingSerializer, ComplianceItemSerializer, EmailDraftSerializer,
)

MAX_PDF = 25 * 1024 * 1024


@api_view(["GET"])
def integrations_status(request):
    from listings.views import guesty_status
    return Response({"anthropic": anthropic_status(), "google": GoogleWorkspace().status(), "guesty": guesty_status()})


class AgreementViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = AgreementDocument.objects.all()
    serializer_class = AgreementSerializer
    parser_classes = [MultiPartParser]

    def create(self, request):
        f = request.FILES.get("file")
        if not f:
            return Response({"detail": "Attach the signed agreement as a PDF."}, status=400)
        if f.size > MAX_PDF or not f.name.lower().endswith(".pdf"):
            return Response({"detail": "Upload a PDF under 25 MB."}, status=400)
        doc = AgreementDocument.objects.create(file=f, original_name=f.name, uploaded_by=request.user)
        intake.read_agreement(doc)
        return Response(AgreementSerializer(doc).data, status=201)

    @action(detail=True, methods=["post"], url_path="create-property", parser_classes=[JSONParser])
    @domain_errors
    def create_property(self, request, pk=None):
        doc = self.get_object()
        prop, run = intake.create_from_agreement(doc, request.data.get("fields") or {}, user=request.user)
        return Response({"property": PropertyDetailSerializer(prop).data, "run": AgentRunSerializer(run).data}, status=201)



class AgentRunViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AgentRunSerializer

    def get_queryset(self):
        qs = AgentRun.objects.select_related("property")
        prop = self.request.query_params.get("property")
        return qs.filter(property_id=prop) if prop else qs[:50]


@api_view(["POST"])
def run_agent(request, pk, agent):
    prop = get_object_or_404(Property, pk=pk)
    if agent == "intake":
        run = intake.run_intake(prop, user=request.user)
    elif agent == "compliance":
        run = compliance.run_compliance(prop, user=request.user)
    elif agent == "listing":
        from listings.services import run_listing
        run = run_listing(prop, user=request.user)
    else:
        return Response({"detail": "Unknown agent."}, status=404)
    return Response(AgentRunSerializer(run).data, status=201)


@api_view(["POST"])
def run_sweeps(request):
    return Response(AgentRunSerializer(compliance.run_sweeps(user=request.user)).data, status=201)


class EmailDraftViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = EmailDraftSerializer

    def get_queryset(self):
        qs = EmailDraft.objects.select_related("property")
        p = self.request.query_params
        if p.get("property"):
            qs = qs.filter(property_id=p["property"])
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        return qs

    def perform_update(self, serializer):
        if serializer.instance.status != EmailDraft.Status.DRAFT:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": "Only drafts can be edited."})
        serializer.save()

    @action(detail=True, methods=["post"])
    @domain_errors
    def send(self, request, pk=None):
        draft = emails.send(self.get_object(), user=request.user)
        return Response(EmailDraftSerializer(draft).data)

    @action(detail=True, methods=["post"])
    def discard(self, request, pk=None):
        d = self.get_object()
        if d.status == EmailDraft.Status.DRAFT:
            d.status = EmailDraft.Status.DISCARDED
            d.save(update_fields=["status"])
            log(d.property, f"Discarded draft “{d.subject}”", actor=actor_name(request.user), user=request.user)
        return Response(EmailDraftSerializer(d).data)


class BuildingViewSet(viewsets.ModelViewSet):
    queryset = Building.objects.prefetch_related("properties")
    serializer_class = BuildingSerializer

    def perform_create(self, serializer):
        b = serializer.save()
        # Link existing properties at this address
        for p in Property.objects.filter(building__isnull=True, street_number=b.street_number):
            if Building.match(p.street_number, p.street_name) == b:
                p.building = b
                p.save(update_fields=["building"])


class ComplianceItemViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = ComplianceItemSerializer

    def get_queryset(self):
        qs = ComplianceItem.objects.all()
        prop = self.request.query_params.get("property")
        return qs.filter(property_id=prop) if prop else qs

    def perform_update(self, serializer):
        item = serializer.save()
        log(item.property, f"Licence packet: {item.label} → {item.get_status_display()}",
            actor=actor_name(self.request.user), user=self.request.user)


@api_view(["GET"])
def licences(request):
    today = timezone.localdate()
    rows = []
    for lic in Licence.objects.select_related("property").order_by("expires_on"):
        p = lic.property
        items = list(p.compliance_items.all())
        rows.append({
            "property": p.id, "nickname": p.nickname, "address": p.address, **LicenceSerializer(lic).data,
            "days_left": (lic.expires_on - today).days if lic.expires_on else None,
            "packet": {"total": len(items), "ready": sum(1 for i in items if i.status in ("received", "not_needed"))},
            "unit_email": p.unit_email,
        })
    return Response(rows)
