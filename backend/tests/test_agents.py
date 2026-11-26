from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from agents import compliance, emails, intake
from agents.integrations import extraction
from agents.models import AgentRun, AgreementDocument, Building, ComplianceItem, EmailDraft, LicenceReminder
from onboarding.models import PropertyStep, PropertyTask
from properties.models import Licence
from properties.services import create_property

SAMPLE = Path(__file__).resolve().parents[1] / "agents" / "data" / "sample_agreement.pdf"
NO_KEYS = dict(ANTHROPIC_API_KEY="", ANTHROPIC_MODEL="claude-sonnet-5-5", GOOGLE_SERVICE_ACCOUNT_FILE="",
               GOOGLE_DELEGATED_ADMIN="", GOOGLE_SENDER_EMAIL="", GOOGLE_DRIVE_PARENT_FOLDER_ID="",
               GOOGLE_TRACKER_SHEET_ID="", GOOGLE_TRACKER_RANGE="Portfolio!A:J")


def upload():
    return AgreementDocument.objects.create(
        file=SimpleUploadedFile("agreement.pdf", SAMPLE.read_bytes(), content_type="application/pdf"),
        original_name="agreement.pdf")


def task_done(prop, step, title):
    return PropertyTask.objects.get(step__property=prop, step__template__number=step, template__title=title).done


@override_settings(INTEGRATIONS=NO_KEYS, MEDIA_ROOT="/tmp/test-media")
class ExtractionTests(TestCase):
    def test_heuristic_reads_sample(self):
        doc = intake.read_agreement(upload())
        self.assertEqual(doc.status, "extracted")
        self.assertEqual(doc.method, "heuristic")
        self.assertEqual(doc.extracted["unit"], "1507")
        self.assertEqual(doc.extracted["lease_start"], "2026-12-15")

    def test_claude_tool_output_is_cleaned(self):
        fake_block = SimpleNamespace(type="tool_use", input={
            "fields": {"owner_name": " Priya Raman ", "unit": "1507", "bedrooms": "2", "lease_start": "December 15, 2026",
                       "owner_type": "Owner"},
            "confidence": {"owner_name": "high"}})
        client = mock.Mock()
        client.messages.create.return_value = SimpleNamespace(content=[fake_block])
        r = extraction.extract_with_claude(b"%PDF-1.4", client=client)
        self.assertEqual(r.fields["owner_name"], "Priya Raman")
        self.assertEqual(r.fields["bedrooms"], 2)
        self.assertEqual(r.fields["lease_start"], "2026-12-15")
        self.assertIn("street_name", r.missing)
        sent = client.messages.create.call_args.kwargs
        self.assertEqual(sent["tool_choice"]["name"], "record_agreement")
        self.assertEqual(sent["messages"][0]["content"][0]["type"], "document")

    def test_unreadable_file_is_reported(self):
        doc = AgreementDocument.objects.create(file=SimpleUploadedFile("x.pdf", b"not a pdf"), original_name="x.pdf")
        intake.read_agreement(doc)
        self.assertEqual(doc.status, "failed")
        self.assertTrue(doc.error)


@override_settings(INTEGRATIONS=NO_KEYS, MEDIA_ROOT="/tmp/test-media")
class IntakeTests(TestCase):
    def setUp(self):
        Building.objects.create(street_number="460", street_name="Spadina Ave", management_email="office@example.com")

    def test_agreement_to_property_dry_run(self):
        doc = intake.read_agreement(upload())
        prop, run = intake.create_from_agreement(doc, {"beds": 3})
        self.assertEqual(prop.nickname[-7:], "SPA1507")
        self.assertEqual(prop.beds, 3)
        self.assertEqual(prop.parking, "Spot P2-41")
        self.assertEqual(run.status, AgentRun.Status.SUCCEEDED, run.trace)
        self.assertTrue(all(s["dry_run"] for s in run.trace if "Drive" in s["label"] or "tracker" in s["label"]))
        self.assertTrue(prop.drive_folder_url.startswith("https://drive.google.com/"))
        self.assertEqual(PropertyStep.objects.get(property=prop, template__number=1).status, "done")
        self.assertTrue(task_done(prop, 2, "Agreement saved to unit Drive folder"))
        self.assertTrue(task_done(prop, 2, "Added to portfolio tracker"))
        draft = prop.email_drafts.get(kind="building_registration")
        self.assertEqual(draft.to, "office@example.com")
        self.assertIn("Unit: 1507", draft.body)
        # Approving the email ticks the lease task
        emails.send(draft)
        draft.refresh_from_db()
        self.assertEqual(draft.status, "sent")
        self.assertTrue(draft.sent_dry_run)
        self.assertTrue(task_done(prop, 2, "Lease sent to building management"))

    def test_cannot_apply_twice(self):
        doc = intake.read_agreement(upload())
        intake.create_from_agreement(doc, {})
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            intake.create_from_agreement(doc, {})

    def test_unknown_building_warns(self):
        Building.objects.all().delete()
        doc = intake.read_agreement(upload())
        doc.extracted.update(building_name="", management_company="")
        doc.save()
        prop, run = intake.create_from_agreement(doc, {})
        self.assertEqual(run.status, AgentRun.Status.PARTIAL)
        self.assertTrue(prop.email_drafts.get().warning)


