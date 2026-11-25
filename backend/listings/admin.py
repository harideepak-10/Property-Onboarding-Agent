from django.contrib import admin

from .models import ListingProfile, Photo, PhotoSet


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 0
    fields = ["image", "room", "caption", "order", "is_cover"]


@admin.register(PhotoSet)
class PhotoSetAdmin(admin.ModelAdmin):
    list_display = ["property", "kind", "source", "is_current", "received_at", "uploaded_to_guesty_at"]
    inlines = [PhotoInline]


@admin.register(ListingProfile)
class ListingProfileAdmin(admin.ModelAdmin):
    list_display = ["property", "title", "base_price", "guesty_status"]


from .models import GuestGuide  # noqa: E402


@admin.register(GuestGuide)
class GuestGuideAdmin(admin.ModelAdmin):
    list_display = ["property", "check_in_time", "wifi_name", "updated_at"]
    exclude = ["lockbox_code", "wifi_password"]  # view these in the app, where each reveal is logged
