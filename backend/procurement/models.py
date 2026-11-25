from decimal import Decimal
from urllib.parse import quote_plus

from django.conf import settings
from django.db import models

from properties.models import Property


class Store(models.Model):
    code = models.SlugField(max_length=20, unique=True)  # amazon, walmart, ikea ...
    name = models.CharField(max_length=60)
    search_url = models.CharField(
        max_length=300, blank=True, help_text="Search URL with {q} for the query, used when an item has no product link."
    )
    color = models.CharField(max_length=9, default="#334155")
    checkout_by_client = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def link_for(self, name, product_url=""):
        if product_url:
            return product_url
        return self.search_url.replace("{q}", quote_plus(name)) if self.search_url else ""


class MasterItem(models.Model):
    class Rule(models.TextChoices):
        FIXED = "fixed", "Fixed (one per unit)"
        PER_BEDROOM = "per_bedroom", "Per bedroom"
        PER_BATHROOM = "per_bathroom", "Per bathroom"
        PER_BED = "per_bed", "Per bed"
        PER_GUEST = "per_guest", "Per guest (sleeps)"

    class Category(models.TextChoices):
        FURNITURE = "furniture", "Furniture"
        KITCHEN = "kitchen", "Kitchen"
        BATH = "bath", "Bath"
        BEDROOM = "bedroom", "Bedroom"
        LIVING = "living", "Living"
        ELECTRONICS = "electronics", "Electronics and fixtures"
        CLEANING = "cleaning", "Cleaning"

    category = models.CharField(max_length=20, choices=Category.choices)
    name = models.CharField(max_length=200)
    item_type = models.CharField(
        max_length=80, help_text="What the item counts as in the cross-check, e.g. 'kettle'. Any brand counts."
    )
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="items")
    typical_price = models.DecimalField(max_digits=9, decimal_places=2)
    rule = models.CharField(max_length=20, choices=Rule.choices, default=Rule.FIXED)
    multiplier = models.PositiveSmallIntegerField(default=1)
    bed_size = models.CharField(max_length=10, blank=True, help_text="Per-bed items only: count just beds of this size (blank = any size)")
    include_sofa_beds = models.BooleanField(default=False, help_text="Per-bed items: also count sofa beds (bedding yes, mattresses no)")
    product_url = models.URLField(blank=True, max_length=600)
    store_sku = models.CharField(max_length=60, blank=True, help_text="Amazon ASIN, Walmart item ID, etc.")
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return self.name

    def quantity_for(self, bedrooms, bathrooms=None, beds=None) -> int:
        """Pass a layout dict (see Property.layout) or the three plain counts."""
        lay = bedrooms if isinstance(bedrooms, dict) else simple_layout(bedrooms, bathrooms, beds)
        if self.rule == self.Rule.PER_BED:
            sofa_size = settings.UNIT["SOFA_BED_SIZE"]
            if self.bed_size:
                base = lay["beds_by_size"].get(self.bed_size, 0)
                if self.include_sofa_beds and self.bed_size == sofa_size:
                    base += lay.get("sofa_beds", 0)
            else:
                base = lay["beds"] + (lay.get("sofa_beds", 0) if self.include_sofa_beds else 0)
        else:
            base = {
                self.Rule.FIXED: 1,
                self.Rule.PER_BEDROOM: lay["bedrooms"],
                self.Rule.PER_BATHROOM: lay["bathrooms"],
                self.Rule.PER_GUEST: lay["sleeps"],
            }[self.rule]
        return base * self.multiplier


def simple_layout(bedrooms, bathrooms, beds, sofa_beds=0):
    size = settings.UNIT["DEFAULT_BED_SIZE"]
    per = settings.UNIT["SLEEPS_PER_BED"].get(size, 2)
    return {"bedrooms": bedrooms, "bathrooms": bathrooms, "beds": beds, "sofa_beds": sofa_beds,
            "sleeps": beds * per + sofa_beds * settings.UNIT["SLEEPS_PER_SOFA_BED"], "beds_by_size": {size: beds}}


class ItemAlternative(models.Model):
    """Pre-approved replacement used when the main product is out of stock or overpriced."""
    item = models.ForeignKey(MasterItem, on_delete=models.CASCADE, related_name="alternatives")
    name = models.CharField(max_length=200)
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="+")
    typical_price = models.DecimalField(max_digits=9, decimal_places=2)
    product_url = models.URLField(blank=True, max_length=600)
    priority = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["priority"]

    def __str__(self):
        return f"{self.name} (alt for {self.item.name})"


