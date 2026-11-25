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
    sofa_beds = models.PositiveSmallIntegerField(default=0)
    sleeps_override = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Leave blank to calculate from beds")

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

    def layout(self):
        """Everything the quantity rules need: counts, beds by size, sofa beds and sleeping capacity."""
        from django.conf import settings as s
        cfg = s.UNIT
        rooms = list(self.bedrooms_detail.all())
        by_size = {}
        for r in rooms:
            by_size[r.bed_size] = by_size.get(r.bed_size, 0) + r.beds
        if not rooms:  # older records: assume queens
            by_size = {"queen": self.beds}
        beds = sum(by_size.values())
        sleeps = self.sleeps_override or (
            sum(cfg["SLEEPS_PER_BED"].get(size, 2) * n for size, n in by_size.items())
            + cfg["SLEEPS_PER_SOFA_BED"] * self.sofa_beds)
        return {"bedrooms": self.bedrooms, "bathrooms": self.bathrooms, "beds": beds, "sofa_beds": self.sofa_beds,
                "sleeps": sleeps, "beds_by_size": by_size}


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
    fee = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
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


class Bedroom(models.Model):
    """A sleeping area and its beds. Drives bed-size-specific purchasing (twin vs queen bedding)."""

    class BedSize(models.TextChoices):
        KING = "king", "King"
        QUEEN = "queen", "Queen"
        DOUBLE = "double", "Double"
        TWIN = "twin", "Twin"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="bedrooms_detail")
    name = models.CharField(max_length=60)
    bed_size = models.CharField(max_length=10, choices=BedSize.choices, default=BedSize.QUEEN)
    beds = models.PositiveSmallIntegerField(default=1)
    is_bedroom = models.BooleanField(default=True, help_text="Off for a studio sleeping area or a den with a bed")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.property.nickname} · {self.name}"


class UnitAccess(models.Model):
    """Keys, fobs, parking and storage for a unit (step 2)."""
    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="access")
    keys_count = models.PositiveSmallIntegerField(default=0)
    fob_count = models.PositiveSmallIntegerField(default=0)
    fob_numbers = models.CharField(max_length=200, blank=True)
    mailbox_key = models.BooleanField(default=False)
    keys_location = models.CharField(max_length=200, blank=True, help_text="Where spare keys and fobs are kept")
    registered_with_building = models.BooleanField(default=False)
    has_parking = models.BooleanField(default=False)
    parking_spot = models.CharField(max_length=60, blank=True)
    parking_permit = models.CharField(max_length=60, blank=True)
    parking_registered = models.BooleanField(default=False)
    locker = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Access for {self.property.nickname}"


class UtilityAccount(models.Model):
    class Kind(models.TextChoices):
        ELECTRICITY = "electricity", "Electricity (hydro)"
        WATER = "water", "Water"
        GAS = "gas", "Gas"
        INTERNET = "internet", "Internet"
        TV = "tv", "TV / streaming"
        INSURANCE = "insurance", "Insurance"

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        REQUESTED = "requested", "Requested"
        ACTIVE = "active", "Active"
        INCLUDED = "included", "Included by building"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="utilities")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    provider = models.CharField(max_length=120, blank=True)
    account_number = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NOT_STARTED)
    active_from = models.DateField(null=True, blank=True)
    monthly_cost = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["kind"]
        unique_together = [("property", "kind")]

    def __str__(self):
        return f"{self.property.nickname} · {self.get_kind_display()}"


class UserProfile(models.Model):
    """App role. Admins manage users; managers approve; coordinators do the work; viewers read."""

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MANAGER = "manager", "Manager"
        COORDINATOR = "coordinator", "Coordinator"
        VIEWER = "viewer", "Viewer"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.COORDINATOR)

    def __str__(self):
        return f"{self.user} ({self.role})"
