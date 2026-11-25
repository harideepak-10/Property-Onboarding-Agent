import csv
import io

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from onboarding.views import domain_errors
from properties.models import Property

from . import services
from .importer import import_csv
from .models import DecorItem, MasterItem, Order, OrderLine, Store
from .serializers import MasterItemSerializer, OrderSerializer, StoreSerializer


class StoreViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Store.objects.all()
    serializer_class = StoreSerializer


class MasterItemViewSet(viewsets.ModelViewSet):
    queryset = MasterItem.objects.select_related("store").prefetch_related("alternatives__store")
    serializer_class = MasterItemSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @action(detail=False, methods=["post"], url_path="import")
    def import_file(self, request):
        f = request.FILES.get("file")
        if not f:
            return Response({"detail": "Attach a CSV file as 'file'."}, status=400)
        result = import_csv(io.TextIOWrapper(f.file, encoding="utf-8-sig"),
                            deactivate_missing=request.data.get("deactivate_missing") in ("1", "true", True))
        return Response(result, status=400 if result["errors"] else 200)


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer

    def get_queryset(self):
        qs = Order.objects.select_related("property").prefetch_related(
            "lines__store", "lines__master_item__alternatives__store", "decor")
        prop = self.request.query_params.get("property")
        return qs.filter(property_id=prop) if prop else qs

    def _out(self, order, code=200):
        order = self.get_queryset().get(pk=order.pk)
        return Response(OrderSerializer(order).data, status=code)

    @domain_errors
    def create(self, request):
        prop = get_object_or_404(Property, pk=request.data.get("property"))
        def num(k):
            v = request.data.get(k)
            return None if v in (None, "") else max(0, int(v))
        order = services.create_order(prop, num("bedrooms"), num("bathrooms"), num("beds"), user=request.user)
        return self._out(order, 201)

    @action(detail=True, methods=["post"])
    @domain_errors
    def check(self, request, pk=None):
        return self._out(services.run_check(self.get_object(), user=request.user))

    @action(detail=True, methods=["post"], url_path="build-carts")
    @domain_errors
    def build_carts(self, request, pk=None):
        return self._out(services.build_carts(self.get_object(), user=request.user))

    @action(detail=True, methods=["post"])
    @domain_errors
    def approve(self, request, pk=None):
        return self._out(services.approve(self.get_object(), user=request.user))

    @action(detail=True, methods=["post"], url_path="manual-lines")
    @domain_errors
    def manual_line(self, request, pk=None):
        order = self.get_object()
        d = request.data
        if not d.get("name") or not d.get("item_type"):
            return Response({"detail": "Name and item type are required."}, status=400)
        store = get_object_or_404(Store, code=d.get("store_code", "amazon"))
        services.add_manual_line(order, name=d["name"], item_type=d["item_type"], store=store,
                                 price=d.get("price") or 0, quantity=int(d.get("quantity") or 1),
                                 category=d.get("category") or "living", product_url=d.get("product_url", ""),
                                 user=request.user)
        return self._out(order, 201)

    @action(detail=True, methods=["post"])
    def decor(self, request, pk=None):
        order = self.get_object()
        if not request.data.get("name"):
            return Response({"detail": "Name is required."}, status=400)
        DecorItem.objects.create(order=order, name=request.data["name"], where=request.data.get("where", ""),
                                 price=request.data.get("price") or 0, quantity=int(request.data.get("quantity") or 1))
        return self._out(order, 201)

    @action(detail=True, methods=["get"], url_path="document")
    def document(self, request, pk=None):
        order = self.get_object()
        buf = io.StringIO()
        csv.writer(buf).writerows(services.order_document_rows(order))
        resp = HttpResponse(buf.getvalue(), content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="{order.property.nickname}-order-{order.pk}.csv"'
        return resp


@api_view(["POST"])
@domain_errors
def resolve_line(request, pk):
    line = get_object_or_404(OrderLine.objects.select_related("order", "master_item"), pk=pk)
    services.resolve_line(line, request.data.get("resolution", ""), user=request.user)
    return Response(OrderSerializer(line.order).data)


@api_view(["DELETE"])
@domain_errors
def delete_line(request, pk):
    line = get_object_or_404(OrderLine, pk=pk)
    if line.source != OrderLine.Source.MANUAL:
        return Response({"detail": "Only team-added lines can be deleted. Use Remove for master-list items."}, status=400)
    if line.order.status == Order.Status.APPROVED:
        return Response({"detail": "This order is already approved."}, status=400)
    order = line.order
    line.delete()
    if order.status == Order.Status.CARTS_BUILT:
        order.status = Order.Status.CHECKED
        order.save(update_fields=["status"])
    return Response(OrderSerializer(order).data)


@api_view(["DELETE"])
def delete_decor(request, pk):
    item = get_object_or_404(DecorItem, pk=pk)
    order = item.order
    item.delete()
    return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)
