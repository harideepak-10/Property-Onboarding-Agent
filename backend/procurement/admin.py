from django.contrib import admin

from .models import DecorItem, ItemAlternative, MasterItem, Order, OrderLine, Store


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "search_url"]


class AlternativeInline(admin.TabularInline):
    model = ItemAlternative
    extra = 0


@admin.register(MasterItem)
class MasterItemAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "item_type", "store", "typical_price", "rule", "multiplier", "is_active"]
    list_filter = ["category", "store", "rule", "is_active"]
    search_fields = ["name", "item_type"]
    inlines = [AlternativeInline]


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "property", "status", "created_at", "approved_at"]
    list_filter = ["status"]
    inlines = [OrderLineInline]


admin.site.register(DecorItem)
