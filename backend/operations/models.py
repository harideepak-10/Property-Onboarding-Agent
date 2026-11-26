"""Site visits (inspection, setup day, photo shoot), inspection reports, and every cost per property."""
from decimal import Decimal

from django.conf import settings
from django.db import models

from properties.models import Property


class Visit(models.Model):
    class Kind(models.TextChoices):
        INSPECTION = "inspection", "Inspection"
        SETUP_DAY = "setup_day", "Setup day"
        PHOTO_SHOOT = "photo_shoot", "Photo shoot"
        DELIVERY = "delivery", "Delivery window"
        REPAIR = "repair", "Repair / handyman"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        BOOKED = "booked", "Booked"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="visits")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    date = models.DateField()
    time = models.CharField(max_length=40, blank=True, help_text="e.g. 10:00–14:00")
    assigned_to = models.CharField(max_length=120, blank=True, help_text="Person or company")
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    cost = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.BOOKED)
    drive_link = models.URLField(blank=True, max_length=600, help_text="Photos or deliverables")
    notes = models.TextField(blank=True)
    checklist = models.JSONField(default=list, blank=True, help_text="[{label, done}] for setup day")
    completed_at = models.DateTimeField(null=True, blank=True)
    followup_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "id"]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.property.nickname} · {self.date}"


class Inspection(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "In progress"
        DONE = "done", "Report generated"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="inspections")
    visit = models.OneToOneField(Visit, null=True, blank=True, on_delete=models.SET_NULL, related_name="inspection")
    inspector = models.CharField(max_length=120, blank=True)
    inspected_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    summary = models.TextField(blank=True)
    photos_link = models.URLField(blank=True, max_length=600)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Inspection {self.pk} · {self.property.nickname}"

    def totals(self):
        items = list(self.items.all())
        return {
            "items": len(items),
            "checked": sum(1 for i in items if i.condition),
            "issues": sum(1 for i in items if i.condition in ("fair", "poor", "missing")),
            "actions": sum(1 for i in items if i.action not in ("", "none")),
            "est_cost": sum((i.est_cost or Decimal("0") for i in items), Decimal("0")),
        }


class InspectionItem(models.Model):
    class Condition(models.TextChoices):
        GOOD = "good", "Good"
        FAIR = "fair", "Fair"
        POOR = "poor", "Poor"
        MISSING = "missing", "Missing"
        NA = "na", "N/A"

    class Action(models.TextChoices):
        NONE = "none", "No action"
        CLEAN = "clean", "Clean"
        REPAIR = "repair", "Repair"
        REPLACE = "replace", "Replace"
        BUY = "buy", "Buy"
        OWNER = "owner", "Ask owner"

    inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE, related_name="items")
    area = models.CharField(max_length=60)
    item = models.CharField(max_length=120)
    condition = models.CharField(max_length=8, choices=Condition.choices, blank=True)
    action = models.CharField(max_length=8, choices=Action.choices, blank=True)
    est_cost = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    notes = models.CharField(max_length=400, blank=True)
    photo = models.ImageField(upload_to="inspections/%Y/%m/", blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]


class RoomMeasurement(models.Model):
    """Room sizes in feet, windows in inches (curtains and rugs are bought from these)."""
    inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE, related_name="rooms")
    room = models.CharField(max_length=60)
    length_ft = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    width_ft = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    windows = models.PositiveSmallIntegerField(default=0)
    window_width_in = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    window_height_in = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["id"]

    @property
    def area_sqft(self):
        if self.length_ft and self.width_ft:
            return (self.length_ft * self.width_ft).quantize(Decimal("0.1"))
        return None


class Expense(models.Model):
    """Any cost that isn't a purchase line: fees, services, repairs, deposits."""

    class Category(models.TextChoices):
        LICENCE = "licence", "Licence / permits"
        INSPECTION = "inspection", "Inspection"
        REPAIR = "repair", "Repairs"
        CLEANING = "cleaning", "Cleaning"
        PHOTOGRAPHY = "photography", "Photography"
        LABOUR = "labour", "Setup labour"
        BUILDING = "building", "Building fees (fobs, parking)"
        UTILITIES = "utilities", "Utilities set-up"
        DELIVERY = "delivery", "Delivery / assembly"
        OTHER = "other", "Other"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="expenses")
    category = models.CharField(max_length=12, choices=Category.choices)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    paid_by = models.CharField(max_length=80, blank=True)
    receipt = models.FileField(upload_to="expenses/%Y/%m/", blank=True)
    visit = models.OneToOneField(Visit, null=True, blank=True, on_delete=models.SET_NULL, related_name="expense")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.property.nickname} · {self.description} · {self.amount}"


class Notification(models.Model):
    """Record of digests and alerts sent, so nothing is sent twice."""
    kind = models.CharField(max_length=30)
    channel = models.CharField(max_length=20)  # email | slack
    subject = models.CharField(max_length=200)
    body = models.TextField()
    dry_run = models.BooleanField(default=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]


class Vendor(models.Model):
    """Handymen, photographers, cleaners and other people the team books for visits."""

    class Kind(models.TextChoices):
        HANDYMAN = "handyman", "Handyman / inspector"
        PHOTOGRAPHER = "photographer", "Photographer"
        CLEANER = "cleaner", "Cleaner"
        MOVER = "mover", "Movers / assembly"
        OTHER = "other", "Other"

    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=14, choices=Kind.choices, default=Kind.OTHER)
    company = models.CharField(max_length=160, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    rate = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True, help_text="Usual price per visit")
    notes = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "name"]

    def __str__(self):
        return self.name
