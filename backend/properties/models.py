from django.conf import settings
from django.db import models


class Property(models.Model):
    class OwnerType(models.TextChoices):
        OWNER = "owner", "Owner"
        AGENT = "agent", "Agent"

    nickname = models.CharField(max_length=40, unique=True)
    sequence = models.PositiveIntegerField(unique=True)
    city_code = models.CharField(max_length=6, default="TOR")

    street_number = models.CharField(max_length=20)
    street_name = models.CharField(max_length=120)
    unit = models.CharField(max_length=20)
    city = models.CharField(max_length=80, default="Toronto")
    postal_code = models.CharField(max_length=12, blank=True)

    owner_name = models.CharField(max_length=160)
    owner_type = models.CharField(max_length=10, choices=OwnerType.choices, default=OwnerType.OWNER)
    owner_email = models.EmailField(blank=True)
    owner_phone = models.CharField(max_length=40, blank=True)

    bedrooms = models.PositiveSmallIntegerField(default=1)
    bathrooms = models.PositiveSmallIntegerField(default=1)
    beds = models.PositiveSmallIntegerField(default=1)

    lease_start = models.DateField(null=True, blank=True)
    lease_end = models.DateField(null=True, blank=True)

    drive_folder_url = models.URLField(blank=True)
    unit_email = models.EmailField(blank=True)
    guesty_listing_id = models.CharField(max_length=60, blank=True)
    drive_folder_id = models.CharField(max_length=120, blank=True)
    building = models.ForeignKey("agents.Building", null=True, blank=True, on_delete=models.SET_NULL, related_name="properties")
    parking = models.CharField(max_length=200, blank=True)
    locker = models.CharField(max_length=200, blank=True)
    special_terms = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-sequence"]
        verbose_name_plural = "properties"

    def __str__(self):
        return self.nickname

    @property
    def address(self):
        return f"{self.street_number} {self.street_name}, Unit {self.unit}"


class Licence(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        SUBMITTED = "submitted", "Submitted"
        RETURNED = "returned", "Returned by city"
        APPROVED = "approved", "Approved"
        EXPIRED = "expired", "Expired"

    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="licence")
    number = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED)
    submitted_on = models.DateField(null=True, blank=True)
    approved_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.property.nickname} licence ({self.get_status_display()})"


class ActivityLog(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="activity")
    actor = models.CharField(max_length=80)  # e.g. "Intake agent", "Team", a user's name
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    message = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.property.nickname}: {self.message}"
