from rest_framework import serializers

from properties.models import ActivityLog, Licence, Property

from . import engine
from .models import PropertyStep, PropertyTask


class LicenceSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Licence
        fields = ["number", "status", "status_label", "submitted_on", "approved_on", "expires_on", "notes"]


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLog
        fields = ["id", "actor", "message", "created_at"]


class TaskSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="template.title")
    requires_proof = serializers.BooleanField(source="template.requires_proof")

    class Meta:
        model = PropertyTask
        fields = ["id", "title", "requires_proof", "done", "done_at", "done_by", "proof_url", "proof_note"]


class StepSerializer(serializers.ModelSerializer):
    number = serializers.IntegerField(source="template.number")
    key = serializers.CharField(source="template.key")
    name = serializers.CharField(source="template.name")
    owner = serializers.CharField(source="template.owner")
    owner_kind = serializers.CharField(source="template.owner_kind")
    depends_on = serializers.SerializerMethodField()
    tasks = TaskSerializer(many=True)

    class Meta:
        model = PropertyStep
        fields = ["id", "number", "key", "name", "owner", "owner_kind", "status", "blocked_reason",
                  "waiting_note", "completed_at", "depends_on", "tasks"]

    def get_depends_on(self, obj):
        return [d.number for d in obj.template.depends_on.all()]


def step_brief(step):
    if not step:
        return None
    return {"id": step.id, "number": step.template.number, "name": step.template.name,
            "owner": step.template.owner, "status": step.status}


def needs_text(prop, cur, state):
    if state == "live":
        return "Onboarding complete"
    if cur is None:
        return ""
    if cur.status == PropertyStep.Status.BLOCKED:
        return cur.blocked_reason
    if cur.status == PropertyStep.Status.WAITING:
        return cur.waiting_note
    nxt = cur.tasks.filter(done=False).select_related("template").first()
    return f"Next: {nxt.template.title}" if nxt else ""


class PropertyListSerializer(serializers.ModelSerializer):
    address = serializers.CharField(read_only=True)
    progress = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()
    current_step = serializers.SerializerMethodField()
    needs = serializers.SerializerMethodField()
    licence = LicenceSerializer(read_only=True)
    cover_url = serializers.SerializerMethodField()
    listing_title = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = ["id", "nickname", "cover_url", "listing_title", "address", "street_number", "street_name", "unit", "city",
                  "owner_name", "owner_type", "bedrooms", "bathrooms", "beds", "lease_start", "lease_end",
                  "progress", "state", "current_step", "needs", "licence", "created_at", "step_statuses"]

    step_statuses = serializers.SerializerMethodField()

    def get_step_statuses(self, obj):
        return list(obj.steps.order_by("template__number").values_list("status", flat=True))

    def _cache(self, obj):
        if not hasattr(obj, "_summary"):
            cur = engine.current_step(obj)
            state = engine.overall_state(obj)
            obj._summary = (cur, state)
        return obj._summary

    def get_cover_url(self, obj):
        ps = obj.photo_sets.filter(is_current=True).first()
        cover = ps.photos.first() if ps else None
        return cover.image.url if cover else None

    def get_listing_title(self, obj):
        lp = getattr(obj, "listing", None) if hasattr(obj, "listing") else None
        return lp.effective_title() if lp else None

    def get_progress(self, obj):
        return engine.progress(obj)

    def get_state(self, obj):
        return self._cache(obj)[1]

    def get_current_step(self, obj):
        return step_brief(self._cache(obj)[0])

    def get_needs(self, obj):
        cur, state = self._cache(obj)
        return needs_text(obj, cur, state)


class PropertyDetailSerializer(PropertyListSerializer):
    steps = serializers.SerializerMethodField()
    activity = serializers.SerializerMethodField()
    latest_order = serializers.SerializerMethodField()

    class Meta(PropertyListSerializer.Meta):
        fields = PropertyListSerializer.Meta.fields + [
            "owner_email", "owner_phone", "postal_code", "drive_folder_url", "unit_email",
            "guesty_listing_id", "steps", "activity", "latest_order", "sofa_beds", "sleeps"]

    sleeps = serializers.SerializerMethodField()

    def get_sleeps(self, obj):
        return obj.layout()["sleeps"]

    def get_steps(self, obj):
        qs = obj.steps.select_related("template").prefetch_related("tasks__template", "template__depends_on")
        return StepSerializer(qs, many=True).data

    def get_activity(self, obj):
        return ActivitySerializer(obj.activity.all()[:40], many=True).data

    def get_latest_order(self, obj):
        o = obj.orders.first()
        return {"id": o.id, "status": o.status} if o else None


class PropertyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = ["street_number", "street_name", "unit", "city", "postal_code", "owner_name", "owner_type",
                  "owner_email", "owner_phone", "bedrooms", "bathrooms", "beds", "lease_start", "lease_end",
                  "drive_folder_url", "nickname", "unit_email"]
        extra_kwargs = {"nickname": {"required": False, "allow_blank": True, "validators": []},
                        "unit_email": {"required": False}}

    def validate_nickname(self, value):
        from django.core.exceptions import ValidationError as DjangoError

        from properties.services import clean_nickname
        if not (value or "").strip():
            if self.instance:
                raise serializers.ValidationError("The nickname can't be empty.")
            return ""
        try:
            return clean_nickname(value, exclude_pk=self.instance.pk if self.instance else None)
        except DjangoError as e:
            raise serializers.ValidationError(e.messages[0])

    def validate(self, attrs):
        if attrs.get("beds", 1) < 1:
            raise serializers.ValidationError({"beds": "A unit needs at least one bed."})
        if attrs.get("lease_start") and attrs.get("lease_end") and attrs["lease_end"] < attrs["lease_start"]:
            raise serializers.ValidationError({"lease_end": "Lease end is before lease start."})
        return attrs
