"""Unit details, purchasing tracker, visits, inspections, costs, roles and the digest."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from agents.models import EmailDraft
from onboarding import engine
from onboarding.models import PropertyTask
from operations import services as ops
from operations.models import Expense, Visit
from procurement import services as proc
from procurement.models import MasterItem, Order, PurchaseStatus, Store
from properties import unit
from properties.models import UserProfile
from properties.services import create_property

SIM = override_settings(PROCUREMENT={"OVER_PRICE_THRESHOLD": 0.25, "PRICE_CHECKER": "simulated"})


def prop_at(steps_done=(1,), br=2, ba=1, beds=3):
    p = create_property(dict(street_number="270", street_name="Queens Quay W", unit="1204", owner_name="H",
                             bedrooms=br, bathrooms=ba, beds=beds))
    PropertyTask.objects.filter(step__property=p, step__template__number__in=steps_done).update(done=True)
    engine.refresh_statuses(p)
    return p


def task_done(p, step, title):
    return PropertyTask.objects.get(step__property=p, step__template__number=step, template__title=title).done


def approved_order(p):
    o = proc.create_order(p)
    for l in o.lines.all():
        l.current_price, l.in_stock = l.typical_price, True
        l.save()
    o.status = Order.Status.CARTS_BUILT
    o.save()
    proc._tick(p, 6, ["Price and stock checked"])
    return proc.approve(o)


class LayoutRuleTests(TestCase):
    def setUp(self):
        call_command("import_master_list", verbosity=0)

    def test_bed_sizes_sofa_beds_and_per_guest(self):
        p = prop_at()
        unit.save_bedrooms(p, [{"name": "Primary", "bed_size": "queen", "beds": 1},
                               {"name": "Kids", "bed_size": "twin", "beds": 2}], sofa_beds=1)
        lay = p.layout()
        self.assertEqual((lay["bedrooms"], lay["beds"], lay["sleeps"]), (2, 3, 2 + 2 + 2))
        o = proc.create_order(p)
        q = {l.item_type: l.quantity for l in o.lines.all()}
        self.assertEqual(q["mattress (queen)"], 1)
        self.assertEqual(q["mattress (twin)"], 2)
        self.assertNotIn("mattress (double)", q)          # sofa beds get no mattress
        self.assertEqual(q["sheet set (double)"], 1)      # ...but do get double bedding
        self.assertEqual(q["pillow"], (3 + 1) * 2)        # pillows count sofa beds
        self.assertEqual(q["wine glass"], 6)              # per guest
        self.assertEqual(q["nightstand"], 4)              # per bedroom x2
        self.assertTrue(proc.cross_check(o)["ok"])

    def test_uncovered_sizes_warn(self):
        p = prop_at()
        unit.save_bedrooms(p, [{"name": "Primary", "bed_size": "king", "beds": 1}])
        o = proc.create_order(p)
        self.assertIn("No king mattress on the master list", proc.cross_check(o)["uncovered"])

    def test_studio_area_is_not_a_bedroom(self):
        p = prop_at()
        unit.save_bedrooms(p, [{"name": "Sleeping area", "bed_size": "queen", "beds": 1, "is_bedroom": False}])
        self.assertEqual((p.bedrooms, p.beds), (0, 1))


class UnitAccessTests(TestCase):
    def test_step2_ticks_from_real_data(self):
        p = prop_at()
        unit.save_access(p, {"keys_count": 2, "fob_count": 2, "registered_with_building": True, "has_parking": False})
        self.assertTrue(task_done(p, 2, "Keys and fobs registered"))
        self.assertTrue(task_done(p, 2, "Parking registered"))   # no parking = nothing to register
        self.assertFalse(task_done(p, 2, "Utilities set up"))
        unit.save_utility(p, "electricity", {"provider": "Toronto Hydro", "status": "active"})
        self.assertTrue(task_done(p, 2, "Utilities set up"))
        self.assertFalse(task_done(p, 2, "Internet set up"))
        unit.save_utility(p, "internet", {"status": "active"})
        self.assertTrue(task_done(p, 2, "Internet set up"))

    def test_parking_must_be_registered(self):
        p = prop_at()
        unit.save_access(p, {"keys_count": 1, "registered_with_building": True, "has_parking": True, "parking_spot": "P2-1"})
        self.assertFalse(task_done(p, 2, "Parking registered"))
        p.refresh_from_db()
        self.assertEqual(p.parking, "P2-1")


class PurchasingTests(TestCase):
    def setUp(self):
        call_command("import_master_list", verbosity=0)
        self.p = prop_at(steps_done=(1, 2, 4))

    def test_track_lines_and_delivery_ticks(self):
        o = approved_order(self.p)
        for store in {l.store.code for l in o.lines.all()}:
            proc.mark_store(o, store, "ordered", store_order_number="X1", expected_delivery=timezone.localdate() + timedelta(days=3))
        self.assertTrue(all(l.ordered_at for l in o.lines.all()))
        lines = list(o.lines.all())
        for l in lines[:-1]:
            proc.update_purchase(l, {"purchase_status": "delivered"})
        self.assertFalse(task_done(self.p, 7, "All deliveries received"))
        proc.update_purchase(lines[-1], {"purchase_status": "delivered", "actual_unit_price": "1.00"})
        self.assertTrue(task_done(self.p, 7, "All deliveries received"))
        self.assertTrue(task_done(self.p, 5, "Delivery confirmed"))
        t = proc.tracking_summary(o)
        self.assertTrue(t["all_delivered"])
        self.assertLess(t["spent"], t["planned"])

    def test_damaged_line_rolls_into_top_up(self):
        o = approved_order(self.p)
        kettle = o.lines.get(item_type="kettle")
        proc.update_purchase(kettle, {"purchase_status": "damaged"})
        top = proc.create_order(self.p, kind=Order.Kind.TOP_UP)
        self.assertEqual([l.item_type for l in top.lines.all()], ["kettle"])
        kettle.refresh_from_db()
        self.assertTrue(kettle.carried_over)
        self.assertTrue(proc.cross_check(top)["ok"])
        # a second top-up doesn't copy it again
        self.assertEqual(proc.create_order(self.p, kind=Order.Kind.TOP_UP).lines.count(), 0)

    def test_tracking_needs_approval(self):
        o = proc.create_order(self.p)
        with self.assertRaises(Exception):
            proc.update_purchase(o.lines.first(), {"purchase_status": "ordered"})

    def test_late_flag(self):
        o = approved_order(self.p)
        l = o.lines.first()
        proc.update_purchase(l, {"purchase_status": "shipped", "expected_delivery": timezone.localdate() - timedelta(days=1)})
        l.refresh_from_db()
        self.assertTrue(l.is_late)


class VisitInspectionTests(TestCase):
    def test_inspection_flow(self):
        p = prop_at(steps_done=(1, 2))
        v = ops.book_visit(p, {"kind": "inspection", "date": timezone.localdate(), "assigned_to": "Ray", "cost": "150",
                               "contact_email": "ray@example.com"})
        self.assertTrue(task_done(p, 4, "Inspection booked"))
        self.assertEqual(Expense.objects.get(visit=v).amount, Decimal("150"))
        self.assertTrue(EmailDraft.objects.filter(property=p, kind="vendor_booking").exists())
        insp = ops.start_inspection(p, visit=v)
        self.assertTrue(insp.items.filter(area="Bathroom", item="Toilet").exists())
        self.assertEqual(insp.rooms.count(), 1 + p.bedrooms)
        with self.assertRaises(Exception):
            ops.complete_inspection(insp)
        items = [{"id": i.id, "condition": "good"} for i in insp.items.all()]
        items[0].update(condition="poor", action="repair", est_cost="90")
        rooms = [{"id": r.id, "length_ft": "12", "width_ft": "10"} for r in insp.rooms.all()]
        ops.save_inspection(insp, {"items": items, "rooms": rooms, "photos_link": "https://drive.google.com/x"})
        self.assertTrue(task_done(p, 4, "Unit measured"))
        self.assertTrue(task_done(p, 4, "Photos saved to Drive"))
        ops.complete_inspection(insp)
        self.assertTrue(task_done(p, 4, "Condition report generated"))
        self.assertEqual(insp.totals()["est_cost"], Decimal("90"))
        v.refresh_from_db()
        self.assertEqual(v.status, "done")

    def test_setup_day_and_photo_shoot(self):
        p = prop_at(steps_done=(1, 2, 3, 4, 5, 6))
        v = ops.book_visit(p, {"kind": "setup_day", "date": timezone.localdate()})
        self.assertIn({"label": "Beds made", "done": False}, v.checklist)
        ops.update_visit(v, {"checklist": [dict(i, done=i["label"] in ("Beds made", "Assembly done")) for i in v.checklist]})
        self.assertTrue(task_done(p, 7, "Beds made"))
        self.assertFalse(task_done(p, 7, "Staging done"))
        PropertyTask.objects.filter(step__property=p, step__template__number=7).update(done=True)
        engine.refresh_statuses(p)
        shoot = ops.book_visit(p, {"kind": "photo_shoot", "date": timezone.localdate() - timedelta(days=5),
                                   "contact_email": "photo@example.com", "draft_email": False})
        self.assertTrue(task_done(p, 8, "Shoot booked"))
        self.assertEqual(len(ops.photo_followups()), 1)
        self.assertEqual(len(ops.photo_followups()), 0)   # only once
        ops.update_visit(shoot, {"drive_link": "https://drive.google.com/shoot"})
        self.assertTrue(task_done(p, 8, "Photos received (Drive link)"))

    def test_cancelled_visit_drops_expense(self):
        p = prop_at(steps_done=(1, 2))
        v = ops.book_visit(p, {"kind": "repair", "date": timezone.localdate(), "cost": "80"})
        ops.update_visit(v, {"status": "cancelled"})
        self.assertFalse(Expense.objects.filter(visit=v).exists())


class ReportTests(TestCase):
    def setUp(self):
        call_command("import_master_list", verbosity=0)

    def test_cost_report_and_timeline(self):
        p = prop_at(steps_done=(1, 2, 4))
        o = approved_order(p)
        p.licence.fee = Decimal("1100")
        p.licence.save()
        Expense.objects.create(property=p, category="cleaning", description="Clean", amount=Decimal("200"), date=timezone.localdate())
        c = ops.cost_report(p)
        self.assertEqual(Decimal(c["expense_total"]), Decimal("1300"))
        self.assertEqual(Decimal(c["purchase_total"]), proc.summary(o)["total"])
        t = ops.timeline_report()
        self.assertEqual(t["steps"][0]["samples"], 1)

    def test_digest(self):
        p = prop_at(steps_done=(1, 2))
        ops.book_visit(p, {"kind": "inspection", "date": timezone.localdate() + timedelta(days=1)})
        text = ops.digest_text(ops.digest_data())
        self.assertIn("Visits in the next 7 days", text)
        posted = []
        with override_settings(OPERATIONS={"SLACK_WEBHOOK_URL": "https://hooks.example/x", "DIGEST_TO": "", "PHOTO_FOLLOWUP_DAYS": 3}):
            class R:
                def raise_for_status(self): pass
            sent = ops.send_digest(post=lambda url, json, timeout: posted.append(json) or R())
        self.assertEqual([n.channel for n in sent], ["email", "slack"])
        self.assertTrue(sent[0].dry_run)
        self.assertEqual(len(posted), 1)


@SIM
class RoleApiTests(TestCase):
    def setUp(self):
        call_command("import_master_list", verbosity=0)
        U = get_user_model()
        self.admin = U.objects.create_superuser("boss", "b@example.com", "pw-12345678")
        self.coord = U.objects.create_user("coord", password="pw-12345678")
        self.viewer = U.objects.create_user("view", password="pw-12345678")
        UserProfile.objects.create(user=self.viewer, role="viewer")
        self.p = prop_at(steps_done=(1, 2, 4))

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def test_me_has_role(self):
        r = self.client_for(self.coord).get("/api/auth/me/")
        self.assertEqual(r.data["role"], "coordinator")
        self.assertNotIn("approve_orders", r.data["permissions"])
        self.assertIn("manage_users", self.client_for(self.admin).get("/api/auth/me/").data["permissions"])

    def test_coordinator_cannot_approve_viewer_cannot_write(self):
        c = self.client_for(self.coord)
        oid = c.post("/api/orders/", {"property": self.p.id}, format="json").data["id"]
        self.assertEqual(c.post(f"/api/orders/{oid}/approve/").status_code, 403)
        self.assertEqual(c.post("/api/master-items/", {}, format="json").status_code, 403)
        v = self.client_for(self.viewer)
        self.assertEqual(v.get(f"/api/properties/{self.p.id}/").status_code, 200)
        self.assertEqual(v.post("/api/orders/", {"property": self.p.id}, format="json").status_code, 403)

    def test_admin_manages_users(self):
        a = self.client_for(self.admin)
        r = a.post("/api/auth/users/", {"username": "new", "password": "longenough1", "role": "manager"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        r = a.patch(f"/api/auth/users/{r.data['id']}/", {"role": "viewer"}, format="json")
        self.assertEqual(r.data["role"], "viewer")
        self.assertEqual(self.client_for(self.coord).get("/api/auth/users/").status_code, 403)
        self.assertEqual(a.patch(f"/api/auth/users/{self.admin.id}/", {"role": "viewer"}, format="json").status_code, 400)

    def test_purchasing_unit_and_reports_api(self):
        a = self.client_for(self.admin)
        o = approved_order(self.p)
        line = o.lines.first()
        r = a.patch(f"/api/order-lines/{line.id}/track/", {"purchase_status": "shipped", "store_order_number": "A-1"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["purchase_status"], "shipped")
        r = a.get("/api/purchasing/", {"status": "shipped"})
        self.assertEqual(len(r.data["rows"]), 1)
        self.assertEqual(a.get("/api/purchasing/", {"export": "csv"}).status_code, 200)
        r = a.put(f"/api/properties/{self.p.id}/unit/", {"bedrooms": [{"name": "B1", "bed_size": "queen", "beds": 1}],
                                                           "access": {"keys_count": 2}, "utilities": [{"kind": "internet", "status": "active"}]},
                  format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["layout"]["beds"], 1)
        self.assertEqual(a.get(f"/api/properties/{self.p.id}/costs/").status_code, 200)
        self.assertEqual(a.get("/api/reports/").status_code, 200)
        self.assertTrue(len(a.get("/api/decisions/").data) > 10)
        r = a.post("/api/inspections/", {"property": self.p.id}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(a.get(f"/api/inspections/{r.data['id']}/report/").status_code, 200)
