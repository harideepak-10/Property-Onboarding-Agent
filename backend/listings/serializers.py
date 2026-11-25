from rest_framework import serializers

from .models import ListingProfile, Photo, PhotoSet


class PhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = Photo
        fields = ["id", "url", "width", "height", "original_name", "room", "caption", "order", "is_cover"]
        read_only_fields = ["width", "height", "original_name", "is_cover"]

    def get_url(self, obj):
        return obj.image.url


class PhotoSetSerializer(serializers.ModelSerializer):
    photos = PhotoSerializer(many=True, read_only=True)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    source_label = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = PhotoSet
        fields = ["id", "kind", "kind_label", "source", "source_label", "drive_url", "is_current", "received_at",
                  "uploaded_to_guesty_at", "photos"]


class ListingProfileSerializer(serializers.ModelSerializer):
    effective_title = serializers.CharField(read_only=True)
    effective_accommodates = serializers.IntegerField(read_only=True)
    guesty_status_label = serializers.CharField(source="get_guesty_status_display", read_only=True)

    class Meta:
        model = ListingProfile
        fields = ["title", "neighbourhood", "description", "base_price", "cleaning_fee", "accommodates", "property_type",
                  "amenities", "guesty_status", "guesty_status_label", "guesty_dry_run", "guesty_synced_at",
                  "effective_title", "effective_accommodates"]
        read_only_fields = ["guesty_status", "guesty_dry_run", "guesty_synced_at"]
