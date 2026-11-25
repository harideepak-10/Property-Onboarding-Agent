from django.conf import settings
from django.db import models

from properties.models import Property


class ListingProfile(models.Model):
    """What guests will see. Angel Host refines titles, descriptions and pricing in step 10."""

    class GuestyStatus(models.TextChoices):
        NOT_CREATED = "not_created", "Not in Guesty yet"
        CREATED = "created", "Listing created"
        PHOTOS_UPLOADED = "photos_uploaded", "Photos uploaded"

    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="listing")
    title = models.CharField(max_length=50, blank=True, help_text="Guesty requires 3–50 characters")
    neighbourhood = models.CharField(max_length=80, blank=True)
    description = models.TextField(blank=True)
    base_price = models.PositiveIntegerField(null=True, blank=True, help_text="Target nightly rate in CAD")
    cleaning_fee = models.PositiveIntegerField(null=True, blank=True)
    accommodates = models.PositiveSmallIntegerField(null=True, blank=True)
    property_type = models.CharField(max_length=40, default="Apartment")
    amenities = models.JSONField(default=list, blank=True)
    guesty_status = models.CharField(max_length=20, choices=GuestyStatus.choices, default=GuestyStatus.NOT_CREATED)
    guesty_dry_run = models.BooleanField(default=False)
    guesty_synced_at = models.DateTimeField(null=True, blank=True)
    is_listed = models.BooleanField(default=False)
    listed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Listing for {self.property.nickname}"

    def effective_title(self):
        p = self.property
        title = self.title or f"{p.bedrooms}-Bedroom {self.property_type} in {self.neighbourhood or p.city}"
        return title[:50]

    def effective_accommodates(self):
        return self.accommodates or max(1, self.property.beds * 2)


class PhotoSet(models.Model):
    class Source(models.TextChoices):
        UPLOAD = "upload", "Uploaded"
        DRIVE = "drive", "Imported from Google Drive"

    class Kind(models.TextChoices):
        INSPECTION = "inspection", "Inspection photos"
        SHOOT = "shoot", "Professional shoot"
        RESHOOT = "reshoot", "Re-shoot"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="photo_sets")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.SHOOT)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.UPLOAD)
    drive_url = models.URLField(blank=True, max_length=500)
    is_current = models.BooleanField(default=True)
    received_at = models.DateTimeField(auto_now_add=True)
    uploaded_to_guesty_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.property.nickname} · {self.get_kind_display()} · {self.received_at:%Y-%m-%d}"


class Photo(models.Model):
    ROOMS = ["Living room", "Bedroom", "Kitchen", "Bathroom", "Dining area", "View", "Balcony", "Building", "Amenity", "Other"]

    photo_set = models.ForeignKey(PhotoSet, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="photos/%Y/%m/", width_field="width", height_field="height")
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    original_name = models.CharField(max_length=255, blank=True)
    room = models.CharField(max_length=40, blank=True)
    caption = models.CharField(max_length=200, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_cover = models.BooleanField(default=False)
    drive_file_id = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-is_cover", "order", "id"]

    def __str__(self):
        return self.caption or self.original_name

    def public_url(self):
        url = self.image.url
        if url.startswith("http"):
            return url
        base = settings.LISTINGS["PUBLIC_BASE_URL"].rstrip("/")
        return f"{base}/{url.lstrip('/')}" if base else ""


class GuestyToken(models.Model):
    """Cached OAuth token: Guesty allows only 5 token requests per client per 24 hours."""
    access_token = models.TextField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-expires_at"]


class GuestGuide(models.Model):
    """Everything a guest needs to get in and settle in. Becomes the Enso Connect guidebook.

    Door/lockbox codes and the Wi-Fi password are hidden in the API unless someone
    explicitly reveals them, and every reveal is logged.
    """
    SECRET_FIELDS = ("lockbox_code", "wifi_password")

    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="guest_guide")
    check_in_time = models.CharField(max_length=20, default="3:00 pm")
    check_out_time = models.CharField(max_length=20, default="11:00 am")
    arrival_instructions = models.TextField(blank=True, help_text="Getting to the building and entering")
    buzzer_instructions = models.TextField(blank=True)
    lockbox_location = models.CharField(max_length=200, blank=True)
    lockbox_code = models.CharField(max_length=40, blank=True)
    wifi_name = models.CharField(max_length=80, blank=True)
    wifi_password = models.CharField(max_length=80, blank=True)
    parking_instructions = models.TextField(blank=True)
    garbage_instructions = models.TextField(blank=True)
    house_rules = models.TextField(blank=True, default="No parties or events. No smoking. Quiet hours 10 pm – 8 am.")
    emergency_contact = models.CharField(max_length=200, blank=True)
    local_tips = models.TextField(blank=True)
    enso_guidebook_url = models.URLField(blank=True, max_length=500)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Guest guide for {self.property.nickname}"

    def missing(self):
        need = {
            "arrival_instructions": "Arrival instructions",
            "buzzer_instructions": "Buzzer instructions",
            "lockbox_location": "Lockbox location",
            "lockbox_code": "Lockbox code",
            "wifi_name": "Wi-Fi name",
            "wifi_password": "Wi-Fi password",
            "emergency_contact": "Emergency contact",
        }
        return [label for f, label in need.items() if not getattr(self, f)]
