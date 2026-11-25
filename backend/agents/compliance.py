"""Compliance agent: unit email, licence packet, renewal reminders and follow-ups."""
import re
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from onboarding.models import PropertyTask
from properties.models import Licence
from properties.services import log, street_code

from . import emails
from .integrations.google_workspace import GoogleWorkspace
from .models import AgentRun, ComplianceItem, EmailDraft, LicenceReminder

AGENT = "Compliance agent"


def unit_email_for(prop) -> str:
    cfg = settings.AGENTS
    local = cfg["UNIT_EMAIL_PATTERN"].format(
        street=street_code(prop.street_name).lower(), unit=re.sub(r"\D", "", prop.unit),
        nickname=prop.nickname.lower())
    return f"{local}@{cfg['UNIT_EMAIL_DOMAIN']}"


def ensure_packet(prop):
    """Create the licence packet checklist and mark what the system already has."""
    for key, label, source in settings.AGENTS["LICENCE_PACKET"]:
        ComplianceItem.objects.get_or_create(property=prop, key=key, defaults={"label": label, "source": source})
    doc = prop.agreements.first()
    if doc:
        ComplianceItem.objects.filter(property=prop, key="agreement", status__in=["missing", "requested"]).update(
            status="received", link=doc.drive_file_url or "", note=doc.original_name)
    if prop.unit_email:
        ComplianceItem.objects.filter(property=prop, key="unit_email").exclude(status="received").update(
            status="received", note=prop.unit_email)
    return list(prop.compliance_items.all())


def tick(prop, step, titles, user=None, note=""):
    from onboarding.engine import complete_by_title
    from django.core.exceptions import ValidationError
    try:
        complete_by_title(prop, step, titles, actor=AGENT, user=user, proof_note=note)
        return True
    except ValidationError:
        return False


def run_compliance(prop, user=None, google=None) -> AgentRun:
    google = google or GoogleWorkspace()
    run = AgentRun.objects.create(agent=AgentRun.Agent.COMPLIANCE, property=prop, started_by=user)
    warnings = 0
    try:
        # 1. Unique unit email
        if not prop.unit_email:
            email = unit_email_for(prop)
            res = google.create_user(email, given_name=f"Unit {prop.unit}", family_name=prop.nickname)
            prop.unit_email = email
            prop.save(update_fields=["unit_email"])
            ok = tick(prop, 3, ["Unique unit email created"], user, email)
            run.add("Created the unit's email address", "ok" if ok else "warn",
                    email + ("" if ok else " · step 3 is locked until the agreement step is done"), dry_run=res.dry_run)
            warnings += not ok
        else:
            run.add("Unit email already exists", "skip", prop.unit_email)

        # 2. Licence packet
        items = ensure_packet(prop)
        missing_owner = [i for i in items if i.status == "missing" and i.source == "owner"]
        missing_other = [i for i in items if i.status == "missing" and i.source != "owner"]
        have = sum(1 for i in items if i.status in ("received", "not_needed"))
        run.add("Checked the licence packet", detail=f"{have} of {len(items)} items ready")
        if missing_owner and not prop.email_drafts.filter(kind=EmailDraft.Kind.OWNER_DOCUMENTS, status="draft").exists():
            draft = emails.owner_documents(prop, [i.label for i in missing_owner])
            ComplianceItem.objects.filter(pk__in=[i.pk for i in missing_owner]).update(status="requested")
            run.add("Drafted an email asking the owner for documents", "warn" if draft.warning else "ok",
                    draft.warning or f"{len(missing_owner)} item(s) · waiting for your approval")
        for i in missing_other:
            run.add(f"Still needed: {i.label}", "warn", f"Comes from the {i.source}")
            warnings += 1

        # 3. Licence status and reminders
        lic = prop.licence
        if lic.status == Licence.Status.APPROVED and lic.expires_on:
            tick(prop, 3, ["Licence expiry added to tracker"], user, f"Expires {lic.expires_on}")
            days = (lic.expires_on - timezone.localdate()).days
            run.add("Scheduled renewal reminders", detail=f"Expires {lic.expires_on} ({days} days) · reminders at "
                    + ", ".join(f"{d}" for d in settings.AGENTS["LICENCE_REMINDER_DAYS"]) + " days before")
        elif lic.status == Licence.Status.NOT_STARTED:
            ready = all(i.status in ("received", "not_needed") for i in prop.compliance_items.all())
            run.add("Licence application", "ok" if ready else "warn",
                    "Packet complete: ready to submit to the City" if ready else "Waiting on packet items before submitting")
        else:
            run.add("Licence status", detail=lic.get_status_display())

        log(prop, "Compliance agent finished: unit email, licence packet and reminders", actor=AGENT, user=user)
        run.status = AgentRun.Status.PARTIAL if warnings else AgentRun.Status.SUCCEEDED
    except Exception as e:  # noqa: BLE001
        run.add("Stopped because of an error", "error", f"{type(e).__name__}: {e}")
        run.status, run.error = AgentRun.Status.FAILED, str(e)
    run.finished_at = timezone.now()
    run.save()
    return run


