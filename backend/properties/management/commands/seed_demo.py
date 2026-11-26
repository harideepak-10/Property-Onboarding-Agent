"""Load the five sample Toronto properties from the client demo, plus a login.

    python manage.py seed_demo            # adds demo data
    python manage.py seed_demo --reset    # deletes all properties first
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

from onboarding import engine
from onboarding.models import PropertyStep, PropertyTask
from procurement.models import MasterItem
from properties.models import Property
from properties.services import create_property, log

DEMO = [
    dict(seq=37313, street_number="1080", street_name="Bay St", unit="617", owner_name="M. Fernandes", owner_type="owner",
         bedrooms=1, bathrooms=1, beds=1, lease_start=date(2026, 7, 1), lease_end=date(2027, 6, 30),
         full=[1, 2, 3, 4, 5, 6, 7, 8], partial={},
         licence=dict(number="STR-2026-104882", status="approved", expires_on=date(2027, 1, 12))),
    dict(seq=37321, street_number="270", street_name="Queens Quay W", unit="1204", owner_name="Harbourline Realty", owner_type="agent",
         bedrooms=2, bathrooms=2, beds=3, lease_start=date(2026, 11, 1), lease_end=date(2027, 10, 31),
         full=[1, 2, 4], partial={3: 2},
         waiting={3: "Licence submitted Nov 12. City review usually takes several weeks."},
         licence=dict(status="submitted", submitted_on=date(2026, 11, 12))),
    dict(seq=37328, street_number="215", street_name="Front St W", unit="2210", owner_name="D. Okafor", owner_type="owner",
         bedrooms=1, bathrooms=1, beds=1, lease_start=date(2026, 11, 15), lease_end=date(2027, 11, 14),
         full=[1, 2], partial={3: 2, 4: 1},
         blocked={3: "City returned the licence application: building consent letter is missing. Requested from property manager."},
         licence=dict(status="returned", submitted_on=date(2026, 11, 6))),
    dict(seq=37330, street_number="87", street_name="Adelaide St E", unit="905", owner_name="Northpoint Holdings", owner_type="agent",
         bedrooms=3, bathrooms=2, beds=4, lease_start=date(2026, 12, 1), lease_end=date(2027, 11, 30),
         full=[1], partial={2: 3},
         waiting={2: "Building management has not confirmed fob registration (5 days). Follow-up email drafted."},
         licence=dict(status="not_started")),
    dict(seq=37302, street_number="5", street_name="St Joseph St", unit="1802", owner_name="L. Chen", owner_type="owner",
         bedrooms=1, bathrooms=1, beds=2, lease_start=date(2026, 1, 1), lease_end=date(2026, 12, 31),
         full=list(range(1, 13)), partial={},
         licence=dict(number="STR-2025-098311", status="approved", expires_on=date(2026, 12, 15))),
]


# Fictional management contacts for the demo buildings (example.com never delivers)
BUILDINGS = [
    ("1080", "Bay St", "Bay Tower", "Crown Property Management", "office.baytower@example.com"),
    ("270", "Queens Quay W", "Harbour Residences", "Waterfront Condo Services", "frontdesk.harbour@example.com"),
    ("215", "Front St W", "Front Street Lofts", "Metro Condo Management", "mgmt.frontlofts@example.com"),
    ("87", "Adelaide St E", "Adelaide Commons", "Northline Property Group", "admin.adelaide@example.com"),
    ("460", "Spadina Ave", "The Spadina Lofts", "Harbour Property Management Ltd.", "office.spadina@example.com"),
]


class Command(BaseCommand):
    help = "Load demo properties and a demo login (ops / onboarding2026)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true")

    def handle(self, reset, **opts):
        if reset:
            Property.objects.all().delete()
        if not MasterItem.objects.exclude(bed_size="").exists():  # first run, or upgrade to the bed-size list
            call_command("import_master_list")
        User = get_user_model()
        import os
        password = os.getenv("DEMO_PASSWORD", "onboarding2026")
        if not User.objects.filter(username="ops").exists():
            User.objects.create_superuser("ops", "ops@example.com", password, first_name="Operations")
        for d in DEMO:
            if Property.objects.filter(sequence=d["seq"]).exists():
                continue
            fields = {k: d[k] for k in ("street_number", "street_name", "unit", "owner_name", "owner_type",
                                         "bedrooms", "bathrooms", "beds", "lease_start", "lease_end")}
            prop = create_property(dict(fields, sequence=d["seq"]))
            for n in d["full"]:
                PropertyTask.objects.filter(step__property=prop, step__template__number=n).update(done=True, done_by="Demo data")
            for n, count in d["partial"].items():
                ids = PropertyTask.objects.filter(step__property=prop, step__template__number=n).order_by("template__order").values_list("id", flat=True)[:count]
                PropertyTask.objects.filter(id__in=list(ids)).update(done=True, done_by="Demo data")
            for n, note in d.get("waiting", {}).items():
                PropertyStep.objects.filter(property=prop, template__number=n).update(waiting_note=note)
            for n, reason in d.get("blocked", {}).items():
                PropertyStep.objects.filter(property=prop, template__number=n).update(blocked_reason=reason)
            for k, v in d["licence"].items():
                setattr(prop.licence, k, v)
            prop.licence.save()
            engine.refresh_statuses(prop)
            log(prop, "Loaded demo data", actor="System")
        from agents.compliance import ensure_packet
        from agents.models import Building
        for num, street, name, company, email in BUILDINGS:
            b, _ = Building.objects.get_or_create(street_number=num, street_name=street, defaults={
                "name": name, "management_company": company, "management_email": email})
            Property.objects.filter(street_number=num, street_name=street, building__isnull=True).update(building=b)
        for prop in Property.objects.all():
            ensure_packet(prop)
        self._photos()
        self._guides()
        self._operations()
        self._backdate()
        self.stdout.write(self.style.SUCCESS(f"Demo ready: {Property.objects.count()} properties. Login: ops / " + ("(DEMO_PASSWORD)" if os.getenv("DEMO_PASSWORD") else "onboarding2026")))

    def _photos(self):
        """Illustrated sample photos (not real units) so the gallery and listing preview have content."""
        from pathlib import Path
        from django.utils import timezone
        from listings import services as ls
        from listings.models import ListingProfile, PhotoSet

        folder = Path(__file__).resolve().parents[3] / "listings" / "data" / "sample_photos"
        plan = {37313: ("set1", "Sleek 1-Bedroom on Bay Street with City Views", "Bay Street Corridor", 189, False),
                37302: ("set2", "Bright Yonge Street Studio Loft with Balcony", "Church-Yonge Corridor", 165, True)}
        for seq, (prefix, title, area, price, uploaded) in plan.items():
            prop = Property.objects.filter(sequence=seq).first()
            if not prop:
                continue
            if prop.photo_sets.exists():
                self._restore_files(prop, folder, prefix)
                continue
            files = [(f.name.split("-", 1)[1], f.read_bytes()) for f in sorted(folder.glob(f"{prefix}-*.jpg"))]
            order = ["living-room.jpg", "bedroom.jpg", "kitchen.jpg", "view.jpg", "bathroom.jpg", "dining-area.jpg", "building-exterior.jpg"]
            files.sort(key=lambda f: order.index(f[0]) if f[0] in order else 99)
            ps = ls.add_photos(prop, files, kind=PhotoSet.Kind.SHOOT)
            prof = ls.profile(prop)
            prof.title, prof.neighbourhood, prof.base_price = title, area, price
            if uploaded:
                ps.uploaded_to_guesty_at = timezone.now()
                ps.save(update_fields=["uploaded_to_guesty_at"])
                prop.guesty_listing_id = "dryrun-demo-yon1802"
                prop.save(update_fields=["guesty_listing_id"])
                prof.guesty_status, prof.guesty_dry_run = ListingProfile.GuestyStatus.PHOTOS_UPLOADED, True
            prof.save()

    def _guides(self):
        """Sample guest guides (fictional codes) for the live unit and the one nearing go-live."""
        from django.utils import timezone
        from listings import golive, services as ls
        from listings.models import GuestGuide

        for seq, full in ((37302, True), (37313, False)):
            prop = Property.objects.filter(sequence=seq).first()
            if not prop or GuestGuide.objects.filter(property=prop).exists():
                continue
            g = golive.guide(prop)
            g.arrival_instructions = "Enter through the main lobby on the street side. Elevators are on the left."
            g.buzzer_instructions = f"Dial {prop.unit} on the panel; it rings our team, who will let you in."
            g.wifi_name = f"Stay-{prop.unit}"
            g.emergency_contact = "Guest support: +1 416-555-0100 (24/7)"
            g.garbage_instructions = "Garbage chute is beside the elevators; recycling room on P1."
            if full:
                g.lockbox_location = "Lockbox on the railing beside the front entrance"
                g.lockbox_code = "4821"
                g.wifi_password = "sample-pass-1802"
                g.enso_guidebook_url = "https://guide.example.com/yon1802"
                lp = ls.profile(prop)
                lp.is_listed, lp.listed_at = True, timezone.now()
                lp.save(update_fields=["is_listed", "listed_at"])
            g.save()

    def _restore_files(self, prop, folder, prefix):
        """Put sample photo files back if the server's disk was reset (e.g. Render free plan)."""
        from django.core.files.storage import default_storage
        from listings.models import Photo
        # .values() avoids building Photo objects, which would try to open the missing files
        for name, original in Photo.objects.filter(photo_set__property=prop).values_list("image", "original_name"):
            if name and not default_storage.exists(name):
                src = folder / f"{prefix}-{original}"
                if src.exists():
                    with open(src, "rb") as fh:
                        default_storage.save(name, fh)

    # ---------- unit details, purchasing, visits, inspections, costs ----------

    LAYOUTS = {
        37313: ([("Bedroom", "queen", 1)], 1),
        37321: ([("Primary bedroom", "queen", 1), ("Second bedroom", "twin", 2)], 0),
        37328: ([("Bedroom", "queen", 1)], 1),
        37330: ([("Primary bedroom", "king", 1), ("Bedroom 2", "queen", 1), ("Bedroom 3", "twin", 2)], 1),
        37302: ([("Bedroom", "queen", 1), ("Den", "double", 1, False)], 0),
    }

    def _operations(self):
        from datetime import timedelta
        from decimal import Decimal

        from django.utils import timezone

        from operations import services as ops
        from operations.models import Expense, Inspection, Visit
        from procurement import services as proc
        from procurement.models import Order, PurchaseStatus
        from properties import unit
        from properties.models import Bedroom, UtilityAccount

        today = timezone.localdate()
        from operations.models import Vendor
        for name, kind, company, email, phone, rate in [
            ("Ray Thompson", "handyman", "Ray's Handyman Services", "ray@example.com", "416-555-0141", "150"),
            ("Northlight Photo", "photographer", "Northlight Photo", "bookings@example.com", "416-555-0177", "275"),
            ("Sparkle Cleaning", "cleaner", "Sparkle Cleaning Co.", "hello.sparkle@example.com", "647-555-0102", "220"),
        ]:
            Vendor.objects.get_or_create(email=email, defaults=dict(name=name, kind=kind, company=company, phone=phone, rate=Decimal(rate)))
        for prop in Property.objects.filter(sequence__in=self.LAYOUTS):
            if prop.bedrooms_detail.exists():
                continue
            rooms, sofa = self.LAYOUTS[prop.sequence]
            Bedroom.objects.bulk_create([Bedroom(property=prop, name=r[0], bed_size=r[1], beds=r[2],
                                                 is_bedroom=r[3] if len(r) > 3 else True, order=i) for i, r in enumerate(rooms)])
            prop.sofa_beds = sofa
            prop.save(update_fields=["sofa_beds"])
            step2_done = prop.steps.filter(template__number=2, status="done").exists()
            acc = unit.access_for(prop)
            acc.keys_count, acc.fob_count = 2, 2 if step2_done else 1
            acc.registered_with_building = step2_done
            acc.keys_location = "Lockbox at the office" if step2_done else ""
            if prop.sequence in (37313, 37302):
                acc.has_parking, acc.parking_spot, acc.parking_registered = True, "P2-118" if prop.sequence == 37313 else "P1-40", True
            acc.save()
            for kind, provider, cost in [("electricity", "Toronto Hydro", "68.00"), ("internet", "Rogers", "85.00"), ("water", "", None)]:
                status = ("active" if kind != "water" else "included") if step2_done else ("requested" if kind == "electricity" else "not_started")
                UtilityAccount.objects.create(property=prop, kind=kind, provider=provider, status=status,
                                              monthly_cost=Decimal(cost) if cost and step2_done else None,
                                              active_from=prop.lease_start if step2_done else None)

        def visit(prop, kind, days, **kw):
            if not Visit.objects.filter(property=prop, kind=kind).exists():
                v = Visit.objects.create(property=prop, kind=kind, date=today + timedelta(days=days), **kw)
                if kind == "setup_day":
                    v.checklist = [{"label": l, "done": kw.get("status") == "done"} for l in ops.SETUP_CHECKLIST]
                    v.save()
                ops._sync_expense(v)
                return v

        def inspection(prop, days_ago):
            if Inspection.objects.filter(property=prop).exists():
                return
            v = visit(prop, "inspection", -days_ago, assigned_to="Ray's Handyman Services", cost=Decimal("150"), status="done")
            insp = ops.start_inspection(prop, visit=v)
            items = list(insp.items.all())
            for i, it in enumerate(items):
                it.condition = "good"
                if it.item == "Caulking and grout":
                    it.condition, it.action, it.est_cost, it.notes = "fair", "repair", Decimal("80"), "Re-caulk the tub"
                if it.item == "Range hood":
                    it.condition, it.action, it.est_cost, it.notes = "poor", "repair", Decimal("120"), "Light out, filter greasy"
                if it.item == "Balcony" and prop.sequence == 37321:
                    it.condition, it.action, it.notes = "na", "", "No balcony"
                it.save()
            for n, r in enumerate(insp.rooms.all()):
                r.length_ft, r.width_ft = (Decimal("16.5"), Decimal("12")) if n == 0 else (Decimal("11"), Decimal("10.5"))
                r.windows, r.window_width_in, r.window_height_in = 1, Decimal("60"), Decimal("72")
                r.save()
            insp.summary = "Unit in good condition overall. Two small repairs before setup day."
            insp.photos_link = "https://drive.google.com/drive/folders/demo-inspection"
            insp.save()
            ops.complete_inspection(insp)

        def order(prop, delivered, problems=()):
            if Order.objects.filter(property=prop).exists():
                return
            o = proc.create_order(prop)
            for l in o.lines.all():
                l.current_price, l.in_stock = l.typical_price, True
                l.save()
            o.status = Order.Status.CARTS_BUILT
            o.save()
            proc._tick(prop, 6, ["Price and stock checked"])
            proc.approve(o)
            for l in o.lines.select_related("store"):
                if delivered == "all" or l.store.code in delivered:
                    l.purchase_status, l.delivered_at, l.quantity_received = PurchaseStatus.DELIVERED, today - timedelta(days=4), l.quantity
                    l.ordered_at = today - timedelta(days=10)
                    l.store_order_number = f"{l.store.code.upper()[:3]}-{1000 + o.pk * 7}"
                    l.actual_unit_price = l.typical_price
                elif delivered != "none":
                    l.purchase_status, l.ordered_at = PurchaseStatus.SHIPPED, today - timedelta(days=6)
                    l.expected_delivery = today - timedelta(days=1) if l.store.code == "wayfair" else today + timedelta(days=2)
                    l.store_order_number = f"{l.store.code.upper()[:3]}-{2000 + o.pk * 7}"
                if l.item_type in problems:
                    l.purchase_status, l.purchase_notes = PurchaseStatus.DAMAGED, "Arrived broken – return started"
                l.save()

        for prop in Property.objects.filter(sequence__in=self.LAYOUTS).select_related("licence"):
            seq = prop.sequence
            if seq in (37313, 37302, 37321):
                inspection(prop, 30 if seq != 37321 else 5)
            if seq == 37313:
                order(prop, "all", problems=("toaster",))
                visit(prop, "setup_day", -6, assigned_to="In-house team", cost=Decimal("400"), status="done")
                visit(prop, "photo_shoot", -3, assigned_to="Northlight Photo", contact_email="bookings@example.com",
                      cost=Decimal("275"), status="done", drive_link="https://drive.google.com/drive/folders/demo-bay617-shoot")
            if seq == 37302:
                order(prop, "all")
                visit(prop, "setup_day", -60, assigned_to="In-house team", cost=Decimal("400"), status="done")
                visit(prop, "photo_shoot", -55, assigned_to="Northlight Photo", contact_email="bookings@example.com",
                      cost=Decimal("275"), status="done", drive_link="https://drive.google.com/drive/folders/demo-yon1802-shoot")
            if seq == 37321:
                order(prop, ("ikea", "costco", "walmart"))
                visit(prop, "setup_day", 4, assigned_to="In-house team", time="10:00–16:00")
                visit(prop, "photo_shoot", 6, assigned_to="Northlight Photo", contact_email="bookings@example.com",
                      time="13:00", cost=Decimal("275"))
            if seq == 37328:
                visit(prop, "inspection", 2, assigned_to="Ray's Handyman Services", contact_email="ray@example.com", time="09:30")
            if prop.licence.status in ("approved", "submitted") and prop.licence.fee is None:
                prop.licence.fee = Decimal("1100.00")
                prop.licence.save(update_fields=["fee"])
            if seq in (37313, 37302) and not Expense.objects.filter(property=prop, visit__isnull=True).exists():
                Expense.objects.create(property=prop, category="building", description="Two extra fobs", amount=Decimal("150"),
                                       date=today - timedelta(days=40), paid_by="Company card")
                Expense.objects.create(property=prop, category="cleaning", description="Deep clean before setup",
                                       amount=Decimal("220"), date=today - timedelta(days=8), paid_by="Company card")

    # Realistic timings so the Reports page has something to show (only touches demo data created today)
    STARTED_DAYS_AGO = {37302: 70, 37313: 34, 37321: 18, 37328: 12, 37330: 6}
    STEP_DAY = {1: 0, 2: 5, 3: 24, 4: 9, 5: 17, 6: 15, 7: 21, 8: 26, 9: 28, 10: 32, 11: 27, 12: 36}

    def _backdate(self):
        from datetime import timedelta

        from django.utils import timezone
        now = timezone.now()
        for prop in Property.objects.filter(sequence__in=self.STARTED_DAYS_AGO):
            if (now - prop.created_at).days > 1:
                continue
            start = now - timedelta(days=self.STARTED_DAYS_AGO[prop.sequence])
            Property.objects.filter(pk=prop.pk).update(created_at=start)
            for step in prop.steps.select_related("template").filter(completed_at__isnull=False):
                when = min(now, start + timedelta(days=self.STEP_DAY[step.template.number]))
                PropertyStep.objects.filter(pk=step.pk).update(completed_at=when)
