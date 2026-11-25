from rest_framework import serializers

from . import services
from .models import DecorItem, ItemAlternative, MasterItem, Order, OrderLine, Store


class StoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = ["id", "code", "name", "color", "search_url"]


class AlternativeSerializer(serializers.ModelSerializer):
    store_code = serializers.SlugRelatedField(source="store", slug_field="code", queryset=Store.objects.all())

    class Meta:
        model = ItemAlternative
        fields = ["id", "name", "store_code", "typical_price", "product_url", "priority"]


class MasterItemSerializer(serializers.ModelSerializer):
    store_code = serializers.SlugRelatedField(source="store", slug_field="code", queryset=Store.objects.all())
    alternatives = AlternativeSerializer(many=True, read_only=True)
    rule_label = serializers.CharField(source="get_rule_display", read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = MasterItem
        fields = ["id", "category", "category_label", "name", "item_type", "store_code", "typical_price", "rule",
                  "rule_label", "multiplier", "product_url", "store_sku", "is_active", "notes", "alternatives"]

    def validate_item_type(self, v):
        return v.strip().lower()


class OrderLineSerializer(serializers.ModelSerializer):
    store_code = serializers.CharField(source="store.code", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    unit_price = serializers.DecimalField(max_digits=9, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=11, decimal_places=2, read_only=True)
    needs_decision = serializers.BooleanField(read_only=True)
    included = serializers.BooleanField(read_only=True)
    link = serializers.CharField(read_only=True)
    rule = serializers.SerializerMethodField()
    alternative = serializers.SerializerMethodField()

    class Meta:
        model = OrderLine
        fields = ["id", "source", "category", "name", "item_type", "store_code", "store_name", "link", "quantity",
                  "typical_price", "current_price", "unit_price", "line_total", "in_stock", "flag", "check_note", "resolution",
                  "replaced_from", "needs_decision", "included", "rule", "alternative"]

    def get_rule(self, obj):
        it = obj.master_item
        return {"rule": it.rule, "label": it.get_rule_display(), "multiplier": it.multiplier} if it else None

    def get_alternative(self, obj):
        if not obj.needs_decision or not obj.master_item:
            return None
        alt = obj.master_item.alternatives.select_related("store").first()
        return {"name": alt.name, "store": alt.store.name, "price": str(alt.typical_price)} if alt else None


class DecorSerializer(serializers.ModelSerializer):
    class Meta:
        model = DecorItem
        fields = ["id", "name", "where", "price", "quantity"]


class OrderSerializer(serializers.ModelSerializer):
    property_nickname = serializers.CharField(source="property.nickname", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    lines = OrderLineSerializer(many=True, read_only=True)
    decor = DecorSerializer(many=True, read_only=True)
    summary = serializers.SerializerMethodField()
    cross_check = serializers.SerializerMethodField()
    carts = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["id", "property", "property_nickname", "status", "status_label", "bedrooms", "bathrooms", "beds",
                  "checked_at", "approved_at", "created_at", "summary", "cross_check", "carts", "lines", "decor"]
        read_only_fields = ["status", "checked_at", "approved_at", "created_at"]

    def get_summary(self, obj):
        return {k: (str(v) if not isinstance(v, int) else v) for k, v in services.summary(obj).items()}

    def get_cross_check(self, obj):
        return services.cross_check(obj) if obj.status != Order.Status.DRAFT else None

    def get_carts(self, obj):
        if obj.status not in (Order.Status.CARTS_BUILT, Order.Status.APPROVED):
            return []
        return [{"store_code": c["store"].code, "store_name": c["store"].name, "color": c["store"].color,
                 "total": str(c["total"]), "cart_url": c["cart_url"], "line_ids": [l.id for l in c["lines"]]}
                for c in services.carts(obj)]