# ---------- daily sweeps ----------

@transaction.atomic
def licence_reminders(today=None):
    """Create one reminder per threshold crossed (60/30/7 days), and mark expired licences."""
    today = today or timezone.localdate()
    thresholds = sorted(settings.AGENTS["LICENCE_REMINDER_DAYS"])
    created = []
    for lic in Licence.objects.filter(expires_on__isnull=False, status__in=[Licence.Status.APPROVED, Licence.Status.EXPIRED]).select_related("property"):
        days = (lic.expires_on - today).days
        if days < 0:
            if lic.status != Licence.Status.EXPIRED:
                lic.status = Licence.Status.EXPIRED
                lic.save(update_fields=["status"])
                log(lic.property, f"STR licence expired on {lic.expires_on}", actor=AGENT)
                listed = getattr(getattr(lic.property, "listing", None), "is_listed", False)
                if listed and not LicenceReminder.objects.filter(licence=lic, days_before=0, expires_on=lic.expires_on).exists():
                    LicenceReminder.objects.create(licence=lic, days_before=0, expires_on=lic.expires_on)
                    created.append(emails.licence_expired(lic.property, lic))
            continue
        crossed = [t for t in thresholds if days <= t]
        if not crossed:
            continue
        target = min(crossed)
        if LicenceReminder.objects.filter(licence=lic, expires_on=lic.expires_on, days_before__lte=target).exists():
            continue
        for t in crossed:
            LicenceReminder.objects.get_or_create(licence=lic, days_before=t, expires_on=lic.expires_on)
        created.append(emails.licence_renewal(lic.property, lic, days))
        log(lic.property, f"Licence renewal reminder drafted ({days} days left)", actor=AGENT)
    return created


BUILDING_TASKS = ["Keys and fobs registered", "Parking registered"]


@transaction.atomic
def building_followups(now=None):
    """Draft a follow-up when building management hasn't replied within FOLLOWUP_DAYS."""
    now = now or timezone.now()
    cutoff = now - timedelta(days=settings.AGENTS["FOLLOWUP_DAYS"])
    created = []
    for sent in EmailDraft.objects.filter(kind=EmailDraft.Kind.BUILDING_REGISTRATION, status="sent", sent_at__lte=cutoff).select_related("property"):
        prop = sent.property
        open_items = list(PropertyTask.objects.filter(step__property=prop, step__template__number=2,
                                                      template__title__in=BUILDING_TASKS, done=False)
                          .values_list("template__title", flat=True))
        if not open_items:
            continue
        if prop.email_drafts.filter(kind=EmailDraft.Kind.BUILDING_FOLLOWUP, created_at__gte=sent.sent_at).exists():
            continue
        created.append(emails.building_followup(prop, sent, open_items))
        days = (now - sent.sent_at).days
        step = prop.steps.get(template__number=2)
        if not step.waiting_note and step.status != "done":
            from onboarding.engine import set_waiting
            set_waiting(step, f"Building management hasn't confirmed {', '.join(t.lower() for t in open_items)} ({days} days). Follow-up drafted.", actor=AGENT)
        log(prop, "Drafted a follow-up to building management", actor=AGENT)
    return created


def run_sweeps(user=None) -> AgentRun:
    run = AgentRun.objects.create(agent=AgentRun.Agent.REMINDERS, started_by=user)
    r = licence_reminders()
    run.add("Checked licence expiry dates", detail=f"{len(r)} renewal reminder(s) drafted")
    f = building_followups()
    run.add("Checked unanswered building emails", detail=f"{len(f)} follow-up(s) drafted")
    run.status, run.finished_at = AgentRun.Status.SUCCEEDED, timezone.now()
    run.save()
    return run
