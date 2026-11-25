from django.conf import settings
from django.db import models

from properties.models import Licence, Property


class Building(models.Model):
    """A condo building and its management office: who gets the lease and registration forms."""
    name = models.CharField(max_length=160, blank=True)
    street_number = models.CharField(max_length=20)
    street_name = models.CharField(max_length=120)
    management_company = models.CharField(max_length=160, blank=True)
    management_email = models.EmailField(blank=True)
    management_phone = models.CharField(max_length=40, blank=True)
    registration_notes = models.TextField(
        blank=True, help_text="What this building needs: forms, fob fees, parking rules, move-in booking…")

    class Meta:
        ordering = ["street_name", "street_number"]
        unique_together = [("street_number", "street_name")]

    def __str__(self):
        return self.name or f"{self.street_number} {self.street_name}"

    @classmethod
    def match(cls, street_number, street_name):
        norm = lambda s: " ".join(s.lower().replace(".", "").split())
        for b in cls.objects.filter(street_number=street_number.strip()):
            if norm(b.street_name) == norm(street_name):
                return b
        return None


class AgreementDocument(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        EXTRACTED = "extracted", "Read"
        FAILED = "failed", "Could not read"
        APPLIED = "applied", "Property created"

    file = models.FileField(upload_to="agreements/%Y/%m/")
    original_name = models.CharField(max_length=255)
    property = models.ForeignKey(Property, null=True, blank=True, on_delete=models.SET_NULL, related_name="agreements")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UPLOADED)
    method = models.CharField(max_length=20, blank=True)  # claude | heuristic
    model = models.CharField(max_length=60, blank=True)
    extracted = models.JSONField(default=dict, blank=True)
    confidence = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    error = models.TextField(blank=True)
    drive_file_url = models.URLField(blank=True, max_length=500)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.original_name


class AgentRun(models.Model):
    """One run of an agent, with a step-by-step trace the UI plays back."""

    class Agent(models.TextChoices):
        INTAKE = "intake", "Intake agent"
        COMPLIANCE = "compliance", "Compliance agent"
        LISTING = "listing", "Listing agent"
        GO_LIVE = "go_live", "Go-live"
        REMINDERS = "reminders", "Reminder sweep"

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Finished"
        PARTIAL = "partial", "Finished with warnings"
        FAILED = "failed", "Failed"

    agent = models.CharField(max_length=20, choices=Agent.choices)
    property = models.ForeignKey(Property, null=True, blank=True, on_delete=models.CASCADE, related_name="agent_runs")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RUNNING)
    trace = models.JSONField(default=list, blank=True)  # [{label, status: ok|warn|error|skip, detail, dry_run}]
    error = models.TextField(blank=True)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.get_agent_display()} · {self.property or 'all'} · {self.status}"

    def add(self, label, status="ok", detail="", dry_run=False):
        self.trace = [*self.trace, {"label": label, "status": status, "detail": detail, "dry_run": dry_run}]
        self.save(update_fields=["trace"])


class EmailDraft(models.Model):
    class Kind(models.TextChoices):
        BUILDING_REGISTRATION = "building_registration", "Building registration"
        BUILDING_FOLLOWUP = "building_followup", "Building follow-up"
        OWNER_DOCUMENTS = "owner_documents", "Documents needed from owner"
        LICENCE_RENEWAL = "licence_renewal", "Licence renewal reminder"
        ANGEL_HOST = "angel_host", "Ready to optimize (Angel Host)"
        VENDOR_BOOKING = "vendor_booking", "Booking confirmation (vendor)"
        VENDOR_FOLLOWUP = "vendor_followup", "Follow-up (vendor)"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        DRAFT = "draft", "Needs review"
        SENT = "sent", "Sent"
        DISCARDED = "discarded", "Discarded"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="email_drafts")
    kind = models.CharField(max_length=30, choices=Kind.choices, default=Kind.OTHER)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    to = models.CharField(max_length=500, blank=True)
    cc = models.CharField(max_length=500, blank=True)
    subject = models.CharField(max_length=250)
    body = models.TextField()
    attach_agreement = models.BooleanField(default=False)
    warning = models.CharField(max_length=300, blank=True)  # e.g. "No email on file for this building"
    created_by_agent = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    sent_dry_run = models.BooleanField(default=False)
    message_id = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.property.nickname}: {self.subject}"


class LicenceReminder(models.Model):
    """Records each reminder so a licence never gets the same reminder twice."""
    licence = models.ForeignKey(Licence, on_delete=models.CASCADE, related_name="reminders")
    days_before = models.IntegerField()
    expires_on = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("licence", "days_before", "expires_on")]


class ComplianceItem(models.Model):
    """One document or prerequisite in a unit's licence packet."""

    class Status(models.TextChoices):
        MISSING = "missing", "Missing"
        REQUESTED = "requested", "Requested"
        RECEIVED = "received", "Received"
        NOT_NEEDED = "not_needed", "Not needed"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="compliance_items")
    key = models.SlugField(max_length=40)
    label = models.CharField(max_length=200)
    source = models.CharField(max_length=20, default="owner")  # owner | building | system | team
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.MISSING)
    link = models.URLField(blank=True, max_length=500)
    note = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        unique_together = [("property", "key")]

    def __str__(self):
        return f"{self.property.nickname}: {self.label} ({self.status})"
