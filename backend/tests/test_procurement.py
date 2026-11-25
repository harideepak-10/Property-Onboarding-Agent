from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from onboarding import engine
from onboarding.models import PropertyStep, PropertyTask
from procurement import services
from procurement.importer import import_csv
from procurement.models import MasterItem, Order, OrderLine, Store
from properties.services import create_property


def unlocked_property(br=2, ba=2, beds=3):
    p = create_property(dict(street_number="270", street_name="Queens Quay W", unit="1204", owner_name="H",
                             bedrooms=br, bathrooms=ba, beds=beds))
    PropertyTask.objects.filter(step__property=p, step__template__number__in=[1, 2, 4]).update(done=True)
    engine.refresh_statuses(p)
    return p


class QuantityTests(TestCase):
    def test_rules(self):
        s = Store.objects.get(code="amazon")
        mk = lambda rule, mult=1: MasterItem(category="kitchen", name="x", item_type="x", store=s, typical_price=1, rule=rule, multiplier=mult)
        self.assertEqual(mk("fixed").quantity_for(3, 2, 4), 1)
        self.assertEqual(mk("per_bedroom").quantity_for(3, 2, 4), 3)
        self.assertEqual(mk("per_bathroom").quantity_for(3, 2, 4), 2)
        self.assertEqual(mk("per_bed", 2).quantity_for(3, 2, 4), 8)
        self.assertEqual(mk("per_bedroom", 2).quantity_for(0, 1, 1), 0)


class ImporterTests(TestCase):
    def test_bad_rows_import_nothing(self):
        import io
        bad = io.StringIO("category,name,item_type,store,typical_price,rule\nkitchen,Kettle,kettle,amazon,30,fixed\nkitchen,Pot,pot,nowhere,10,fixed\n")
        res = import_csv(bad)
        self.assertEqual(res["created"], 0)
        self.assertIn("unknown store", res["errors"][0])
        self.assertFalse(MasterItem.objects.exists())

    def test_reimport_updates(self):
        call_command("import_master_list", verbosity=0)
        call_command("import_master_list", verbosity=0)
        self.assertEqual(MasterItem.objects.count(), 68)


SIM = override_settings(PROCUREMENT={"OVER_PRICE_THRESHOLD": 0.25, "PRICE_CHECKER": "simulated"})


@SIM
class OrderFlowTests(TestCase):
    def setUp(self):
        call_command("import_master_list", verbosity=0)
        self.p = unlocked_property()

    def test_locked_step_6_blocks_order(self):
        p = create_property(dict(street_number="1", street_name="Bay St", unit="1", owner_name="x"))
        with self.assertRaises(ValidationError):
            services.create_order(p)

    def test_full_flow_completes_step_6(self):
        o = services.create_order(self.p)
        self.assertEqual(o.lines.get(item_type="wine glass").quantity, 6)   # 3 beds x 2
        self.assertEqual(o.lines.get(item_type="towel set").quantity, 2)    # per bedroom
        self.assertEqual(o.lines.get(item_type="shower rod").quantity, 2)   # per bathroom
        services.run_check(o)
        flagged = o.lines.exclude(flag="")
        self.assertEqual(flagged.count(), 4)
        with self.assertRaises(ValidationError):
            services.build_carts(o)
        for line in flagged:
            services.resolve_line(line, "replace")
        # Team adds a second kettle -> duplicate by type
        services.add_manual_line(o, name="Kettle (team)", item_type="Kettle", store=Store.objects.get(code="walmart"), price=Decimal("29.97"))
        services.build_carts(o)
        self.assertIn("kettle", services.cross_check(o)["duplicates"])
        with self.assertRaises(ValidationError):
            services.approve(o)
        o.lines.filter(source=OrderLine.Source.MANUAL).delete()
        o.refresh_from_db()
        services.approve(o)
        o.refresh_from_db()
        self.assertEqual(o.status, Order.Status.APPROVED)
        step6 = PropertyStep.objects.get(property=self.p, template__number=6)
        self.assertEqual(step6.status, PropertyStep.Status.DONE)
        step5 = PropertyTask.objects.get(step__property=self.p, step__template__number=5, template__title="Furniture ordered")
        self.assertTrue(step5.done)

    def test_cannot_keep_out_of_stock(self):
        o = services.create_order(self.p)
        services.run_check(o)
        oos = o.lines.get(name="12-cup coffee maker")
        with self.assertRaises(ValidationError):
            services.resolve_line(oos, "keep")

    def test_removing_required_item_shows_missing(self):
        o = services.create_order(self.p)
        services.run_check(o)
        services.resolve_line(o.lines.get(name="12-cup coffee maker"), "remove")
        self.assertIn("coffee maker", services.cross_check(o)["missing"])

    def test_amazon_cart_link_when_all_have_asins(self):
        MasterItem.objects.filter(store__code="amazon").update(store_sku="B000TEST01")
        o = services.create_order(self.p)
        services.run_check(o)
        for l in o.lines.exclude(flag=""):
            services.resolve_line(l, "remove")
        services.build_carts(o)
        amazon = [c for c in services.carts(o) if c["store"].code == "amazon"][0]
        self.assertTrue(amazon["cart_url"].startswith("https://www.amazon.ca/gp/aws/cart/add.html?ASIN.1="))


