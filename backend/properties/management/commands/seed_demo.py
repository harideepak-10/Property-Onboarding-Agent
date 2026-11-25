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
        if not MasterItem.objects.exists():
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
