from django.contrib import admin

from .models import ActivityLog, Licence, Property


class LicenceInline(admin.StackedInline):
    model = Licence
    extra = 0


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ["nickname", "street_name", "unit", "owner_name", "bedrooms", "bathrooms", "beds", "created_at"]
    search_fields = ["nickname", "street_name", "owner_name"]
    inlines = [LicenceInline]


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "property", "actor", "message"]
    list_filter = ["actor"]
    search_fields = ["message", "property__nickname"]
