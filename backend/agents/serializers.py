from rest_framework import serializers

from .models import AgentRun, AgreementDocument, Building, ComplianceItem, EmailDraft


class AgreementSerializer(serializers.ModelSerializer):
    missing = serializers.SerializerMethodField()

    class Meta:
        model = AgreementDocument
        fields = ["id", "original_name", "status", "method", "model", "extracted", "confidence", "notes", "error",
                  "property", "drive_file_url", "uploaded_at", "missing"]

    def get_missing(self, obj):
        req = ["owner_name", "street_number", "street_name", "unit", "bedrooms", "bathrooms", "lease_start", "lease_end"]
        return [k for k in req if obj.extracted.get(k) in (None, "")]


class AgentRunSerializer(serializers.ModelSerializer):
    agent_label = serializers.CharField(source="get_agent_display", read_only=True)
    property_nickname = serializers.CharField(source="property.nickname", read_only=True, default=None)

    class Meta:
        model = AgentRun
        fields = ["id", "agent", "agent_label", "property", "property_nickname", "status", "trace", "error",
                  "started_at", "finished_at"]


class EmailDraftSerializer(serializers.ModelSerializer):
    property_nickname = serializers.CharField(source="property.nickname", read_only=True)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    attachment = serializers.SerializerMethodField()

    class Meta:
        model = EmailDraft
        fields = ["id", "property", "property_nickname", "kind", "kind_label", "status", "to", "cc", "subject", "body",
                  "attach_agreement", "attachment", "warning", "created_by_agent", "created_at", "sent_at", "sent_dry_run"]
        read_only_fields = ["property", "kind", "status", "created_by_agent", "created_at", "sent_at", "sent_dry_run"]

    def get_attachment(self, obj):
        if not obj.attach_agreement:
            return None
        doc = obj.property.agreements.first()
        return doc.original_name if doc else None


class BuildingSerializer(serializers.ModelSerializer):
    units = serializers.IntegerField(source="properties.count", read_only=True)

    class Meta:
        model = Building
        fields = ["id", "name", "street_number", "street_name", "management_company", "management_email",
                  "management_phone", "registration_notes", "units"]


class ComplianceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplianceItem
        fields = ["id", "key", "label", "source", "status", "link", "note", "updated_at"]
        read_only_fields = ["key", "label", "source", "updated_at"]