@override_settings(INTEGRATIONS=NO_KEYS, MEDIA_ROOT="/tmp/test-media")
class ComplianceTests(TestCase):
    def setUp(self):
        self.p = create_property(dict(street_number="270", street_name="Queens Quay W", unit="1204", owner_name="Pat Lee",
                                      owner_email="pat@example.com", bedrooms=2, bathrooms=2, beds=3))
        PropertyTask.objects.filter(step__property=self.p, step__template__number=1).update(done=True)
        from onboarding.engine import refresh_statuses
        refresh_statuses(self.p)

    def test_unit_email_gmail_alias_default(self):
        from django.conf import settings
        with override_settings(AGENTS={**settings.AGENTS, "UNIT_EMAIL_MODE": "gmail_alias", "UNIT_EMAIL_BASE": "krypsos.ops@gmail.com"}):
            compliance.run_compliance(self.p)
        self.p.refresh_from_db()
        self.assertEqual(self.p.unit_email, "krypsos.ops+que1204@gmail.com")
        self.assertTrue(task_done(self.p, 3, "Unique unit email created"))

    def test_unit_email_manual(self):
        from django.conf import settings
        with override_settings(AGENTS={**settings.AGENTS, "UNIT_EMAIL_MODE": "manual"}):
            run = compliance.run_compliance(self.p)
        self.p.refresh_from_db()
        self.assertEqual(self.p.unit_email, "")
        self.assertIn("que1204@gmail.com", run.trace[0]["detail"])
        self.assertFalse(task_done(self.p, 3, "Unique unit email created"))

    def test_unit_email_and_packet(self):
        from django.conf import settings
        with override_settings(AGENTS={**settings.AGENTS, "UNIT_EMAIL_MODE": "workspace"}):
            run = compliance.run_compliance(self.p)
        self.p.refresh_from_db()
        self.assertEqual(self.p.unit_email, "que1204@stays.example.com")
        self.assertTrue(task_done(self.p, 3, "Unique unit email created"))
        self.assertEqual(ComplianceItem.objects.get(property=self.p, key="unit_email").status, "received")
        self.assertEqual(ComplianceItem.objects.get(property=self.p, key="owner_consent").status, "requested")
        self.assertTrue(self.p.email_drafts.filter(kind="owner_documents", to="pat@example.com").exists())
        self.assertEqual(run.status, AgentRun.Status.PARTIAL)  # building consent still missing
        # Running again doesn't duplicate the owner email
        compliance.run_compliance(self.p)
        self.assertEqual(self.p.email_drafts.filter(kind="owner_documents").count(), 1)

    def test_reminders_once_per_threshold(self):
        lic = self.p.licence
        lic.status, lic.expires_on = Licence.Status.APPROVED, timezone.localdate() + timedelta(days=21)
        lic.save()
        self.assertEqual(len(compliance.licence_reminders()), 1)  # 30-day reminder (60 also marked)
        self.assertEqual(len(compliance.licence_reminders()), 0)
        self.assertEqual(LicenceReminder.objects.filter(licence=lic).count(), 2)
        self.assertEqual(len(compliance.licence_reminders(today=timezone.localdate() + timedelta(days=15))), 1)  # 7-day
        compliance.licence_reminders(today=lic.expires_on + timedelta(days=1))
        lic.refresh_from_db()
        self.assertEqual(lic.status, Licence.Status.EXPIRED)

    def test_building_followup_after_silence(self):
        Building.objects.create(street_number="270", street_name="Queens Quay W", management_email="desk@example.com")
        self.p.building = Building.objects.get()
        self.p.save()
        d = emails.building_registration(self.p)
        emails.send(d)
        EmailDraft.objects.filter(pk=d.pk).update(sent_at=timezone.now() - timedelta(days=6))
        made = compliance.building_followups()
        self.assertEqual(len(made), 1)
        self.assertIn("Keys and fobs registered", made[0].body)
        self.assertEqual(PropertyStep.objects.get(property=self.p, template__number=2).status, "waiting")
        self.assertEqual(len(compliance.building_followups()), 0)


@override_settings(INTEGRATIONS=NO_KEYS, MEDIA_ROOT="/tmp/test-media")
class AgentApiTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_superuser("ops", "ops@example.com", "pw-12345678")
        self.c = APIClient()
        self.c.login(username="ops", password="pw-12345678")

    def test_upload_review_create_and_approve(self):
        with open(SAMPLE, "rb") as f:
            r = self.c.post("/api/agreements/", {"file": f}, format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["missing"], [])
        r = self.c.post(f"/api/agreements/{r.data['id']}/create-property/", {"fields": {"beds": 2}}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        pid = r.data["property"]["id"]
        self.assertIn(r.data["run"]["status"], ("succeeded", "partial"))
        drafts = self.c.get(f"/api/emails/?property={pid}&status=draft").data
        self.assertEqual(len(drafts), 1)
        r = self.c.patch(f"/api/emails/{drafts[0]['id']}/", {"to": "office@example.com"}, format="json")
        self.assertEqual(r.status_code, 200)
        r = self.c.post(f"/api/emails/{drafts[0]['id']}/send/")
        self.assertEqual(r.data["status"], "sent")
        r = self.c.post(f"/api/properties/{pid}/agents/compliance/")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.c.get("/api/integrations/").data["google"]["drive"], "dry_run")
        self.assertEqual(len(self.c.get("/api/licences/").data), 1)

    def test_rejects_non_pdf(self):
        r = self.c.post("/api/agreements/", {"file": SimpleUploadedFile("a.txt", b"hi")}, format="multipart")
        self.assertEqual(r.status_code, 400)
