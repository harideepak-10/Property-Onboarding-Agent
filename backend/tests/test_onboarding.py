from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from onboarding import engine
from onboarding.models import PropertyStep, PropertyTask
from properties.services import build_nickname, create_property

S = PropertyStep.Status


def make_property(**kw):
    data = dict(street_number="460", street_name="Spadina Ave", unit="1507", owner_name="R. Patel",
                bedrooms=2, bathrooms=1, beds=2)
    data.update(kw)
    return create_property(data)


def task(prop, step, order):
    return PropertyTask.objects.get(step__property=prop, step__template__number=step, template__order=order)


def step(prop, n):
    return PropertyStep.objects.get(property=prop, template__number=n)


class NicknameTests(TestCase):
    def test_format(self):
        self.assertEqual(build_nickname(37313, "TOR", "Bay St", "617"), "A37313-TOR-BAY617")
        self.assertEqual(build_nickname(1, "tor", "St Joseph St", "PH-02"), "A1-TOR-JOS02")
        self.assertEqual(build_nickname(2, "TOR", "The Esplanade", "5"), "A2-TOR-ESP5")

    def test_sequence_increments(self):
        a, b = make_property(), make_property(unit="1508")
        self.assertEqual(b.sequence, a.sequence + 1)
        self.assertTrue(b.nickname.endswith("SPA1508"))


class ChecklistTests(TestCase):
    def setUp(self):
        self.p = make_property()

    def test_new_property_has_12_steps_with_first_ready(self):
        self.assertEqual(self.p.steps.count(), 12)
        self.assertEqual(step(self.p, 1).status, S.READY)
        self.assertEqual(step(self.p, 2).status, S.LOCKED)
        self.assertEqual(engine.progress(self.p), 0)

    def test_locked_step_rejects_task(self):
        with self.assertRaises(ValidationError):
            engine.set_task(task(self.p, 2, 2), True, actor="Test")

    def test_proof_required(self):
        with self.assertRaises(ValidationError):
            engine.set_task(task(self.p, 1, 2), True, actor="Test")
        engine.set_task(task(self.p, 1, 2), True, actor="Test", proof_url="https://drive.example/agreement.pdf")
        self.assertTrue(task(self.p, 1, 2).done)

    def test_completing_step_1_unlocks_2_3_6(self):
        engine.set_task(task(self.p, 1, 1), True, actor="Test")
        unlocked = engine.set_task(task(self.p, 1, 2), True, actor="Test", proof_note="PDF in Drive")
        self.assertEqual(sorted(unlocked), [2, 3, 6])
        self.assertEqual(step(self.p, 1).status, S.DONE)
        self.assertEqual(step(self.p, 4).status, S.LOCKED)

    def test_go_live_needs_licence_step(self):
        # Everything except step 3 done -> step 12 stays locked
        PropertyTask.objects.filter(step__property=self.p).exclude(step__template__number__in=[3, 12]).update(done=True)
        engine.refresh_statuses(self.p)
        self.assertEqual(step(self.p, 12).status, S.LOCKED)
        PropertyTask.objects.filter(step__property=self.p, step__template__number=3).update(done=True)
        engine.refresh_statuses(self.p)
        self.assertEqual(step(self.p, 12).status, S.READY)

    def test_blocked_and_waiting(self):
        engine.set_task(task(self.p, 1, 1), True, actor="Test")
        engine.set_task(task(self.p, 1, 2), True, actor="Test", proof_note="x")
        engine.set_blocked(step(self.p, 3), "Consent letter missing", actor="Test")
        self.assertEqual(step(self.p, 3).status, S.BLOCKED)
        self.assertEqual(engine.overall_state(self.p), "blocked")
        engine.set_blocked(step(self.p, 3), "", actor="Test")
        engine.set_waiting(step(self.p, 3), "City review", actor="Test")
        self.assertEqual(step(self.p, 3).status, S.WAITING)

    def test_reopening_relocks_dependents(self):
        engine.set_task(task(self.p, 1, 1), True, actor="Test")
        engine.set_task(task(self.p, 1, 2), True, actor="Test", proof_note="x")
        engine.set_task(task(self.p, 1, 1), False, actor="Test")
        self.assertEqual(step(self.p, 2).status, S.LOCKED)


class ApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("ops", password="pw-12345678")
        self.c = APIClient()
        r = self.c.post("/api/auth/login/", {"username": "ops", "password": "pw-12345678"}, format="json")
        self.c.credentials(HTTP_AUTHORIZATION="Token " + r.data["token"])

    def test_requires_auth(self):
        self.assertEqual(APIClient().get("/api/properties/").status_code, 401)

    def test_create_and_tick(self):
        r = self.c.post("/api/properties/", {"street_number": "1", "street_name": "Bay St", "unit": "9",
                                             "owner_name": "X", "bedrooms": 1, "bathrooms": 1, "beds": 1}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(len(r.data["steps"]), 12)
        t = r.data["steps"][0]["tasks"][0]["id"]
        r2 = self.c.post(f"/api/tasks/{t}/set/", {"done": True}, format="json")
        self.assertEqual(r2.status_code, 200)
        locked = r.data["steps"][1]["tasks"][0]["id"]
        r3 = self.c.post(f"/api/tasks/{locked}/set/", {"done": True}, format="json")
        self.assertEqual(r3.status_code, 400)
        self.assertIn("locked", r3.data["detail"])

    def test_dashboard(self):
        make_property()
        r = self.c.get("/api/dashboard/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["kpis"]["onboarding"], 1)