@SIM
class ProcurementApiTests(TestCase):
    def setUp(self):
        call_command("import_master_list", verbosity=0)
        get_user_model().objects.create_superuser("ops", "ops@example.com", "pw-12345678")
        self.c = APIClient()
        self.c.login(username="ops", password="pw-12345678")
        self.p = unlocked_property()

    def test_api_flow_and_document(self):
        r = self.c.post("/api/orders/", {"property": self.p.id}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        oid = r.data["id"]
        r = self.c.post(f"/api/orders/{oid}/check/")
        self.assertEqual(r.data["summary"]["flags_open"], 4)
        for line in [l for l in r.data["lines"] if l["needs_decision"]]:
            self.assertIsNotNone(line["alternative"])
            r = self.c.post(f"/api/order-lines/{line['id']}/resolve/", {"resolution": "replace"}, format="json")
        r = self.c.post(f"/api/orders/{oid}/build-carts/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["carts"])
        r = self.c.post(f"/api/orders/{oid}/approve/")
        self.assertEqual(r.data["status"], "approved")
        doc = self.c.get(f"/api/orders/{oid}/document/")
        self.assertEqual(doc["Content-Type"], "text/csv")
        self.assertIn(b"Item,Type,Qty,Store", doc.content)

    def test_master_item_import_endpoint(self):
        path = Path(__file__).resolve().parents[1] / "procurement" / "data" / "master_list_sample.csv"
        with open(path, "rb") as f:
            r = self.c.post("/api/master-items/import/", {"file": f}, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["updated"], 68)


class WebCheckerTests(TestCase):
    def _checker(self, status=200, html=""):
        from unittest import mock
        from procurement.pricing import WebPriceChecker
        s = mock.Mock()
        s.get.return_value = mock.Mock(status_code=status, ok=200 <= status < 300, text=html)
        return WebPriceChecker(session=s)

    def check(self, c, url="https://shop.example/p/1"):
        return c.check(name="Kettle", item_type="kettle", store_code="amazon", typical_price=Decimal("34.99"), product_url=url)

    def test_json_ld_product(self):
        html = """<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Kettle",
        "offers":{"@type":"Offer","price":"39.99","priceCurrency":"CAD","availability":"https://schema.org/InStock"}}</script>"""
        r = self.check(self._checker(html=html))
        self.assertEqual((r.price, r.in_stock), (Decimal("39.99"), True))

    def test_graph_and_out_of_stock(self):
        html = """<script type='application/ld+json'>{"@graph":[{"@type":"WebPage"},{"@type":"Product",
        "offers":[{"price":1299,"availability":"http://schema.org/OutOfStock"}]}]}</script>"""
        r = self.check(self._checker(html=html))
        self.assertEqual((r.price, r.in_stock), (Decimal("1299.00"), False))

    def test_meta_tags(self):
        html = '<meta property="product:price:amount" content="1,049.50"><meta property="product:availability" content="in stock">'
        r = self.check(self._checker(html=html))
        self.assertEqual((r.price, r.in_stock), (Decimal("1049.50"), True))

    def test_blocked_and_missing(self):
        self.assertIn("blocked", self.check(self._checker(status=503)).note)
        self.assertIn("No product link", self.check(self._checker(), url="").note)
        self.assertIn("not found", self.check(self._checker(html="<html></html>")).note)

    @override_settings(PROCUREMENT={"OVER_PRICE_THRESHOLD": 0.25, "PRICE_CHECKER": "web"})
    def test_unchecked_lines_do_not_block(self):
        from procurement.models import Order
        call_command("import_master_list", verbosity=0)
        p = unlocked_property()
        o = services.create_order(p)
        with self.settings(PROCUREMENT={"OVER_PRICE_THRESHOLD": 0.25, "PRICE_CHECKER": "web"}):
            services.run_check(o)  # sample list has no product links -> soft notes, no flags
        self.assertEqual(o.lines.exclude(flag="").count(), 0)
        self.assertEqual(services.summary(o)["unchecked"], o.lines.count())
        services.build_carts(o)
        self.assertEqual(Order.objects.get(pk=o.pk).status, "carts_built")
