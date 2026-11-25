import io
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from agents import emails
from agents.models import AgentRun, EmailDraft
from listings import services
from listings.guesty import Guesty, listing_payload
from listings.models import GuestyToken, PhotoSet
from onboarding.engine import refresh_statuses
from onboarding.models import PropertyStep, PropertyTask
from properties.services import create_property

LISTINGS = dict(GUESTY_CLIENT_ID="", GUESTY_CLIENT_SECRET="", GUESTY_BASE_URL="https://open-api.guesty.com",
                PUBLIC_BASE_URL="", ANGEL_HOST_EMAIL="ops@angelhost.example", MIN_PHOTOS=5, DEFAULT_BASE_PRICE=150,
                CURRENCY="CAD", TIMEZONE="America/Toronto")


def jpg(name="living-room.jpg", color=(120, 160, 150)):
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buf, "JPEG")
    return (name, buf.getvalue())


def ready_property(upto=7):
    p = create_property(dict(street_number="1080", street_name="Bay St", unit="617", owner_name="M. F",
                             bedrooms=1, bathrooms=1, beds=1, postal_code="M5S 2B4"))
    PropertyTask.objects.filter(step__property=p, step__template__number__lte=upto).update(done=True)
    refresh_statuses(p)
    return p


def done(p, step, title):
    return PropertyTask.objects.get(step__property=p, step__template__number=step, template__title=title).done


@override_settings(LISTINGS=LISTINGS, MEDIA_ROOT="/tmp/test-media")
class PhotoTests(TestCase):
    def setUp(self):
        self.p = ready_property()

    def test_upload_guesses_rooms_and_cover(self):
        ps = services.add_photos(self.p, [jpg("01_kitchen.jpg"), jpg("bedroom-2.jpg"), jpg("IMG_0003.jpg")])
        photos = services.ordered(ps)
        self.assertEqual(photos[0].room, "Kitchen")
        self.assertTrue(photos[0].is_cover)
        self.assertEqual([x.room for x in photos], ["Kitchen", "Bedroom", ""])
        self.assertEqual(photos[0].width, 64)

    def test_reshoot_starts_new_set(self):
        a = services.add_photos(self.p, [jpg()])
        b = services.add_photos(self.p, [jpg()], kind="reshoot", new_set=True)
        a.refresh_from_db()
        self.assertFalse(a.is_current)
        self.assertEqual(services.current_set(self.p), b)

    def test_rejects_non_images(self):
        with self.assertRaises(ValidationError):
            services.add_photos(self.p, [("notes.pdf", b"%PDF")])

    def test_cover_and_reorder(self):
        ps = services.add_photos(self.p, [jpg("a.jpg"), jpg("b.jpg"), jpg("c.jpg")])
        a, b, c = services.ordered(ps)
        services.set_cover(c)
        services.reorder(ps, [b.id, a.id])
        self.assertEqual([x.original_name for x in services.ordered(ps)], ["c.jpg", "b.jpg", "a.jpg"])

    def test_drive_import_dry_run_explains(self):
        with self.assertRaises(ValidationError) as e:
            services.import_from_drive(self.p, "https://drive.google.com/drive/folders/abc123XYZ")
        self.assertIn("dry-run", str(e.exception))
        with self.assertRaises(ValidationError):
            services.import_from_drive(self.p, "https://example.com/not-drive")


@override_settings(LISTINGS=LISTINGS, MEDIA_ROOT="/tmp/test-media")
class ListingAgentTests(TestCase):
    def test_full_dry_run(self):
        p = ready_property()
        services.add_photos(p, [jpg(f"photo{i}.jpg") for i in range(5)])
        run = services.run_listing(p)
        self.assertEqual(run.status, AgentRun.Status.SUCCEEDED, run.trace)
        p.refresh_from_db()
        self.assertTrue(p.guesty_listing_id.startswith("dryrun-"))
        self.assertEqual(PropertyStep.objects.get(property=p, template__number=8).status, "done")
        self.assertEqual(PropertyStep.objects.get(property=p, template__number=9).status, "done")
        draft = p.email_drafts.get(kind="angel_host")
        self.assertEqual(draft.to, "ops@angelhost.example")
        emails.send(draft)
        self.assertTrue(done(p, 10, "Angel Host emailed: ready to optimize"))
        # second run does nothing new
        services.run_listing(p)
        self.assertEqual(p.email_drafts.filter(kind="angel_host").count(), 1)
        # re-shoot replaces photos and drafts an update
        services.add_photos(p, [jpg(f"new{i}.jpg") for i in range(6)], kind="reshoot", new_set=True)
        run = services.run_listing(p)
        self.assertIn("Replaced the photos in Guesty", [s["label"] for s in run.trace])
        self.assertTrue(p.email_drafts.filter(subject__startswith="Updated photos").exists())

    def test_needs_enough_photos(self):
        p = ready_property()
        services.add_photos(p, [jpg()])
        run = services.run_listing(p)
        self.assertEqual(run.status, AgentRun.Status.PARTIAL)
        self.assertFalse(p.guesty_listing_id)

    def test_waits_for_setup_day(self):
        p = ready_property(upto=6)
        services.add_photos(p, [jpg(f"p{i}.jpg") for i in range(5)])
        run = services.run_listing(p)
        p.refresh_from_db()
        self.assertFalse(p.guesty_listing_id)
        self.assertIn("Listing not built yet", [s["label"] for s in run.trace])

    def test_readiness(self):
        p = ready_property()
        r = services.readiness(p)
        self.assertEqual(r["pct"], 0)
        services.add_photos(p, [jpg(f"p{i}.jpg") for i in range(5)])
        self.assertGreater(services.readiness(p)["pct"], 0)


