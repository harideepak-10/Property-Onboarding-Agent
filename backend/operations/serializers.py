from rest_framework import serializers

from properties.models import Bedroom, UnitAccess, UtilityAccount

from .models import Expense, Inspection, InspectionItem, Notification, RoomMeasurement, Vendor, Visit


class BedroomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bedroom
        fields = ["id", "name", "bed_size", "beds", "is_bedroom"]


class AccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitAccess
        exclude = ["id", "property"]


class UtilitySerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = UtilityAccount
        fields = ["id", "kind", "kind_label", "provider", "account_number", "status", "status_label", "active_from", "monthly_cost", "notes"]


class VisitSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    nickname = serializers.CharField(source="property.nickname", read_only=True)
    inspection_id = serializers.SerializerMethodField()

    class Meta:
        model = Visit
        fields = ["id", "property", "nickname", "kind", "kind_label", "date", "time", "assigned_to", "contact_email", "contact_phone",
                  "cost", "status", "status_label", "drive_link", "notes", "checklist", "completed_at", "followup_sent_at", "inspection_id"]

    def get_inspection_id(self, obj):
        insp = getattr(obj, "inspection", None)
        return insp.id if insp else None


class InspectionItemSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = InspectionItem
        fields = ["id", "area", "item", "condition", "action", "est_cost", "notes", "photo_url"]

    def get_photo_url(self, obj):
        return obj.photo.url if obj.photo else ""


class RoomSerializer(serializers.ModelSerializer):
    area_sqft = serializers.DecimalField(max_digits=8, decimal_places=1, read_only=True)

    class Meta:
        model = RoomMeasurement
        fields = ["id", "room", "length_ft", "width_ft", "area_sqft", "windows", "window_width_in", "window_height_in", "notes"]


class InspectionSerializer(serializers.ModelSerializer):
    items = InspectionItemSerializer(many=True, read_only=True)
    rooms = RoomSerializer(many=True, read_only=True)
    totals = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Inspection
        fields = ["id", "property", "visit", "inspector", "inspected_on", "status", "status_label", "summary", "photos_link",
                  "completed_at", "created_at", "totals", "items", "rooms"]

    def get_totals(self, obj):
        t = obj.totals()
        t["est_cost"] = str(t["est_cost"])
        return t


class ExpenseSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    nickname = serializers.CharField(source="property.nickname", read_only=True)
    receipt_url = serializers.SerializerMethodField()
    from_visit = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = ["id", "property", "nickname", "category", "category_label", "description", "amount", "date", "paid_by",
                  "receipt", "receipt_url", "from_visit"]
        extra_kwargs = {"receipt": {"write_only": True, "required": False}}

    def get_receipt_url(self, obj):
        return obj.receipt.url if obj.receipt else ""

    def get_from_visit(self, obj):
        return bool(obj.visit_id)


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "kind", "channel", "subject", "body", "dry_run", "sent_at"]


class VendorSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    visits = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = ["id", "name", "kind", "kind_label", "company", "email", "phone", "rate", "notes", "is_active", "visits"]

    def get_visits(self, obj):
        return Visit.objects.filter(contact_email__iexact=obj.email).count() if obj.email else 0