class Order(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Quantities calculated"
        CHECKED = "checked", "Price and stock checked"
        CARTS_BUILT = "carts_built", "Carts staged for review"
        APPROVED = "approved", "Approved and placed"

    class Kind(models.TextChoices):
        FULL = "full", "Full kit"
        TOP_UP = "top_up", "Top-up / replacement"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="orders")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.FULL)
    layout = models.JSONField(default=dict, blank=True, help_text="Snapshot of the unit layout the quantities came from")
    budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    bedrooms = models.PositiveSmallIntegerField()
    bathrooms = models.PositiveSmallIntegerField()
    beds = models.PositiveSmallIntegerField()
    checked_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.pk} for {self.property.nickname}"


class PurchaseStatus(models.TextChoices):
    TO_BUY = "to_buy", "To buy"
    ORDERED = "ordered", "Ordered"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    MISSING = "missing", "Missing"
    DAMAGED = "damaged", "Damaged"
    RETURNED = "returned", "Returned"


class OrderLine(models.Model):
    PurchaseStatus = PurchaseStatus

    class Resolution(models.TextChoices):
        NONE = "", "None"
        REPLACE = "replace", "Use replacement"
        KEEP = "keep", "Keep at this price"
        REMOVE = "remove", "Remove"

    class Source(models.TextChoices):
        MASTER = "master", "Master list"
        MANUAL = "manual", "Added by team"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    master_item = models.ForeignKey(MasterItem, null=True, blank=True, on_delete=models.SET_NULL)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MASTER)
    category = models.CharField(max_length=20, choices=MasterItem.Category.choices)
    name = models.CharField(max_length=200)
    item_type = models.CharField(max_length=80)
    store = models.ForeignKey(Store, on_delete=models.PROTECT)
    product_url = models.URLField(blank=True, max_length=600)
    quantity = models.PositiveSmallIntegerField()
    typical_price = models.DecimalField(max_digits=9, decimal_places=2)
    current_price = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    in_stock = models.BooleanField(null=True)
    flag = models.CharField(max_length=120, blank=True)
    check_note = models.CharField(max_length=200, blank=True)  # e.g. "The store blocked the automated check"
    resolution = models.CharField(max_length=10, choices=Resolution.choices, blank=True, default="")
    # Filled when the line is switched to a replacement
    replaced_from = models.CharField(max_length=200, blank=True)

    # --- purchase tracking (after approval) ---
    purchase_status = models.CharField(max_length=10, choices=PurchaseStatus.choices, default=PurchaseStatus.TO_BUY)
    store_order_number = models.CharField(max_length=80, blank=True)
    actual_unit_price = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    quantity_received = models.PositiveSmallIntegerField(null=True, blank=True)
    ordered_at = models.DateField(null=True, blank=True)
    expected_delivery = models.DateField(null=True, blank=True)
    delivered_at = models.DateField(null=True, blank=True)
    receipt = models.FileField(upload_to="receipts/%Y/%m/", blank=True)
    purchase_notes = models.CharField(max_length=300, blank=True)
    carried_over = models.BooleanField(default=False, help_text="A replacement was added to a top-up order")

    class Meta:
        ordering = ["category", "id"]

    def __str__(self):
        return f"{self.quantity} × {self.name}"

    @property
    def unit_price(self) -> Decimal:
        return self.current_price if self.current_price is not None else self.typical_price

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity

    @property
    def included(self) -> bool:
        return self.resolution != self.Resolution.REMOVE and self.quantity > 0

    @property
    def actual_total(self) -> Decimal:
        price = self.actual_unit_price if self.actual_unit_price is not None else self.unit_price
        return price * self.quantity

    @property
    def is_late(self) -> bool:
        from django.utils import timezone
        return (self.purchase_status in (PurchaseStatus.ORDERED, PurchaseStatus.SHIPPED) and self.expected_delivery is not None
                and self.expected_delivery < timezone.localdate())

    @property
    def needs_decision(self) -> bool:
        return bool(self.flag) and not self.resolution

    @property
    def link(self):
        return self.store.link_for(self.name, self.product_url)


class DecorItem(models.Model):
    """Lamps, art, throws, plants, coffee tables: picked by hand, never auto-added."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="decor")
    name = models.CharField(max_length=200)
    where = models.CharField(max_length=120, blank=True)
    price = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    quantity = models.PositiveSmallIntegerField(default=1)

    def __str__(self):
        return self.name
