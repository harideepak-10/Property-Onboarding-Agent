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
    product_url = models.URLField(blank=True, max_length=600)
    store_sku = models.CharField(max_length=60, blank=True, help_text="Amazon ASIN, Walmart item ID, etc.")
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return self.name

    def quantity_for(self, bedrooms: int, bathrooms: int, beds: int) -> int:
        base = {
            self.Rule.FIXED: 1,
            self.Rule.PER_BEDROOM: bedrooms,
            self.Rule.PER_BATHROOM: bathrooms,
            self.Rule.PER_BED: beds,
        }[self.rule]
        return base * self.multiplier


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

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="orders")
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


class OrderLine(models.Model):
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