@override_settings(LISTINGS={**LISTINGS, "GUESTY_CLIENT_ID": "id", "GUESTY_CLIENT_SECRET": "secret",
                             "PUBLIC_BASE_URL": "https://api.example.com"}, MEDIA_ROOT="/tmp/test-media")
class GuestyClientTests(TestCase):
    def _session(self):
        s = mock.Mock()
        tok = mock.Mock(ok=True, status_code=200)
        tok.json.return_value = {"access_token": "T0K", "expires_in": 86400}
        s.post.return_value = tok
        resp = mock.Mock(ok=True, status_code=200, content=b"{}")
        resp.json.return_value = {"_id": "64abc"}
        s.request.return_value = resp
        return s

    def test_token_cached_and_listing_created(self):
        s = self._session()
        g = Guesty(session=s)
        p = ready_property()
        self.assertEqual(g.create_listing(listing_payload(p, services.profile(p)))["_id"], "64abc")
        g.add_photos("64abc", [{"url": "https://api.example.com/media/x.jpg", "caption": "Kitchen"}])
        self.assertEqual(s.post.call_count, 1)  # one token for both calls
        self.assertEqual(GuestyToken.objects.count(), 1)
        method, url = s.request.call_args_list[0].args
        self.assertEqual((method, url), ("POST", "https://open-api.guesty.com/v1/listings"))
        body = s.request.call_args_list[0].kwargs["json"]
        self.assertEqual(body["nickname"], p.nickname)
        self.assertFalse(body["isListed"])
        self.assertEqual(body["prices"]["currency"], "CAD")
        self.assertIn("/properties-api/property-photos/property-photos/64abc", s.request.call_args_list[1].args[1])

    def test_agent_uses_public_urls(self):
        s = self._session()
        p = ready_property()
        services.add_photos(p, [jpg(f"p{i}.jpg") for i in range(5)])
        run = services.run_listing(p, guesty=Guesty(session=s))
        self.assertEqual(run.status, "succeeded", run.trace)
        photos = s.request.call_args_list[1].kwargs["json"]
        self.assertTrue(photos[0]["url"].startswith("https://api.example.com/media/photos/"))


@override_settings(LISTINGS=LISTINGS, MEDIA_ROOT="/tmp/test-media")
class ListingApiTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_user("ops", password="pw-12345678")
        self.c = APIClient()
        self.c.login(username="ops", password="pw-12345678")
        self.p = ready_property()

    def test_upload_edit_and_run(self):
        files = [io.BytesIO(jpg(f"p{i}.jpg")[1]) for i in range(5)]
        for i, f in enumerate(files):
            f.name = f"kitchen{i}.jpg"
        r = self.c.post(f"/api/properties/{self.p.id}/photos/", {"files": files}, format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        photos = r.data["photo_set"]["photos"]
        self.assertEqual(len(photos), 5)
        r = self.c.patch(f"/api/photos/{photos[2]['id']}/", {"is_cover": True, "caption": "Open kitchen"}, format="json")
        self.assertEqual(r.data["photo_set"]["photos"][0]["caption"], "Open kitchen")
        r = self.c.patch(f"/api/properties/{self.p.id}/listing/", {"title": "Sunny Bay St suite", "base_price": 199}, format="json")
        self.assertEqual(r.data["profile"]["effective_title"], "Sunny Bay St suite")
        r = self.c.post(f"/api/properties/{self.p.id}/agents/listing/")
        self.assertEqual(r.data["status"], "succeeded", r.data)
        self.assertEqual(self.c.get("/api/integrations/").data["guesty"], "dry_run")
        lst = self.c.get("/api/properties/").data
        self.assertTrue(lst[0]["cover_url"].startswith("/media/photos/"))
