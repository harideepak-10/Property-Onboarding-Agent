from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from agents import compliance
from listings import golive, services
from listings.models import PhotoSet
from onboarding.engine import refresh_statuses
from onboarding.models import PropertyStep, PropertyTask
from properties.models import Licence
from properties.services import create_property
from tests.test_listings import LISTINGS, jpg


def prop_at(upto):
    p = create_property(dict(street_number="5", street_name="St Joseph St", unit="1802", owner_name="L. Chen",
                             bedrooms=1, bathrooms=1, beds=2))
    PropertyTask.objects.filter(step__property=p, step__template__number__lte=upto).update(done=True)
    refresh_statuses(p)
    return p


def full_guide(p, **extra):
    data = dict(arrival_instructions="Lobby", buzzer_instructions="Dial 1802", lockbox_location="Railing", lockbox_code="4821",
                wifi_name="Stay", wifi_password="pw", emergency_contact="416-555-0100")
    data.update(extra)
    return golive.update_guide(p, data)


def go_live_ready():
    p = prop_at(10)
    lic = p.licence
    lic.status, lic.number, lic.expires_on = Licence.Status.APPROVED, "STR-1", timezone.localdate() + timedelta(days=200)
    lic.save()
    services.add_photos(p, [jpg(f"p{i}.jpg") for i in range(5)])
    p.guesty_listing_id = "dryrun-abc"
    p.save()
    ps = services.current_set(p)
    ps.uploaded_to_guesty_at = timezone.now()
    ps.save()
    full_guide(p, enso_guidebook_url="https://guide.example.com/x")
    return p


@override_settings(LISTINGS=LISTINGS, MEDIA_ROOT="/tmp/test-media")
class GuideTests(TestCase):
    def test_guide_ticks_step_11(self):
        p = prop_at(7)
        g, notes = full_guide(p)
        self.assertFalse(notes)
        t = lambda title: PropertyTask.objects.get(step__property=p, step__template__number=11, template__title=title).done
        self.assertTrue(t("Lockbox code set"))
        self.assertTrue(t("Building buzzer access set"))
        self.assertFalse(t("Enso Connect guidebook set up"))
        golive.update_guide(p, {"enso_guidebook_url": "https://guide.example.com/x"})
        self.assertTrue(t("Enso Connect guidebook set up"))

    def test_locked_step_keeps_guide(self):
        p = prop_at(3)
        g, notes = full_guide(p)
        self.assertTrue(notes)
        self.assertEqual(g.lockbox_code, "4821")

    def test_mask_does_not_overwrite(self):
        p = prop_at(7)
        full_guide(p)
        g, _ = golive.update_guide(p, {"lockbox_code": golive.MASK, "wifi_name": "New"})
        self.assertEqual(g.lockbox_code, "4821")
        self.assertIn("Code: 4821", golive.guidebook_text(p))


@override_settings(LISTINGS=LISTINGS, MEDIA_ROOT="/tmp/test-media")
class GoLiveTests(TestCase):
    def test_blocks_until_ready(self):
        p = prop_at(5)
        pf = golive.preflight(p)
        self.assertFalse(pf["ready"])
        with self.assertRaises(ValidationError):
            golive.approve(p)

    def test_approve_confirm_and_unlist(self):
        p = go_live_ready()
        self.assertTrue(golive.preflight(p)["ready"], golive.preflight(p))
        run = golive.approve(p)
        self.assertEqual(run.status, "partial")
        self.assertTrue(services.profile(p).is_listed)
        for ch in ("airbnb", "booking", "direct"):
            golive.confirm_channel(p, ch)
        self.assertEqual(PropertyStep.objects.get(property=p, template__number=12).status, "done")
        golive.unlist(p, "Licence renewal")
        self.assertFalse(services.profile(p).is_listed)
        self.assertNotEqual(PropertyStep.objects.get(property=p, template__number=12).status, "done")

    def test_expired_licence_alert_when_listed(self):
        p = go_live_ready()
        golive.approve(p)
        lic = p.licence
        lic.expires_on = timezone.localdate() - timedelta(days=1)
        lic.save()
        made = compliance.licence_reminders()
        self.assertTrue(any("URGENT" in d.subject for d in made))
        self.assertFalse(any("URGENT" in d.subject for d in compliance.licence_reminders()))


@override_settings(LISTINGS=LISTINGS, MEDIA_ROOT="/tmp/test-media")
class GoLiveApiTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_user("ops", password="pw-12345678")
        self.c = APIClient()
        self.c.login(username="ops", password="pw-12345678")

    def test_secrets_masked_and_reveal_logged(self):
        p = prop_at(7)
        r = self.c.patch(f"/api/properties/{p.id}/guest-guide/", {"lockbox_code": "9911", "lockbox_location": "Door"}, format="json")
        self.assertEqual(r.data["lockbox_code"], golive.MASK)
        r = self.c.post(f"/api/properties/{p.id}/guest-guide/reveal/")
        self.assertEqual(r.data["lockbox_code"], "9911")
        self.assertTrue(p.activity.filter(message__icontains="Viewed the guest access codes").exists())

    def test_go_live_flow(self):
        p = go_live_ready()
        self.assertTrue(self.c.get(f"/api/properties/{p.id}/go-live/").data["ready"])
        r = self.c.post(f"/api/properties/{p.id}/go-live/approve/")
        self.assertTrue(r.data["is_listed"])
        r = self.c.post(f"/api/properties/{p.id}/go-live/channels/airbnb/")
        self.assertTrue(r.data["channels"][0]["live"])
        r = self.c.post(f"/api/properties/{p.id}/go-live/unlist/", {"reason": "test"}, format="json")
        self.assertFalse(r.data["is_listed"])
